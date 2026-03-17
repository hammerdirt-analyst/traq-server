"""Unit tests for reusable customer and billing service behavior."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.services.customer_service import CustomerService
from app.services.job_mutation_service import JobMutationService
from app.db import create_schema, init_database


class CustomerServiceTests(unittest.TestCase):
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
        self.service = CustomerService()
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

    def test_create_list_and_update_customer(self) -> None:
        created = self.service.create_customer(
            name="Sacramento State Arboretum",
            phone="555-1212",
            address="6000 J St",
        )
        self.assertEqual(created["customer_code"], "C0001")
        self.assertEqual(created["name"], "Sacramento State Arboretum")

        rows = self.service.list_customers(search="Arboretum")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["customer_id"], created["customer_id"])

        updated = self.service.update_customer(
            created["customer_id"],
            phone="555-9999",
            address="6000 J Street",
        )
        self.assertEqual(updated["phone"], "555-9999")
        self.assertEqual(updated["address"], "6000 J Street")

    def test_customer_name_is_required(self) -> None:
        with self.assertRaises(ValueError):
            self.service.create_customer(name="   ")

    def test_customer_duplicates_groups_by_name(self) -> None:
        self.service.create_customer(name="Test", phone="1")
        self.service.create_customer(name=" Test ", phone="2")
        duplicates = self.service.customer_duplicates()
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["normalized_name"], "test")
        self.assertEqual(duplicates[0]["count"], 2)

    def test_create_list_and_update_billing_profile(self) -> None:
        created = self.service.create_billing_profile(
            billing_name="City of Trees",
            billing_contact_name="A. Manager",
            billing_address="123 Elm",
            contact_preference="email",
        )
        self.assertEqual(created["billing_code"], "B0001")
        self.assertEqual(created["billing_name"], "City of Trees")

        rows = self.service.list_billing_profiles(search="Trees")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["billing_profile_id"], created["billing_profile_id"])

        updated = self.service.update_billing_profile(
            created["billing_profile_id"],
            billing_contact_name="B. Manager",
            contact_preference="phone",
        )
        self.assertEqual(updated["billing_contact_name"], "B. Manager")
        self.assertEqual(updated["contact_preference"], "phone")

    def test_missing_records_raise(self) -> None:
        with self.assertRaises(KeyError):
            self.service.update_customer("missing", name="Name")
        with self.assertRaises(KeyError):
            self.service.update_billing_profile("missing", billing_name="Name")

    def test_billing_duplicates_groups_by_name(self) -> None:
        self.service.create_billing_profile(billing_name="Test")
        self.service.create_billing_profile(billing_name=" Test ")
        duplicates = self.service.billing_duplicates()
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0]["normalized_billing_name"], "test")
        self.assertEqual(duplicates[0]["count"], 2)

    def test_customer_usage_and_merge(self) -> None:
        source = self.service.create_customer(name="Source Customer")
        target = self.service.create_customer(name="Target Customer")
        self.job_service.create_job(
            job_id="job_1",
            job_number="J0001",
            customer_id=source["customer_id"],
            tree_number="1",
            job_name="Tree One",
        )
        self.job_service.create_job(
            job_id="job_2",
            job_number="J0002",
            customer_id=source["customer_id"],
            tree_number="2",
            job_name="Tree Two",
        )

        usage = self.service.customer_usage(source["customer_id"])
        self.assertEqual(usage["customer"]["customer_code"], "C0001")
        self.assertEqual(usage["job_count"], 2)
        self.assertEqual(usage["tree_count"], 2)
        self.assertEqual(usage["job_numbers"], ["J0001", "J0002"])
        self.assertEqual(usage["jobs"][0]["billing_code"], None)

        merged = self.service.merge_customer(
            source["customer_id"],
            target_customer_id=target["customer_id"],
        )
        self.assertEqual(merged["moved_job_count"], 2)
        self.assertEqual(merged["moved_tree_count"], 2)

        job = self.job_service.update_job("J0001")
        self.assertEqual(job["customer_id"], target["customer_id"])
        self.assertEqual(job["tree_number"], 1)
        self.assertIsNone(self.service.get_customer(source["customer_id"]))
        self.assertEqual(self.service.get_customer("C0002")["name"], "Target Customer")

    def test_billing_usage_and_merge(self) -> None:
        customer = self.service.create_customer(name="Customer")
        source = self.service.create_billing_profile(billing_name="Source Billing")
        target = self.service.create_billing_profile(billing_name="Target Billing")
        self.job_service.create_job(
            job_id="job_3",
            job_number="J0003",
            customer_id=customer["customer_id"],
            billing_profile_id=source["billing_profile_id"],
            tree_number="1",
            job_name="Tree Three",
        )

        usage = self.service.billing_usage(source["billing_profile_id"])
        self.assertEqual(usage["billing_profile"]["billing_code"], "B0001")
        self.assertEqual(usage["job_count"], 1)
        self.assertEqual(usage["job_numbers"], ["J0003"])
        self.assertEqual(usage["jobs"][0]["customer_code"], customer["customer_code"])

        merged = self.service.merge_billing_profile(
            source["billing_profile_id"],
            target_billing_profile_id=target["billing_profile_id"],
        )
        self.assertEqual(merged["moved_job_count"], 1)

        job = self.job_service.update_job("J0003")
        self.assertEqual(job["billing_profile_id"], target["billing_profile_id"])
        self.assertIsNone(self.service.get_billing_profile(source["billing_profile_id"]))
        self.assertEqual(self.service.get_billing_profile("B0002")["billing_name"], "Target Billing")

    def test_delete_unused_customer_and_billing_profile(self) -> None:
        customer = self.service.create_customer(name="Delete Me")
        billing = self.service.create_billing_profile(billing_name="Delete Billing")
        deleted_customer = self.service.delete_customer(customer["customer_code"])
        deleted_billing = self.service.delete_billing_profile(billing["billing_code"])
        self.assertTrue(deleted_customer["deleted"])
        self.assertTrue(deleted_billing["deleted"])
        self.assertIsNone(self.service.get_customer(customer["customer_code"]))
        self.assertIsNone(self.service.get_billing_profile(billing["billing_code"]))

    def test_delete_in_use_billing_profile_fails(self) -> None:
        customer = self.service.create_customer(name="Customer")
        billing = self.service.create_billing_profile(billing_name="Billing")
        self.job_service.create_job(
            job_id="job_4",
            job_number="J0004",
            customer_id=customer["customer_code"],
            billing_profile_id=billing["billing_code"],
            tree_number="1",
            job_name="Tree Four",
        )
        with self.assertRaises(ValueError):
            self.service.delete_billing_profile(billing["billing_code"])


if __name__ == "__main__":
    unittest.main()
