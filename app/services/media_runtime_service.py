"""Media runtime helpers extracted from the HTTP entrypoint."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Callable

from openai import OpenAI

from ..artifact_storage import ArtifactStore
from ..db_store import DatabaseStore


class MediaRuntimeService:
    """Handle media-specific runtime helpers for recordings and images."""

    def __init__(
        self,
        *,
        db_store: DatabaseStore,
        artifact_store: ArtifactStore,
        logger: logging.Logger,
    ) -> None:
        self._db_store = db_store
        self._artifact_store = artifact_store
        self._logger = logger

    @staticmethod
    def guess_extension(content_type: str | None, default: str) -> str:
        """Infer file extension from content type."""
        if not content_type:
            return default
        ct = content_type.lower()
        if ct in {"audio/mp4", "audio/m4a"}:
            return ".m4a"
        if ct in {"audio/wav", "audio/x-wav"}:
            return ".wav"
        if ct in {"image/jpeg", "image/jpg"}:
            return ".jpg"
        if ct == "image/png":
            return ".png"
        return default

    @staticmethod
    def probe_audio_metadata(file_path: Path) -> dict[str, Any]:
        """Best-effort audio probe metadata for debugging cross-device issues."""
        probe: dict[str, Any] = {
            "file_bytes": file_path.stat().st_size,
            "ext": file_path.suffix.lower(),
        }
        try:
            ffprobe_bin = os.environ.get("TRAQ_FFPROBE_BIN", "ffprobe")
            cmd = [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                (
                    "stream=codec_name,sample_rate,channels,bit_rate"
                    ":format=format_name,duration,bit_rate"
                ),
                "-of",
                "json",
                str(file_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            if result.returncode != 0:
                probe["ffprobe_error"] = (result.stderr or "").strip()[:240]
                return probe
            payload = json.loads(result.stdout or "{}")
            streams = payload.get("streams") or []
            fmt = payload.get("format") or {}
            if streams and isinstance(streams[0], dict):
                stream0 = streams[0]
                probe["codec_name"] = stream0.get("codec_name")
                probe["sample_rate"] = stream0.get("sample_rate")
                probe["channels"] = stream0.get("channels")
                probe["stream_bit_rate"] = stream0.get("bit_rate")
            probe["format_name"] = fmt.get("format_name")
            probe["duration"] = fmt.get("duration")
            probe["format_bit_rate"] = fmt.get("bit_rate")
            probe["ffprobe_bin"] = ffprobe_bin
        except FileNotFoundError:
            probe["ffprobe_error"] = "ffprobe_not_found"
        except Exception as exc:
            probe["ffprobe_error"] = str(exc)[:240]
        return probe

    @staticmethod
    def is_canonical_transcribe_audio(
        file_path: Path,
        probe: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether audio already matches canonical transcribe format."""
        if file_path.suffix.lower() != ".wav":
            return False
        if not isinstance(probe, dict):
            return False
        codec = str(probe.get("codec_name") or "").lower()
        sample_rate = str(probe.get("sample_rate") or "").strip()
        channels = str(probe.get("channels") or "").strip()
        return codec == "pcm_s16le" and sample_rate == "16000" and channels == "1"

    def normalize_audio_for_transcription(self, file_path: Path) -> tuple[Path, bool]:
        """Normalize audio to 16kHz mono PCM WAV for consistent transcription input."""
        ffmpeg_bin = os.environ.get("TRAQ_FFMPEG_BIN", "ffmpeg")
        normalized_path = file_path.with_suffix(".norm16k.wav")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(file_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(normalized_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if result.returncode != 0 or not normalized_path.exists():
                self._logger.warning(
                    "Audio normalize failed file=%s error=%s",
                    file_path,
                    (result.stderr or "").strip()[:240],
                )
                return file_path, False
            return normalized_path, True
        except FileNotFoundError:
            self._logger.warning("Audio normalize skipped: ffmpeg not found (%s)", ffmpeg_bin)
            return file_path, False
        except Exception as exc:
            self._logger.warning("Audio normalize failed file=%s error=%s", file_path, str(exc)[:240])
            return file_path, False

    @staticmethod
    def build_report_image_variant(source_path: Path, report_path: Path) -> tuple[Path, int]:
        """Build compressed report-image variant for PDF embedding."""
        try:
            from PIL import Image, ImageOps  # type: ignore

            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                image.save(
                    report_path,
                    format="JPEG",
                    quality=72,
                    optimize=True,
                    progressive=False,
                )
        except Exception:
            shutil.copyfile(source_path, report_path)
        return report_path, report_path.stat().st_size

    def load_job_report_images(
        self,
        *,
        job_id: str,
        round_id: str,
    ) -> list[dict[str, str]]:
        """Load report-image metadata for a job from DB-backed image state."""
        images: list[dict[str, str]] = []
        for row in self._db_store.list_round_images(job_id, round_id=round_id):
            meta = dict(row.get("metadata_json") or {})
            report_path = str(meta.get("report_image_path") or "").strip()
            stored_path = str(meta.get("stored_path") or row.get("artifact_path") or "").strip()
            candidate_key = report_path or stored_path
            if not candidate_key:
                continue
            candidate = self._artifact_store.materialize_path(candidate_key)
            if not candidate.exists():
                continue
            caption = str(
                row.get("caption")
                or meta.get("caption")
                or meta.get("caption_text")
                or ""
            ).strip()
            uploaded_at = str(meta.get("uploaded_at") or "").strip()
            images.append(
                {
                    "path": str(candidate),
                    "caption": caption,
                    "uploaded_at": uploaded_at,
                }
            )
        images.sort(key=lambda item: item.get("uploaded_at", ""))
        return images[:5]

    def transcribe_recording(
        self,
        file_path: Path,
        *,
        probe: dict[str, Any] | None = None,
        log_event: Callable[[str, str, Any], None] | Callable[..., None],
    ) -> str:
        """Transcribe one audio recording with optional normalization."""
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get("TRAQ_OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        language = os.environ.get("TRAQ_OPENAI_TRANSCRIBE_LANGUAGE", "en")
        prompt = os.environ.get(
            "TRAQ_OPENAI_TRANSCRIBE_PROMPT",
            (
                "Arborist TRAQ field recording. Keep exact wording and numbers. "
                "Common terms: target one/two, mobile home unit, one times height, "
                "occupancy constant/frequent, dripline, not practical to move, "
                "restriction practical/not practical, rerouting with cones."
            ),
        )
        if file_path.stat().st_size > 25 * 1024 * 1024:
            raise RuntimeError(f"Recording exceeds 25MB limit: {file_path}")
        if self.is_canonical_transcribe_audio(file_path, probe):
            transcribe_path, normalized = file_path, False
            self._logger.info("Transcribe normalize skipped: canonical wav16k mono pcm input")
        else:
            transcribe_path, normalized = self.normalize_audio_for_transcription(file_path)
        log_event("TRANSCRIBE", "input file=%s normalized=%s", transcribe_path.name, normalized)
        timeout_seconds = float(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_TIMEOUT", "90"))
        max_attempts = max(1, int(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_ATTEMPTS", "3")))
        backoff_seconds = float(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_BACKOFF", "1.5"))
        client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with transcribe_path.open("rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model=model,
                        file=audio_file,
                        language=language,
                        prompt=prompt,
                    )
                return response.text if hasattr(response, "text") else str(response)
            except Exception as exc:
                last_exc = exc
                self._logger.warning(
                    "[TRANSCRIBE] attempt %s/%s failed file=%s error=%s",
                    attempt,
                    max_attempts,
                    file_path.name,
                    exc,
                )
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
        raise RuntimeError(
            f"Transcription failed after {max_attempts} attempts for {file_path.name}"
        ) from last_exc

    def save_recording_runtime_state(
        self,
        *,
        job_id: str,
        round_id: str,
        section_id: str,
        recording_id: str,
        meta: dict[str, Any],
        job_artifact_key: Callable[..., str],
    ) -> None:
        """Persist DB-authoritative recording runtime state and transcript artifact."""
        existing = self._db_store.get_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
        )
        if not isinstance(existing, dict):
            return
        self._db_store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
            upload_status=str(existing.get("upload_status") or "uploaded"),
            content_type=existing.get("content_type"),
            duration_ms=existing.get("duration_ms"),
            artifact_path=existing.get("artifact_path"),
            metadata_json=meta,
        )
        transcript_text = str(meta.get("transcript_text") or "").strip()
        if transcript_text:
            self._artifact_store.write_text(
                job_artifact_key(
                    job_id,
                    "sections",
                    section_id,
                    "recordings",
                    f"{recording_id}.transcript.txt",
                ),
                transcript_text,
            )
