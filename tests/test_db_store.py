"""Service-level tests for the database-backed operational store."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from server.app import db as db_module
from server.app.config import load_settings
from server.app.db import create_schema, init_database
from server.app.db_store import DatabaseStore


class DatabaseStoreTests(unittest.TestCase):
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

    def test_device_token_flow(self) -> None:
        registered = self.store.register_device(
            device_id="device-1",
            device_name="Pixel",
            app_version="0.1.0",
            profile_summary={"name": "Roger"},
        )
        self.assertEqual(registered["status"], "pending")

        approved = self.store.approve_device("device-1")
        self.assertEqual(approved["status"], "approved")

        issued = self.store.issue_token("device-1", ttl_seconds=3600)
        self.assertEqual(issued["device_id"], "device-1")
        auth = self.store.validate_token(issued["access_token"])
        self.assertIsNotNone(auth)
        self.assertEqual(auth.device_id, "device-1")
        self.assertFalse(auth.is_admin)

    def test_job_assignment_flow(self) -> None:
        self.store.register_device(
            device_id="device-1",
            device_name="Pixel",
            app_version="0.1.0",
            profile_summary=None,
        )
        self.store.approve_device("device-1")
        self.store.upsert_job(
            job_id="job_abc",
            job_number="J0001",
            status="DRAFT",
            details={
                "job_name": "Customer Tree",
                "job_address": "123 Oak St",
                "tree_number": 4,
            },
        )

        assignment = self.store.assign_job(
            job_id="job_abc",
            device_id="device-1",
            assigned_by="admin",
        )
        self.assertEqual(assignment["job_id"], "job_abc")
        self.assertEqual(assignment["device_id"], "device-1")

        assignments = self.store.list_job_assignments()
        self.assertEqual(len(assignments), 1)
        self.assertEqual(assignments[0]["job_id"], "job_abc")

        job = self.store.get_job("job_abc")
        self.assertIsNotNone(job)
        self.assertEqual(job["tree_number"], 4)

    def test_runtime_profile_flow(self) -> None:
        self.assertIsNone(self.store.get_runtime_profile("device:abc"))

        stored = self.store.upsert_runtime_profile(
            identity_key="device:abc",
            profile_payload={
                "name": "Roger Erismann",
                "phone": "916 699 1113",
                "isa_number": "WE-380138A",
            },
        )
        self.assertEqual(stored["name"], "Roger Erismann")

        fetched = self.store.get_runtime_profile("device:abc")
        self.assertEqual(fetched, stored)

        updated = self.store.upsert_runtime_profile(
            identity_key="device:abc",
            profile_payload={
                "name": "Updated Name",
                "phone": "916 699 1113",
            },
        )
        self.assertEqual(updated["name"], "Updated Name")
        self.assertEqual(
            self.store.get_runtime_profile("device:abc"),
            {"name": "Updated Name", "phone": "916 699 1113"},
        )

    def test_round_recording_flow(self) -> None:
        self.store.upsert_job(
            job_id="job_round",
            job_number="J0009",
            status="DRAFT",
            latest_round_id="round_1",
            latest_round_status="DRAFT",
            details={},
        )
        self.store.upsert_job_round(
            job_id="job_round",
            round_id="round_1",
            status="DRAFT",
            manifest=[],
        )

        stored = self.store.upsert_round_recording(
            job_id="job_round",
            round_id="round_1",
            section_id="site_factors",
            recording_id="rec_1",
            upload_status="uploaded",
            content_type="audio/wav",
            duration_ms=1250,
            artifact_path="/tmp/rec_1.wav",
            metadata_json={
                "stored_path": "/tmp/rec_1.wav",
                "uploaded_at": "2026-03-17T00:00:00Z",
            },
        )
        self.assertEqual(stored["recording_id"], "rec_1")
        self.assertEqual(stored["upload_status"], "uploaded")

        fetched = self.store.get_round_recording(
            job_id="job_round",
            round_id="round_1",
            section_id="site_factors",
            recording_id="rec_1",
        )
        self.assertEqual(fetched["artifact_path"], "/tmp/rec_1.wav")
        self.assertEqual(fetched["content_type"], "audio/wav")

        rows = self.store.list_round_recordings("job_round", "round_1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["recording_id"], "rec_1")

    def test_round_image_flow(self) -> None:
        self.store.upsert_job(
            job_id="job_image",
            job_number="J0010",
            status="DRAFT",
            latest_round_id="round_1",
            latest_round_status="DRAFT",
            details={},
        )
        self.store.upsert_job_round(
            job_id="job_image",
            round_id="round_1",
            status="DRAFT",
            manifest=[],
        )

        stored = self.store.upsert_round_image(
            job_id="job_image",
            round_id="round_1",
            section_id="job_photos",
            image_id="img_1",
            upload_status="uploaded",
            caption="Tree base",
            latitude="38.5",
            longitude="-121.0",
            artifact_path="/tmp/img_1.jpg",
            metadata_json={
                "stored_path": "/tmp/img_1.jpg",
                "report_image_path": "/tmp/img_1.report.jpg",
            },
        )
        self.assertEqual(stored["image_id"], "img_1")
        self.assertEqual(stored["caption"], "Tree base")

        fetched = self.store.get_round_image(
            job_id="job_image",
            round_id="round_1",
            section_id="job_photos",
            image_id="img_1",
        )
        self.assertEqual(fetched["artifact_path"], "/tmp/img_1.jpg")
        self.assertEqual(fetched["latitude"], "38.5")

        rows = self.store.list_round_images("job_image", "round_1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_id"], "img_1")


if __name__ == "__main__":
    unittest.main()
