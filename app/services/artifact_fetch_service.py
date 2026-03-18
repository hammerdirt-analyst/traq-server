"""Operator-oriented artifact export helpers for the admin CLI."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..artifact_storage import ArtifactStore
from ..config import Settings
from ..db_store import DatabaseStore


class ArtifactFetchService:
    """Resolve and export customer-facing artifacts by job reference."""

    def __init__(
        self,
        *,
        settings: Settings,
        db_store: DatabaseStore,
        artifact_store: ArtifactStore,
        export_root: Path | None = None,
    ) -> None:
        """Bind the service to runtime settings, metadata, and storage backends."""
        self._settings = settings
        self._db_store = db_store
        self._artifact_store = artifact_store
        self._export_root = export_root or (Path.cwd() / "exports")

    def fetch(self, job_ref: str, *, kind: str) -> dict[str, Any]:
        """Export one artifact kind for the provided job reference."""
        normalized_kind = (kind or "").strip().lower()
        if normalized_kind not in {"report-pdf", "traq-pdf", "transcript", "final-json"}:
            raise ValueError(f"Unsupported artifact kind: {kind}")

        job = self._resolve_job(job_ref)
        job_id = str(job["job_id"])
        job_number = str(job["job_number"])
        export_dir = self._export_root / job_number
        export_dir.mkdir(parents=True, exist_ok=True)

        if normalized_kind == "transcript":
            variant, transcript = self._resolve_transcript(job_id)
            filename = f"{job_number}_transcript.txt" if variant == "final" else f"{job_number}_correction_transcript.txt"
            saved_path = export_dir / filename
            saved_path.write_text(transcript, encoding="utf-8")
        elif normalized_kind == "final-json":
            variant, payload = self._resolve_final_payload(job_id)
            filename = f"{job_number}_final.json" if variant == "final" else f"{job_number}_correction.json"
            saved_path = export_dir / filename
            saved_path.write_text(self._to_json(payload), encoding="utf-8")
        else:
            variant, key = self._resolve_binary_artifact(job_id, normalized_kind)
            filename = self._export_filename(job_number, normalized_kind, variant)
            saved_path = export_dir / filename
            source_path = self._artifact_store.materialize_path(key)
            shutil.copy2(source_path, saved_path)

        return {
            "job_number": job_number,
            "job_id": job_id,
            "kind": normalized_kind,
            "variant": variant,
            "saved_path": str(saved_path),
        }

    def _resolve_job(self, job_ref: str) -> dict[str, Any]:
        """Resolve a CLI job reference to the current DB-backed job record."""
        normalized = (job_ref or "").strip()
        if not normalized:
            raise ValueError("Job reference is required")
        if normalized.startswith("job_"):
            row = self._db_store.get_job(normalized)
        else:
            row = self._db_store.get_job_by_number(normalized.upper())
        if row is None:
            raise RuntimeError(f"Job not found: {job_ref}")
        return row

    def _resolve_binary_artifact(self, job_id: str, kind: str) -> tuple[str, str]:
        """Return the preferred binary artifact key for a finalized job."""
        candidate_names = {
            "report-pdf": [
                ("correction", "final_report_letter_correction.pdf"),
                ("final", "final_report_letter.pdf"),
            ],
            "traq-pdf": [
                ("correction", "final_traq_page1_correction.pdf"),
                ("final", "final_traq_page1.pdf"),
            ],
        }[kind]
        for variant, filename in candidate_names:
            key = self._job_artifact_key(job_id, filename)
            if self._artifact_store.exists(key):
                return variant, key
        raise RuntimeError(f"No {kind} artifact found for job {job_id}")

    def _resolve_transcript(self, job_id: str) -> tuple[str, str]:
        """Return the preferred archived transcript text for a finalized job."""
        for variant in ("correction", "final"):
            row = self._db_store.get_job_final(job_id, variant)
            payload = (row or {}).get("payload")
            if isinstance(payload, dict):
                transcript = str(payload.get("transcript") or "").strip()
                if transcript:
                    return variant, transcript
        raise RuntimeError(f"No archived transcript found for job {job_id}")

    def _resolve_final_payload(self, job_id: str) -> tuple[str, dict[str, Any]]:
        """Return the preferred archived final or correction JSON payload."""
        for variant in ("correction", "final"):
            row = self._db_store.get_job_final(job_id, variant)
            payload = (row or {}).get("payload")
            if isinstance(payload, dict):
                return variant, payload
        raise RuntimeError(f"No archived final payload found for job {job_id}")

    @staticmethod
    def _export_filename(job_number: str, kind: str, variant: str) -> str:
        """Return the canonical export filename for one artifact kind."""
        if kind == "report-pdf":
            return (
                f"{job_number}_correction_report_letter.pdf"
                if variant == "correction"
                else f"{job_number}_report_letter.pdf"
            )
        if kind == "traq-pdf":
            return (
                f"{job_number}_correction_traq_page1.pdf"
                if variant == "correction"
                else f"{job_number}_traq_page1.pdf"
            )
        raise ValueError(f"Unsupported export filename kind: {kind}")

    @staticmethod
    def _to_json(payload: dict[str, Any]) -> str:
        """Serialize an exported JSON payload consistently for operators."""
        import json

        return json.dumps(payload, indent=2, sort_keys=True)

    def _job_artifact_key(self, job_id: str, filename: str) -> str:
        """Build the canonical storage key for one job-scoped artifact."""
        return self._artifact_store.resolve_key("jobs", job_id, filename)
