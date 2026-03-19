"""Focused tests for review-form normalization and merge helpers."""

from __future__ import annotations

import unittest

from app.services.review_form_service import ReviewFormService


class ReviewFormServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReviewFormService()

    def test_normalize_form_schema_moves_legacy_landscape_environment(self) -> None:
        normalized = self.service.normalize_form_schema(
            {
                "site_factors": {
                    "landscape_environment": "urban street",
                    "site_changes": {},
                },
                "recommended_inspection_interval": {"interval": "12 months"},
            }
        )

        self.assertEqual(
            normalized["site_factors"]["site_changes"]["landscape_environment"],
            "urban street",
        )
        self.assertEqual(
            normalized["recommended_inspection_interval"]["text"],
            "12 months",
        )

    def test_apply_form_patch_recurses_nested_groups(self) -> None:
        result = self.service.apply_form_patch(
            {
                "data": {
                    "client_tree_details": {"client": "A"},
                    "site_factors": {"topography": {"flat": None}},
                }
            },
            {
                "data": {
                    "site_factors": {"topography": {"flat": True}},
                }
            },
        )

        self.assertEqual(result["data"]["client_tree_details"]["client"], "A")
        self.assertTrue(result["data"]["site_factors"]["topography"]["flat"])

    def test_merge_client_tree_details_preserves_existing_non_empty_values(self) -> None:
        merged = self.service.merge_client_tree_details(
            {
                "client": "Software Test",
                "tree_species": "apple tree",
                "dbh": 22,
            },
            {
                "client": "Software Test",
                "tree_species": None,
                "dbh": None,
                "height": 18,
            },
        )

        self.assertEqual(merged["tree_species"], "apple tree")
        self.assertEqual(merged["dbh"], 22)
        self.assertEqual(merged["height"], 18)


if __name__ == "__main__":
    unittest.main()
