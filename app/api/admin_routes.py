"""Admin lifecycle routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body, Header, HTTPException

from .models import (
    AdminDeviceApproveRequest,
    AdminDeviceTokenRequest,
    AdminJobStatusRequest,
    AdminJobUnlockRequest,
    AssignJobRequest,
)


def build_admin_router(
    *,
    require_api_key: Callable[..., Any],
    ensure_job_record: Callable[[str], Any],
    assign_job_record: Callable[..., dict[str, Any]],
    unassign_job_record: Callable[[str], dict[str, Any]],
    list_job_assignments: Callable[[], list[dict[str, Any]]],
    save_job_record: Callable[[Any], None],
    db_store: Any,
    round_record_factory: Callable[..., Any],
    logger: Any,
) -> APIRouter:
    """Build admin-only assignment and status mutation routes."""

    router = APIRouter()

    @router.get("/v1/admin/devices")
    def admin_list_devices(
        status: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing registered devices."""
        require_api_key(x_api_key, required_role="admin")
        rows = db_store.list_devices(status=(status or "").strip() or None)
        return {"ok": True, "devices": rows}

    @router.get("/v1/admin/devices/pending")
    def admin_list_pending_devices(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing pending devices."""
        require_api_key(x_api_key, required_role="admin")
        rows = db_store.list_devices(status="pending")
        return {"ok": True, "devices": rows}

    @router.post("/v1/admin/devices/{device_id}/approve")
    def admin_approve_device(
        device_id: str,
        payload: AdminDeviceApproveRequest = Body(default_factory=AdminDeviceApproveRequest),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint approving one device by id."""
        require_api_key(x_api_key, required_role="admin")
        try:
            row = db_store.approve_device(device_id.strip(), role=(payload.role or "arborist").strip() or "arborist")
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info("POST /v1/admin/devices/%s/approve -> role=%s", device_id, row.get("role"))
        return {"ok": True, "device": row}

    @router.post("/v1/admin/devices/{device_id}/revoke")
    def admin_revoke_device(
        device_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint revoking one device by id."""
        require_api_key(x_api_key, required_role="admin")
        try:
            row = db_store.revoke_device(device_id.strip())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        logger.info("POST /v1/admin/devices/%s/revoke", device_id)
        return {"ok": True, "device": row}

    @router.post("/v1/admin/devices/{device_id}/issue-token")
    def admin_issue_device_token(
        device_id: str,
        payload: AdminDeviceTokenRequest = Body(default_factory=AdminDeviceTokenRequest),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint issuing a device token."""
        require_api_key(x_api_key, required_role="admin")
        try:
            issued = db_store.issue_token(device_id.strip(), ttl_seconds=payload.ttl_seconds or 604800)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        logger.info("POST /v1/admin/devices/%s/issue-token", device_id)
        return {"ok": True, **issued}

    @router.post("/v1/admin/jobs/{job_id}/rounds/{round_id}/reopen")
    def admin_reopen_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint to reopen round back to DRAFT state."""
        require_api_key(x_api_key, required_role="admin")
        record = ensure_job_record(job_id)
        if not record or round_id not in record.rounds:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds[round_id]
        round_record.status = "DRAFT"
        record.latest_round_id = round_id
        record.latest_round_status = "DRAFT"
        record.status = "DRAFT"
        save_job_record(record)
        logger.info("POST /v1/admin/jobs/%s/rounds/%s/reopen", job_id, round_id)
        return {"ok": True, "job_id": job_id, "round_id": round_id, "status": "DRAFT"}

    @router.post("/v1/admin/jobs/{job_id}/unlock")
    def admin_unlock_job(
        job_id: str,
        payload: AdminJobUnlockRequest = Body(default_factory=AdminJobUnlockRequest),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint reopening a finalized job and optionally reassigning it."""
        require_api_key(x_api_key, required_role="admin")
        record = ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")

        round_id = (payload.round_id or record.latest_round_id or "").strip()
        if not round_id:
            raise HTTPException(status_code=400, detail="round_id is required")
        if round_id not in record.rounds:
            raise HTTPException(status_code=404, detail="Round not found")

        round_record = record.rounds[round_id]
        round_record.status = "DRAFT"
        record.latest_round_id = round_id
        record.latest_round_status = "DRAFT"
        record.status = "DRAFT"
        save_job_record(record)

        assignment = None
        device_id = (payload.device_id or "").strip()
        if device_id:
            try:
                assignment = assign_job_record(
                    job_id=job_id,
                    device_id=device_id,
                    assigned_by="admin_unlock",
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc

        logger.info("POST /v1/admin/jobs/%s/unlock -> round=%s device=%s", job_id, round_id, device_id or None)
        return {
            "ok": True,
            "job_id": job_id,
            "round_id": round_id,
            "status": "DRAFT",
            "assignment": assignment,
        }

    @router.get("/v1/admin/jobs/assignments")
    def admin_list_job_assignments(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing current job assignments."""
        require_api_key(x_api_key, required_role="admin")
        return {"ok": True, "assignments": list_job_assignments()}

    @router.post("/v1/admin/jobs/{job_id}/assign")
    def admin_assign_job(
        job_id: str,
        payload: AssignJobRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint assigning/reassigning a job to device."""
        require_api_key(x_api_key, required_role="admin")
        if ensure_job_record(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        device_id = (payload.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        try:
            row = assign_job_record(
                job_id=job_id,
                device_id=device_id,
                assigned_by="admin",
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        logger.info("POST /v1/admin/jobs/%s/assign -> %s", job_id, device_id)
        return {"ok": True, "assignment": row}

    @router.post("/v1/admin/jobs/{job_id}/unassign")
    def admin_unassign_job(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint removing job assignment."""
        require_api_key(x_api_key, required_role="admin")
        try:
            removed = unassign_job_record(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        logger.info("POST /v1/admin/jobs/%s/unassign", job_id)
        return {"ok": True, "removed": removed}

    @router.post("/v1/admin/jobs/{job_id}/status")
    def admin_set_job_status(
        job_id: str,
        payload: AdminJobStatusRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint forcing job status update."""
        require_api_key(x_api_key, required_role="admin")
        record = ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")

        allowed_job_status = {
            "NOT_STARTED",
            "DRAFT",
            "SUBMITTED_FOR_PROCESSING",
            "REVIEW_RETURNED",
            "ARCHIVED",
            "FAILED",
        }
        allowed_round_status = {
            "DRAFT",
            "SUBMITTED_FOR_PROCESSING",
            "REVIEW_RETURNED",
            "FAILED",
        }

        status = (payload.status or "").strip().upper()
        if status not in allowed_job_status:
            raise HTTPException(status_code=400, detail=f"Invalid job status: {status}")

        round_id = (payload.round_id or "").strip() or None
        round_status = (payload.round_status or "").strip().upper() or None
        if round_status and round_status not in allowed_round_status:
            raise HTTPException(status_code=400, detail=f"Invalid round status: {round_status}")

        record.status = status
        if round_id:
            round_record = record.rounds.get(round_id)
            if round_record is None:
                persisted_round = db_store.get_job_round(job_id, round_id)
                if not isinstance(persisted_round, dict):
                    raise HTTPException(status_code=404, detail="Round not found")
                round_record = round_record_factory(
                    round_id=round_id,
                    status=str(persisted_round.get("status") or "DRAFT"),
                    manifest=list(persisted_round.get("manifest") or []),
                    server_revision_id=persisted_round.get("server_revision_id"),
                )
                record.rounds[round_id] = round_record
            if round_status:
                round_record.status = round_status
            record.latest_round_id = round_id
            record.latest_round_status = round_record.status
        elif round_status:
            latest_round_id = record.latest_round_id
            if latest_round_id and latest_round_id in record.rounds:
                record.rounds[latest_round_id].status = round_status
                record.latest_round_status = round_status

        logger.info(
            "POST /v1/admin/jobs/%s/status -> job=%s round_id=%s round_status=%s",
            job_id,
            record.status,
            record.latest_round_id,
            record.latest_round_status,
        )
        save_job_record(record)
        return {
            "ok": True,
            "job_id": job_id,
            "status": record.status,
            "latest_round_id": record.latest_round_id,
            "latest_round_status": record.latest_round_status,
        }

    return router
