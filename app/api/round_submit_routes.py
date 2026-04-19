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
    round_submit_service: Any,
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
        if submit_payload and submit_payload.client_revision_id:
            round_record.client_revision_id = submit_payload.client_revision_id
        persisted_round = db_store.get_job_round(job_id, round_id)
        existing_round_review = round_submit_service.load_existing_round_review(persisted_round)
        round_submit_service.ensure_round_manifest(
            job_id=job_id,
            round_id=round_id,
            round_record=round_record,
            persisted_round=persisted_round,
            existing_round_review=existing_round_review,
            build_reprocess_manifest=build_reprocess_manifest,
            logger=logger,
        )

        has_manifest_items = bool(round_record.manifest)
        has_client_patch = round_submit_service.has_client_patch(submit_payload)

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

        base_review_override = round_submit_service.build_base_review_override(
            job_id=job_id,
            round_id=round_id,
            existing_round_review=existing_round_review,
            submit_payload=submit_payload,
            load_latest_review=load_latest_review,
            apply_form_patch=apply_form_patch,
            normalize_form_schema=normalize_form_schema,
        )

        review_payload: dict[str, Any] = {}
        try:
            review_payload = process_round(job_id, round_id, record, base_review_override)
            if has_client_patch and submit_payload:
                updated_review = round_submit_service.apply_post_process_client_patch(
                    review_payload=review_payload,
                    submit_payload=submit_payload,
                    tree_number=record.tree_number,
                    apply_form_patch=apply_form_patch,
                    normalize_form_schema=normalize_form_schema,
                )
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
