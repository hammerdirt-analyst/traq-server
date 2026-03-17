"""Unit tests for the legacy PostgreSQL importer helpers.

These tests stay off the live server/runtime path. They validate the helper
logic used to map legacy files into the SQL schema.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from server.app.db_models import ArtifactKind, JobStatus, RoundStatus, UploadStatus
from server.tools import import_legacy_jobs


class ImportLegacyJobsTests(unittest.TestCase):
    def test_parse_job_status_defaults_to_draft(self) -> None:
        self.assertEqual(import_legacy_jobs._parse_job_status(None), JobStatus.draft)
        self.assertEqual(import_legacy_jobs._parse_job_status("ARCHIVED"), JobStatus.archived)
        self.assertEqual(import_legacy_jobs._parse_job_status("nonsense"), JobStatus.draft)

    def test_parse_round_status_defaults_to_draft(self) -> None:
        self.assertEqual(import_legacy_jobs._parse_round_status(None), RoundStatus.draft)
        self.assertEqual(import_legacy_jobs._parse_round_status("REVIEW_RETURNED"), RoundStatus.review_returned)
        self.assertEqual(import_legacy_jobs._parse_round_status("bad"), RoundStatus.draft)

    def test_parse_upload_status_defaults_to_pending(self) -> None:
        self.assertEqual(import_legacy_jobs._parse_upload_status(None), UploadStatus.pending)
        self.assertEqual(import_legacy_jobs._parse_upload_status("processed"), UploadStatus.processed)
        self.assertEqual(import_legacy_jobs._parse_upload_status("bad"), UploadStatus.pending)

    def test_artifact_kind_mapping(self) -> None:
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("a.wav")), ArtifactKind.audio)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("a.transcript.txt")), ArtifactKind.transcript_txt)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("a.review.json".replace("a.", ""))), ArtifactKind.review_json)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("final_report_letter.pdf")), ArtifactKind.report_pdf)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("final_report_letter_correction.docx")), ArtifactKind.report_docx)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("final_traq_page1.pdf")), ArtifactKind.final_pdf)
        self.assertEqual(import_legacy_jobs._artifact_kind_for_suffix(Path("final.geojson")), ArtifactKind.geojson)
        self.assertIsNone(import_legacy_jobs._artifact_kind_for_suffix(Path("ignored.bin")))

    def test_build_job_from_job_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = Path(tmp) / "job_test"
            job_dir.mkdir(parents=True)
            (job_dir / "job_record.json").write_text(
                json.dumps(
                    {
                        "job_id": "job_test",
                        "job_number": "J9999",
                        "status": "ARCHIVED",
                        "latest_round_id": "round_3",
                        "latest_round_status": "REVIEW_RETURNED",
                    }
                ),
                encoding="utf-8",
            )
            job = import_legacy_jobs._build_job(job_dir)
        self.assertIsNotNone(job)
        assert job is not None
        self.assertEqual(job.job_id, "job_test")
        self.assertEqual(job.job_number, "J9999")
        self.assertEqual(job.status, JobStatus.archived)
        self.assertEqual(job.latest_round_id, "round_3")
        self.assertEqual(job.latest_round_status, RoundStatus.review_returned)


if __name__ == "__main__":
    unittest.main()
