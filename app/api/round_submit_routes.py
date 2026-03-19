"""Round submit route extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body, Header, HTTPException

from .models import SubmitRoundRequest


def build_round_submit_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_round_record: Callable[[str, str], tuple[Any, Any]],
    assert_round_editable: Callable[[Any, str, Any], None],
    save_job_record: Callable[[Any], None],
    save_round_record: Callable[[str, Any], None],
    requested_tree_number_from_form: Callable[[dict[str, Any]], int | None],
    resolve_server_tree_number: Callable[..., int | None],
    apply_tree_number_to_form: Callable[[dict[str, Any], int | None], dict[str, Any]],
    db_store: Any,
    build_reprocess_manifest: Callable[[str, Any, dict[str, Any]], list[dict[str, Any]]],
    load_latest_review: Callable[[str], dict[str, Any]],
    apply_form_patch: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    process_round: Callable[[str, str, Any, dict[str, Any] | None], dict[str, Any]],
    logger: Any,
) -> APIRouter:
    """Build the round submit route."""

    router = APIRouter()

    @router.post("/v1/jobs/{job_id}/rounds/{round_id}/submit")
    def submit_round(
        job_id: str,
        round_id: str,
        submit_payload: SubmitRoundRequest | None = Body(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Submit a round for processing and return review-ready status."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record, round_record = ensure_round_record(job_id, round_id)
        required_fields = {
            "job_name": record.job_name,
            "job_address": record.job_address,
            "job_phone": record.job_phone,
            "contact_preference": record.contact_preference,
            "billing_name": record.billing_name,
            "billing_address": record.billing_address,
        }
        missing = [
            field
            for field, value in required_fields.items()
            if value is None or str(value).strip() == ""
        ]
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"error": "Missing required job metadata.", "fields": missing},
            )
        if submit_payload and submit_payload.form:
            requested_tree_number = requested_tree_number_from_form(submit_payload.form)
            resolved_tree_number = resolve_server_tree_number(
                record,
                requested_tree_number=requested_tree_number,
            )
            submit_payload.form = apply_tree_number_to_form(
                submit_payload.form,
                resolved_tree_number,
            )
        assert_round_editable(record, round_id, auth, allow_correction=True)
        round_record.status = "SUBMITTED_FOR_PROCESSING"
        record.latest_round_status = round_record.status
        record.status = "SUBMITTED_FOR_PROCESSING"
        save_job_record(record)
        save_round_record(job_id, round_record)
        logger.info("POST /v1/jobs/%s/rounds/%s/submit", job_id, round_id)
        round_record.server_revision_id = round_record.server_revision_id or f"rev_{round_id}"
        existing_round_review: dict[str, Any] = {}
        persisted_round = db_store.get_job_round(job_id, round_id)
        if isinstance((persisted_round or {}).get("review_payload"), dict):
            existing_round_review = dict(persisted_round["review_payload"])

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

        has_manifest_items = bool(round_record.manifest)
        has_client_patch = bool(
            submit_payload and (submit_payload.form or submit_payload.narrative)
        )

        if not has_manifest_items and not has_client_patch and existing_round_review:
            logger.info(
                "POST /v1/jobs/%s/rounds/%s/submit noop (no manifest items, no edits)",
                job_id,
                round_id,
            )
            round_record.status = "REVIEW_RETURNED"
            record.latest_round_status = round_record.status
            record.status = "REVIEW_RETURNED"
            save_job_record(record)
            save_round_record(job_id, round_record, review_payload=existing_round_review)
            logger.info(
                "[SUBMIT] job=%s round=%s accepted=true status=%s processed=0 failed=0",
                job_id,
                round_id,
                round_record.status,
            )
            return {
                "ok": True,
                "accepted": True,
                "round_id": round_id,
                "status": round_record.status,
                "tree_number": record.tree_number,
                "lock_editing": False,
                "message": "No new artifacts or edits; existing review retained.",
                "processed_count": 0,
                "failed_count": 0,
                "failed_artifacts": [],
                "can_resubmit_failed": False,
            }

        base_review_override = dict(existing_round_review) if existing_round_review else None
        if has_client_patch:
            base_review = dict(existing_round_review) if existing_round_review else {}
            if not base_review:
                base_review = load_latest_review(job_id, exclude_round_id=round_id)
            draft_form = base_review.get("draft_form") or {}
            if submit_payload and submit_payload.form:
                form_patch = submit_payload.form
                if isinstance(draft_form.get("data"), dict) and "data" not in form_patch:
                    form_patch = {"data": form_patch}
                draft_form = apply_form_patch(draft_form, form_patch)
            draft_form_data = dict(draft_form.get("data") or {})
            draft_form["data"] = normalize_form_schema(draft_form_data)
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

        review_payload: dict[str, Any] = {}
        try:
            review_payload = process_round(job_id, round_id, record, base_review_override)
            if has_client_patch and submit_payload:
                updated_review = dict(review_payload)
                draft_form = dict(updated_review.get("draft_form") or {})
                if submit_payload.form:
                    form_patch = submit_payload.form
                    if isinstance(draft_form.get("data"), dict) and "data" not in form_patch:
                        form_patch = {"data": form_patch}
                    draft_form = apply_form_patch(draft_form, form_patch)
                draft_data = normalize_form_schema(dict(draft_form.get("data") or {}))
                draft_form["data"] = draft_data
                updated_review["draft_form"] = draft_form
                updated_review["form"] = draft_data
                updated_review["tree_number"] = record.tree_number
                if submit_payload.narrative:
                    narrative_text = submit_payload.narrative.get("text")
                    if narrative_text is not None:
                        updated_review["draft_narrative"] = narrative_text
                        updated_review["narrative"] = narrative_text
                save_round_record(job_id, round_record, review_payload=updated_review)
                review_payload = updated_review
            round_record.status = "REVIEW_RETURNED"
            record.latest_round_status = round_record.status
            record.status = "REVIEW_RETURNED"
            save_job_record(record)
            save_round_record(job_id, round_record, review_payload=review_payload)
        except Exception as exc:
            logger.exception("Round processing failed for %s/%s", job_id, round_id)
            round_record.status = "FAILED"
            record.latest_round_status = "FAILED"
            record.status = "FAILED"
            save_job_record(record)
            save_round_record(job_id, round_record)
            logger.info(
                "[SUBMIT] job=%s round=%s accepted=false status=%s error=PROCESSING_FAILED detail=%s",
                job_id,
                round_id,
                round_record.status,
                str(exc),
            )
            return {
                "ok": False,
                "accepted": False,
                "round_id": round_id,
                "status": round_record.status,
                "lock_editing": False,
                "message": "Round processing failed.",
                "error_code": "PROCESSING_FAILED",
                "error_detail": str(exc),
                "processed_count": 0,
                "failed_count": 0,
                "failed_artifacts": [],
                "can_resubmit_failed": True,
            }

        failures = review_payload.get("transcription_failures") or []
        manifest_items = list(round_record.manifest or [])
        total_recordings = sum(1 for item in manifest_items if item.get("kind") == "recording")
        failed_artifacts = [
            {
                "section_id": failure.get("section_id"),
                "artifact_id": failure.get("recording_id"),
                "reason": failure.get("error"),
            }
            for failure in failures
        ]
        failed_count = len(failed_artifacts)
        processed_count = max(total_recordings - failed_count, 0)
        logger.info(
            "[SUBMIT] job=%s round=%s accepted=true status=%s processed=%s failed=%s can_resubmit_failed=%s",
            job_id,
            round_id,
            round_record.status,
            processed_count,
            failed_count,
            failed_count > 0,
        )
        return {
            "ok": True,
            "accepted": True,
            "round_id": round_id,
            "status": round_record.status,
            "tree_number": record.tree_number,
            "lock_editing": False,
            "message": (
                "Round processed with transcription failures."
                if failed_count
                else "Round processed successfully."
            ),
            "transcription_failures": failures,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "failed_artifacts": failed_artifacts,
            "can_resubmit_failed": failed_count > 0,
        }

    return router
