"""Read-only job status/review routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException

from .models import AssignedJob, RoundArtifactStatus, RoundReconciliationResponse, StatusResponse


def build_job_read_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_job_record: Callable[[str], Any],
    list_job_assignments: Callable[[], list[dict[str, Any]]],
    resolve_assigned_job: Callable[[str], AssignedJob | None],
    save_job_record: Callable[[Any], None],
    save_round_record: Callable[[str, Any], None],
    review_payload_service: Any,
    normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    db_store: Any,
    logger: Any,
) -> APIRouter:
    """Build read-only job assignment, status, and review routes."""

    router = APIRouter()

    @router.get("/v1/jobs/assigned", response_model=list[AssignedJob])
    def list_assigned_jobs(
        x_api_key: str | None = Header(default=None),
    ) -> list[AssignedJob]:
        """List jobs assigned to the caller (or all for admin)."""
        auth = require_api_key(x_api_key)
        logger.info("GET /v1/jobs/assigned")
        assignments = list_job_assignments()
        if auth.is_admin:
            allowed_job_ids = [str(row.get("job_id")) for row in assignments]
        else:
            if not auth.device_id:
                return []
            allowed_job_ids = [
                str(row.get("job_id"))
                for row in assignments
                if str(row.get("device_id") or "") == auth.device_id
            ]
        out: list[AssignedJob] = []
        seen: set[str] = set()
        for job_id in allowed_job_ids:
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)
            resolved = resolve_assigned_job(job_id)
            if resolved is not None:
                out.append(resolved)
        return out

    @router.get("/v1/jobs/{job_id}", response_model=StatusResponse)
    def get_job(job_id: str, x_api_key: str | None = Header(default=None)) -> StatusResponse:
        """Return current job status and latest round revision info."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")
        logger.info("GET /v1/jobs/%s", job_id)
        review_ready = record.latest_round_status == "REVIEW_RETURNED"
        server_revision_id = None
        if record.latest_round_id:
            round_record = record.rounds.get(record.latest_round_id)
            if round_record:
                server_revision_id = round_record.server_revision_id
        return StatusResponse(
            status=record.status,
            latest_round_id=record.latest_round_id,
            latest_round_status=record.latest_round_status,
            project_id=getattr(record, "project_id", None),
            project=getattr(record, "project", None),
            project_slug=getattr(record, "project_slug", None),
            tree_number=record.tree_number,
            review_ready=review_ready,
            server_revision_id=server_revision_id,
        )

    @router.get("/v1/jobs/{job_id}/rounds/{round_id}", response_model=RoundReconciliationResponse)
    def get_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> RoundReconciliationResponse:
        """Return authoritative round reconciliation state for retry recovery."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")
        persisted_round = db_store.get_job_round(job_id, round_id)
        if not isinstance(persisted_round, dict):
            raise HTTPException(status_code=404, detail="Round not found")

        round_record = record.rounds.get(round_id)
        status = str(
            (getattr(round_record, "status", None) or persisted_round.get("status") or "DRAFT")
        )
        server_revision_id = (
            getattr(round_record, "server_revision_id", None)
            or persisted_round.get("server_revision_id")
        )
        client_revision_id = (
            getattr(round_record, "client_revision_id", None)
            or persisted_round.get("client_revision_id")
        )
        recordings_rows = list(db_store.list_round_recordings(job_id, round_id))
        images_rows = list(db_store.list_round_images(job_id, round_id))
        review_payload = persisted_round.get("review_payload") or {}
        review_ready = status == "REVIEW_RETURNED" or isinstance(review_payload, dict)

        if status == "SUBMITTED_FOR_PROCESSING":
            processing_state = "processing"
        elif status == "REVIEW_RETURNED":
            processing_state = "completed"
        elif status == "FAILED":
            processing_state = "failed"
        else:
            processing_state = "accepted"

        return RoundReconciliationResponse(
            job_id=job_id,
            round_id=round_id,
            status=status,
            server_revision_id=server_revision_id,
            client_revision_id=client_revision_id,
            review_ready=review_ready,
            processing_state=processing_state,
            recordings=[
                RoundArtifactStatus(
                    section_id=str(row.get("section_id") or ""),
                    recording_id=str(row.get("recording_id") or ""),
                    upload_status=str(row.get("upload_status") or ""),
                )
                for row in recordings_rows
                if str(row.get("recording_id") or "")
            ],
            images=[
                RoundArtifactStatus(
                    section_id=str(row.get("section_id") or ""),
                    image_id=str(row.get("image_id") or ""),
                    upload_status=str(row.get("upload_status") or ""),
                )
                for row in images_rows
                if str(row.get("image_id") or "")
            ],
            accepted_recording_ids=[
                str(row.get("recording_id") or "")
                for row in recordings_rows
                if str(row.get("recording_id") or "")
            ],
            accepted_image_ids=[
                str(row.get("image_id") or "")
                for row in images_rows
                if str(row.get("image_id") or "")
            ],
            transcription_failures=(
                list(review_payload.get("transcription_failures") or [])
                if isinstance(review_payload, dict)
                else []
            ),
        )

    @router.get("/v1/jobs/{job_id}/rounds/{round_id}/review")
    def get_review(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return cached/normalized review payload for a processed round."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record or round_id not in record.rounds:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds[round_id]
        if not round_record.server_revision_id:
            round_record.server_revision_id = f"rev_{round_id}"
        record.latest_round_status = "REVIEW_RETURNED"
        record.status = "REVIEW_RETURNED"
        round_record.status = "REVIEW_RETURNED"
        save_job_record(record)
        persisted_round = db_store.get_job_round(job_id, round_id)
        payload = (persisted_round or {}).get("review_payload")
        hydrated_images = review_payload_service.build_round_images(
            db_store.list_round_images(job_id, round_id)
        )
        if isinstance(payload, dict):
            logger.info("GET /v1/jobs/%s/rounds/%s/review (cached)", job_id, round_id)
            return review_payload_service.normalize_payload(
                payload,
                tree_number=record.tree_number,
                normalize_form_schema=normalize_form_schema,
                hydrated_images=hydrated_images,
            )
        payload = review_payload_service.build_default_payload(
            round_id=round_id,
            server_revision_id=round_record.server_revision_id,
            tree_number=record.tree_number,
            images=hydrated_images,
        )
        save_round_record(job_id, round_record, review_payload=payload)
        logger.info("GET /v1/jobs/%s/rounds/%s/review", job_id, round_id)
        return payload

    return router
