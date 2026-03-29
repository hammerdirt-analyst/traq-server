"""Focused tests for completed-final report image helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.services.final_report_images_service import (
    completed_report_image_exports,
    legacy_report_image_key,
    merge_completed_report_images,
    resolve_completed_report_image_path,
)


class FinalReportImagesServiceTests(unittest.TestCase):
    def test_legacy_report_image_key_reconstructs_expected_key(self) -> None:
        self.assertEqual(
            legacy_report_image_key(
                job_id="job_1",
                raw_path="/app/local_data/artifact_cache/jobs/job_1/sections/job_photos/images/img_1.report.jpg",
            ),
            "jobs/job_1/sections/job_photos/images/img_1.report.jpg",
        )

    def test_completed_report_image_exports_builds_download_entries(self) -> None:
        payload = {
            "report_images": [
                {"caption": "canopy", "uploaded_at": "2026-03-28T12:00:00Z"},
                {"caption": "trunk", "uploaded_at": "2026-03-28T12:01:00Z"},
            ]
        }
        exported = completed_report_image_exports(
            payload=payload,
            job_id="job_1",
            build_image_url=lambda job_id, image_ref: f"/img/{job_id}/{image_ref}",
        )
        self.assertEqual(exported[0]["image_ref"], "report_1")
        self.assertEqual(exported[1]["download_url"], "/img/job_1/report_2")

    def test_merge_completed_report_images_uses_runtime_merge_when_available(self) -> None:
        class _MediaService:
            @staticmethod
            def merge_report_images(*image_lists):
                merged = []
                for image_list in image_lists:
                    for item in image_list or []:
                        merged.append(item)
                return merged

        merged = merge_completed_report_images(
            media_runtime_service=_MediaService(),
            current_report_images=[{"path": "/tmp/new.jpg"}],
            archived_final_payload={"report_images": [{"path": "/tmp/old.jpg"}]},
            archived_correction_payload={"report_images": [{"path": "/tmp/correction.jpg"}]},
        )
        self.assertEqual(len(merged), 3)

    def test_resolve_completed_report_image_path_prefers_stored_path(self) -> None:
        with TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            target = root / "jobs/job_1/images/report.jpg"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x")
            resolved = resolve_completed_report_image_path(
                job_id="job_1",
                image_ref="report_1",
                payload={"report_images": [{"stored_path": "jobs/job_1/images/report.jpg"}]},
                materialize_artifact_path=lambda key: root / key,
            )
            self.assertEqual(resolved, target)
