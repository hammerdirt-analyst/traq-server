"""Unit tests for downstream export sync service behavior."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.customer_service import CustomerService
from app.services.export_sync_service import ExportSyncService
from app.services.final_mutation_service import FinalMutationService
from app.services.job_mutation_service import JobMutationService
from app.services.review_form_service import ReviewFormService


class ExportSyncServiceTests(unittest.TestCase):
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

        customer = CustomerService().create_customer(name="Export Test Customer")
        self.job_service = JobMutationService()
        self.db_store = DatabaseStore()
        self.final_mutation_service = FinalMutationService()
        self.export_service = ExportSyncService(
            normalize_form_schema=ReviewFormService().normalize_form_schema,
            materialize_artifact_path=lambda key: self.storage_root / key,
        )

        self.job_service.create_job(
            job_id="job_in_process",
            job_number="J0001",
            customer_id=customer["customer_id"],
            tree_number=1,
            job_name="In Process Job",
            status="REVIEW_RETURNED",
        )
        self.job_service.create_job(
            job_id="job_completed",
            job_number="J0002",
            customer_id=customer["customer_id"],
            tree_number=2,
            job_name="Completed Job",
            status="DRAFT",
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

    def _write_artifact(self, relative_key: str, content: bytes = b"artifact") -> Path:
        path = self.storage_root / relative_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_build_changes_returns_in_process_review_payload_and_images(self) -> None:
        self.db_store.upsert_job_round(
            job_id="job_in_process",
            round_id="round_1",
            status="REVIEW_RETURNED",
            server_revision_id="rev_round_1",
            review_payload={
                "transcript": "site factors transcript",
                "form": {"client_tree_details": {"client": "Acme"}, "site_factors": {"history_of_failures": "None"}},
            },
        )
        self.db_store.upsert_job(
            job_id="job_in_process",
            job_number="J0001",
            status="REVIEW_RETURNED",
            latest_round_id="round_1",
            latest_round_status="REVIEW_RETURNED",
        )
        self._write_artifact("jobs/job_in_process/sections/job_photos/images/img_1.jpg")
        self._write_artifact("jobs/job_in_process/sections/job_photos/images/img_1.report.jpg")
        self.db_store.upsert_round_image(
            job_id="job_in_process",
            round_id="round_1",
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            caption="canopy photo",
            artifact_path="jobs/job_in_process/sections/job_photos/images/img_1.jpg",
            metadata_json={
                "uploaded_at": "2026-03-24T18:31:00Z",
                "stored_path": "jobs/job_in_process/sections/job_photos/images/img_1.jpg",
                "report_image_path": "jobs/job_in_process/sections/job_photos/images/img_1.report.jpg",
            },
        )

        payload = self.export_service.build_changes(
            cursor=None,
            build_image_url=lambda job_id, image_ref: f"/img/{job_id}/{image_ref}",
            build_geojson_url=lambda job_id: f"/geo/{job_id}",
        )

        self.assertEqual(len(payload["in_process"]), 2)
        job_payload = next(item for item in payload["in_process"] if item["job_id"] == "job_in_process")
        self.assertEqual(job_payload["review"]["round_id"], "round_1")
        self.assertEqual(job_payload["review"]["transcript"], "site factors transcript")
        self.assertEqual(job_payload["review"]["form"]["data"]["client_tree_details"]["client"], "Acme")
        self.assertIsNone(job_payload["profile"])
        self.assertEqual(job_payload["review"]["images"][0]["download_url"], "/img/job_in_process/img_1")
        self.assertEqual(
            job_payload["review"]["images"][0]["report_download_url"],
            "/img/job_in_process/img_1?variant=report",
        )

    def test_build_changes_returns_completed_payload_profile_and_transition(self) -> None:
        self.final_mutation_service.set_final(
            "J0002",
            payload={
                "round_id": "round_2",
                "server_revision_id": "rev_round_2",
                "client_revision_id": "client_rev_2",
                "archived_at": "2026-03-24T18:41:00Z",
                "transcript": "completed transcript",
                "form": {"data": {"client_tree_details": {"client": "Finished Client"}}},
                "narrative": {"text": "done"},
                "user_name": "Jane Arborist",
                "profile": {
                    "name": "Jane Arborist",
                    "phone": "555-111-2222",
                    "isa_number": "WE-1234A",
                    "correspondence_email": "jane@example.com",
                },
                "report_images": [
                    {
                        "path": str(self._write_artifact("jobs/job_completed/final_report_image_1.jpg")),
                        "caption": "root flare",
                        "uploaded_at": "2026-03-24T18:35:00Z",
                    }
                ],
            },
            geojson_payload={"type": "FeatureCollection", "features": []},
        )

        payload = self.export_service.build_changes(
            cursor="2026-03-24T18:40:30Z",
            build_image_url=lambda job_id, image_ref: f"/img/{job_id}/{image_ref}",
            build_geojson_url=lambda job_id: f"/geo/{job_id}",
        )

        self.assertEqual(len(payload["completed"]), 1)
        completed = payload["completed"][0]
        self.assertEqual(completed["job_id"], "job_completed")
        self.assertEqual(completed["profile"]["name"], "Jane Arborist")
        self.assertEqual(completed["final"]["form"]["data"]["client_tree_details"]["client"], "Finished Client")
        self.assertEqual(completed["final"]["report_images"][0]["image_ref"], "report_1")
        self.assertEqual(completed["final"]["report_images"][0]["download_url"], "/img/job_completed/report_1")
        self.assertEqual(completed["final"]["geojson_url"], "/geo/job_completed")
        self.assertEqual(len(payload["transitioned_to_completed"]), 1)
        self.assertEqual(payload["transitioned_to_completed"][0]["job_id"], "job_completed")

    def test_resolve_image_path_prefers_requested_variant_for_in_process_and_completed(self) -> None:
        original = self._write_artifact("jobs/job_in_process/sections/job_photos/images/img_1.jpg", b"original")
        report = self._write_artifact("jobs/job_in_process/sections/job_photos/images/img_1.report.jpg", b"report")
        self.db_store.upsert_job_round(
            job_id="job_in_process",
            round_id="round_1",
            status="REVIEW_RETURNED",
            review_payload={"form": {"site_factors": {}}},
        )
        self.db_store.upsert_job(
            job_id="job_in_process",
            job_number="J0001",
            status="REVIEW_RETURNED",
            latest_round_id="round_1",
            latest_round_status="REVIEW_RETURNED",
        )
        self.db_store.upsert_round_image(
            job_id="job_in_process",
            round_id="round_1",
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            artifact_path="jobs/job_in_process/sections/job_photos/images/img_1.jpg",
            metadata_json={
                "stored_path": "jobs/job_in_process/sections/job_photos/images/img_1.jpg",
                "report_image_path": "jobs/job_in_process/sections/job_photos/images/img_1.report.jpg",
            },
        )
        completed_path = self._write_artifact("jobs/job_completed/final_report_image_1.jpg", b"completed")
        self.final_mutation_service.set_final(
            "J0002",
            payload={
                "round_id": "round_2",
                "server_revision_id": "rev_round_2",
                "client_revision_id": "client_rev_2",
                "archived_at": "2026-03-24T18:41:00Z",
                "transcript": "completed transcript",
                "form": {"data": {}},
                "narrative": {"text": "done"},
                "user_name": "Jane Arborist",
                "profile": {"name": "Jane Arborist"},
                "report_images": [{"path": str(completed_path), "caption": "report image"}],
            },
            geojson_payload={"type": "FeatureCollection", "features": []},
        )

        resolved_original = self.export_service.resolve_image_path(
            job_id="job_in_process",
            image_ref="img_1",
            variant="original",
        )
        resolved_report = self.export_service.resolve_image_path(
            job_id="job_in_process",
            image_ref="img_1",
            variant="report",
        )
        resolved_completed = self.export_service.resolve_image_path(
            job_id="job_completed",
            image_ref="report_1",
            variant="auto",
        )

        self.assertEqual(resolved_original, original)
        self.assertEqual(resolved_report, report)
        self.assertEqual(resolved_completed, completed_path)

    def test_resolve_image_path_for_completed_job_prefers_stored_path_key(self) -> None:
        canonical_report = self._write_artifact("jobs/job_completed/final_report_image_1.jpg", b"completed")
        self.final_mutation_service.set_final(
            "J0002",
            payload={
                "round_id": "round_2",
                "server_revision_id": "rev_round_2",
                "client_revision_id": "client_rev_2",
                "archived_at": "2026-03-24T18:41:00Z",
                "transcript": "completed transcript",
                "form": {"data": {}},
                "narrative": {"text": "done"},
                "user_name": "Jane Arborist",
                "profile": {"name": "Jane Arborist"},
                "report_images": [
                    {
                        "path": "/tmp/non-portable/location/final_report_image_1.jpg",
                        "stored_path": "jobs/job_completed/final_report_image_1.jpg",
                        "caption": "report image",
                    }
                ],
            },
            geojson_payload={"type": "FeatureCollection", "features": []},
        )

        resolved = self.export_service.resolve_image_path(
            job_id="job_completed",
            image_ref="report_1",
            variant="report",
        )
        self.assertEqual(resolved, canonical_report)

    def test_resolve_geojson_payload_and_invalid_cursor(self) -> None:
        self.final_mutation_service.set_final(
            "J0002",
            payload={
                "round_id": "round_2",
                "server_revision_id": "rev_round_2",
                "client_revision_id": "client_rev_2",
                "archived_at": "2026-03-24T18:41:00Z",
                "transcript": "completed transcript",
                "form": {"data": {}},
                "narrative": {"text": "done"},
                "user_name": "Jane Arborist",
                "profile": {"name": "Jane Arborist"},
                "report_images": [],
            },
            geojson_payload={"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        )

        geojson = self.export_service.resolve_geojson_payload(job_id="job_completed")
        self.assertEqual(geojson["type"], "FeatureCollection")
        self.assertEqual(len(geojson["features"]), 1)
        with self.assertRaises(ValueError):
            self.export_service.build_changes(
                cursor="not-a-cursor",
                build_image_url=lambda job_id, image_ref: f"/img/{job_id}/{image_ref}",
                build_geojson_url=lambda job_id: f"/geo/{job_id}",
            )


if __name__ == "__main__":
    unittest.main()
