"""Round reprocess route extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException


def build_round_reprocess_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_round_record: Callable[[str, str], tuple[Any, Any]],
    db_store: Any,
    build_reprocess_manifest: Callable[[str, Any, dict[str, Any]], list[dict[str, Any]]],
    save_job_record: Callable[[Any], None],
    load_latest_review: Callable[[str], dict[str, Any]],
    process_round: Callable[..., dict[str, Any]],
    logger: Any,
) -> APIRouter:
    """Build the round reprocess route."""

    router = APIRouter()

    @router.post("/v1/jobs/{job_id}/rounds/{round_id}/reprocess")
    def reprocess_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Force re-transcribe/re-extract all server-stored round recordings."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record, round_record = ensure_round_record(job_id, round_id)
        persisted_round = db_store.get_job_round(job_id, round_id)
        round_review = (persisted_round or {}).get("review_payload")
        if not isinstance(round_review, dict):
            raise HTTPException(status_code=404, detail="Review not found for round")
        manifest = build_reprocess_manifest(job_id, round_record, round_review)
        if not manifest:
            raise HTTPException(status_code=400, detail="No server recordings available to reprocess")

        logger.info(
            "POST /v1/jobs/%s/rounds/%s/reprocess (%s recordings)",
            job_id,
            round_id,
            len(manifest),
        )
        round_record.status = "SUBMITTED_FOR_PROCESSING"
        record.latest_round_status = round_record.status
        record.status = "SUBMITTED_FOR_PROCESSING"
        save_job_record(record)
        round_record.server_revision_id = round_record.server_revision_id or f"rev_{round_id}"
        base_review_override = load_latest_review(job_id, exclude_round_id=round_id)
        review_payload: dict[str, Any] = {}
        try:
            review_payload = process_round(
                job_id,
                round_id,
                record,
                base_review_override=base_review_override,
                manifest_override=manifest,
                force_reprocess=True,
                force_transcribe=True,
            )
            round_record.status = "REVIEW_RETURNED"
            record.latest_round_status = round_record.status
            record.status = "REVIEW_RETURNED"
            save_job_record(record)
        except Exception:
            logger.exception("Round reprocess failed for %s/%s", job_id, round_id)
            round_record.status = "FAILED"
            record.latest_round_status = "FAILED"
            record.status = "FAILED"
            save_job_record(record)
            raise HTTPException(status_code=500, detail="Round reprocess failed")

        return {
            "ok": True,
            "round_id": round_id,
            "status": round_record.status,
            "tree_number": record.tree_number,
            "manifest_count": len(manifest),
            "transcription_failures": review_payload.get("transcription_failures") or [],
        }

    return router
