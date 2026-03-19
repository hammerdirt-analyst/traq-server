"""Unit tests for media runtime helper extraction."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.artifact_storage import LocalArtifactStore
from app.services.media_runtime_service import MediaRuntimeService


class _DummyDbStore:
    def __init__(self) -> None:
        self.recording = {
            "upload_status": "uploaded",
            "content_type": "audio/wav",
            "duration_ms": 1234,
            "artifact_path": "jobs/job_1/sections/site_factors/recordings/rec_1.wav",
            "metadata_json": {},
        }
        self.upsert_calls: list[dict] = []
        self.image_rows: list[dict] = []

    def get_round_recording(self, **_kwargs):
        return dict(self.recording)

    def upsert_round_recording(self, **kwargs):
        self.upsert_calls.append(kwargs)
        return kwargs

    def list_round_images(self, job_id: str, round_id: str):
        del job_id, round_id
        return list(self.image_rows)


class MediaRuntimeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.store = LocalArtifactStore(self.root)
        self.db = _DummyDbStore()
        self.service = MediaRuntimeService(
            db_store=self.db,
            artifact_store=self.store,
            logger=logging.getLogger("media-runtime-test"),
        )

    def test_guess_extension_maps_supported_content_types(self) -> None:
        self.assertEqual(self.service.guess_extension("audio/wav", ".bin"), ".wav")
        self.assertEqual(self.service.guess_extension("image/jpeg", ".bin"), ".jpg")
        self.assertEqual(self.service.guess_extension(None, ".bin"), ".bin")

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

        self.assertEqual(images, [{"path": str(report_path), "caption": "Canopy", "uploaded_at": "2026-03-19T10:00:00Z"}])

    def test_save_recording_runtime_state_updates_db_and_writes_transcript(self) -> None:
        self.service.save_recording_runtime_state(
            job_id="job_1",
            round_id="round_1",
            section_id="site_factors",
            recording_id="rec_1",
            meta={"transcript_text": "DB transcript", "processed": True},
            job_artifact_key=lambda job_id, *parts: self.store.resolve_key("jobs", job_id, *parts),
        )

        self.assertEqual(len(self.db.upsert_calls), 1)
        transcript_path = self.root / "jobs/job_1/sections/site_factors/recordings/rec_1.transcript.txt"
        self.assertEqual(transcript_path.read_text(encoding="utf-8"), "DB transcript")

    def test_transcribe_recording_uses_openai_client(self) -> None:
        audio_path = self.root / "input.wav"
        audio_path.write_bytes(b"audio-bytes")
        old_env = {key: os.environ.get(key) for key in ("OPENAI_API_KEY",)}
        os.environ["OPENAI_API_KEY"] = "test-key"
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) if v is not None else os.environ.pop(k, None) for k, v in old_env.items()])

        class _Response:
            text = "Transcript text"

        class _Transcriptions:
            @staticmethod
            def create(**_kwargs):
                return _Response()

        class _Audio:
            transcriptions = _Transcriptions()

        class _Client:
            def __init__(self, *args, **kwargs):
                self.audio = _Audio()

        with patch("app.services.media_runtime_service.OpenAI", _Client):
            transcript = self.service.transcribe_recording(
                audio_path,
                probe={"codec_name": "pcm_s16le", "sample_rate": "16000", "channels": "1"},
                log_event=lambda *args, **kwargs: None,
            )

        self.assertEqual(transcript, "Transcript text")


if __name__ == "__main__":
    unittest.main()
