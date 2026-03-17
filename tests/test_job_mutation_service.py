"""Unit tests for operational job mutation behavior."""

from __future__ import annotations

import os
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.app import db as db_module
from server.app.config import load_settings
from server.app.services.customer_service import CustomerService
from server.app.db import create_schema, init_database
from server.app.services.job_mutation_service import JobMutationService


class JobMutationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.old_env = {key: os.environ.get(key) for key in self._env_keys()}
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        os.environ["TRAQ_DATABASE_URL"] = f"sqlite:///{self.storage_root / 'test.db'}"
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        init_database(load_settings())
        create_schema()
        self.customer_service = CustomerService()
        self.job_service = JobMutationService()

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return ("TRAQ_STORAGE_ROOT", "TRAQ_DATABASE_URL")

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None

    def test_create_job_with_customer_billing_and_tree(self) -> None:
        customer = self.customer_service.create_customer(name="Sacramento State Arboretum")
        billing = self.customer_service.create_billing_profile(billing_name="City of Trees")

        created = self.job_service.create_job(
            job_id="job_1",
            job_number="J0001",
            customer_id=customer["customer_id"],
            billing_profile_id=billing["billing_profile_id"],
            tree_number=4,
            job_name="Valley Oak",
            job_address="6000 J St",
            reason="Routine assessment",
        )
        self.assertEqual(created["job_id"], "job_1")
        self.assertEqual(created["job_number"], "J0001")
        self.assertEqual(created["tree_number"], 4)
        self.assertEqual(created["customer_id"], customer["customer_id"])
        self.assertEqual(created["billing_profile_id"], billing["billing_profile_id"])

    def test_update_job_reuses_customer_scoped_tree_number(self) -> None:
        customer = self.customer_service.create_customer(name="Test Customer")
        first = self.job_service.create_job(
            job_id="job_1",
            job_number="J0001",
            customer_id=customer["customer_id"],
            tree_number=1,
            job_name="First Tree",
        )
        second = self.job_service.create_job(
            job_id="job_2",
            job_number="J0002",
            customer_id=customer["customer_id"],
            tree_number=2,
            job_name="Second Tree",
        )
        self.assertEqual(first["tree_number"], 1)
        self.assertEqual(second["tree_number"], 2)

        updated = self.job_service.update_job(
            "J0002",
            tree_number=1,
            job_name="Second Tree Revisit",
        )
        self.assertEqual(updated["tree_number"], 1)
        self.assertEqual(updated["job_name"], "Second Tree Revisit")

    def test_tree_number_requires_customer(self) -> None:
        with self.assertRaises(ValueError):
            self.job_service.create_job(
                job_id="job_1",
                job_number="J0001",
                tree_number=1,
            )

    def test_update_missing_job_raises(self) -> None:
        with self.assertRaises(KeyError):
            self.job_service.update_job("J9999", job_name="Missing")

    def test_update_job_accepts_customer_and_billing_codes(self) -> None:
        customer = self.customer_service.create_customer(name="Customer One")
        billing = self.customer_service.create_billing_profile(billing_name="Billing One")
        self.job_service.create_job(
            job_id="job_9",
            job_number="J0009",
            customer_id=customer["customer_id"],
            billing_profile_id=billing["billing_profile_id"],
            tree_number=1,
            job_name="Tree",
        )

        customer_two = self.customer_service.create_customer(name="Customer Two")
        billing_two = self.customer_service.create_billing_profile(billing_name="Billing Two")
        updated = self.job_service.update_job(
            "J0009",
            customer_id=customer_two["customer_code"],
            billing_profile_id=billing_two["billing_code"],
            tree_number=2,
        )
        self.assertEqual(updated["customer_code"], customer_two["customer_code"])
        self.assertEqual(updated["billing_code"], billing_two["billing_code"])
        self.assertEqual(updated["tree_number"], 2)
        self.assertEqual(updated["billing_name"], "Billing Two")
        self.assertEqual(updated["billing_address"], None)

    def test_relinking_customer_updates_job_snapshot_fields_by_default(self) -> None:
        customer_one = self.customer_service.create_customer(
            name="Customer One",
            phone="555-1111",
            address="123 Oak St",
        )
        customer_two = self.customer_service.create_customer(
            name="Customer Two",
            phone="555-2222",
            address="456 Pine St",
        )
        created = self.job_service.create_job(
            job_id="job_11",
            job_number="J0011",
            customer_id=customer_one["customer_id"],
            tree_number=1,
            job_name="Original Job Name",
            job_address="Original Job Address",
        )
        self.assertEqual(created["job_name"], "Original Job Name")
        self.assertEqual(created["job_address"], "Original Job Address")

        updated = self.job_service.update_job(
            "J0011",
            customer_id=customer_two["customer_code"],
        )
        self.assertEqual(updated["customer_name"], "Customer Two")
        self.assertEqual(updated["job_name"], "Customer Two")
        self.assertEqual(updated["job_address"], "456 Pine St")
        self.assertEqual(updated["job_phone"], "555-2222")
        self.assertEqual(updated["tree_number"], 1)

    def test_relinking_customer_allocates_new_tree_number_by_default(self) -> None:
        customer_one = self.customer_service.create_customer(name="Customer One")
        customer_two = self.customer_service.create_customer(name="Customer Two")
        self.job_service.create_job(
            job_id="job_12",
            job_number="J0012",
            customer_id=customer_one["customer_id"],
            tree_number=1,
            job_name="Tree One",
        )
        self.job_service.create_job(
            job_id="job_13",
            job_number="J0013",
            customer_id=customer_two["customer_id"],
            tree_number=1,
            job_name="Tree Two",
        )

        updated = self.job_service.update_job(
            "J0013",
            customer_id=customer_one["customer_code"],
        )
        self.assertEqual(updated["customer_code"], customer_one["customer_code"])
        self.assertEqual(updated["tree_number"], 2)

    def test_update_job_syncs_runtime_job_record(self) -> None:
        customer = self.customer_service.create_customer(
            name="Customer One",
            phone="555-1111",
            address="123 Oak St",
        )
        billing = self.customer_service.create_billing_profile(
            billing_name="Billing One",
            billing_contact_name="Casey",
            billing_address="123 Oak St",
            contact_preference="text",
        )
        self.job_service.create_job(
            job_id="job_10",
            job_number="J0010",
            customer_id=customer["customer_id"],
            billing_profile_id=billing["billing_profile_id"],
            tree_number=1,
            job_name="Original Tree",
        )

        customer_two = self.customer_service.create_customer(
            name="Customer Two",
            phone="555-2222",
            address="456 Pine St",
        )
        billing_two = self.customer_service.create_billing_profile(
            billing_name="Billing Two",
            billing_contact_name="Jordan",
            billing_address="456 Pine St",
            contact_preference="phone",
        )

        self.job_service.update_job(
            "J0010",
            customer_id=customer_two["customer_code"],
            billing_profile_id=billing_two["billing_code"],
            tree_number=2,
            status="REVIEW_RETURNED",
            job_name="Updated Tree",
        )

        job_record = self.storage_root / "jobs" / "job_10" / "job_record.json"
        payload = json.loads(job_record.read_text(encoding="utf-8"))
        self.assertEqual(payload["customer_name"], "Customer Two")
        self.assertEqual(payload["billing_name"], "Billing Two")
        self.assertEqual(payload["tree_number"], 2)
        self.assertEqual(payload["status"], "REVIEW_RETURNED")
        self.assertEqual(payload["job_phone"], "555-2222")

    def test_update_job_overwrites_copied_billing_fields_from_selected_profile(self) -> None:
        customer = self.customer_service.create_customer(
            name="Field test 3",
            phone="123456789",
            address="Chicory Fields Way, Elk Grove, CA 95624",
        )
        original_billing = self.customer_service.create_billing_profile(
            billing_name="Field test 3",
            billing_contact_name="Homeowner",
            billing_address="Chicory Fields Way, Elk Grove, CA 95624",
            contact_preference="phone call",
        )
        replacement_billing = self.customer_service.create_billing_profile(
            billing_name="Software Testing",
            billing_contact_name="Roger Erismann",
            billing_address="2266 Windward ln, Rancho Cordova, CA 95670",
            contact_preference="text",
        )
        self.job_service.create_job(
            job_id="job_7",
            job_number="J0007",
            customer_id=customer["customer_id"],
            billing_profile_id=original_billing["billing_profile_id"],
            tree_number=1,
            job_name="Field test 3",
            details={
                "billing_name": "Field test 3",
                "billing_address": "Chicory Fields Way, Elk Grove, CA 95624",
                "billing_contact_name": "Homeowner",
                "contact_preference": "phone call",
            },
        )

        updated = self.job_service.update_job(
            "J0007",
            billing_profile_id=replacement_billing["billing_code"],
        )
        self.assertEqual(updated["billing_name"], "Software Testing")
        self.assertEqual(updated["billing_address"], "2266 Windward ln, Rancho Cordova, CA 95670")
        self.assertEqual(updated["billing_contact_name"], "Roger Erismann")
        self.assertEqual(updated["contact_preference"], "text")

        job_record = self.storage_root / "jobs" / "job_7" / "job_record.json"
        payload = json.loads(job_record.read_text(encoding="utf-8"))
        self.assertEqual(payload["billing_name"], "Software Testing")
        self.assertEqual(payload["billing_address"], "2266 Windward ln, Rancho Cordova, CA 95670")
        self.assertEqual(payload["billing_contact_name"], "Roger Erismann")
        self.assertEqual(payload["contact_preference"], "text")


if __name__ == "__main__":
    unittest.main()
