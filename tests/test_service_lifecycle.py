"""End-to-end service-layer lifecycle test without FastAPI transport."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.app import db as db_module
from server.app.config import load_settings
from server.app.db import create_schema, init_database
from server.app.db_store import DatabaseStore
from server.app.services.customer_service import CustomerService
from server.app.services.final_mutation_service import FinalMutationService
from server.app.services.inspection_service import InspectionService
from server.app.services.job_mutation_service import JobMutationService


class ServiceLifecycleTests(unittest.TestCase):
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

        self.store = DatabaseStore()
        self.customer_service = CustomerService()
        self.job_service = JobMutationService()
        self.final_service = FinalMutationService()
        self.inspection_service = InspectionService(settings=load_settings(), db_store=self.store)

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

    def test_customer_job_final_correction_lifecycle(self) -> None:
        customer = self.customer_service.create_customer(
            name="Sacramento State Arboretum",
            phone="555-1212",
            address="6000 J St",
        )
        billing = self.customer_service.create_billing_profile(
            billing_name="City of Trees",
            billing_contact_name="A. Manager",
            billing_address="123 Elm",
            contact_preference="email",
        )
        created = self.job_service.create_job(
            job_id="job_9",
            job_number="J0009",
            customer_id=customer["customer_id"],
            billing_profile_id=billing["billing_profile_id"],
            tree_number=1,
            job_name="Valley Oak",
            job_address="123 Oak St",
            reason="Inspection",
            location_notes="Near sidewalk",
            tree_species="Quercus lobata",
        )
        self.assertEqual(created["tree_number"], 1)

        updated = self.job_service.update_job(
            "J0009",
            tree_number=2,
            job_name="Valley Oak Revisit",
            status="REVIEW_RETURNED",
        )
        self.assertEqual(updated["tree_number"], 2)
        self.assertEqual(updated["status"], "REVIEW_RETURNED")

        job_dir = self.storage_root / "jobs" / "job_9"
        round_dir = job_dir / "rounds" / "round_2"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "manifest.json").write_text(
            json.dumps([{"artifact_id": "rec_1", "kind": "recording"}]),
            encoding="utf-8",
        )
        (round_dir / "review.json").write_text(
            json.dumps(
                {
                    "server_revision_id": "rev_round_2",
                    "tree_number": 2,
                    "transcript": "Review transcript",
                    "section_transcripts": {"client_tree_details": "hello"},
                    "images": [],
                    "draft_form": {
                        "schema_name": "demo",
                        "schema_version": "0.0",
                        "data": {"client_tree_details": {"tree_number": "2"}},
                    },
                }
            ),
            encoding="utf-8",
        )

        self.final_service.set_final(
            "J0009",
            payload={"round_id": "round_2", "transcript": "Final transcript"},
            geojson_payload={"type": "FeatureCollection", "features": []},
        )
        self.final_service.set_correction(
            "J0009",
            payload={"round_id": "round_3", "transcript": "Correction transcript"},
        )

        (job_dir / "final.json").write_text(
            json.dumps({"round_id": "round_2", "transcript": "Final transcript", "report_images": []}),
            encoding="utf-8",
        )
        (job_dir / "final_correction.json").write_text(
            json.dumps({"round_id": "round_3", "transcript": "Correction transcript", "report_images": []}),
            encoding="utf-8",
        )
        (job_dir / "final_report_letter.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final_traq_page1.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}),
            encoding="utf-8",
        )

        inspected_job = self.inspection_service.inspect_job("J0009")
        self.assertEqual(inspected_job["status"], "ARCHIVED")
        self.assertEqual(inspected_job["customer_code"], customer["customer_code"])
        self.assertEqual(inspected_job["billing_code"], billing["billing_code"])
        self.assertEqual(inspected_job["tree_number"], 2)

        inspected_review = self.inspection_service.inspect_review("J0009", "round_2")
        self.assertEqual(inspected_review["server_revision_id"], "rev_round_2")

        inspected_final = self.inspection_service.inspect_final("J0009")
        self.assertTrue(inspected_final["final"]["exists"])
        self.assertTrue(inspected_final["correction"]["exists"])
        self.assertEqual(inspected_final["correction"]["round_id"], "round_3")


if __name__ == "__main__":
    unittest.main()
