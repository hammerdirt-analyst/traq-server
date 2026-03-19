"""Focused checks for manifest and review-state read helpers."""

from __future__ import annotations

import unittest

from app.services.review_state_service import ReviewStateService


class _DummyDbStore:
    def __init__(self) -> None:
        self.rounds = [
            {"round_id": "round_1", "manifest": [{"artifact_id": "a1", "section_id": "s1", "kind": "recording"}], "review_payload": {"rev": 1}},
            {"round_id": "round_2", "manifest": [{"artifact_id": "a1", "section_id": "s1", "kind": "recording"}, {"artifact_id": "a2", "section_id": "s2", "kind": "recording"}], "review_payload": {"rev": 2}},
        ]

    def get_job_round(self, job_id: str, round_id: str):
        del job_id
        for row in self.rounds:
            if row["round_id"] == round_id:
                return row
        return None

    def list_job_rounds(self, job_id: str):
        del job_id
        return list(self.rounds)


class ReviewStateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReviewStateService(db_store=_DummyDbStore())

    def test_load_round_manifest_filters_non_dict_items(self) -> None:
        manifest = self.service.load_round_manifest("job_1", "round_1")
        self.assertEqual(manifest, [{"artifact_id": "a1", "section_id": "s1", "kind": "recording"}])

    def test_load_all_manifests_deduplicates_by_artifact_section_kind(self) -> None:
        manifests = self.service.load_all_manifests("job_1")
        self.assertEqual(
            manifests,
            [
                {"artifact_id": "a1", "section_id": "s1", "kind": "recording"},
                {"artifact_id": "a2", "section_id": "s2", "kind": "recording"},
            ],
        )

    def test_load_latest_review_respects_exclusion(self) -> None:
        review = self.service.load_latest_review("job_1", exclude_round_id="round_2")
        self.assertEqual(review, {"rev": 1})


if __name__ == "__main__":
    unittest.main()
