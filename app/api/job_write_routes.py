"""Low-risk job creation routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException

from .models import CreateJobRequest, CreateJobResponse, CreateRoundResponse, UpdateJobRequest


def build_job_write_router(
    *,
    require_api_key: Callable[[str | None], Any],
    jobs: dict[str, Any],
    next_job_number: Callable[[], str],
    customer_service: Any,
    job_mutation_service: Any,
    load_job_record: Callable[[str], Any],
    assign_job_record: Callable[..., Any],
    save_job_record: Callable[[Any], None],
    save_round_record: Callable[[str, Any], None],
    round_record_factory: Callable[..., Any],
    logger: Any,
    uuid_hex_supplier: Callable[[], str],
    assert_job_assignment: Callable[[str, Any], None],
    assert_job_editable: Callable[[Any, Any], None],
    ensure_job_record: Callable[[str], Any],
) -> APIRouter:
    """Build job/round creation routes."""

    router = APIRouter()

    @router.post("/v1/jobs", response_model=CreateJobResponse)
    def create_job(
        payload: CreateJobRequest,
        x_api_key: str | None = Header(default=None),
    ) -> CreateJobResponse:
        """Create a new server job and auto-assign it to calling device."""
        auth = require_api_key(x_api_key)
        while True:
            job_id = f"job_{uuid_hex_supplier()[:12]}"
            if job_id not in jobs:
                break
        job_number = next_job_number()
        customer = customer_service.get_or_create_customer(
            name=payload.customer_name or payload.job_name,
            phone=payload.job_phone,
            address=payload.job_address,
        )
        billing = customer_service.get_or_create_billing_profile(
            billing_name=payload.billing_name,
            billing_contact_name=payload.billing_contact_name,
            billing_address=payload.billing_address,
            contact_preference=payload.contact_preference,
        )
        try:
            created = job_mutation_service.create_job(
                job_id=job_id,
                job_number=job_number,
                status="DRAFT",
                customer_id=customer["customer_id"],
                billing_profile_id=billing["billing_profile_id"] if billing else None,
                project_id=getattr(payload, "project_id", None),
                tree_number=payload.tree_number,
                job_name=payload.job_name,
                job_address=payload.job_address,
                location_notes=payload.location_notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        record = load_job_record(job_id)
        if record is not None:
            jobs[job_id] = record
        if auth.device_id and not auth.is_admin:
            try:
                assign_job_record(
                    job_id=job_id,
                    device_id=auth.device_id,
                    assigned_by="auto",
                )
            except Exception:
                logger.exception(
                    "Failed to auto-assign job %s to device %s",
                    job_id,
                    auth.device_id,
                )
        logger.info("POST /v1/jobs -> %s", job_id)
        return CreateJobResponse(
            job_id=job_id,
            job_number=job_number,
            status="DRAFT",
            project_id=created.get("project_id"),
            project=created.get("project"),
            project_slug=created.get("project_slug"),
            customer_name=created.get("customer_name"),
            tree_number=created.get("tree_number"),
            address=created.get("address"),
            job_name=created.get("job_name"),
            job_address=created.get("job_address"),
            job_phone=created.get("job_phone"),
            contact_preference=created.get("contact_preference"),
            billing_name=created.get("billing_name"),
            billing_address=created.get("billing_address"),
            billing_contact_name=created.get("billing_contact_name"),
            location_notes=created.get("location_notes"),
        )

    @router.post("/v1/jobs/{job_id}/rounds", response_model=CreateRoundResponse)
    def create_round(job_id: str, x_api_key: str | None = Header(default=None)) -> CreateRoundResponse:
        """Create a new DRAFT round for an assigned job."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")
        if not auth.is_admin:
            latest = (record.latest_round_status or "").strip().upper()
            if latest == "SUBMITTED_FOR_PROCESSING":
                raise HTTPException(
                    status_code=409,
                    detail="Job is locked while processing. Wait for review.",
                )
            if latest == "ARCHIVED":
                raise HTTPException(
                    status_code=409,
                    detail="Job is archived. Admin must reopen to DRAFT.",
                )
        round_id = f"round_{len(record.rounds) + 1}"
        round_record = round_record_factory(round_id=round_id, status="DRAFT")
        record.rounds[round_id] = round_record
        record.latest_round_id = round_id
        record.latest_round_status = "DRAFT"
        record.status = "DRAFT"
        save_job_record(record)
        save_round_record(job_id, round_record)
        logger.info("POST /v1/jobs/%s/rounds -> %s", job_id, round_id)
        return CreateRoundResponse(round_id=round_id, status="DRAFT")

    @router.patch("/v1/jobs/{job_id}", response_model=CreateJobResponse)
    def update_job(
        job_id: str,
        payload: UpdateJobRequest,
        x_api_key: str | None = Header(default=None),
    ) -> CreateJobResponse:
        """Update editable job metadata for the assigned caller."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_job_editable(record, auth, allow_metadata_update=True)
        fields_set = getattr(payload, "model_fields_set", None) or getattr(payload, "__fields_set__", set())
        try:
            updated = job_mutation_service.update_job(
                job_id,
                project_id=getattr(payload, "project_id", None) if "project_id" in fields_set else job_mutation_service.UNSET,
                job_name=payload.job_name,
                job_address=payload.job_address,
                location_notes=payload.location_notes,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        refreshed = load_job_record(job_id)
        if refreshed is not None:
            jobs[job_id] = refreshed
        logger.info("PATCH /v1/jobs/%s", job_id)
        return CreateJobResponse(
            job_id=updated["job_id"],
            job_number=updated["job_number"],
            status=updated["status"],
            project_id=updated.get("project_id"),
            project=updated.get("project"),
            project_slug=updated.get("project_slug"),
            customer_name=updated.get("customer_name"),
            tree_number=updated.get("tree_number"),
            address=updated.get("address"),
            job_name=updated.get("job_name"),
            job_address=updated.get("job_address"),
            job_phone=updated.get("job_phone"),
            contact_preference=updated.get("contact_preference"),
            billing_name=updated.get("billing_name"),
            billing_address=updated.get("billing_address"),
            billing_contact_name=updated.get("billing_contact_name"),
            location_notes=updated.get("location_notes"),
        )

    return router
