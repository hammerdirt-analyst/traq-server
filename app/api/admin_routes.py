"""Admin lifecycle routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body, Header, HTTPException
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

from .models import (
    AdminBillingCreateRequest,
    AdminBillingMergeRequest,
    AdminBillingUpdateRequest,
    AdminCustomerCreateRequest,
    AdminCustomerMergeRequest,
    AdminCustomerUpdateRequest,
    AdminDeviceApproveRequest,
    AdminDeviceTokenRequest,
    AdminJobCreateRequest,
    AdminJobStatusRequest,
    AdminJobUpdateRequest,
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
    customer_service: Any | None = None,
    job_mutation_service: Any | None = None,
    inspection_service: Any | None = None,
    artifact_fetch_service: Any | None = None,
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

    @router.get("/v1/admin/jobs/resolve")
    def admin_resolve_job(
        job_ref: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint resolving a job reference to canonical ids."""
        require_api_key(x_api_key, required_role="admin")
        normalized = (job_ref or "").strip()
        if not normalized:
            raise HTTPException(status_code=400, detail="job_ref is required")
        payload = db_store.get_job(normalized) if normalized.startswith("job_") else db_store.get_job_by_number(normalized)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=404, detail="Job not found")
        return {
            "ok": True,
            "job_id": payload.get("job_id"),
            "job_number": payload.get("job_number"),
            "status": payload.get("status"),
        }

    @router.get("/v1/admin/customers")
    def admin_list_customers(
        search: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing reusable customers."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        return {"ok": True, "customers": customer_service.list_customers(search=search)}

    @router.get("/v1/admin/customers/duplicates")
    def admin_customer_duplicates(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing duplicate customer candidates."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        return {"ok": True, "duplicates": customer_service.customer_duplicates()}

    @router.post("/v1/admin/customers")
    def admin_create_customer(
        payload: AdminCustomerCreateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint creating one reusable customer."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            customer = customer_service.create_customer(
                name=payload.name,
                phone=payload.phone,
                address=payload.address,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "customer": customer}

    @router.patch("/v1/admin/customers/{customer_ref}")
    def admin_update_customer(
        customer_ref: str,
        payload: AdminCustomerUpdateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint updating one reusable customer."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            customer = customer_service.update_customer(
                customer_ref,
                name=payload.name,
                phone=payload.phone,
                address=payload.address,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "customer": customer}

    @router.get("/v1/admin/customers/{customer_ref}/usage")
    def admin_customer_usage(
        customer_ref: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint summarizing customer-linked jobs and trees."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            payload = customer_service.customer_usage(customer_ref)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, **payload}

    @router.post("/v1/admin/customers/{customer_ref}/merge")
    def admin_merge_customer(
        customer_ref: str,
        payload: AdminCustomerMergeRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint merging one customer into another."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            result = customer_service.merge_customer(customer_ref, target_customer_id=payload.into)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **result}

    @router.delete("/v1/admin/customers/{customer_ref}")
    def admin_delete_customer(
        customer_ref: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint deleting one unused customer."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            payload = customer_service.delete_customer(customer_ref)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **payload}

    @router.get("/v1/admin/billing-profiles")
    def admin_list_billing_profiles(
        search: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing reusable billing profiles."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        return {"ok": True, "billing_profiles": customer_service.list_billing_profiles(search=search)}

    @router.get("/v1/admin/billing-profiles/duplicates")
    def admin_billing_duplicates(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing duplicate billing candidates."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        return {"ok": True, "duplicates": customer_service.billing_duplicates()}

    @router.post("/v1/admin/billing-profiles")
    def admin_create_billing_profile(
        payload: AdminBillingCreateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint creating one reusable billing profile."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        billing_profile = customer_service.create_billing_profile(
            billing_name=payload.billing_name,
            billing_contact_name=payload.billing_contact_name,
            billing_address=payload.billing_address,
            contact_preference=payload.contact_preference,
        )
        return {"ok": True, "billing_profile": billing_profile}

    @router.patch("/v1/admin/billing-profiles/{billing_ref}")
    def admin_update_billing_profile(
        billing_ref: str,
        payload: AdminBillingUpdateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint updating one reusable billing profile."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            billing_profile = customer_service.update_billing_profile(
                billing_ref,
                billing_name=payload.billing_name,
                billing_contact_name=payload.billing_contact_name,
                billing_address=payload.billing_address,
                contact_preference=payload.contact_preference,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, "billing_profile": billing_profile}

    @router.get("/v1/admin/billing-profiles/{billing_ref}/usage")
    def admin_billing_usage(
        billing_ref: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint summarizing billing-linked jobs."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            payload = customer_service.billing_usage(billing_ref)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"ok": True, **payload}

    @router.post("/v1/admin/billing-profiles/{billing_ref}/merge")
    def admin_merge_billing_profile(
        billing_ref: str,
        payload: AdminBillingMergeRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint merging one billing profile into another."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            result = customer_service.merge_billing_profile(
                billing_ref,
                target_billing_profile_id=payload.into,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **result}

    @router.delete("/v1/admin/billing-profiles/{billing_ref}")
    def admin_delete_billing_profile(
        billing_ref: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint deleting one unused billing profile."""
        require_api_key(x_api_key, required_role="admin")
        if customer_service is None:
            raise HTTPException(status_code=501, detail="Customer service not configured")
        try:
            payload = customer_service.delete_billing_profile(billing_ref)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **payload}

    @router.post("/v1/admin/jobs")
    def admin_create_job(
        payload: AdminJobCreateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint creating one operational job record."""
        require_api_key(x_api_key, required_role="admin")
        if job_mutation_service is None:
            raise HTTPException(status_code=501, detail="Job mutation service not configured")
        try:
            job = job_mutation_service.create_job(
                job_id=payload.job_id,
                job_number=payload.job_number,
                status=payload.status,
                customer_id=payload.customer_id,
                billing_profile_id=payload.billing_profile_id,
                tree_number=payload.tree_number,
                job_name=payload.job_name,
                job_address=payload.job_address,
                reason=payload.reason,
                location_notes=payload.location_notes,
                tree_species=payload.tree_species,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "job": job}

    @router.patch("/v1/admin/jobs/{job_ref}")
    def admin_update_job(
        job_ref: str,
        payload: AdminJobUpdateRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint updating one operational job record."""
        require_api_key(x_api_key, required_role="admin")
        if job_mutation_service is None:
            raise HTTPException(status_code=501, detail="Job mutation service not configured")
        try:
            job = job_mutation_service.update_job(
                job_ref,
                customer_id=payload.customer_id,
                billing_profile_id=payload.billing_profile_id,
                tree_number=payload.tree_number,
                job_name=payload.job_name,
                job_address=payload.job_address,
                reason=payload.reason,
                location_notes=payload.location_notes,
                tree_species=payload.tree_species,
                status=payload.status,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "job": job}

    @router.get("/v1/admin/jobs/{job_id}/inspect")
    def admin_inspect_job(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint returning job inspection payload."""
        require_api_key(x_api_key, required_role="admin")
        if inspection_service is None:
            raise HTTPException(status_code=501, detail="Inspection service not configured")
        try:
            return inspection_service.inspect_job(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/v1/admin/jobs/{job_id}/rounds/{round_id}/inspect")
    def admin_inspect_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint returning round inspection payload."""
        require_api_key(x_api_key, required_role="admin")
        if inspection_service is None:
            raise HTTPException(status_code=501, detail="Inspection service not configured")
        try:
            return inspection_service.inspect_round(job_id, round_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/v1/admin/jobs/{job_id}/rounds/{round_id}/review/inspect")
    def admin_inspect_review(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint returning review inspection payload."""
        require_api_key(x_api_key, required_role="admin")
        if inspection_service is None:
            raise HTTPException(status_code=501, detail="Inspection service not configured")
        try:
            return inspection_service.inspect_review(job_id, round_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/v1/admin/jobs/{job_id}/final/inspect")
    def admin_inspect_final(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint returning final/correction inspection payload."""
        require_api_key(x_api_key, required_role="admin")
        if inspection_service is None:
            raise HTTPException(status_code=501, detail="Inspection service not configured")
        try:
            return inspection_service.inspect_final(job_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.get("/v1/admin/jobs/{job_id}/artifacts/{kind}")
    def admin_fetch_artifact(
        job_id: str,
        kind: str,
        x_api_key: str | None = Header(default=None),
    ):
        """Admin endpoint exporting one preferred artifact variant for a job."""
        require_api_key(x_api_key, required_role="admin")
        if artifact_fetch_service is None:
            raise HTTPException(status_code=501, detail="Artifact fetch service not configured")
        try:
            payload = artifact_fetch_service.fetch(job_id, kind=kind)
        except RuntimeError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        saved_path = str(payload.get("saved_path") or "").strip()
        if not saved_path:
            raise HTTPException(status_code=500, detail="Artifact export path not available")
        variant = str(payload.get("variant") or "final")

        if kind == "transcript":
            try:
                from pathlib import Path

                path = Path(saved_path)
                return PlainTextResponse(
                    path.read_text(encoding="utf-8"),
                    headers={
                        "Content-Disposition": f'attachment; filename="{path.name}"',
                        "X-Artifact-Variant": variant,
                    },
                )
            except OSError as exc:
                raise HTTPException(status_code=500, detail="Failed to read transcript artifact") from exc

        if kind == "final-json":
            try:
                from pathlib import Path
                import json

                path = Path(saved_path)
                return JSONResponse(
                    json.loads(path.read_text(encoding="utf-8")),
                    headers={
                        "Content-Disposition": f'attachment; filename="{path.name}"',
                        "X-Artifact-Variant": variant,
                    },
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=500, detail="Failed to read final JSON artifact") from exc

        return FileResponse(
            path=saved_path,
            filename=saved_path.rsplit("/", 1)[-1],
            headers={"X-Artifact-Variant": variant},
        )

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
