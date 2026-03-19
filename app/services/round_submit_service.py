"""Round submit orchestration helpers for review payload assembly."""

from __future__ import annotations

from typing import Any, Callable


class RoundSubmitService:
    """Own submit-time merge rules so routes do not mutate review payloads directly."""

    @staticmethod
    def _prune_empty_patch(value: Any) -> Any:
        """Drop null/blank placeholders so client defaults do not wipe extracted data."""
        if isinstance(value, dict):
            pruned: dict[str, Any] = {}
            for key, child in value.items():
                child_value = RoundSubmitService._prune_empty_patch(child)
                if child_value is None:
                    continue
                pruned[key] = child_value
            return pruned or None
        if isinstance(value, list):
            pruned_items = [
                item
                for item in (RoundSubmitService._prune_empty_patch(child) for child in value)
                if item is not None
            ]
            return pruned_items or None
        if value is None:
            return None
        if isinstance(value, str) and value == "":
            return None
        return value

    def has_client_patch(self, submit_payload: Any | None) -> bool:
        """Return whether the submit request carries form or narrative edits."""
        return bool(submit_payload and (submit_payload.form or submit_payload.narrative))

    @staticmethod
    def load_existing_round_review(persisted_round: dict[str, Any] | None) -> dict[str, Any]:
        """Return persisted round review payload if present."""
        if isinstance((persisted_round or {}).get("review_payload"), dict):
            return dict((persisted_round or {})["review_payload"])
        return {}

    def apply_client_form_patch(
        self,
        draft_form: dict[str, Any],
        form_patch: dict[str, Any],
        *,
        apply_form_patch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Merge one client patch into draft form without erasing extracted values."""
        sanitized_patch = self._prune_empty_patch(form_patch)
        merged_form = dict(draft_form or {})
        if isinstance(sanitized_patch, dict) and sanitized_patch:
            normalized_patch = sanitized_patch
            if isinstance(merged_form.get("data"), dict) and "data" not in normalized_patch:
                normalized_patch = {"data": normalized_patch}
            merged_form = apply_form_patch(merged_form, normalized_patch)
        draft_form_data = dict(merged_form.get("data") or {})
        merged_form["data"] = normalize_form_schema(draft_form_data)
        return merged_form

    def build_base_review_override(
        self,
        *,
        job_id: str,
        round_id: str,
        existing_round_review: dict[str, Any],
        submit_payload: Any | None,
        load_latest_review: Callable[..., dict[str, Any]],
        apply_form_patch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Build the review payload override used as input to round processing."""
        if not self.has_client_patch(submit_payload):
            return dict(existing_round_review) if existing_round_review else None
        base_review = dict(existing_round_review) if existing_round_review else {}
        if not base_review:
            base_review = load_latest_review(job_id, exclude_round_id=round_id)
        draft_form = dict(base_review.get("draft_form") or {})
        if submit_payload and submit_payload.form:
            draft_form = self.apply_client_form_patch(
                draft_form,
                submit_payload.form,
                apply_form_patch=apply_form_patch,
                normalize_form_schema=normalize_form_schema,
            )
        draft_narrative = base_review.get("draft_narrative") or ""
        if submit_payload and submit_payload.narrative:
            narrative_text = submit_payload.narrative.get("text")
            if narrative_text is not None:
                draft_narrative = narrative_text
        base_review_override = dict(base_review)
        base_review_override["draft_form"] = draft_form
        base_review_override["draft_narrative"] = draft_narrative
        if submit_payload and submit_payload.client_revision_id:
            base_review_override["client_revision_id"] = submit_payload.client_revision_id
        return base_review_override

    @staticmethod
    def ensure_round_manifest(
        *,
        job_id: str,
        round_id: str,
        round_record: Any,
        persisted_round: dict[str, Any] | None,
        existing_round_review: dict[str, Any],
        build_reprocess_manifest: Callable[[str, Any, dict[str, Any]], list[dict[str, Any]]],
        logger: Any,
    ) -> None:
        """Populate round manifest from persisted or synthesized sources when needed."""
        if not round_record.manifest:
            persisted_manifest = list((persisted_round or {}).get("manifest") or [])
            if persisted_manifest:
                round_record.manifest = persisted_manifest
                logger.info(
                    "Recovered manifest from disk for %s/%s (%s items)",
                    job_id,
                    round_id,
                    len(persisted_manifest),
                )
        if not round_record.manifest:
            synthesized = build_reprocess_manifest(job_id, round_record, existing_round_review)
            if synthesized:
                round_record.manifest = synthesized
                logger.info(
                    "Synthesized manifest from server recordings for %s/%s (%s items)",
                    job_id,
                    round_id,
                    len(synthesized),
                )

    def apply_post_process_client_patch(
        self,
        *,
        review_payload: dict[str, Any],
        submit_payload: Any,
        tree_number: int | None,
        apply_form_patch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> dict[str, Any]:
        """Apply final client edits onto processed review output non-destructively."""
        updated_review = dict(review_payload)
        draft_form = dict(updated_review.get("draft_form") or {})
        if submit_payload.form:
            draft_form = self.apply_client_form_patch(
                draft_form,
                submit_payload.form,
                apply_form_patch=apply_form_patch,
                normalize_form_schema=normalize_form_schema,
            )
        draft_data = normalize_form_schema(dict(draft_form.get("data") or {}))
        draft_form["data"] = draft_data
        updated_review["draft_form"] = draft_form
        updated_review["form"] = draft_data
        updated_review["tree_number"] = tree_number
        if submit_payload.narrative:
            narrative_text = submit_payload.narrative.get("text")
            if narrative_text is not None:
                updated_review["draft_narrative"] = narrative_text
                updated_review["narrative"] = narrative_text
        return updated_review
