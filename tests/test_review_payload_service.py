"""Unit tests for review-payload normalization helpers."""

from __future__ import annotations

import unittest

from app.services.review_payload_service import ReviewPayloadService


class ReviewPayloadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReviewPayloadService()

    def test_build_round_images_maps_db_rows_to_review_entries(self) -> None:
        rows = [
            {
                "section_id": "job_photos",
                "image_id": "img_1",
                "upload_status": "uploaded",
                "caption": "Tree base",
                "latitude": "38.5",
                "longitude": "-121.0",
                "artifact_path": "jobs/job_1/sections/job_photos/images/img_1.jpg",
                "metadata_json": {
                    "report_image_path": "jobs/job_1/sections/job_photos/images/img_1.report.jpg",
                    "uploaded_at": "2026-03-19T10:00:00Z",
                },
            }
        ]

        images = self.service.build_round_images(rows)

        self.assertEqual(images, [
            {
                "id": "img_1",
                "image_id": "img_1",
                "section_id": "job_photos",
                "upload_status": "uploaded",
                "caption": "Tree base",
                "stored_path": "jobs/job_1/sections/job_photos/images/img_1.jpg",
                "report_image_path": "jobs/job_1/sections/job_photos/images/img_1.report.jpg",
                "uploaded_at": "2026-03-19T10:00:00Z",
                "gps": {"latitude": "38.5", "longitude": "-121.0"},
            }
        ])

    def test_normalize_payload_prefers_hydrated_images_and_sets_tree_number(self) -> None:
        payload = {
            "draft_form": {
                "schema_name": "demo",
                "schema_version": "0.0",
                "data": {"client_tree_details": {}},
            },
            "draft_narrative": "Narrative",
            "images": [],
        }
        hydrated_images = [{"id": "img_1"}]

        normalized = self.service.normalize_payload(
            payload,
            tree_number=4,
            normalize_form_schema=lambda data: data,
            hydrated_images=hydrated_images,
        )

        self.assertEqual(normalized["tree_number"], 4)
        self.assertEqual(normalized["narrative"], "Narrative")
        self.assertEqual(normalized["images"], hydrated_images)
        self.assertEqual(
            normalized["draft_form"]["data"]["client_tree_details"]["tree_number"],
            "4",
        )
        self.assertEqual(normalized["form"]["client_tree_details"]["tree_number"], "4")

    def test_build_default_payload_uses_supplied_images(self) -> None:
        payload = self.service.build_default_payload(
            round_id="round_1",
            server_revision_id="rev_round_1",
            tree_number=7,
            images=[{"id": "img_1"}],
        )

        self.assertEqual(payload["round_id"], "round_1")
        self.assertEqual(payload["server_revision_id"], "rev_round_1")
        self.assertEqual(payload["tree_number"], 7)
        self.assertEqual(payload["images"], [{"id": "img_1"}])


if __name__ == "__main__":
    unittest.main()
