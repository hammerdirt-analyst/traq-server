"""Tests for operator-facing artifact export workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.artifact_storage import create_artifact_store
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.artifact_fetch_service import ArtifactFetchService
from app.services.final_mutation_service import FinalMutationService
from app.services.job_mutation_service import JobMutationService
import app.db as db_module


class ArtifactFetchServiceTests(unittest.TestCase):
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
        self.settings = load_settings()
        self.store = DatabaseStore()
        self.job_service = JobMutationService()
        self.final_service = FinalMutationService()
        self.fetch_service = ArtifactFetchService(
            settings=self.settings,
            db_store=self.store,
            artifact_store=create_artifact_store(self.settings),
        )

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

    def _create_finalized_job(self, *, correction: bool = False) -> str:
        self.job_service.create_job(
            job_id="job_1",
            job_number="J0001",
            status="ARCHIVED",
            job_name="Tree Report",
            job_address="123 Main St",
        )
        payload = {"round_id": "round_1", "transcript": "Final transcript"}
        self.final_service.set_final("J0001", payload=payload)

        job_dir = self.storage_root / "jobs" / "job_1"
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "final_report_letter.pdf").write_bytes(b"final-report")
        (job_dir / "final_traq_page1.pdf").write_bytes(b"final-traq")
        if correction:
            self.final_service.set_correction(
                "J0001",
                payload={"round_id": "round_2", "transcript": "Correction transcript"},
            )
            (job_dir / "final_report_letter_correction.pdf").write_bytes(b"corr-report")
            (job_dir / "final_traq_page1_correction.pdf").write_bytes(b"corr-traq")
        return "job_1"

    def test_fetch_report_pdf_exports_canonical_filename(self) -> None:
        self._create_finalized_job()

        result = self.fetch_service.fetch("J0001", kind="report-pdf")

        self.assertEqual(result["variant"], "final")
        saved_path = Path(result["saved_path"])
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.name, "J0001_report_letter.pdf")
        self.assertEqual(saved_path.read_bytes(), b"final-report")

    def test_fetch_uses_correction_variant_when_present(self) -> None:
        self._create_finalized_job(correction=True)

        result = self.fetch_service.fetch("J0001", kind="traq-pdf")

        self.assertEqual(result["variant"], "correction")
        saved_path = Path(result["saved_path"])
        self.assertEqual(saved_path.name, "J0001_correction_traq_page1.pdf")
        self.assertEqual(saved_path.read_bytes(), b"corr-traq")

    def test_fetch_transcript_exports_text_file(self) -> None:
        self._create_finalized_job(correction=True)

        result = self.fetch_service.fetch("J0001", kind="transcript")

        self.assertEqual(result["variant"], "correction")
        saved_path = Path(result["saved_path"])
        self.assertEqual(saved_path.name, "J0001_correction_transcript.txt")
        self.assertEqual(saved_path.read_text(encoding="utf-8"), "Correction transcript")

    def test_fetch_final_json_exports_payload(self) -> None:
        self._create_finalized_job(correction=True)

        result = self.fetch_service.fetch("J0001", kind="final-json")

        self.assertEqual(result["variant"], "correction")
        saved_path = Path(result["saved_path"])
        self.assertEqual(saved_path.name, "J0001_correction.json")
        exported = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertEqual(exported["transcript"], "Correction transcript")
