"""Focused tests for report-image runtime helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.artifact_storage import LocalArtifactStore
from app.services.report_image_runtime_service import ReportImageRuntimeService


class _DummyDbStore:
    def __init__(self) -> None:
        self.image_rows: list[dict] = []
        self.job_round_rows: list[dict] = []

    def list_round_images(self, job_id: str, round_id: str):
        if callable(getattr(self, "_list_round_images", None)):
            return self._list_round_images(job_id, round_id)  # type: ignore[misc]
        del job_id
        return list(self.image_rows)

    def list_job_rounds(self, job_id: str):
        del job_id
        return list(self.job_round_rows)


class ReportImageRuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.store = LocalArtifactStore(self.root)
        self.db = _DummyDbStore()
        self.service = ReportImageRuntimeService(
            db_store=self.db,
            artifact_store=self.store,
        )

    def test_load_job_report_images_uses_db_backed_metadata(self) -> None:
        report_key = "jobs/job_1/sections/job_photos/images/img_1.report.jpg"
        report_path = self.store.write_bytes(report_key, b"img")
        self.db.image_rows = [
            {
                "caption": "Canopy",
                "artifact_path": "jobs/job_1/sections/job_photos/images/img_1.jpg",
                "metadata_json": {
                    "report_image_path": report_key,
                    "uploaded_at": "2026-03-19T10:00:00Z",
                },
            }
        ]

        images = self.service.load_job_report_images(job_id="job_1", round_id="round_1")

        self.assertEqual(
            images,
            [
                {
                    "path": str(report_path),
                    "stored_path": report_key,
                    "caption": "Canopy",
                    "uploaded_at": "2026-03-19T10:00:00Z",
                }
            ],
        )

    def test_merge_report_images_preserves_prior_and_appends_new(self) -> None:
        merged = self.service.merge_report_images(
            [
                {
                    "path": "/tmp/img_1.jpg",
                    "stored_path": "jobs/job_1/sections/job_photos/images/img_1.report.jpg",
                    "caption": "Existing 1",
                    "uploaded_at": "2026-03-19T09:00:00Z",
                },
                {
                    "path": "/tmp/img_2.jpg",
                    "stored_path": "jobs/job_1/sections/job_photos/images/img_2.report.jpg",
                    "caption": "Existing 2",
                    "uploaded_at": "2026-03-19T09:05:00Z",
                },
            ],
            [
                {
                    "path": "/tmp/other-location.jpg",
                    "stored_path": "jobs/job_1/sections/job_photos/images/img_2.report.jpg",
                    "caption": "Updated Existing 2",
                    "uploaded_at": "2026-03-19T09:07:00Z",
                },
                {
                    "path": "/tmp/img_3.jpg",
                    "stored_path": "jobs/job_1/sections/job_photos/images/img_3.report.jpg",
                    "caption": "New",
                    "uploaded_at": "2026-03-19T09:10:00Z",
                },
            ],
        )
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[1]["path"], "/tmp/other-location.jpg")
        self.assertEqual(merged[1]["stored_path"], "jobs/job_1/sections/job_photos/images/img_2.report.jpg")

    def test_load_effective_job_report_images_merges_preferred_and_prior_rounds(self) -> None:
        report_key_round_1 = "jobs/job_1/sections/job_photos/images/img_1.report.jpg"
        report_key_round_2 = "jobs/job_1/sections/job_photos/images/img_2.report.jpg"
        report_path_round_1 = self.store.write_bytes(report_key_round_1, b"img-1")
        report_path_round_2 = self.store.write_bytes(report_key_round_2, b"img-2")
        self.db.job_round_rows = [
            {"round_id": "round_1"},
            {"round_id": "round_2"},
        ]

        def _list_round_images(job_id: str, round_id: str):
            del job_id
            if round_id == "round_2":
                return [
                    {
                        "caption": "Newer",
                        "artifact_path": "jobs/job_1/sections/job_photos/images/img_2.jpg",
                        "metadata_json": {
                            "report_image_path": report_key_round_2,
                            "uploaded_at": "2026-03-19T11:00:00Z",
                        },
                    }
                ]
            if round_id == "round_1":
                return [
                    {
                        "caption": "Older",
                        "artifact_path": "jobs/job_1/sections/job_photos/images/img_1.jpg",
                        "metadata_json": {
                            "report_image_path": report_key_round_1,
                            "uploaded_at": "2026-03-19T10:00:00Z",
                        },
                    }
                ]
            return []

        self.db._list_round_images = _list_round_images

        images = self.service.load_effective_job_report_images(
            job_id="job_1",
            preferred_round_id="round_2",
        )

        self.assertEqual(
            images,
            [
                {
                    "path": str(report_path_round_2),
                    "stored_path": report_key_round_2,
                    "caption": "Newer",
                    "uploaded_at": "2026-03-19T11:00:00Z",
                },
                {
                    "path": str(report_path_round_1),
                    "stored_path": report_key_round_1,
                    "caption": "Older",
                    "uploaded_at": "2026-03-19T10:00:00Z",
                },
            ],
        )
