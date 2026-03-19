"""Low-risk auth/profile/lookup routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException

from .models import (
    BillingProfileLookupRow,
    CustomerLookupRow,
    IssueTokenRequest,
    ProfilePayload,
    RegisterDeviceRequest,
)


def build_core_router(
    *,
    settings: Any,
    logger: Any,
    require_api_key: Callable[[str | None], Any],
    register_device_record: Callable[..., dict[str, Any]],
    get_device_record: Callable[[str], dict[str, Any] | None],
    issue_device_token_record: Callable[..., dict[str, Any]],
    load_runtime_profile: Callable[[str], dict[str, Any] | None],
    save_runtime_profile: Callable[[str, dict[str, Any]], dict[str, Any]],
    identity_key: Callable[[Any, str | None], str],
    customer_service: Any,
) -> APIRouter:
    """Build health/auth/profile/customer lookup routes."""

    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, Any]:
        """Health check endpoint for connectivity and storage-root visibility."""
        logger.info("GET /health")
        return {
            "status": "ok",
            "storage_root": str(settings.storage_root),
        }

    @router.post("/v1/auth/register-device")
    def register_device(payload: RegisterDeviceRequest) -> dict[str, Any]:
        """Register or refresh a device record in pending/approved workflow."""
        if not payload.device_id.strip():
            raise HTTPException(status_code=400, detail="device_id is required")
        device = register_device_record(
            device_id=payload.device_id.strip(),
            device_name=(payload.device_name or "").strip() or None,
            app_version=(payload.app_version or "").strip() or None,
            profile_summary=payload.profile_summary or {},
        )
        return {
            "ok": True,
            "device_id": device.get("device_id"),
            "status": device.get("status"),
            "role": device.get("role"),
        }

    @router.post("/v1/auth/token")
    def issue_device_token(payload: IssueTokenRequest) -> dict[str, Any]:
        """Issue bearer token for an approved device."""
        device_id = (payload.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        device = get_device_record(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        status = str(device.get("status") or "")
        if status != "approved":
            raise HTTPException(status_code=403, detail=f"Device status is {status or 'unknown'}")
        try:
            issued = issue_device_token_record(
                device_id=device_id,
                ttl_seconds=payload.ttl_seconds or 604800,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Token issuance failed") from exc
        return {"ok": True, **issued}

    @router.get("/v1/auth/device/{device_id}/status")
    def get_device_status(device_id: str) -> dict[str, Any]:
        """Return registration/approval status for a device id."""
        device = get_device_record(device_id.strip())
        if not device:
            return {"ok": True, "device_id": device_id, "status": "not_registered"}
        return {
            "ok": True,
            "device_id": device.get("device_id"),
            "status": device.get("status"),
            "role": device.get("role"),
            "updated_at": device.get("updated_at"),
        }

    @router.get("/v1/profile", response_model=ProfilePayload)
    def get_profile(x_api_key: str | None = Header(default=None)) -> ProfilePayload:
        """Load the DB-authoritative profile for the current auth identity."""
        auth = require_api_key(x_api_key)
        payload = load_runtime_profile(identity_key(auth, x_api_key))
        if isinstance(payload, dict):
            return ProfilePayload(**payload)
        return ProfilePayload()

    @router.put("/v1/profile", response_model=ProfilePayload)
    def put_profile(
        payload: ProfilePayload,
        x_api_key: str | None = Header(default=None),
    ) -> ProfilePayload:
        """Persist the DB-authoritative profile for the current auth identity."""
        auth = require_api_key(x_api_key)
        stored = save_runtime_profile(identity_key(auth, x_api_key), payload.model_dump())
        return ProfilePayload(**stored)

    @router.get("/v1/customers", response_model=list[CustomerLookupRow])
    def list_customer_lookup_rows(
        query: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> list[CustomerLookupRow]:
        """List reusable customer defaults for Start New Job prefill."""
        require_api_key(x_api_key)
        rows = customer_service.list_customers(search=query)
        return [
            CustomerLookupRow(
                customer_id=row["customer_id"],
                customer_code=row["customer_code"],
                customer_name=row["name"],
                job_name=row["name"],
                job_address=row.get("address"),
                job_phone=row.get("phone"),
            )
            for row in rows
        ]

    @router.get("/v1/billing-profiles", response_model=list[BillingProfileLookupRow])
    def list_billing_profile_lookup_rows(
        query: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> list[BillingProfileLookupRow]:
        """List reusable billing defaults for Start New Job prefill."""
        require_api_key(x_api_key)
        rows = customer_service.list_billing_profiles(search=query)
        return [BillingProfileLookupRow(**row) for row in rows]

    return router
