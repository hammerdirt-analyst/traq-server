"""Helpers for preparing finalization payloads and artifact names."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FinalArtifactNames:
    """Canonical artifact filenames for one finalization mode."""

    pdf_name: str
    report_name: str
    report_docx_name: str
    final_json_name: str
    geojson_name: str


class FinalizationService:
    """Prepare finalization inputs while keeping route handlers thin."""

    @staticmethod
    def artifact_names(correction_mode: bool) -> FinalArtifactNames:
        """Return artifact filenames for final vs correction output."""
        suffix = "_correction" if correction_mode else ""
        return FinalArtifactNames(
            pdf_name=f"final_traq_page1{suffix}.pdf",
            report_name=f"final_report_letter{suffix}.pdf",
            report_docx_name=f"final_report_letter{suffix}.docx",
            final_json_name=f"final{suffix}.json",
            geojson_name=f"final{suffix}.geojson",
        )

    @staticmethod
    def ensure_risk_defaults(
        form: dict[str, Any],
        *,
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Normalize final form data and clamp long notes before PDF generation."""
        normalized_form = dict(form)
        data = normalize_form_schema(dict(normalized_form.get("data") or {}))
        rows = list(data.get("risk_categorization") or [])
        data["risk_categorization"] = rows
        notes_section = data.get("notes_explanations_descriptions")
        if isinstance(notes_section, dict):
            notes_val = notes_section.get("notes")
            if isinstance(notes_val, str):
                notes_clean = " ".join(notes_val.split())
                if len(notes_clean) > 230:
                    trimmed = notes_clean[:230].rstrip()
                    if " " in trimmed:
                        trimmed = trimmed.rsplit(" ", 1)[0]
                    notes_section["notes"] = trimmed
        normalized_form["data"] = data
        return normalized_form

    @staticmethod
    def transcript_from_review_payload(review_payload: dict[str, Any] | None) -> str:
        """Extract transcript text from a persisted review payload."""
        if not isinstance(review_payload, dict):
            return ""
        transcript = review_payload.get("transcript", "") or ""
        return str(transcript)

    @staticmethod
    def resolve_profile_payload(
        explicit_profile_payload: dict[str, Any] | None,
        *,
        fallback_loader: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Prefer explicit profile data and fall back to stored runtime profile."""
        if explicit_profile_payload:
            return explicit_profile_payload
        try:
            return fallback_loader()
        except Exception:
            return None

    @staticmethod
    def build_job_info(record: Any) -> dict[str, Any]:
        """Build the report-letter job context from the runtime job record."""
        return {
            "job_address": record.job_address,
            "address": record.address,
            "billing_name": record.billing_name,
            "billing_address": record.billing_address,
            "billing_contact_name": record.billing_contact_name,
        }

    @staticmethod
    def build_final_payload(
        *,
        job_id: str,
        round_id: str,
        server_revision_id: str,
        client_revision_id: str,
        archived_at: str,
        transcript: str,
        form: dict[str, Any],
        narrative: Any,
        user_name: str | None,
        profile: dict[str, Any] | None,
        report_images: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the archived final/correction payload written to storage and DB."""
        return {
            "job_id": job_id,
            "round_id": round_id,
            "server_revision_id": server_revision_id,
            "client_revision_id": client_revision_id,
            "archived_at": archived_at,
            "transcript": transcript,
            "form": form,
            "narrative": narrative,
            "user_name": user_name,
            "profile": dict(profile or {}) if isinstance(profile, dict) else None,
            "report_images": report_images,
        }
