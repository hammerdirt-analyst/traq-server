"""Unit tests for finalization helper extraction."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.finalization_service import FinalizationService


class FinalizationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = FinalizationService()

    def test_artifact_names_switch_for_correction_mode(self) -> None:
        final_names = self.service.artifact_names(False)
        correction_names = self.service.artifact_names(True)

        self.assertEqual(final_names.pdf_name, "final_traq_page1.pdf")
        self.assertEqual(final_names.final_json_name, "final.json")
        self.assertEqual(correction_names.pdf_name, "final_traq_page1_correction.pdf")
        self.assertEqual(correction_names.final_json_name, "final_correction.json")

    def test_ensure_risk_defaults_normalizes_rows_and_trims_notes(self) -> None:
        form = {
            "data": {
                "notes_explanations_descriptions": {
                    "notes": "word " * 80,
                }
            }
        }

        normalized = self.service.ensure_risk_defaults(
            form,
            normalize_form_schema=lambda data: data,
        )

        self.assertEqual(normalized["data"]["risk_categorization"], [])
        self.assertLessEqual(
            len(normalized["data"]["notes_explanations_descriptions"]["notes"]),
            230,
        )

    def test_resolve_profile_payload_prefers_explicit_and_swallows_fallback_errors(self) -> None:
        explicit = {"name": "Tester"}
        resolved = self.service.resolve_profile_payload(
            explicit,
            fallback_loader=lambda: {"name": "Fallback"},
        )
        self.assertEqual(resolved, explicit)

        resolved = self.service.resolve_profile_payload(
            None,
            fallback_loader=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        self.assertIsNone(resolved)

    def test_build_final_payload_keeps_finalization_contract(self) -> None:
        payload = self.service.build_final_payload(
            job_id="job_1",
            round_id="round_1",
            server_revision_id="server-rev",
            client_revision_id="client-rev",
            archived_at="2026-03-19T00:00:00Z",
            transcript="Transcript",
            form={"data": {}},
            narrative={"text": "Narrative"},
            user_name="Tester",
            profile=None,
            report_images=[{"id": "img_1"}],
        )

        self.assertEqual(payload["job_id"], "job_1")
        self.assertEqual(payload["round_id"], "round_1")
        self.assertEqual(payload["transcript"], "Transcript")
        self.assertEqual(payload["user_name"], "Tester")
        self.assertEqual(payload["report_images"], [{"id": "img_1"}])

    def test_build_job_info_reads_expected_fields(self) -> None:
        record = SimpleNamespace(
            job_address="123 Oak",
            address="123 Oak",
            billing_name="Billing",
            billing_address="PO Box 1",
            billing_contact_name="Alex",
        )

        job_info = self.service.build_job_info(record)

        self.assertEqual(job_info["job_address"], "123 Oak")
        self.assertEqual(job_info["billing_contact_name"], "Alex")


if __name__ == "__main__":
    unittest.main()
