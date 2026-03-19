"""Inspection helpers for the current operational server lifecycle.

This service exposes read-only inspection methods for the same workflow surfaces
the client relies on: jobs, rounds, review payloads, and final/correction
outputs.

Runtime state is DB-backed. Local storage is inspected only for artifact files
and exported debug copies under the configured storage root.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import Settings
from ..db_store import DatabaseStore


class InspectionService:
    """Read-only inspection service for CLI/operator workflows."""

    def __init__(self, *, settings: Settings, db_store: DatabaseStore) -> None:
        """Bind storage-root and DB dependencies for inspection commands."""
        self._settings = settings
        self._db_store = db_store

    def resolve_job_id(self, job_ref: str) -> str:
        """Resolve a server job reference to its authoritative ``job_id``."""
        normalized = job_ref.strip()
        if normalized.startswith("job_"):
            return normalized
        row = self._db_store.get_job_by_number(normalized)
        if row is not None:
            return str(row.get("job_id"))
        raise RuntimeError(f"Job not found for reference: {job_ref}")

    def inspect_job(self, job_ref: str) -> dict[str, Any]:
        """Return hybrid operational state for one job."""
        job_id = self.resolve_job_id(job_ref)
        job = self._db_store.get_job(job_id)
        if job is None:
            raise RuntimeError(f"Job not found: {job_ref}")
        assignment = self._db_store.get_job_assignment(job_id)
        job_dir = self._job_dir(job_id)
        rounds_dir = job_dir / "rounds"
        round_ids = sorted(
            child.name for child in rounds_dir.iterdir() if child.is_dir()
        ) if rounds_dir.exists() else []
        return {
            "job_id": job_id,
            "job_number": job.get("job_number"),
            "status": job.get("status"),
            "customer_id": job.get("customer_id"),
            "customer_code": job.get("customer_code"),
            "customer_name": job.get("customer_name"),
            "billing_profile_id": job.get("billing_profile_id"),
            "billing_code": job.get("billing_code"),
            "billing_name": job.get("billing_name"),
            "tree_number": job.get("tree_number"),
            "latest_round_id": job.get("latest_round_id"),
            "latest_round_status": job.get("latest_round_status"),
            "assignment": assignment,
            "job_record_path": str(job_dir / "job_record.json"),
            "round_ids": round_ids,
            "has_final": (job_dir / "final.json").exists(),
            "has_correction": (job_dir / "final_correction.json").exists(),
            "details": job,
        }

    def inspect_round(self, job_ref: str, round_id: str) -> dict[str, Any]:
        """Return current manifest/review state for one round."""
        job = self.inspect_job(job_ref)
        round_dir = self._job_dir(job["job_id"]) / "rounds" / round_id
        if not round_dir.exists():
            raise RuntimeError(f"Round not found: {round_id}")
        manifest = self._read_json(round_dir / "manifest.json")
        review = self._read_json(round_dir / "review.json")
        return {
            "job_id": job["job_id"],
            "job_number": job["job_number"],
            "round_id": round_id,
            "round_dir": str(round_dir),
            "manifest_count": len(manifest) if isinstance(manifest, list) else 0,
            "has_manifest": isinstance(manifest, list),
            "has_review": isinstance(review, dict),
            "server_revision_id": review.get("server_revision_id") if isinstance(review, dict) else None,
            "transcription_failure_count": len(review.get("transcription_failures") or []) if isinstance(review, dict) else 0,
        }

    def inspect_review(self, job_ref: str, round_id: str) -> dict[str, Any]:
        """Return summary + payload for one round review."""
        job_id = self.resolve_job_id(job_ref)
        review_path = self._job_dir(job_id) / "rounds" / round_id / "review.json"
        review = self._read_json(review_path)
        if not isinstance(review, dict):
            raise RuntimeError(f"Review not found for round: {round_id}")
        draft_form = review.get("draft_form") or {}
        form_data = draft_form.get("data") if isinstance(draft_form, dict) else None
        return {
            "job_id": job_id,
            "round_id": round_id,
            "review_path": str(review_path),
            "server_revision_id": review.get("server_revision_id"),
            "tree_number": review.get("tree_number"),
            "transcript_length": len(str(review.get("transcript") or "")),
            "section_count": len(review.get("section_transcripts") or {}),
            "image_count": len(review.get("images") or []),
            "has_form": isinstance(form_data, dict),
            "payload": review,
        }

    def inspect_final(self, job_ref: str) -> dict[str, Any]:
        """Return final/correction output presence and payload summary."""
        job_id = self.resolve_job_id(job_ref)
        job_dir = self._job_dir(job_id)
        final_payload = self._read_json(job_dir / "final.json")
        correction_payload = self._read_json(job_dir / "final_correction.json")
        return {
            "job_id": job_id,
            "final": self._final_summary(job_dir, "final", final_payload),
            "correction": self._final_summary(job_dir, "final_correction", correction_payload),
        }

    def _final_summary(
        self,
        job_dir: Path,
        prefix: str,
        payload: Any,
    ) -> dict[str, Any]:
        """Summarize one final or correction artifact set for CLI display."""
        is_correction = prefix == "final_correction"
        report_pdf = "final_report_letter_correction.pdf" if is_correction else "final_report_letter.pdf"
        report_docx = "final_report_letter_correction.docx" if is_correction else "final_report_letter.docx"
        traq_pdf = "final_traq_page1_correction.pdf" if is_correction else "final_traq_page1.pdf"
        geojson = "final_correction.geojson" if is_correction else "final.geojson"
        return {
            "exists": isinstance(payload, dict),
            "json_path": str(job_dir / f"{prefix}.json"),
            "report_pdf_exists": (job_dir / report_pdf).exists(),
            "report_docx_exists": (job_dir / report_docx).exists(),
            "traq_pdf_exists": (job_dir / traq_pdf).exists(),
            "geojson_exists": (job_dir / geojson).exists(),
            "round_id": payload.get("round_id") if isinstance(payload, dict) else None,
            "user_name": payload.get("user_name") if isinstance(payload, dict) else None,
            "transcript_length": len(str(payload.get("transcript") or "")) if isinstance(payload, dict) else 0,
            "image_count": len(payload.get("report_images") or []) if isinstance(payload, dict) else 0,
        }

    def _job_dir(self, job_id: str) -> Path:
        """Return the on-disk job directory for one authoritative job id."""
        return self._settings.storage_root / "jobs" / job_id

    @staticmethod
    def _read_json(path: Path) -> Any:
        """Load JSON from disk and return ``None`` for missing or invalid files."""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
