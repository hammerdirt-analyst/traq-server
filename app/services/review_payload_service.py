"""Helpers for normalizing and hydrating review payloads."""
from __future__ import annotations

from typing import Any, Callable


class ReviewPayloadService:
    """Normalize review payloads and hydrate image metadata from DB state."""

    def build_round_images(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert stored round-image rows into API review-payload image entries."""
        images: list[dict[str, Any]] = []
        for row in rows:
            metadata = dict(row.get("metadata_json") or {})
            gps: dict[str, str] = {}
            latitude = str(row.get("latitude") or metadata.get("latitude") or "").strip()
            longitude = str(row.get("longitude") or metadata.get("longitude") or "").strip()
            if latitude:
                gps["latitude"] = latitude
            if longitude:
                gps["longitude"] = longitude
            image_id = str(row.get("image_id") or metadata.get("image_id") or "").strip()
            section_id = str(row.get("section_id") or metadata.get("section_id") or "").strip()
            if not image_id:
                continue
            image_payload: dict[str, Any] = {
                "id": image_id,
                "image_id": image_id,
                "section_id": section_id,
                "upload_status": str(row.get("upload_status") or metadata.get("upload_status") or "uploaded"),
                "caption": str(row.get("caption") or metadata.get("caption") or "").strip(),
                "stored_path": str(row.get("artifact_path") or metadata.get("stored_path") or "").strip(),
                "report_image_path": str(metadata.get("report_image_path") or "").strip(),
                "uploaded_at": str(metadata.get("uploaded_at") or "").strip(),
            }
            if gps:
                image_payload["gps"] = gps
            images.append(image_payload)
        images.sort(key=lambda item: (item.get("section_id") or "", item.get("id") or ""))
        return images

    def normalize_payload(
        self,
        payload: dict[str, Any],
        *,
        tree_number: int | None,
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
        hydrated_images: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Fill derived review fields and prefer DB-backed image metadata when present."""
        normalized = dict(payload)
        if "form" not in normalized:
            draft_form = normalized.get("draft_form") or {}
            if isinstance(draft_form, dict):
                normalized["form"] = draft_form.get("data", {})
        if isinstance(normalized.get("draft_form"), dict):
            draft_form = dict(normalized.get("draft_form") or {})
            draft_data = normalize_form_schema(dict(draft_form.get("data") or {}))
            draft_data = dict(draft_data)
            client_tree_details = dict(draft_data.get("client_tree_details") or {})
            if tree_number is not None:
                client_tree_details["tree_number"] = str(tree_number)
                draft_data["client_tree_details"] = client_tree_details
            draft_form["data"] = draft_data
            normalized["draft_form"] = draft_form
            normalized["form"] = draft_data
        elif isinstance(normalized.get("form"), dict):
            form_data = normalize_form_schema(dict(normalized.get("form") or {}))
            form_data = dict(form_data)
            client_tree_details = dict(form_data.get("client_tree_details") or {})
            if tree_number is not None:
                client_tree_details["tree_number"] = str(tree_number)
                form_data["client_tree_details"] = client_tree_details
            normalized["form"] = form_data
        if "narrative" not in normalized:
            normalized["narrative"] = normalized.get("draft_narrative") or ""
        normalized["tree_number"] = tree_number
        if hydrated_images:
            normalized["images"] = hydrated_images
        else:
            normalized.setdefault("images", [])
        return normalized

    def build_default_payload(
        self,
        *,
        round_id: str,
        server_revision_id: str,
        tree_number: int | None,
        images: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Build the fallback review payload used before round processing runs."""
        return {
            "round_id": round_id,
            "server_revision_id": server_revision_id,
            "transcript": "Transcript ready.",
            "section_recordings": {},
            "section_transcripts": {},
            "draft_form": {"schema_name": "demo", "schema_version": "0.0", "data": {}},
            "draft_narrative": "Demo narrative.",
            "form": {},
            "narrative": "Demo narrative.",
            "tree_number": tree_number,
            "images": list(images or []),
        }
