"""Direct tests for the read-only inspection service."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.customer_service import CustomerService
from app.services.final_mutation_service import FinalMutationService
from app.services.inspection_service import InspectionService
from app.services.job_mutation_service import JobMutationService


class InspectionServiceTests(unittest.TestCase):
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

        customer = self.customer_service.create_customer(name="Test Customer")
        self.job_service.create_job(
            job_id="job_1",
            job_number="J0001",
            customer_id=customer["customer_id"],
            tree_number=2,
            job_name="Valley Oak",
            job_address="123 Oak St",
            status="REVIEW_RETURNED",
        )
        job_dir = self.storage_root / "jobs" / "job_1"
        round_dir = job_dir / "rounds" / "round_1"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "manifest.json").write_text(
            json.dumps([{"artifact_id": "rec_1", "kind": "recording"}]),
            encoding="utf-8",
        )
        (round_dir / "review.json").write_text(
            json.dumps(
                {
                    "server_revision_id": "rev_round_1",
                    "tree_number": 2,
                    "transcript": "Transcript ready.",
                    "section_transcripts": {"client_tree_details": "hello"},
                    "images": [{"id": "img_1"}],
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
            "J0001",
            payload={
                "round_id": "round_1",
                "user_name": "Roger",
                "transcript": "Final transcript",
                "report_images": [],
            },
            geojson_payload={"type": "FeatureCollection", "features": []},
        )
        (job_dir / "final.json").write_text(
            json.dumps(
                {
                    "round_id": "round_1",
                    "user_name": "Roger",
                    "transcript": "Final transcript",
                    "report_images": [],
                }
            ),
            encoding="utf-8",
        )
        (job_dir / "final_traq_page1.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final_report_letter.pdf").write_text("pdf", encoding="utf-8")
        (job_dir / "final.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": []}),
            encoding="utf-8",
        )

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

    def test_resolve_job_id_and_inspect_job(self) -> None:
        self.assertEqual(self.inspection_service.resolve_job_id("J0001"), "job_1")
        payload = self.inspection_service.inspect_job("J0001")
        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["customer_code"], "C0001")
        self.assertEqual(payload["customer_name"], "Test Customer")
        self.assertIsNone(payload["billing_code"])
        self.assertEqual(payload["tree_number"], 2)
        self.assertEqual(payload["round_ids"], ["round_1"])
        self.assertTrue(payload["has_final"])

    def test_inspect_round_and_review(self) -> None:
        round_payload = self.inspection_service.inspect_round("J0001", "round_1")
        self.assertTrue(round_payload["has_manifest"])
        self.assertTrue(round_payload["has_review"])
        self.assertEqual(round_payload["manifest_count"], 1)
        self.assertEqual(round_payload["server_revision_id"], "rev_round_1")

        review_payload = self.inspection_service.inspect_review("J0001", "round_1")
        self.assertEqual(review_payload["tree_number"], 2)
        self.assertTrue(review_payload["has_form"])
        self.assertEqual(review_payload["section_count"], 1)
        self.assertEqual(review_payload["image_count"], 1)

    def test_inspect_final(self) -> None:
        payload = self.inspection_service.inspect_final("J0001")
        self.assertTrue(payload["final"]["exists"])
        self.assertTrue(payload["final"]["report_pdf_exists"])
        self.assertTrue(payload["final"]["geojson_exists"])
        self.assertEqual(payload["final"]["round_id"], "round_1")
        self.assertFalse(payload["correction"]["exists"])


if __name__ == "__main__":
    unittest.main()
