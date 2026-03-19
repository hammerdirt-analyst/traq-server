"""Focused regression checks for submit-time review merge behavior."""

from __future__ import annotations

import unittest

from app.services.round_submit_service import RoundSubmitService


class RoundSubmitServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RoundSubmitService()

    def test_apply_client_form_patch_ignores_null_placeholders(self) -> None:
        draft_form = {
            "schema_name": "demo",
            "schema_version": "0.0",
            "data": {
                "client_tree_details": {
                    "client": "Software Test",
                    "tree_species": "apple tree",
                    "dbh": 22,
                    "height": 18,
                }
            },
        }
        form_patch = {
            "client_tree_details": {
                "client": "Software Test",
                "tree_species": None,
                "dbh": None,
                "height": None,
            }
        }

        result = self.service.apply_client_form_patch(
            draft_form,
            form_patch,
            apply_form_patch=self._apply_form_patch,
            normalize_form_schema=lambda form: form,
        )

        details = result["data"]["client_tree_details"]
        self.assertEqual(details["client"], "Software Test")
        self.assertEqual(details["tree_species"], "apple tree")
        self.assertEqual(details["dbh"], 22)
        self.assertEqual(details["height"], 18)

    def test_apply_post_process_client_patch_preserves_extracted_values(self) -> None:
        review_payload = {
            "draft_form": {
                "schema_name": "demo",
                "schema_version": "0.0",
                "data": {
                    "client_tree_details": {
                        "client": "Software Test",
                        "tree_species": "apple tree",
                        "dbh": 22,
                    }
                },
            },
            "form": {
                "client_tree_details": {
                    "client": "Software Test",
                    "tree_species": "apple tree",
                    "dbh": 22,
                }
            },
            "draft_narrative": "Original",
            "narrative": "Original",
        }

        class SubmitPayload:
            form = {
                "client_tree_details": {
                    "client": "Software Test",
                    "tree_species": None,
                    "dbh": None,
                }
            }
            narrative = {"text": "Client narrative"}

        updated = self.service.apply_post_process_client_patch(
            review_payload=review_payload,
            submit_payload=SubmitPayload(),
            tree_number=1,
            apply_form_patch=self._apply_form_patch,
            normalize_form_schema=lambda form: form,
        )

        details = updated["draft_form"]["data"]["client_tree_details"]
        self.assertEqual(details["tree_species"], "apple tree")
        self.assertEqual(details["dbh"], 22)
        self.assertEqual(updated["narrative"], "Client narrative")
        self.assertEqual(updated["tree_number"], 1)

    def test_build_base_review_override_reuses_latest_review_when_current_round_empty(self) -> None:
        class SubmitPayload:
            form = {"client_tree_details": {"client": "Software Test"}}
            narrative = None
            client_revision_id = "client-rev-1"

        override = self.service.build_base_review_override(
            job_id="job_1",
            round_id="round_1",
            existing_round_review={},
            submit_payload=SubmitPayload(),
            load_latest_review=lambda job_id, exclude_round_id=None: {
                "draft_form": {"data": {"client_tree_details": {"tree_species": "apple tree"}}},
                "draft_narrative": "Previous",
            },
            apply_form_patch=self._apply_form_patch,
            normalize_form_schema=lambda form: form,
        )

        details = override["draft_form"]["data"]["client_tree_details"]
        self.assertEqual(details["client"], "Software Test")
        self.assertEqual(details["tree_species"], "apple tree")
        self.assertEqual(override["client_revision_id"], "client-rev-1")

    @staticmethod
    def _apply_form_patch(base_form: dict, patch: dict) -> dict:
        merged = dict(base_form or {})
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = RoundSubmitServiceTests._apply_form_patch(
                    dict(merged.get(key) or {}),
                    dict(value),
                )
            else:
                merged[key] = value
        return merged


if __name__ == "__main__":
    unittest.main()
