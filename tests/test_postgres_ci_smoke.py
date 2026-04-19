"""PostgreSQL-backed CI smoke tests for migration and store parity."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import uuid

from app import db as db_module
from app.config import load_settings
from app.db import init_database
from app.db_store import DatabaseStore


@unittest.skipUnless(
    str(os.environ.get("TRAQ_DATABASE_URL") or "").startswith("postgresql+psycopg://"),
    "Postgres CI smoke tests require TRAQ_DATABASE_URL to point at PostgreSQL",
)
class PostgresCiSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.old_storage_root = os.environ.get("TRAQ_STORAGE_ROOT")
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        init_database(load_settings())
        self.store = DatabaseStore()

    def _restore_env(self) -> None:
        if self.old_storage_root is None:
            os.environ.pop("TRAQ_STORAGE_ROOT", None)
        else:
            os.environ["TRAQ_STORAGE_ROOT"] = self.old_storage_root
        if db_module._engine is not None:
            db_module._engine.dispose()
        db_module._engine = None
        db_module._SessionLocal = None

    def test_device_job_round_recording_and_image_round_trip(self) -> None:
        suffix = uuid.uuid4().hex[:8]
        device_id = f"device-{suffix}"
        job_id = f"job_{suffix}"
        round_id = f"round_{suffix}"

        registered = self.store.register_device(
            device_id=device_id,
            device_name="CI Pixel",
            app_version="1.0.0",
            profile_summary={"branch": "postgres-ci"},
        )
        self.assertEqual(registered["status"], "pending")

        approved = self.store.approve_device(device_id, role="admin")
        self.assertEqual(approved["status"], "approved")
        token_payload = self.store.issue_token(device_id, ttl_seconds=600)
        auth = self.store.validate_token(token_payload["access_token"])
        self.assertIsNotNone(auth)
        self.assertTrue(auth.is_admin)

        allocated_job_number = self.store.allocate_job_number()
        job = self.store.upsert_job(
            job_id=job_id,
            job_number=allocated_job_number,
            status="DRAFT",
            details={
                "job_name": "Postgres CI Smoke",
                "tree_number": 7,
                "tree_species": "Quercus agrifolia",
            },
        )
        self.assertEqual(job["job_id"], job_id)
        self.assertEqual(job["job_number"], allocated_job_number)

        assignment = self.store.assign_job(job_id=job_id, device_id=device_id, assigned_by="ci")
        self.assertEqual(assignment["device_id"], device_id)
        self.assertTrue(self.store.is_job_assigned_to_device(job_id, device_id))

        round_row = self.store.upsert_job_round(
            job_id=job_id,
            round_id=round_id,
            status="DRAFT",
            server_revision_id=f"rev_{suffix}",
            manifest=[{"section_id": "site_factors"}],
        )
        self.assertEqual(round_row["round_id"], round_id)
        self.assertEqual(round_row["status"], "DRAFT")

        recording = self.store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id="site_factors",
            recording_id="rec_1",
            upload_status="uploaded",
            content_type="audio/wav",
            duration_ms=1200,
            artifact_path=f"artifacts/{job_id}/{round_id}/rec_1.wav",
            metadata_json={"source": "ci"},
        )
        self.assertEqual(recording["upload_status"], "uploaded")

        image = self.store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            caption="The tree: CI smoke view",
            artifact_path=f"artifacts/{job_id}/{round_id}/img_1.jpg",
            metadata_json={"variant": "report"},
        )
        self.assertEqual(image["caption"], "The tree: CI smoke view")

        fetched_job = self.store.get_job(job_id)
        fetched_round = self.store.get_job_round(job_id, round_id)
        recordings = self.store.list_round_recordings(job_id, round_id)
        images = self.store.list_round_images(job_id, round_id)

        self.assertEqual(fetched_job["job_name"], "Postgres CI Smoke")
        self.assertEqual(fetched_round["server_revision_id"], f"rev_{suffix}")
        self.assertEqual(len(recordings), 1)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["caption"], "The tree: CI smoke view")

    def test_round_metadata_reconciliation_fields_round_trip(self) -> None:
        suffix = uuid.uuid4().hex[:8]
        job_id = f"job_{suffix}"
        round_id = f"round_{suffix}"

        allocated_job_number = self.store.allocate_job_number()
        self.store.upsert_job(
            job_id=job_id,
            job_number=allocated_job_number,
            status="DRAFT",
            latest_round_id=round_id,
            latest_round_status="DRAFT",
            details={
                "job_name": "Postgres Reconciliation Smoke",
                "tree_number": 11,
            },
        )

        self.store.upsert_job_round(
            job_id=job_id,
            round_id=round_id,
            status="DRAFT",
            server_revision_id=f"rev_{suffix}",
            client_revision_id=f"client-rev-{suffix}",
            manifest=[{"section_id": "site_factors", "artifact_id": "rec_1", "kind": "recording"}],
        )

        self.store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id="site_factors",
            recording_id="rec_1",
            upload_status="uploaded",
            content_type="audio/wav",
            duration_ms=1200,
            artifact_path=f"artifacts/{job_id}/{round_id}/rec_1.wav",
            metadata_json={"source": "ci"},
        )
        self.store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id="site_factors",
            recording_id="rec_1",
            upload_status="uploaded",
            content_type="audio/x-wav",
            duration_ms=1300,
            artifact_path=f"artifacts/{job_id}/{round_id}/rec_1_retry.wav",
            metadata_json={"source": "ci-retry"},
        )
        self.store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            caption="Initial image",
            artifact_path=f"artifacts/{job_id}/{round_id}/img_1.jpg",
            metadata_json={"variant": "report"},
        )
        self.store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            caption="Retried image",
            artifact_path=f"artifacts/{job_id}/{round_id}/img_1_retry.jpg",
            metadata_json={"variant": "report"},
        )

        fetched_round = self.store.get_job_round(job_id, round_id)
        recordings = self.store.list_round_recordings(job_id, round_id)
        images = self.store.list_round_images(job_id, round_id)

        self.assertEqual(fetched_round["client_revision_id"], f"client-rev-{suffix}")
        self.assertEqual(fetched_round["server_revision_id"], f"rev_{suffix}")
        self.assertEqual(len(recordings), 1)
        self.assertEqual(len(images), 1)
        self.assertEqual(recordings[0]["recording_id"], "rec_1")
        self.assertEqual(recordings[0]["artifact_path"], f"artifacts/{job_id}/{round_id}/rec_1_retry.wav")
        self.assertEqual(images[0]["image_id"], "img_1")
        self.assertEqual(images[0]["caption"], "Retried image")

    def test_allocate_job_number_is_monotonic(self) -> None:
        first = self.store.allocate_job_number()
        second = self.store.allocate_job_number()
        self.assertTrue(first.startswith("J"))
        self.assertTrue(second.startswith("J"))
        self.assertLess(int(first[1:]), int(second[1:]))


if __name__ == "__main__":
    unittest.main()
