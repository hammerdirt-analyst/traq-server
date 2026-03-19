"""Focused regression checks for round processing orchestration."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.review_form_service import ReviewFormService
from app.services.round_processing_service import RoundProcessingService


class _DummyDbStore:
    def list_round_images(self, job_id: str, round_id: str):
        del job_id, round_id
        return [{"image_id": "img_1"}]


class _DummyReviewPayloadService:
    def build_round_images(self, rows):
        return list(rows)


class _ExtractionResult:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return dict(self._payload)


class _DummyLogger:
    def __init__(self) -> None:
        self.events = []

    def info(self, *args, **kwargs):
        self.events.append(("info", args, kwargs))

    def exception(self, *args, **kwargs):
        self.events.append(("exception", args, kwargs))


class RoundProcessingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.saved_review = None
        self.logger = _DummyLogger()
        self.review_form_service = ReviewFormService()
        self.service = RoundProcessingService(
            db_store=_DummyDbStore(),
            review_form_service=self.review_form_service,
            review_payload_service=_DummyReviewPayloadService(),
            build_section_transcript=self._build_section_transcript,
            load_latest_review=lambda job_id, exclude_round_id=None: {
                "draft_form": {
                    "schema_name": "demo",
                    "schema_version": "0.0",
                    "data": {"client_tree_details": {"client": None}},
                }
            },
            run_extraction_logged=self._run_extraction_logged,
            generate_summary=self._generate_summary,
            save_round_record=self._save_round_record,
            logger=self.logger,
        )
        self.record = SimpleNamespace(
            tree_number=7,
            rounds={
                "round_1": SimpleNamespace(
                    round_id="round_1",
                    server_revision_id="rev-1",
                    manifest=[
                        {
                            "kind": "recording",
                            "section_id": "client_tree_details",
                            "artifact_id": "rec_1",
                            "recorded_at": "2026-03-19T08:00:00",
                        }
                    ],
                )
            },
        )

    def _build_section_transcript(
        self,
        job_id,
        round_id,
        section_id,
        manifest,
        issue_id=None,
        seen_recordings=None,
        force_reprocess=False,
        force_transcribe=False,
    ):
        del job_id, round_id, manifest, issue_id, seen_recordings, force_reprocess, force_transcribe
        if section_id == "client_tree_details":
            return ("client transcript", ["rec_1"], [])
        return ("", [], [])

    def _run_extraction_logged(self, section_id: str, transcript: str):
        del transcript
        if section_id == "client_tree_details":
            return _ExtractionResult(
                {
                    "section_id": "client_tree_details",
                    "client": "Software Test",
                    "tree_species": "apple tree",
                }
            )
        if section_id == "risk_categorization":
            return _ExtractionResult({"rows": []})
        return _ExtractionResult({"section_id": section_id})

    def _generate_summary(self, *, form_data, transcript):
        self.summary_input = (form_data, transcript)
        return "summary text"

    def _save_round_record(self, job_id, round_record, *, review_payload=None):
        self.saved_review = (job_id, round_record, review_payload)

    def test_process_round_merges_extracted_values_and_persists_review(self):
        review = self.service.process_round("job_1", "round_1", self.record)

        details = review["draft_form"]["data"]["client_tree_details"]
        self.assertEqual(details["client"], "Software Test")
        self.assertEqual(details["tree_species"], "apple tree")
        self.assertEqual(details["tree_number"], "7")
        self.assertEqual(review["transcript"], "[client_tree_details]\nclient transcript")
        self.assertEqual(review["images"], [{"image_id": "img_1"}])
        self.assertEqual(self.saved_review[0], "job_1")

    def test_process_round_falls_back_when_summary_generation_fails(self):
        self.service = RoundProcessingService(
            db_store=_DummyDbStore(),
            review_form_service=self.review_form_service,
            review_payload_service=_DummyReviewPayloadService(),
            build_section_transcript=self._build_section_transcript,
            load_latest_review=lambda job_id, exclude_round_id=None: {},
            run_extraction_logged=self._run_extraction_logged,
            generate_summary=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            save_round_record=self._save_round_record,
            logger=self.logger,
            narrative_paragraphs_supplier=lambda: ["fallback paragraph"],
        )

        review = self.service.process_round("job_1", "round_1", self.record)

        self.assertEqual(review["narrative"], "fallback paragraph")
        self.assertTrue(any(event[0] == "exception" for event in self.logger.events))


if __name__ == "__main__":
    unittest.main()
