"""Main FastAPI application for TRAQ field-data processing.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Exposes the end-to-end server workflow used by the mobile client:
    device auth, job/round lifecycle, media ingest, transcription/extraction,
    review payload generation, and final artifact exports (TRAQ PDF, report
    letter PDF, and GeoJSON).

Architecture highlights:
    - Overlay-based PDF fill (`pdf_fill.py`) using canonical mapping
      (`server/app/traq_2_schema/traq_full_map.json`)
    - Registry-driven section extraction (`extractors/registry.py`)
    - File-backed security and assignment control (`security_store.py`)
    - JSON artifacts persisted per job/round under `server_data/jobs/`

Operational notes:
    - Logging is configured here (console + rotating file under
      `server_data/logs/server.log`).
    - This module uses nested helper functions inside `create_app()` to keep
      closure access to settings/log/security state explicit and centralized.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import logging.config
import logging.handlers
import os
import time
from pathlib import Path
import shutil
import subprocess
from typing import Any
import re
import hashlib
import uuid

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from .config import load_settings
from .db import init_database, session_scope
from .db_store import DatabaseStore
from .extractors.registry import run_extraction as _run_extraction_core
from .security_store import AuthContext, SecurityStore
from .service_discovery import DiscoveryConfig, ServiceDiscoveryAdvertiser
from .services.tree_store import (
    apply_tree_number_to_form,
    get_or_create_customer,
    parse_tree_number,
    requested_tree_number_from_form,
    resolve_tree,
)
from .services.customer_service import CustomerService
from .services.job_mutation_service import JobMutationService

JOB_PHOTOS_SECTION_ID = "job_photos"


@dataclass
class JobRecord:
    job_id: str
    job_number: str
    status: str
    customer_name: str | None = None
    tree_number: int | None = None
    address: str | None = None
    tree_species: str | None = None
    reason: str | None = None
    job_name: str | None = None
    job_address: str | None = None
    job_phone: str | None = None
    contact_preference: str | None = None
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    location_notes: str | None = None
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    rounds: dict[str, "RoundRecord"] = field(default_factory=dict)


@dataclass
class RoundRecord:
    round_id: str
    status: str
    manifest: list[dict[str, Any]] = field(default_factory=list)
    server_revision_id: str | None = None


class AssignedJob(BaseModel):
    job_id: str
    job_number: str
    status: str
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    customer_name: str
    tree_number: int | None = None
    address: str
    tree_species: str
    reason: str | None = None
    job_name: str
    job_address: str
    job_phone: str
    contact_preference: str
    billing_name: str
    billing_address: str
    billing_contact_name: str | None = None
    location_notes: str | None = None
    server_revision_id: str | None = None
    review_payload: dict[str, Any] | None = None


class CustomerLookupRow(BaseModel):
    customer_id: str
    customer_code: str
    customer_name: str
    job_name: str
    job_address: str | None = None
    job_phone: str | None = None


class BillingProfileLookupRow(BaseModel):
    billing_profile_id: str
    billing_code: str
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    contact_preference: str | None = None


class CreateJobResponse(BaseModel):
    job_id: str
    job_number: str
    status: str
    customer_name: str | None = None
    tree_number: int | None = None
    address: str | None = None
    tree_species: str | None = None
    reason: str | None = None
    job_name: str | None = None
    job_address: str | None = None
    job_phone: str | None = None
    contact_preference: str | None = None
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    location_notes: str | None = None


class CreateRoundResponse(BaseModel):
    round_id: str
    status: str


class CreateJobRequest(BaseModel):
    customer_name: str | None = Field(default=None, description="Customer/client name.")
    job_name: str = Field(..., description="Client/job name.")
    job_address: str = Field(..., description="Job site address.")
    job_phone: str = Field(..., description="Primary contact phone.")
    contact_preference: str = Field(..., description="Contact preference (text/phone call).")
    billing_name: str = Field(..., description="Billing name.")
    billing_address: str = Field(..., description="Billing address.")
    billing_contact_name: str | None = Field(
        default=None,
        description="Billing contact name (person).",
    )
    tree_number: int | None = Field(
        default=None,
        description="Optional customer-scoped tree number. Server validates or allocates the authoritative value.",
    )
    location_notes: str | None = Field(
        default=None,
        description="Free text notes describing the tree location on the property.",
    )


class ProfilePayload(BaseModel):
    name: str | None = None
    phone: str | None = None
    isa_number: str | None = None
    correspondence_street: str | None = None
    correspondence_city: str | None = None
    correspondence_state: str | None = None
    correspondence_zip: str | None = None
    correspondence_email: str | None = None


class StatusResponse(BaseModel):
    status: str
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    tree_number: int | None = None
    review_ready: bool = False
    server_revision_id: str | None = None


class ManifestItem(BaseModel):
    artifact_id: str
    section_id: str
    client_order: int = Field(default=0)
    kind: str = Field(default="recording")
    issue_id: str | None = None
    recorded_at: str | None = None


class FinalSubmitRequest(BaseModel):
    round_id: str
    server_revision_id: str
    client_revision_id: str
    form: dict[str, Any]
    narrative: dict[str, Any]
    profile: ProfilePayload | None = None


class SubmitRoundRequest(BaseModel):
    server_revision_id: str | None = None
    client_revision_id: str | None = None
    form: dict[str, Any] | None = None
    narrative: dict[str, Any] | None = None


class RegisterDeviceRequest(BaseModel):
    device_id: str
    device_name: str | None = None
    app_version: str | None = None
    profile_summary: dict[str, Any] | None = None


class IssueTokenRequest(BaseModel):
    device_id: str
    ttl_seconds: int | None = 604800


class AssignJobRequest(BaseModel):
    device_id: str


class AdminJobStatusRequest(BaseModel):
    status: str
    round_id: str | None = None
    round_status: str | None = None


class SiteFactorsRequest(BaseModel):
    transcript: str = Field(..., description="Full transcript for site factors section.")


class ClientTreeDetailsRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for client & tree details section.",
    )


class LoadFactorsRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for load factors section.",
    )


class CrownAndBranchesRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for crown and branches section.",
    )


class TrunkRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for trunk section.",
    )


class RootsAndRootCollarRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for roots and root collar section.",
    )


class TargetAssessmentRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for target assessment section.",
    )


class SummaryRequest(BaseModel):
    form: dict[str, Any] = Field(
        ...,
        description="Draft form payload with extracted section data.",
    )
    transcript: str = Field(
        ...,
        description="Combined transcript text for the job/round.",
    )


class TreeHealthAndSpeciesRequest(BaseModel):
    transcript: str = Field(
        ...,
        description="Full transcript for tree health and species section.",
    )


def create_app() -> FastAPI:
    """Construct and configure the FastAPI app instance.

    Returns:
        Configured FastAPI application with all routes, helper closures,
        logging setup, and startup hook registered.
    """
    settings = load_settings()
    init_database(settings)
    logs_dir = settings.storage_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "server.log"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "level": "INFO",
                    "formatter": "standard",
                },
                "file": {
                    "class": "logging.handlers.RotatingFileHandler",
                    "level": "INFO",
                    "formatter": "standard",
                    "filename": str(log_path),
                    "maxBytes": 10 * 1024 * 1024,
                    "backupCount": 5,
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["console", "file"],
            },
            "loggers": {
                # Keep Uvicorn output on the same formatter/handlers as app logs.
                "uvicorn": {
                    "level": "INFO",
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": "INFO",
                    "handlers": ["console", "file"],
                    "propagate": False,
                },
            },
        }
    )
    logger = logging.getLogger("traq_demo")
    app = FastAPI(title="Tree Risk Demo API")
    jobs: dict[str, JobRecord] = {}
    security = SecurityStore(settings.storage_root / "security")
    db_store = DatabaseStore()
    customer_service = CustomerService()
    job_mutation_service = JobMutationService()
    advertiser = ServiceDiscoveryAdvertiser(
        DiscoveryConfig(
            port=settings.discovery_port,
            service_name=settings.discovery_name,
        ),
        logger=logger,
    )

    def _log_event(tag: str, message: str, *args: Any) -> None:
        """Log tagged operational event through app logger."""
        logger.info("[%s] " + message, tag, *args)

    def _run_extraction_logged(section_id: str, transcript: str):
        """Run section extraction with start/ok event logging."""
        text = transcript or ""
        _log_event("EXTRACT", "start section=%s chars=%s", section_id, len(text))
        result = _run_extraction_core(section_id, transcript)
        _log_event("EXTRACT", "ok section=%s", section_id)
        return result

    def _to_assigned_job(record: JobRecord) -> AssignedJob:
        """Convert internal JobRecord to API AssignedJob model."""
        server_revision_id = None
        review_payload: dict[str, Any] | None = None
        if record.latest_round_id:
            round_record = record.rounds.get(record.latest_round_id)
            if round_record is not None:
                server_revision_id = round_record.server_revision_id
            review_data = (db_store.get_job_round(record.job_id, record.latest_round_id) or {}).get("review_payload")
            if isinstance(review_data, dict):
                review_payload = review_data
                if server_revision_id is None:
                    server_revision_id = review_data.get("server_revision_id")
        return AssignedJob(
            job_id=record.job_id,
            job_number=record.job_number,
            status=record.status or "NOT_STARTED",
            latest_round_id=record.latest_round_id,
            latest_round_status=record.latest_round_status,
            customer_name=record.customer_name or "",
            tree_number=record.tree_number,
            address=record.address or "",
            tree_species=record.tree_species or "",
            reason=record.reason,
            job_name=record.job_name or "",
            job_address=record.job_address or "",
            job_phone=record.job_phone or "",
            contact_preference=record.contact_preference or "",
            billing_name=record.billing_name or "",
            billing_address=record.billing_address or "",
            billing_contact_name=record.billing_contact_name,
            location_notes=record.location_notes,
            server_revision_id=server_revision_id,
            review_payload=review_payload,
        )

    def _resolve_assigned_job(job_id: str) -> AssignedJob | None:
        """Resolve assigned job object from the latest persisted runtime state."""
        persisted = _refresh_job_record_from_store(job_id)
        if persisted is not None:
            return _to_assigned_job(persisted)
        record = jobs.get(job_id)
        if record is not None:
            return _to_assigned_job(record)
        return None

    def _register_device_record(
        *,
        device_id: str,
        device_name: str | None,
        app_version: str | None,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Write device registration to the DB store only."""
        try:
            return db_store.register_device(
                device_id=device_id,
                device_name=device_name,
                app_version=app_version,
                profile_summary=profile_summary,
            )
        except Exception as exc:
            logger.exception("DB device registration failed for %s", device_id)
            raise HTTPException(status_code=500, detail="Device registration failed") from exc

    def _get_device_record(device_id: str) -> dict[str, Any] | None:
        """Read device record from the DB store only."""
        try:
            return db_store.get_device(device_id)
        except Exception:
            logger.exception("DB device lookup failed for %s", device_id)
            return None

    def _issue_device_token_record(device_id: str, ttl_seconds: int) -> dict[str, Any]:
        """Issue device token from the DB store only."""
        try:
            return db_store.issue_token(device_id=device_id, ttl_seconds=ttl_seconds)
        except Exception:
            logger.exception("DB token issuance failed for %s", device_id)
            raise

    def _list_job_assignments() -> list[dict[str, Any]]:
        """List DB-backed job assignments only."""
        try:
            return db_store.list_job_assignments()
        except Exception:
            logger.exception("DB assignment listing failed")
            return []

    def _assign_job_record(*, job_id: str, device_id: str, assigned_by: str | None) -> dict[str, Any]:
        """Write job assignment to the DB store only."""
        try:
            return db_store.assign_job(
                job_id=job_id,
                device_id=device_id,
                assigned_by=assigned_by,
            )
        except (KeyError, PermissionError) as exc:
            logger.warning("DB assignment failed for %s -> %s: %s", job_id, device_id, exc)
            raise
        except Exception:
            logger.exception("DB assignment failed for %s -> %s", job_id, device_id)
            raise

    def _unassign_job_record(job_id: str) -> dict[str, Any]:
        """Remove job assignment from the DB store only."""
        try:
            return db_store.unassign_job(job_id)
        except Exception:
            logger.exception("DB unassign failed for %s", job_id)
            raise

    def require_api_key(
        x_api_key: str | None,
        *,
        required_role: str | None = None,
    ) -> AuthContext:
        """Authenticate request using server API key or device token."""
        if x_api_key and x_api_key == settings.api_key:
            return AuthContext(
                device_id=None,
                role="admin",
                is_admin=True,
                source="server_api_key",
            )
        if x_api_key:
            auth = None
            try:
                auth = db_store.validate_token(x_api_key)
            except Exception:
                logger.exception("DB token validation failed")
            if auth is not None:
                if required_role == "admin" and not auth.is_admin:
                    raise HTTPException(status_code=403, detail="Admin role required")
                return auth
        raise HTTPException(status_code=401, detail="Invalid credentials")

    def _identity_key(auth: AuthContext, x_api_key: str | None) -> str:
        """Build identity key used to scope profile persistence."""
        if auth.source == "device_token" and auth.device_id:
            return f"device:{auth.device_id}"
        return f"admin:{x_api_key or ''}"

    def _resolve_server_tree_number(
        record: JobRecord,
        *,
        requested_tree_number: int | None = None,
    ) -> int | None:
        """Resolve the authoritative customer-scoped tree number for a job."""
        customer_name = (record.customer_name or "").strip()
        if not customer_name:
            return record.tree_number
        with session_scope() as session:
            customer = get_or_create_customer(
                session,
                name=customer_name,
                phone=(record.job_phone or "").strip() or None,
                address=(record.address or "").strip() or None,
            )
            tree = resolve_tree(
                session,
                customer=customer,
                requested_tree_number=requested_tree_number or record.tree_number,
            )
            record.tree_number = tree.tree_number
            return record.tree_number


    def _assert_round_editable(
        record: JobRecord,
        round_id: str,
        auth: AuthContext,
        *,
        allow_correction: bool = False,
    ) -> None:
        """Enforce round edit lock rules for non-admin callers."""
        if auth.is_admin:
            return
        if allow_correction and (record.status or "").strip().upper() == "ARCHIVED":
            return
        round_record = record.rounds.get(round_id)
        if round_record is None:
            return
        if round_record.status != "DRAFT":
            raise HTTPException(
                status_code=409,
                detail="Round is locked. Admin must reopen to DRAFT.",
            )

    def _assert_job_editable(
        record: JobRecord,
        auth: AuthContext,
        *,
        allow_correction: bool = False,
    ) -> None:
        """Enforce job-level edit lock rules for non-admin callers."""
        if auth.is_admin:
            return
        if allow_correction and (record.status or "").strip().upper() == "ARCHIVED":
            return
        latest = (record.latest_round_status or "").strip()
        if latest and latest != "DRAFT":
            raise HTTPException(
                status_code=409,
                detail="Job is locked. Admin must reopen round to DRAFT.",
            )

    def _assert_job_assignment(job_id: str, auth: AuthContext) -> None:
        """Enforce caller authorization for target job id."""
        if auth.is_admin:
            return
        if not auth.device_id:
            raise HTTPException(status_code=403, detail="Device identity required")
        assigned = db_store.get_job_assignment(job_id)
        if assigned is None:
            # Allow auto-claim for jobs that already exist either in memory
            # or on disk (common after server restart).
            job_exists_in_memory = job_id in jobs
            job_exists_in_db = db_store.get_job(job_id) is not None
            if job_exists_in_memory or job_exists_in_db:
                try:
                    db_store.assign_job(
                        job_id=job_id,
                        device_id=auth.device_id,
                        assigned_by="auto",
                    )
                    return
                except Exception as exc:
                    raise HTTPException(status_code=403, detail=f"Job assignment failed: {exc}") from exc
            raise HTTPException(status_code=403, detail="Job is not assigned to this device")
        assigned_device = str(assigned.get("device_id") or "")
        if assigned_device != auth.device_id:
            raise HTTPException(status_code=403, detail="Job is assigned to another device")

    def _job_dir(job_id: str) -> Path:
        """Return filesystem directory path for a job id."""
        path = settings.storage_root / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _is_correction_mode(job_id: str, record: JobRecord | None) -> bool:
        """Return True when writes should target correction artifacts."""
        if record and (record.status or "").strip().upper() == "ARCHIVED":
            return True
        return (_job_dir(job_id) / "final.json").exists()

    def _job_record_path(job_id: str) -> Path:
        """Return path to compatibility/debug job record JSON file."""
        return _job_dir(job_id) / "job_record.json"

    def _save_job_record(record: JobRecord) -> None:
        """Persist authoritative job shell state to DB and export a file copy."""
        payload = {
            "job_id": record.job_id,
            "job_number": record.job_number,
            "status": record.status,
            "customer_name": record.customer_name,
            "tree_number": record.tree_number,
            "address": record.address,
            "tree_species": record.tree_species,
            "reason": record.reason,
            "job_name": record.job_name,
            "job_address": record.job_address,
            "job_phone": record.job_phone,
            "contact_preference": record.contact_preference,
            "billing_name": record.billing_name,
            "billing_address": record.billing_address,
            "billing_contact_name": record.billing_contact_name,
            "location_notes": record.location_notes,
            "latest_round_id": record.latest_round_id,
            "latest_round_status": record.latest_round_status,
        }
        try:
            db_store.upsert_job(
                job_id=record.job_id,
                job_number=record.job_number,
                status=record.status,
                latest_round_id=record.latest_round_id,
                latest_round_status=record.latest_round_status,
                details=payload,
            )
        except Exception:
            logger.exception("DB job upsert failed for %s", record.job_id)
        _write_json(_job_record_path(record.job_id), payload)

    def _job_record_from_payload(payload: dict[str, Any], fallback_job_id: str) -> JobRecord:
        """Build JobRecord from normalized payload data."""
        return JobRecord(
            job_id=str(payload.get("job_id") or fallback_job_id),
            job_number=str(payload.get("job_number") or fallback_job_id),
            status=str(payload.get("status") or "DRAFT"),
            customer_name=payload.get("customer_name"),
            tree_number=parse_tree_number(payload.get("tree_number")),
            address=payload.get("address"),
            tree_species=payload.get("tree_species"),
            reason=payload.get("reason"),
            job_name=payload.get("job_name"),
            job_address=payload.get("job_address"),
            job_phone=payload.get("job_phone"),
            contact_preference=payload.get("contact_preference"),
            billing_name=payload.get("billing_name"),
            billing_address=payload.get("billing_address"),
            billing_contact_name=payload.get("billing_contact_name"),
            location_notes=payload.get("location_notes"),
            latest_round_id=payload.get("latest_round_id"),
            latest_round_status=payload.get("latest_round_status"),
        )

    def _load_rounds_from_db(job_id: str) -> dict[str, RoundRecord]:
        """Load persisted round metadata from the authoritative DB store."""
        rounds: dict[str, RoundRecord] = {}
        try:
            for row in db_store.list_job_rounds(job_id):
                round_id = str(row.get("round_id") or "")
                if not round_id:
                    continue
                rounds[round_id] = RoundRecord(
                    round_id=round_id,
                    status=str(row.get("status") or "DRAFT"),
                    manifest=list(row.get("manifest") or []),
                    server_revision_id=row.get("server_revision_id"),
                )
        except Exception:
            logger.exception("DB round listing failed for %s", job_id)
        return rounds

    def _load_job_record_from_db(job_id: str) -> JobRecord | None:
        """Load a job record from the authoritative DB store."""
        payload = db_store.get_job(job_id)
        if not isinstance(payload, dict):
            return None
        return _job_record_from_payload(payload, job_id)

    def _load_job_record_from_disk(job_id: str) -> JobRecord | None:
        """Load compatibility/debug job record from disk."""
        path = _job_record_path(job_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return _job_record_from_payload(payload, job_id)

    def _load_job_record(job_id: str) -> JobRecord | None:
        """Load a job record, preferring the DB and falling back to disk."""
        persisted = _load_job_record_from_db(job_id)
        if persisted is not None:
            return persisted
        return _load_job_record_from_disk(job_id)

    def _refresh_job_record_from_store(job_id: str) -> JobRecord | None:
        """Refresh cached runtime metadata from the authoritative store."""
        persisted = _load_job_record(job_id)
        if persisted is None:
            return None
        persisted.rounds = _load_rounds_from_db(job_id)
        existing = jobs.get(job_id)
        if existing is not None:
            persisted.rounds.update(existing.rounds)
        jobs[job_id] = persisted
        return persisted

    def _save_round_record(
        job_id: str,
        round_record: RoundRecord,
        *,
        review_payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist authoritative round state to DB and export compatibility files."""
        try:
            db_store.upsert_job_round(
                job_id=job_id,
                round_id=round_record.round_id,
                status=round_record.status,
                server_revision_id=round_record.server_revision_id,
                manifest=list(round_record.manifest or []),
                review_payload=review_payload,
            )
        except Exception:
            logger.exception("DB round upsert failed for %s/%s", job_id, round_record.round_id)
        _write_json(_round_manifest_path(job_id, round_record.round_id), round_record.manifest)
        if review_payload is not None:
            _write_json(_round_dir(job_id, round_record.round_id) / "review.json", review_payload)

    def _existing_job_numbers() -> set[str]:
        """Collect existing job numbers from authoritative job storage."""
        values: set[str] = {r.job_number for r in jobs.values() if r.job_number}
        try:
            for row in db_store.list_jobs():
                number = str(row.get("job_number") or "").strip()
                if number:
                    values.add(number)
        except Exception:
            logger.exception("DB job listing failed while collecting job numbers")
        return values

    def _job_number_counter_path() -> Path:
        """Return path to job-number counter file."""
        return settings.storage_root / "jobs" / "_job_number_counter.txt"

    def _next_job_number() -> str:
        """Allocate next unique human-readable job number."""
        counter_path = _job_number_counter_path()
        counter_path.parent.mkdir(parents=True, exist_ok=True)
        current = 0
        if counter_path.exists():
            try:
                current = int(counter_path.read_text(encoding="utf-8").strip() or "0")
            except ValueError:
                current = 0
        used = _existing_job_numbers()
        while True:
            current += 1
            candidate = f"J{current:04d}"
            if candidate not in used:
                counter_path.write_text(str(current), encoding="utf-8")
                return candidate

    def _round_dir(job_id: str, round_id: str) -> Path:
        """Return filesystem directory for a job round."""
        path = _job_dir(job_id) / "rounds" / round_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _ensure_job_record(job_id: str) -> JobRecord | None:
        """Resolve job record from memory or storage."""
        persisted = _refresh_job_record_from_store(job_id)
        if persisted is not None:
            return persisted
        return jobs.get(job_id)

    def _ensure_round_record(job_id: str, round_id: str) -> tuple[JobRecord, RoundRecord]:
        """Resolve a persisted round from authoritative storage."""
        record = _ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds.get(round_id)
        if round_record is None:
            persisted_round = db_store.get_job_round(job_id, round_id)
            if not isinstance(persisted_round, dict):
                raise HTTPException(status_code=404, detail="Round not found")
            round_record = RoundRecord(
                round_id=round_id,
                status=str(persisted_round.get("status") or "DRAFT"),
                manifest=list(persisted_round.get("manifest") or []),
                server_revision_id=persisted_round.get("server_revision_id"),
            )
            record.rounds[round_id] = round_record
        return record, round_record

    def _section_dir(job_id: str, section_id: str) -> Path:
        """Return filesystem directory for a section within a job."""
        path = _job_dir(job_id) / "sections" / section_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _round_manifest_path(job_id: str, round_id: str) -> Path:
        """Return path to round manifest JSON file."""
        return _round_dir(job_id, round_id) / "manifest.json"

    def _profile_dir() -> Path:
        """Return profile storage directory path."""
        path = settings.storage_root / "profiles"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _profile_path(identity_key: str) -> Path:
        """Return the exported debug profile path for one identity."""
        digest = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()
        return _profile_dir() / f"{digest}.json"

    def _load_runtime_profile(identity_key: str) -> dict[str, Any] | None:
        """Load runtime profile payload from the authoritative DB store."""
        payload = db_store.get_runtime_profile(identity_key)
        if isinstance(payload, dict):
            return dict(payload)
        return None

    def _save_runtime_profile(identity_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist runtime profile payload to DB and export a debug copy."""
        stored = db_store.upsert_runtime_profile(
            identity_key=identity_key,
            profile_payload=dict(payload or {}),
        )
        _write_json(_profile_path(identity_key), stored)
        return stored

    def _load_round_manifest(job_id: str, round_id: str) -> list[dict[str, Any]]:
        """Load one round manifest payload from the authoritative DB store."""
        payload = (db_store.get_job_round(job_id, round_id) or {}).get("manifest")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _load_all_manifests(job_id: str) -> list[dict[str, Any]]:
        """Load manifests across all rounds for a job from the DB store."""
        manifest_items: list[dict[str, Any]] = []
        for row in db_store.list_job_rounds(job_id):
            manifest_items.extend(list(row.get("manifest") or []))
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for item in manifest_items:
            artifact_id = item.get("artifact_id") or ""
            section_id = item.get("section_id") or ""
            kind = item.get("kind") or ""
            key = (artifact_id, section_id, kind)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _load_latest_review(job_id: str, exclude_round_id: str | None = None) -> dict[str, Any]:
        """Load latest review payload for baseline merges from the DB store."""
        for row in reversed(db_store.list_job_rounds(job_id)):
            if exclude_round_id and row.get("round_id") == exclude_round_id:
                continue
            payload = row.get("review_payload")
            if isinstance(payload, dict):
                return dict(payload)
        return {}

    def _recording_meta(
        job_id: str,
        round_id: str,
        section_id: str,
        recording_id: str,
    ) -> dict[str, Any]:
        """Load DB-authoritative recording metadata for one uploaded recording."""
        payload = db_store.get_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
        )
        if not isinstance(payload, dict):
            return {}
        meta = dict(payload.get("metadata_json") or {})
        if payload.get("artifact_path") and "stored_path" not in meta:
            meta["stored_path"] = payload.get("artifact_path")
        if payload.get("content_type") is not None and "content_type" not in meta:
            meta["content_type"] = payload.get("content_type")
        if payload.get("duration_ms") is not None and "duration_ms" not in meta:
            meta["duration_ms"] = payload.get("duration_ms")
        return meta

    def _build_reprocess_manifest(
        job_id: str,
        round_record: RoundRecord,
        round_review: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build server-side manifest for forced reprocess from DB recording metadata."""
        by_section: dict[str, set[str]] = {}
        recorded_at_map: dict[tuple[str, str], str] = {}

        # Source A: DB-backed uploaded recording metadata for this round.
        for payload in db_store.list_round_recordings(job_id, round_record.round_id):
            section_id = str(payload.get("section_id") or "")
            recording_id = str(payload.get("recording_id") or "")
            if not section_id or not recording_id:
                continue
            by_section.setdefault(section_id, set()).add(recording_id)
            meta = dict(payload.get("metadata_json") or {})
            uploaded_at = meta.get("uploaded_at")
            if isinstance(uploaded_at, str) and uploaded_at.strip():
                recorded_at_map[(section_id, recording_id)] = uploaded_at

        # Source B: round manifest (fallback for edge-cases).
        for item in round_record.manifest:
            if item.get("kind") != "recording":
                continue
            section_id = item.get("section_id")
            artifact_id = item.get("artifact_id")
            if not section_id or not artifact_id:
                continue
            s = str(section_id)
            r = str(artifact_id)
            by_section.setdefault(s, set()).add(r)
            recorded_at = item.get("recorded_at")
            if isinstance(recorded_at, str) and recorded_at.strip():
                recorded_at_map[(s, r)] = recorded_at

        # Source C: prior review references.
        section_recordings = round_review.get("section_recordings")
        if isinstance(section_recordings, dict):
            for section_id, recording_ids in section_recordings.items():
                if not isinstance(recording_ids, list):
                    continue
                for recording_id in recording_ids:
                    if not recording_id:
                        continue
                    by_section.setdefault(str(section_id), set()).add(str(recording_id))

        manifest: list[dict[str, Any]] = []
        client_order = 1
        for section_id in sorted(by_section.keys()):
            for recording_id in sorted(by_section[section_id]):
                meta = _recording_meta(job_id, round_record.round_id, section_id, recording_id)
                stored_path = meta.get("stored_path")
                if not stored_path:
                    continue
                manifest.append(
                    {
                        "artifact_id": recording_id,
                        "section_id": section_id,
                        "client_order": client_order,
                        "kind": "recording",
                        "issue_id": None,
                        "recorded_at": recorded_at_map.get(
                            (section_id, recording_id),
                            meta.get("uploaded_at"),
                        ),
                    }
                )
                client_order += 1
        return manifest

    def _merge_optional_str(
        existing: str | None,
        incoming: str | None,
        append: bool = False,
    ) -> str | None:
        """Merge scalar text values with preserve/append behavior."""
        if incoming is None or incoming == "":
            return existing
        if existing is None or existing == "":
            return incoming
        if append and incoming not in existing:
            return f"{existing} {incoming}".strip()
        return existing

    def _merge_optional_notes(
        existing: str | None,
        incoming: str | None,
    ) -> str | None:
        """Merge freeform notes preserving prior content."""
        if incoming is None or incoming == "":
            return existing
        if existing is None or existing == "":
            return incoming
        if incoming in existing:
            return existing
        return f"{existing}\n\n{incoming}".strip()

    def _cap_text(value: str | None, limit: int) -> str | None:
        """Cap text length at word boundary for field constraints."""
        if value is None:
            return None
        text = " ".join(str(value).split())
        if len(text) <= limit:
            return text
        clipped = text[:limit].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return clipped

    def _merge_flat_section(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge flat section payloads preserving existing values."""
        merged = dict(existing)
        if "section_id" in incoming:
            merged["section_id"] = incoming.get("section_id")
        for key, value in incoming.items():
            if key == "section_id":
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_notes_explanations_descriptions(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge notes section with append/cap rules."""
        merged = dict(existing)
        merged["section_id"] = incoming.get(
            "section_id",
            "notes_explanations_descriptions",
        )
        merged_notes = _merge_optional_notes(
            merged.get("notes"),
            incoming.get("notes"),
        )
        merged["notes"] = _cap_text(merged_notes, 230)
        return merged

    def _merge_mitigation_options(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge mitigation option rows without duplication."""
        merged = dict(existing)
        merged["section_id"] = incoming.get("section_id", "mitigation_options")
        existing_rows = merged.get("options")
        if not isinstance(existing_rows, list):
            existing_rows = []
        existing_rows = [
            dict(row) for row in existing_rows if isinstance(row, dict)
        ]

        incoming_rows = incoming.get("options")
        if not isinstance(incoming_rows, list):
            incoming_rows = []
        incoming_rows = [
            dict(row) for row in incoming_rows if isinstance(row, dict)
        ]

        def _row_has_values(row: dict[str, Any]) -> bool:
            return any(value not in (None, "") for value in row.values())

        def _row_key(row: dict[str, Any]) -> tuple[str | None, str | None]:
            return (
                (row.get("option") or "").strip() or None,
                (row.get("residual_risk") or "").strip() or None,
            )

        existing_keys = {
            _row_key(row) for row in existing_rows if _row_has_values(row)
        }

        for incoming_row in incoming_rows:
            if not _row_has_values(incoming_row):
                continue
            key = _row_key(incoming_row)
            if key in existing_keys:
                continue
            existing_rows.append(incoming_row)
            existing_keys.add(key)
            if len(existing_rows) >= 4:
                break

        merged["options"] = existing_rows
        return merged

    def _apply_form_patch(
        base_form: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply incoming client patch onto draft form payload."""
        merged: dict[str, Any] = dict(base_form or {})
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _apply_form_patch(
                    dict(merged.get(key) or {}),
                    dict(value),
                )
            else:
                merged[key] = value
        return merged

    def _normalize_form_schema(data: dict[str, Any]) -> dict[str, Any]:
        """Normalize form payload to expected full schema."""
        normalized = dict(data or {})

        site = normalized.get("site_factors")
        if isinstance(site, dict):
            site_obj = dict(site)
            site_changes = site_obj.get("site_changes")
            site_changes_obj = dict(site_changes) if isinstance(site_changes, dict) else {}
            legacy_landscape = site_obj.pop("landscape_environment", None)
            if (
                site_changes_obj.get("landscape_environment") in (None, "")
                and legacy_landscape not in (None, "")
            ):
                site_changes_obj["landscape_environment"] = legacy_landscape
            # Canonical schema: site_changes.describe is deprecated.
            site_changes_obj.pop("describe", None)
            site_changes_obj.setdefault("landscape_environment", None)
            site_obj["site_changes"] = site_changes_obj
            normalized["site_factors"] = site_obj

        recommended = normalized.get("recommended_inspection_interval")
        if isinstance(recommended, dict):
            rec_obj = dict(recommended)
            if rec_obj.get("text") in (None, "") and rec_obj.get("interval") not in (None, ""):
                rec_obj["text"] = rec_obj.get("interval")
            rec_obj.pop("interval", None)
            rec_obj.setdefault("text", None)
            normalized["recommended_inspection_interval"] = rec_obj

        crown = normalized.get("crown_and_branches")
        if isinstance(crown, dict):
            crown_obj = dict(crown)
            crown_obj.setdefault("cracks_notes", None)
            normalized["crown_and_branches"] = crown_obj

        return normalized

    def _merge_site_factors(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Section-specific merge for site factors payload."""
        merged = dict(existing)
        for key in ("history_of_failures", "prevailing_wind_direction", "notes"):
            if key not in merged:
                merged[key] = incoming.get(key)
                continue
            merged[key] = _merge_optional_str(
                merged.get(key),
                incoming.get(key),
                append=key == "notes",
            )
        for group_key, describe_key in (
            ("site_changes", None),
            ("soil_conditions", "describe"),
            ("common_weather", "describe"),
        ):
            base_group = dict(merged.get(group_key) or {})
            incoming_group = incoming.get(group_key) or {}
            # Backward compatibility: older payloads had landscape_environment at top-level.
            if (
                group_key == "site_changes"
                and "landscape_environment" not in incoming_group
                and incoming.get("landscape_environment") not in (None, "")
            ):
                incoming_group = dict(incoming_group)
                incoming_group["landscape_environment"] = incoming.get("landscape_environment")
            if group_key == "site_changes":
                base_group.pop("describe", None)
                if isinstance(incoming_group, dict):
                    incoming_group = dict(incoming_group)
                    incoming_group.pop("describe", None)
            for k, v in incoming_group.items():
                if k not in base_group:
                    base_group[k] = v
                    continue
                if describe_key is not None and k == describe_key:
                    base_group[k] = _merge_optional_str(
                        base_group.get(k),
                        v,
                        append=True,
                    )
                else:
                    if base_group.get(k) is None and v is not None:
                        base_group[k] = v
            merged[group_key] = base_group
        topography = dict(merged.get("topography") or {})
        incoming_topo = incoming.get("topography") or {}
        for k, v in incoming_topo.items():
            if k not in topography:
                topography[k] = v
                continue
            if topography.get(k) is None and v is not None:
                topography[k] = v
        merged["topography"] = topography
        return merged

    def _merge_client_tree_details(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Section-specific merge for client/tree details."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_target_assessment(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Section-specific merge for target assessment rows."""
        merged = dict(existing)
        merged["section_id"] = incoming.get("section_id", "target_assessment")

        existing_targets = merged.get("targets")
        if not isinstance(existing_targets, list):
            existing_targets = []
        existing_targets = [
            dict(item) for item in existing_targets if isinstance(item, dict)
        ]

        incoming_targets = incoming.get("targets")
        if not isinstance(incoming_targets, list):
            incoming_targets = []
        incoming_targets = [
            dict(item) for item in incoming_targets if isinstance(item, dict)
        ]

        for idx, incoming_target in enumerate(incoming_targets):
            if idx < len(existing_targets):
                base = dict(existing_targets[idx])
                for key, value in incoming_target.items():
                    if base.get(key) not in (None, ""):
                        continue
                    if value not in (None, ""):
                        base[key] = value
                existing_targets[idx] = base
            else:
                existing_targets.append(incoming_target)

        merged["targets"] = existing_targets
        return merged

    def _merge_tree_health_and_species(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-specific merge for tree health/species."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if isinstance(value, dict):
                base_group = dict(merged.get(key) or {})
                for subkey, subval in value.items():
                    if subkey not in base_group:
                        base_group[subkey] = subval
                        continue
                    if base_group.get(subkey) in (None, "") and subval not in (None, ""):
                        base_group[subkey] = subval
                merged[key] = base_group
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_load_factors(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-specific merge for load factors."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_crown_and_branches(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-specific merge for crown/branches."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if isinstance(value, dict):
                base_group = dict(merged.get(key) or {})
                for subkey, subval in value.items():
                    if subkey not in base_group:
                        base_group[subkey] = subval
                        continue
                    if base_group.get(subkey) in (None, "") and subval not in (None, ""):
                        base_group[subkey] = subval
                merged[key] = base_group
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_trunk(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-specific merge for trunk findings."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _merge_roots_and_root_collar(
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Section-specific merge for roots/root collar."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def _guess_extension(content_type: str | None, default: str) -> str:
        """Infer file extension from content type."""
        if not content_type:
            return default
        ct = content_type.lower()
        if ct in {"audio/mp4", "audio/m4a"}:
            return ".m4a"
        if ct in {"audio/wav", "audio/x-wav"}:
            return ".wav"
        if ct in {"image/jpeg", "image/jpg"}:
            return ".jpg"
        if ct == "image/png":
            return ".png"
        return default

    def _probe_audio_metadata(file_path: Path) -> dict[str, Any]:
        """Best-effort audio probe metadata for debugging cross-device issues."""
        probe: dict[str, Any] = {
            "file_bytes": file_path.stat().st_size,
            "ext": file_path.suffix.lower(),
        }
        try:
            ffprobe_bin = os.environ.get("TRAQ_FFPROBE_BIN", "ffprobe")
            cmd = [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                (
                    "stream=codec_name,sample_rate,channels,bit_rate"
                    ":format=format_name,duration,bit_rate"
                ),
                "-of",
                "json",
                str(file_path),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=4,
            )
            if result.returncode != 0:
                probe["ffprobe_error"] = (result.stderr or "").strip()[:240]
                return probe
            payload = json.loads(result.stdout or "{}")
            streams = payload.get("streams") or []
            fmt = payload.get("format") or {}
            if streams and isinstance(streams[0], dict):
                stream0 = streams[0]
                probe["codec_name"] = stream0.get("codec_name")
                probe["sample_rate"] = stream0.get("sample_rate")
                probe["channels"] = stream0.get("channels")
                probe["stream_bit_rate"] = stream0.get("bit_rate")
            probe["format_name"] = fmt.get("format_name")
            probe["duration"] = fmt.get("duration")
            probe["format_bit_rate"] = fmt.get("bit_rate")
            probe["ffprobe_bin"] = ffprobe_bin
        except FileNotFoundError:
            probe["ffprobe_error"] = "ffprobe_not_found"
        except Exception as exc:
            probe["ffprobe_error"] = str(exc)[:240]
        return probe

    def _is_canonical_transcribe_audio(
        file_path: Path,
        probe: dict[str, Any] | None = None,
    ) -> bool:
        """Check whether audio already matches canonical transcribe format."""
        if file_path.suffix.lower() != ".wav":
            return False
        if not isinstance(probe, dict):
            return False
        codec = str(probe.get("codec_name") or "").lower()
        sample_rate = str(probe.get("sample_rate") or "").strip()
        channels = str(probe.get("channels") or "").strip()
        return codec == "pcm_s16le" and sample_rate == "16000" and channels == "1"

    def _normalize_audio_for_transcription(file_path: Path) -> tuple[Path, bool]:
        """Normalize audio to 16kHz mono PCM WAV for consistent transcription input."""
        ffmpeg_bin = os.environ.get("TRAQ_FFMPEG_BIN", "ffmpeg")
        normalized_path = file_path.with_suffix(".norm16k.wav")
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(file_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(normalized_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if result.returncode != 0 or not normalized_path.exists():
                logger.warning(
                    "Audio normalize failed file=%s error=%s",
                    file_path,
                    (result.stderr or "").strip()[:240],
                )
                return file_path, False
            return normalized_path, True
        except FileNotFoundError:
            logger.warning("Audio normalize skipped: ffmpeg not found (%s)", ffmpeg_bin)
            return file_path, False
        except Exception as exc:
            logger.warning("Audio normalize failed file=%s error=%s", file_path, str(exc)[:240])
            return file_path, False

    def _build_report_image_variant(source_path: Path, image_id: str) -> tuple[Path, int]:
        """Build compressed report-image variant for PDF embedding."""
        report_path = source_path.with_name(f"{image_id}.report.jpg")
        try:
            from PIL import Image, ImageOps  # type: ignore

            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                image.save(
                    report_path,
                    format="JPEG",
                    quality=72,
                    optimize=True,
                    progressive=False,
                )
        except Exception:
            shutil.copyfile(source_path, report_path)
        return report_path, report_path.stat().st_size

    def _load_job_report_images(job_id: str) -> list[dict[str, str]]:
        """Load and normalize report image metadata for job from DB-backed image state."""
        images: list[dict[str, str]] = []
        for row in db_store.list_round_images(job_id, round_id=_ensure_job_record(job_id).latest_round_id or ""):
            meta = dict(row.get("metadata_json") or {})
            report_path = str(meta.get("report_image_path") or "").strip()
            stored_path = str(meta.get("stored_path") or row.get("artifact_path") or "").strip()
            candidate = Path(report_path) if report_path else Path(stored_path)
            if not candidate.exists():
                continue
            caption = str(
                row.get("caption")
                or meta.get("caption")
                or meta.get("caption_text")
                or ""
            ).strip()
            uploaded_at = str(meta.get("uploaded_at") or "").strip()
            images.append(
                {
                    "path": str(candidate),
                    "caption": caption,
                    "uploaded_at": uploaded_at,
                }
            )
        images.sort(key=lambda item: item.get("uploaded_at", ""))
        return images[:5]

    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        """Write JSON payload to disk with UTF-8 encoding."""
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_json(path: Path) -> Any:
        """Read JSON payload from disk, returning `None` on decode or existence errors."""
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _generate_summary(
        *,
        form_data: dict[str, Any],
        transcript: str,
    ) -> str:
        """Generate five-paragraph narrative summary from form+transcript."""
        from . import report_letter

        return report_letter.generate_summary(
            form_data=form_data,
            transcript=transcript,
        )

    def _generate_traq_pdf(
        *,
        form_data: dict[str, Any],
        output_path: Path,
    ) -> None:
        """Render overlay-filled TRAQ PDF to `output_path`."""
        from . import pdf_fill

        pdf_fill.generate_traq_pdf(form_data=form_data, output_path=output_path, flatten=True)

    def _transcribe_recording(
        file_path: Path,
        probe: dict[str, Any] | None = None,
    ) -> str:
        """Transcribe one audio recording, with optional normalization step.

        Returns:
            Raw transcript text from the configured OpenAI transcription model.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        model = os.environ.get("TRAQ_OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
        language = os.environ.get("TRAQ_OPENAI_TRANSCRIBE_LANGUAGE", "en")
        prompt = os.environ.get(
            "TRAQ_OPENAI_TRANSCRIBE_PROMPT",
            (
                "Arborist TRAQ field recording. Keep exact wording and numbers. "
                "Common terms: target one/two, mobile home unit, one times height, "
                "occupancy constant/frequent, dripline, not practical to move, "
                "restriction practical/not practical, rerouting with cones."
            ),
        )
        if file_path.stat().st_size > 25 * 1024 * 1024:
            raise RuntimeError(f"Recording exceeds 25MB limit: {file_path}")
        if _is_canonical_transcribe_audio(file_path, probe):
            transcribe_path, normalized = file_path, False
            logger.info("Transcribe normalize skipped: canonical wav16k mono pcm input")
        else:
            transcribe_path, normalized = _normalize_audio_for_transcription(file_path)
        _log_event(
            "TRANSCRIBE",
            "input file=%s normalized=%s",
            transcribe_path.name,
            normalized,
        )
        timeout_seconds = float(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_TIMEOUT", "90"))
        max_attempts = max(1, int(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_ATTEMPTS", "3")))
        backoff_seconds = float(os.environ.get("TRAQ_OPENAI_TRANSCRIBE_BACKOFF", "1.5"))
        client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=0)

        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                with transcribe_path.open("rb") as audio_file:
                    response = client.audio.transcriptions.create(
                        model=model,
                        file=audio_file,
                        language=language,
                        prompt=prompt,
                    )
                return response.text if hasattr(response, "text") else str(response)
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "[TRANSCRIBE] attempt %s/%s failed file=%s error=%s",
                    attempt,
                    max_attempts,
                    file_path.name,
                    exc,
                )
                if attempt < max_attempts:
                    time.sleep(backoff_seconds * attempt)
        raise RuntimeError(
            f"Transcription failed after {max_attempts} attempts for {file_path.name}"
        ) from last_exc

    def _transcript_cache_path(job_id: str, section_id: str, recording_id: str) -> Path:
        """Return exported transcript path for one recording."""
        return _section_dir(job_id, section_id) / "recordings" / f"{recording_id}.transcript.txt"

    def _save_recording_runtime_state(
        job_id: str,
        round_id: str,
        section_id: str,
        recording_id: str,
        meta: dict[str, Any],
    ) -> None:
        """Persist DB-authoritative recording runtime state and export transcript text."""
        existing = db_store.get_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
        )
        if not isinstance(existing, dict):
            return
        db_store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
            upload_status=str(existing.get("upload_status") or "uploaded"),
            content_type=existing.get("content_type"),
            duration_ms=existing.get("duration_ms"),
            artifact_path=existing.get("artifact_path"),
            metadata_json=meta,
        )
        transcript_text = str(meta.get("transcript_text") or "").strip()
        if transcript_text:
            _transcript_cache_path(job_id, section_id, recording_id).write_text(
                transcript_text,
                encoding="utf-8",
            )

    def _build_section_transcript(
        job_id: str,
        round_id: str,
        section_id: str,
        manifest: list[dict[str, Any]],
        issue_id: str | None = None,
        seen_recordings: set[str] | None = None,
        force_reprocess: bool = False,
        force_transcribe: bool = False,
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        """Build section transcript using DB-backed recording runtime state."""
        lines: list[str] = []
        used: list[str] = []
        failures: list[dict[str, Any]] = []
        local_seen: set[str] = set()
        for item in manifest:
            if item.get("kind") != "recording":
                continue
            if item.get("section_id") != section_id:
                continue
            if issue_id is not None and item.get("issue_id") != issue_id:
                continue
            rec_id = item.get("artifact_id") or "unknown"
            if rec_id in local_seen:
                continue
            if not force_reprocess and seen_recordings and rec_id in seen_recordings:
                continue
            meta = _recording_meta(job_id, round_id, section_id, rec_id)
            stored_path = meta.get("stored_path")
            if not stored_path:
                continue
            transcript = str(meta.get("transcript_text") or "").strip()
            if transcript and not force_transcribe:
                pass
            else:
                probe = meta.get("audio_probe") or {}
                _log_event(
                    "TRANSCRIBE",
                    (
                        "start job=%s section=%s recording=%s "
                        "bytes=%s codec=%s sr=%s ch=%s duration=%s format=%s ffprobe_error=%s"
                    ),
                    job_id,
                    section_id,
                    rec_id,
                    meta.get("bytes"),
                    probe.get("codec_name"),
                    probe.get("sample_rate"),
                    probe.get("channels"),
                    probe.get("duration"),
                    probe.get("format_name"),
                    probe.get("ffprobe_error"),
                )
                try:
                    transcript = _transcribe_recording(Path(stored_path), probe=probe).strip()
                    meta["transcript_text"] = transcript
                    meta["processed"] = True
                    meta.pop("transcription_error", None)
                    _save_recording_runtime_state(job_id, round_id, section_id, rec_id, meta)
                    if os.environ.get("TRAQ_LOG_RAW_TRANSCRIPTS", "0").strip() == "1":
                        _log_event(
                            "TRANSCRIBE",
                            "raw section=%s recording=%s text=%s",
                            section_id,
                            rec_id,
                            transcript[:800],
                        )
                    _log_event(
                        "TRANSCRIBE",
                        "ok section=%s recording=%s chars=%s",
                        section_id,
                        rec_id,
                        len(transcript),
                    )
                except Exception as exc:
                    logger.exception(
                        "[TRANSCRIBE] failed for job=%s section=%s recording=%s",
                        job_id,
                        section_id,
                        rec_id,
                    )
                    failures.append(
                        {
                            "section_id": section_id,
                            "recording_id": rec_id,
                            "error": str(exc),
                        }
                    )
                    meta["processed"] = False
                    meta["transcription_error"] = str(exc)
                    _save_recording_runtime_state(job_id, round_id, section_id, rec_id, meta)
                    local_seen.add(rec_id)
                    continue
            if transcript:
                lines.append(transcript)
                used.append(rec_id)
            local_seen.add(rec_id)
        if not lines:
            return "", [], failures
        return "\n\n".join(lines), used, failures

    def _process_round(
        job_id: str,
        round_id: str,
        record: JobRecord,
        base_review_override: dict[str, Any] | None = None,
        manifest_override: list[dict[str, Any]] | None = None,
        force_reprocess: bool = False,
        force_transcribe: bool = False,
    ) -> dict[str, Any]:
        """Process one round into a normalized review payload.

        Orchestrates transcription, section extraction, data merges, narrative
        generation, and persistence of the round review payload.
        """
        round_record = record.rounds[round_id]
        manifest = manifest_override if manifest_override is not None else round_record.manifest
        section_ids = sorted(
            {
                item.get("section_id")
                for item in manifest
                if item.get("section_id")
            }
        )
        issue_ids_by_section: dict[str, set[str]] = {}
        for item in manifest:
            section_id = item.get("section_id")
            issue_id = item.get("issue_id")
            if not section_id or not issue_id:
                continue
            issue_ids_by_section.setdefault(str(section_id), set()).add(str(issue_id))
        base_review = (
            base_review_override
            if base_review_override is not None
            else _load_latest_review(job_id, exclude_round_id=round_id)
        )
        section_recordings: dict[str, list[str]] = dict(
            base_review.get("section_recordings") or {}
        )
        delta_transcripts: dict[str, str] = {}
        transcription_failures: list[dict[str, Any]] = []
        for section_id in section_ids:
            seen = set(section_recordings.get(section_id) or [])
            transcript, used, failures = _build_section_transcript(
                job_id,
                round_id,
                section_id,
                manifest,
                seen_recordings=seen,
                force_reprocess=force_reprocess,
                force_transcribe=force_transcribe,
            )
            delta_transcripts[section_id] = transcript
            if failures:
                transcription_failures.extend(failures)
            if used:
                section_recordings[section_id] = list(seen.union(used))
        earliest_recorded_at: datetime | None = None
        for item in manifest:
            if item.get("kind") != "recording":
                continue
            recorded_raw = item.get("recorded_at")
            if not recorded_raw:
                continue
            try:
                recorded_dt = datetime.fromisoformat(recorded_raw)
            except ValueError:
                continue
            if earliest_recorded_at is None or recorded_dt < earliest_recorded_at:
                earliest_recorded_at = recorded_dt

        def _narrative_paragraphs() -> list[str]:
            return []

        base_form = base_review.get("draft_form") or {}
        draft_form: dict[str, Any] = {
            "schema_name": base_form.get("schema_name", "demo"),
            "schema_version": base_form.get("schema_version", "0.0"),
            "data": _normalize_form_schema(dict(base_form.get("data") or {})),
        }
        section_transcripts: dict[str, str] = dict(
            base_review.get("section_transcripts") or {}
        )
        issue_transcripts: dict[str, dict[str, str]] = dict(
            base_review.get("issue_transcripts") or {}
        )
        issue_recordings: dict[str, dict[str, list[str]]] = dict(
            base_review.get("issue_recordings") or {}
        )
        if (
            "client_tree_details" in delta_transcripts
            and delta_transcripts["client_tree_details"].strip()
        ):
            extraction = _run_extraction_logged("client_tree_details", 
                delta_transcripts["client_tree_details"],
            )
            details = extraction.model_dump()
            if earliest_recorded_at is not None:
                if not details.get("date"):
                    details["date"] = earliest_recorded_at.strftime("%Y-%m-%d")
                if not details.get("time"):
                    details["time"] = earliest_recorded_at.strftime("%H:%M")
            prior_details = draft_form["data"].get("client_tree_details") or {}
            draft_form["data"]["client_tree_details"] = _merge_client_tree_details(
                prior_details,
                details,
            )
        if "site_factors" in delta_transcripts and delta_transcripts["site_factors"].strip():
            extraction = _run_extraction_logged("site_factors", delta_transcripts["site_factors"])
            prior_site = draft_form["data"].get("site_factors") or {}
            draft_form["data"]["site_factors"] = _merge_site_factors(
                prior_site,
                extraction.model_dump(),
            )
        if (
            "tree_health_and_species" in delta_transcripts
            and delta_transcripts["tree_health_and_species"].strip()
        ):
            extraction = _run_extraction_logged("tree_health_and_species", 
                delta_transcripts["tree_health_and_species"],
            )
            prior_health = draft_form["data"].get("tree_health_and_species") or {}
            draft_form["data"]["tree_health_and_species"] = _merge_tree_health_and_species(
                prior_health,
                extraction.model_dump(),
            )
        if "load_factors" in delta_transcripts and delta_transcripts["load_factors"].strip():
            extraction = _run_extraction_logged("load_factors", delta_transcripts["load_factors"])
            prior_load = draft_form["data"].get("load_factors") or {}
            draft_form["data"]["load_factors"] = _merge_load_factors(
                prior_load,
                extraction.model_dump(),
            )
        if "crown_and_branches" in delta_transcripts and delta_transcripts["crown_and_branches"].strip():
            extraction = _run_extraction_logged("crown_and_branches", 
                delta_transcripts["crown_and_branches"],
            )
            prior_crown = draft_form["data"].get("crown_and_branches") or {}
            draft_form["data"]["crown_and_branches"] = _merge_crown_and_branches(
                prior_crown,
                extraction.model_dump(),
            )
        if "trunk" in delta_transcripts and delta_transcripts["trunk"].strip():
            extraction = _run_extraction_logged("trunk", delta_transcripts["trunk"])
            prior_trunk = draft_form["data"].get("trunk") or {}
            draft_form["data"]["trunk"] = _merge_trunk(
                prior_trunk,
                extraction.model_dump(),
            )
        if (
            "roots_and_root_collar" in delta_transcripts
            and delta_transcripts["roots_and_root_collar"].strip()
        ):
            extraction = _run_extraction_logged("roots_and_root_collar", 
                delta_transcripts["roots_and_root_collar"],
            )
            prior_roots = draft_form["data"].get("roots_and_root_collar") or {}
            draft_form["data"]["roots_and_root_collar"] = _merge_roots_and_root_collar(
                prior_roots,
                extraction.model_dump(),
            )
        if (
            "target_assessment" in delta_transcripts
            and delta_transcripts["target_assessment"].strip()
        ):
            extraction = _run_extraction_logged("target_assessment", 
                delta_transcripts["target_assessment"],
            )
            prior_targets = draft_form["data"].get("target_assessment") or {}
            draft_form["data"]["target_assessment"] = _merge_target_assessment(
                prior_targets,
                extraction.model_dump(),
            )
        if (
            "notes_explanations_descriptions" in delta_transcripts
            and delta_transcripts["notes_explanations_descriptions"].strip()
        ):
            extraction = _run_extraction_logged(
                "notes_explanations_descriptions",
                delta_transcripts["notes_explanations_descriptions"],
            )
            prior_notes = draft_form["data"].get("notes_explanations_descriptions") or {}
            draft_form["data"]["notes_explanations_descriptions"] = (
                _merge_notes_explanations_descriptions(
                    prior_notes,
                    extraction.model_dump(),
                )
            )
        if (
            "mitigation_options" in delta_transcripts
            and delta_transcripts["mitigation_options"].strip()
        ):
            extraction = _run_extraction_logged(
                "mitigation_options",
                delta_transcripts["mitigation_options"],
            )
            prior_mitigation = draft_form["data"].get("mitigation_options") or {}
            draft_form["data"]["mitigation_options"] = _merge_mitigation_options(
                prior_mitigation,
                extraction.model_dump(),
            )
        if (
            "overall_tree_risk_rating" in delta_transcripts
            and delta_transcripts["overall_tree_risk_rating"].strip()
        ):
            extraction = _run_extraction_logged(
                "overall_tree_risk_rating",
                delta_transcripts["overall_tree_risk_rating"],
            )
            prior_rating = draft_form["data"].get("overall_tree_risk_rating") or {}
            draft_form["data"]["overall_tree_risk_rating"] = _merge_flat_section(
                prior_rating,
                extraction.model_dump(),
            )
        if "work_priority" in delta_transcripts and delta_transcripts["work_priority"].strip():
            extraction = _run_extraction_logged("work_priority", delta_transcripts["work_priority"])
            prior_priority = draft_form["data"].get("work_priority") or {}
            draft_form["data"]["work_priority"] = _merge_flat_section(
                prior_priority,
                extraction.model_dump(),
            )
        if (
            "overall_residual_risk" in delta_transcripts
            and delta_transcripts["overall_residual_risk"].strip()
        ):
            extraction = _run_extraction_logged(
                "overall_residual_risk",
                delta_transcripts["overall_residual_risk"],
            )
            prior_residual = draft_form["data"].get("overall_residual_risk") or {}
            draft_form["data"]["overall_residual_risk"] = _merge_flat_section(
                prior_residual,
                extraction.model_dump(),
            )
        if (
            "recommended_inspection_interval" in delta_transcripts
            and delta_transcripts["recommended_inspection_interval"].strip()
        ):
            extraction = _run_extraction_logged(
                "recommended_inspection_interval",
                delta_transcripts["recommended_inspection_interval"],
            )
            prior_interval = draft_form["data"].get("recommended_inspection_interval") or {}
            draft_form["data"]["recommended_inspection_interval"] = _merge_flat_section(
                prior_interval,
                extraction.model_dump(),
            )
        if "data_status" in delta_transcripts and delta_transcripts["data_status"].strip():
            extraction = _run_extraction_logged("data_status", delta_transcripts["data_status"])
            prior_status = draft_form["data"].get("data_status") or {}
            draft_form["data"]["data_status"] = _merge_flat_section(
                prior_status,
                extraction.model_dump(),
            )
        if (
            "advanced_assessment_needed" in delta_transcripts
            and delta_transcripts["advanced_assessment_needed"].strip()
        ):
            extraction = _run_extraction_logged(
                "advanced_assessment_needed",
                delta_transcripts["advanced_assessment_needed"],
            )
            prior_needed = draft_form["data"].get("advanced_assessment_needed") or {}
            draft_form["data"]["advanced_assessment_needed"] = _merge_flat_section(
                prior_needed,
                extraction.model_dump(),
            )
        if (
            "advanced_assessment_type_reason" in delta_transcripts
            and delta_transcripts["advanced_assessment_type_reason"].strip()
        ):
            extraction = _run_extraction_logged(
                "advanced_assessment_type_reason",
                delta_transcripts["advanced_assessment_type_reason"],
            )
            prior_reason = draft_form["data"].get("advanced_assessment_type_reason") or {}
            draft_form["data"]["advanced_assessment_type_reason"] = _merge_flat_section(
                prior_reason,
                extraction.model_dump(),
            )
        if (
            "inspection_limitations" in delta_transcripts
            and delta_transcripts["inspection_limitations"].strip()
        ):
            extraction = _run_extraction_logged(
                "inspection_limitations",
                delta_transcripts["inspection_limitations"],
            )
            prior_limits = draft_form["data"].get("inspection_limitations") or {}
            draft_form["data"]["inspection_limitations"] = _merge_flat_section(
                prior_limits,
                extraction.model_dump(),
            )
        if (
            "inspection_limitations_describe" in delta_transcripts
            and delta_transcripts["inspection_limitations_describe"].strip()
        ):
            extraction = _run_extraction_logged(
                "inspection_limitations_describe",
                delta_transcripts["inspection_limitations_describe"],
            )
            prior_limits_desc = draft_form["data"].get("inspection_limitations_describe") or {}
            draft_form["data"]["inspection_limitations_describe"] = _merge_flat_section(
                prior_limits_desc,
                extraction.model_dump(),
            )

        for section_id, delta_text in delta_transcripts.items():
            if not delta_text:
                continue
            existing_text = section_transcripts.get(section_id, "")
            if existing_text:
                if delta_text in existing_text:
                    continue
                section_transcripts[section_id] = f"{existing_text}\n\n{delta_text}"
            else:
                section_transcripts[section_id] = delta_text

        for section_id in section_ids:
            issue_ids = issue_ids_by_section.get(section_id) or set()
            if not issue_ids:
                continue
            for issue_id in sorted(issue_ids):
                transcript, used, failures = _build_section_transcript(
                    job_id,
                    round_id,
                    section_id,
                    manifest,
                    issue_id=issue_id,
                    seen_recordings=set(
                        (issue_recordings.get(section_id) or {})
                        .get(issue_id, [])
                        or []
                    ),
                    force_reprocess=force_reprocess,
                    force_transcribe=force_transcribe,
                )
                if failures:
                    transcription_failures.extend(failures)
                if not transcript:
                    continue
                issue_transcripts.setdefault(section_id, {})
                issue_recordings.setdefault(section_id, {})
                existing_issue_text = issue_transcripts[section_id].get(issue_id, "")
                if existing_issue_text and transcript in existing_issue_text:
                    continue
                if existing_issue_text:
                    issue_transcripts[section_id][issue_id] = (
                        f"{existing_issue_text}\n\n{transcript}"
                    )
                else:
                    issue_transcripts[section_id][issue_id] = transcript
                if used:
                    existing_used = issue_recordings[section_id].get(issue_id, [])
                    issue_recordings[section_id][issue_id] = list(
                        sorted(set(existing_used).union(set(used)))
                    )

        def _empty_risk_row(section_id: str, tree_part: str) -> dict[str, Any]:
            return {
                "section_id": section_id,
                "issue_id": None,
                "tree_part": tree_part,
                "condition": None,
                "part_size": None,
                "fall_distance": None,
                "target_number": None,
                "target_label": None,
                "target_protection": None,
                "failure_likelihood": None,
                "impact_likelihood": None,
                "consequences": None,
                "risk_rating": None,
            }

        def _merge_risk_row(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
            merged = dict(existing)
            for key, value in incoming.items():
                if merged.get(key) in (None, "") and value not in (None, ""):
                    merged[key] = value
            return merged

        def _extract_risk_rows(text: str) -> list[dict[str, Any]]:
            if not isinstance(text, str) or not text.strip():
                return []
            extraction = _run_extraction_logged("risk_categorization", text)
            extracted = extraction.model_dump()
            rows = extracted.get("rows") or []
            if not isinstance(rows, list):
                return []
            normalized = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                normalized.append(
                    {
                        "condition_number": row.get("condition_number"),
                        "tree_part": row.get("tree_part"),
                        "condition": row.get("condition"),
                        "part_size": row.get("part_size"),
                        "fall_distance": row.get("fall_distance"),
                        "target_number": row.get("target_number"),
                        "target_protection": row.get("target_protection"),
                        "failure_likelihood": row.get("failure_likelihood"),
                        "impact_likelihood": row.get("impact_likelihood"),
                        "failure_and_impact": row.get("failure_and_impact"),
                        "consequences": row.get("consequences"),
                        "risk_rating": row.get("risk_rating"),
                    }
                )
            return normalized

        existing_rows = list(draft_form["data"].get("risk_categorization") or [])
        section_id = "risk_categorization"
        issue_map = issue_transcripts.get(section_id)
        issue_text = ""
        if isinstance(issue_map, dict) and issue_map:
            issue_text = "\n\n".join(
                text for text in issue_map.values() if isinstance(text, str) and text.strip()
            )
        delta_text = delta_transcripts.get(section_id) or ""
        combined_text = "\n\n".join(
            part for part in [issue_text, delta_text] if isinstance(part, str) and part.strip()
        )

        try:
            incoming_rows = _extract_risk_rows(combined_text)
        except Exception:
            logger.exception("Risk categorization extraction failed", extra={"section_id": section_id})
            incoming_rows = []

        merged_rows: list[dict[str, Any]] = []
        for idx, incoming in enumerate(incoming_rows):
            if idx < len(existing_rows):
                merged_rows.append(_merge_risk_row(existing_rows[idx], incoming))
            else:
                merged_rows.append(incoming)
        if len(existing_rows) > len(merged_rows):
            merged_rows.extend(existing_rows[len(merged_rows):])

        draft_form["data"]["risk_categorization"] = merged_rows

        narrative = ""
        combined_transcript = "\n\n".join(
            f"[{section_id}]\n{text}".strip()
            for section_id, text in section_transcripts.items()
            if text
        )
        try:
            narrative = _generate_summary(
                form_data=draft_form.get("data", {}),
                transcript=combined_transcript,
            )
        except Exception:
            logger.exception("Failed to generate summary narrative")
            narrative = "\n\n".join(_narrative_paragraphs())

        normalized_data = _normalize_form_schema(draft_form.get("data") or {})
        client_tree_details = dict(normalized_data.get("client_tree_details") or {})
        if record.tree_number is not None:
            client_tree_details["tree_number"] = str(record.tree_number)
            normalized_data["client_tree_details"] = client_tree_details
        draft_form["data"] = normalized_data
        review_payload = {
            "round_id": round_id,
            "server_revision_id": round_record.server_revision_id,
            "transcript": "\n\n".join(
                f"[{section_id}]\n{text}".strip()
                for section_id, text in section_transcripts.items()
                if text
            ),
            "section_recordings": section_recordings,
            "section_transcripts": section_transcripts,
            "issue_recordings": issue_recordings,
            "issue_transcripts": issue_transcripts,
            "draft_form": draft_form,
            "draft_narrative": narrative,
            "form": normalized_data,
            "narrative": narrative,
            "tree_number": record.tree_number,
            "images": [],
            "transcription_failures": transcription_failures,
        }
        logger.info(
            "[ROUND] job=%s round=%s sections=%s transcript_sections=%s failures=%s",
            job_id,
            round_id,
            len(section_ids),
            len([s for s, t in section_transcripts.items() if t]),
            len(transcription_failures),
        )
        _save_round_record(job_id, round_record, review_payload=review_payload)
        return review_payload

    @app.get("/health")
    def health() -> dict:
        """Health check endpoint for connectivity and storage-root visibility."""
        logger.info("GET /health")
        return {
            "status": "ok",
            "storage_root": str(settings.storage_root),
        }

    @app.post("/v1/auth/register-device")
    def register_device(payload: RegisterDeviceRequest) -> dict[str, Any]:
        """Register or refresh a device record in pending/approved workflow."""
        if not payload.device_id.strip():
            raise HTTPException(status_code=400, detail="device_id is required")
        device = _register_device_record(
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

    @app.post("/v1/auth/token")
    def issue_device_token(payload: IssueTokenRequest) -> dict[str, Any]:
        """Issue bearer token for an approved device."""
        device_id = (payload.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        device = _get_device_record(device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        status = str(device.get("status") or "")
        if status != "approved":
            raise HTTPException(status_code=403, detail=f"Device status is {status or 'unknown'}")
        try:
            issued = _issue_device_token_record(
                device_id=device_id,
                ttl_seconds=payload.ttl_seconds or 604800,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Token issuance failed") from exc
        return {"ok": True, **issued}

    @app.get("/v1/auth/device/{device_id}/status")
    def get_device_status(device_id: str) -> dict[str, Any]:
        """Return registration/approval status for a device id."""
        device = _get_device_record(device_id.strip())
        if not device:
            return {"ok": True, "device_id": device_id, "status": "not_registered"}
        return {
            "ok": True,
            "device_id": device.get("device_id"),
            "status": device.get("status"),
            "role": device.get("role"),
            "updated_at": device.get("updated_at"),
        }

    @app.get("/v1/profile", response_model=ProfilePayload)
    def get_profile(x_api_key: str | None = Header(default=None)) -> ProfilePayload:
        """Load the DB-authoritative profile for the current auth identity."""
        auth = require_api_key(x_api_key)
        payload = _load_runtime_profile(_identity_key(auth, x_api_key))
        if isinstance(payload, dict):
            return ProfilePayload(**payload)
        return ProfilePayload()

    @app.put("/v1/profile", response_model=ProfilePayload)
    def put_profile(
        payload: ProfilePayload,
        x_api_key: str | None = Header(default=None),
    ) -> ProfilePayload:
        """Persist the DB-authoritative profile for the current auth identity."""
        auth = require_api_key(x_api_key)
        stored = _save_runtime_profile(_identity_key(auth, x_api_key), payload.model_dump())
        return ProfilePayload(**stored)

    @app.post("/v1/jobs", response_model=CreateJobResponse)
    def create_job(
        payload: CreateJobRequest,
        x_api_key: str | None = Header(default=None),
    ) -> CreateJobResponse:
        """Create a new server job and auto-assign it to calling device."""
        auth = require_api_key(x_api_key)
        while True:
            job_id = f"job_{uuid.uuid4().hex[:12]}"
            if job_id not in jobs:
                break
        job_number = _next_job_number()
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
        created = job_mutation_service.create_job(
            job_id=job_id,
            job_number=job_number,
            status="DRAFT",
            customer_id=customer["customer_id"],
            billing_profile_id=billing["billing_profile_id"] if billing else None,
            tree_number=payload.tree_number,
            job_name=payload.job_name,
            job_address=payload.job_address,
            location_notes=payload.location_notes,
        )
        record = _load_job_record(job_id)
        if record is not None:
            jobs[job_id] = record
        if auth.device_id and not auth.is_admin:
            try:
                _assign_job_record(
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

    @app.get("/v1/customers", response_model=list[CustomerLookupRow])
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

    @app.get("/v1/billing-profiles", response_model=list[BillingProfileLookupRow])
    def list_billing_profile_lookup_rows(
        query: str | None = None,
        x_api_key: str | None = Header(default=None),
    ) -> list[BillingProfileLookupRow]:
        """List reusable billing defaults for Start New Job prefill."""
        require_api_key(x_api_key)
        rows = customer_service.list_billing_profiles(search=query)
        return [BillingProfileLookupRow(**row) for row in rows]

    @app.get("/v1/jobs/assigned", response_model=list[AssignedJob])
    def list_assigned_jobs(
        x_api_key: str | None = Header(default=None),
    ) -> list[AssignedJob]:
        """List jobs assigned to the caller (or all for admin)."""
        auth = require_api_key(x_api_key)
        logger.info("GET /v1/jobs/assigned")
        assignments = _list_job_assignments()
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
            resolved = _resolve_assigned_job(job_id)
            if resolved is not None:
                out.append(resolved)
        return out

    @app.get("/v1/jobs/{job_id}", response_model=StatusResponse)
    def get_job(job_id: str, x_api_key: str | None = Header(default=None)) -> StatusResponse:
        """Return current job status and latest round revision info."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record = _ensure_job_record(job_id)
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
            tree_number=record.tree_number,
            review_ready=review_ready,
            server_revision_id=server_revision_id,
        )

    @app.post("/v1/jobs/{job_id}/rounds", response_model=CreateRoundResponse)
    def create_round(job_id: str, x_api_key: str | None = Header(default=None)) -> CreateRoundResponse:
        """Create a new DRAFT round for an assigned job."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record = _ensure_job_record(job_id)
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
        round_record = RoundRecord(round_id=round_id, status="DRAFT")
        record.rounds[round_id] = round_record
        record.latest_round_id = round_id
        record.latest_round_status = "DRAFT"
        record.status = "DRAFT"
        _save_job_record(record)
        _save_round_record(job_id, round_record)
        logger.info("POST /v1/jobs/%s/rounds -> %s", job_id, round_id)
        return CreateRoundResponse(round_id=round_id, status="DRAFT")

    @app.put("/v1/jobs/{job_id}/rounds/{round_id}/manifest")
    def set_manifest(
        job_id: str,
        round_id: str,
        manifest: list[ManifestItem],
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Replace round manifest (recordings/images metadata list)."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record, round_record = _ensure_round_record(job_id, round_id)
        _assert_round_editable(record, round_id, auth, allow_correction=True)
        round_record.manifest = [item.model_dump() for item in manifest]
        _save_round_record(job_id, round_record)
        logger.info(
            "PUT /v1/jobs/%s/rounds/%s/manifest (%s items)",
            job_id,
            round_id,
            len(manifest),
        )
        return {"ok": True, "round_id": round_id, "manifest_count": len(manifest)}

    @app.post("/v1/jobs/{job_id}/rounds/{round_id}/submit")
    def submit_round(
        job_id: str,
        round_id: str,
        submit_payload: SubmitRoundRequest | None = Body(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Submit a round for processing and return review-ready status."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record, round_record = _ensure_round_record(job_id, round_id)
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
            resolved_tree_number = _resolve_server_tree_number(
                record,
                requested_tree_number=requested_tree_number,
            )
            submit_payload.form = apply_tree_number_to_form(
                submit_payload.form,
                resolved_tree_number,
            )
        _assert_round_editable(record, round_id, auth, allow_correction=True)
        round_record.status = "SUBMITTED_FOR_PROCESSING"
        record.latest_round_status = round_record.status
        record.status = "SUBMITTED_FOR_PROCESSING"
        _save_job_record(record)
        _save_round_record(job_id, round_record)
        logger.info("POST /v1/jobs/%s/rounds/%s/submit", job_id, round_id)
        round_record.server_revision_id = round_record.server_revision_id or f"rev_{round_id}"
        existing_round_review: dict[str, Any] = {}
        persisted_round = db_store.get_job_round(job_id, round_id)
        if isinstance((persisted_round or {}).get("review_payload"), dict):
            existing_round_review = dict(persisted_round["review_payload"])

        # Recovery path: if in-memory round manifest is empty (e.g. after restart),
        # reload persisted manifest from disk before deciding there is no work.
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

        # Secondary recovery: if manifest is still empty but recordings exist on
        # disk, synthesize a processing manifest from server storage.
        if not round_record.manifest:
            synthesized = _build_reprocess_manifest(job_id, round_record, existing_round_review)
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
            _save_job_record(record)
            _save_round_record(job_id, round_record, review_payload=existing_round_review)
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
                base_review = _load_latest_review(job_id, exclude_round_id=round_id)
            draft_form = base_review.get("draft_form") or {}
            if submit_payload and submit_payload.form:
                form_patch = submit_payload.form
                if (
                    isinstance(draft_form.get("data"), dict)
                    and "data" not in form_patch
                ):
                    form_patch = {"data": form_patch}
                draft_form = _apply_form_patch(draft_form, form_patch)
            draft_form_data = dict(draft_form.get("data") or {})
            draft_form["data"] = _normalize_form_schema(draft_form_data)
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
            review_payload = _process_round(job_id, round_id, record, base_review_override)
            # Re-apply client edits after extraction merges so manual edits always win.
            if has_client_patch and submit_payload:
                updated_review = dict(review_payload)
                draft_form = dict(updated_review.get("draft_form") or {})
                if submit_payload.form:
                    form_patch = submit_payload.form
                    if (
                        isinstance(draft_form.get("data"), dict)
                        and "data" not in form_patch
                    ):
                        form_patch = {"data": form_patch}
                    draft_form = _apply_form_patch(draft_form, form_patch)
                draft_data = _normalize_form_schema(dict(draft_form.get("data") or {}))
                draft_form["data"] = draft_data
                updated_review["draft_form"] = draft_form
                updated_review["form"] = draft_data
                updated_review["tree_number"] = record.tree_number
                if submit_payload.narrative:
                    narrative_text = submit_payload.narrative.get("text")
                    if narrative_text is not None:
                        updated_review["draft_narrative"] = narrative_text
                        updated_review["narrative"] = narrative_text
                _save_round_record(job_id, round_record, review_payload=updated_review)
                review_payload = updated_review
            round_record.status = "REVIEW_RETURNED"
            record.latest_round_status = round_record.status
            record.status = "REVIEW_RETURNED"
            _save_job_record(record)
            _save_round_record(job_id, round_record, review_payload=review_payload)
        except Exception as exc:
            logger.exception("Round processing failed for %s/%s", job_id, round_id)
            round_record.status = "FAILED"
            record.latest_round_status = "FAILED"
            record.status = "FAILED"
            _save_job_record(record)
            _save_round_record(job_id, round_record)
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
        total_recordings = sum(
            1 for item in manifest_items if item.get("kind") == "recording"
        )
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

    @app.post("/v1/jobs/{job_id}/rounds/{round_id}/reprocess")
    def reprocess_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Force re-transcribe/re-extract all server-stored round recordings."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record, round_record = _ensure_round_record(job_id, round_id)
        persisted_round = db_store.get_job_round(job_id, round_id)
        round_review = (persisted_round or {}).get("review_payload")
        if not isinstance(round_review, dict):
            raise HTTPException(status_code=404, detail="Review not found for round")
        manifest = _build_reprocess_manifest(job_id, round_record, round_review)
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
        _save_job_record(record)
        round_record.server_revision_id = round_record.server_revision_id or f"rev_{round_id}"
        base_review_override = _load_latest_review(job_id, exclude_round_id=round_id)
        review_payload: dict[str, Any] = {}
        try:
            review_payload = _process_round(
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
            _save_job_record(record)
        except Exception:
            logger.exception("Round reprocess failed for %s/%s", job_id, round_id)
            round_record.status = "FAILED"
            record.latest_round_status = "FAILED"
            record.status = "FAILED"
            _save_job_record(record)
            raise HTTPException(status_code=500, detail="Round reprocess failed")

        return {
            "ok": True,
            "round_id": round_id,
            "status": round_record.status,
            "tree_number": record.tree_number,
            "manifest_count": len(manifest),
            "transcription_failures": review_payload.get("transcription_failures") or [],
        }

    @app.post("/v1/admin/jobs/{job_id}/rounds/{round_id}/reopen")
    def admin_reopen_round(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint to reopen round back to DRAFT state."""
        require_api_key(x_api_key, required_role="admin")
        record = _ensure_job_record(job_id)
        if not record or round_id not in record.rounds:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds[round_id]
        round_record.status = "DRAFT"
        record.latest_round_id = round_id
        record.latest_round_status = "DRAFT"
        record.status = "DRAFT"
        _save_job_record(record)
        logger.info("POST /v1/admin/jobs/%s/rounds/%s/reopen", job_id, round_id)
        return {"ok": True, "job_id": job_id, "round_id": round_id, "status": "DRAFT"}

    @app.get("/v1/admin/jobs/assignments")
    def admin_list_job_assignments(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint listing current job assignments."""
        require_api_key(x_api_key, required_role="admin")
        return {"ok": True, "assignments": _list_job_assignments()}

    @app.post("/v1/admin/jobs/{job_id}/assign")
    def admin_assign_job(
        job_id: str,
        payload: AssignJobRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint assigning/reassigning a job to device."""
        require_api_key(x_api_key, required_role="admin")
        if _ensure_job_record(job_id) is None:
            raise HTTPException(status_code=404, detail="Job not found")
        device_id = (payload.device_id or "").strip()
        if not device_id:
            raise HTTPException(status_code=400, detail="device_id is required")
        try:
            row = _assign_job_record(
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

    @app.post("/v1/admin/jobs/{job_id}/unassign")
    def admin_unassign_job(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint removing job assignment."""
        require_api_key(x_api_key, required_role="admin")
        try:
            removed = _unassign_job_record(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        logger.info("POST /v1/admin/jobs/%s/unassign", job_id)
        return {"ok": True, "removed": removed}

    @app.post("/v1/admin/jobs/{job_id}/status")
    def admin_set_job_status(
        job_id: str,
        payload: AdminJobStatusRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Admin endpoint forcing job status update."""
        require_api_key(x_api_key, required_role="admin")
        record = _ensure_job_record(job_id)
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
                round_record = RoundRecord(
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
        _save_job_record(record)
        return {
            "ok": True,
            "job_id": job_id,
            "status": record.status,
            "latest_round_id": record.latest_round_id,
            "latest_round_status": record.latest_round_status,
        }

    @app.put("/v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}")
    async def upload_recording(
        job_id: str,
        section_id: str,
        recording_id: str,
        request: Request,
        content_type: str | None = Header(default=None, alias="Content-Type"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record = _ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        _assert_job_editable(record, auth, allow_correction=True)
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Empty recording payload")
        recordings_dir = _section_dir(job_id, section_id) / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        ext = _guess_extension(content_type, ".m4a")
        file_path = recordings_dir / f"{recording_id}{ext}"
        file_path.write_bytes(payload)
        audio_probe = _probe_audio_metadata(file_path)
        meta = {
            "recording_id": recording_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": str(file_path),
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "audio_probe": audio_probe,
        }
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for recording upload")
        db_store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
            upload_status="uploaded",
            content_type=content_type,
            duration_ms=audio_probe.get("duration_ms"),
            artifact_path=str(file_path),
            metadata_json=meta,
        )
        _write_json(recordings_dir / f"{recording_id}.meta.json", meta)
        _log_event(
            "RECORDING",
            (
                "PUT /v1/jobs/%s/sections/%s/recordings/%s "
                "content_type=%s bytes=%s codec=%s sr=%s ch=%s "
                "duration=%s format=%s ffprobe_error=%s"
            ),
            job_id,
            section_id,
            recording_id,
            content_type,
            len(payload),
            audio_probe.get("codec_name"),
            audio_probe.get("sample_rate"),
            audio_probe.get("channels"),
            audio_probe.get("duration"),
            audio_probe.get("format_name"),
            audio_probe.get("ffprobe_error"),
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "recording_id": recording_id,
            "bytes": len(payload),
        }

    @app.put("/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}")
    async def upload_image(
        job_id: str,
        section_id: str,
        image_id: str,
        request: Request,
        content_type: str | None = Header(default=None, alias="Content-Type"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        if section_id != JOB_PHOTOS_SECTION_ID:
            raise HTTPException(
                status_code=400,
                detail=f"Images must use section_id='{JOB_PHOTOS_SECTION_ID}'",
            )
        record = _ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        _assert_job_editable(record, auth, allow_correction=True)
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Empty image payload")
        images_dir = _section_dir(job_id, section_id) / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for image upload")
        existing_ids = {
            str(row.get("image_id") or "")
            for row in db_store.list_round_images(job_id, round_id)
            if str(row.get("section_id") or "") == section_id
        }
        if image_id not in existing_ids and len(existing_ids) >= 5:
            raise HTTPException(status_code=400, detail="Maximum 5 images per job")
        ext = _guess_extension(content_type, ".jpg")
        file_path = images_dir / f"{image_id}{ext}"
        file_path.write_bytes(payload)
        report_path, report_bytes = _build_report_image_variant(file_path, image_id)
        meta = {
            "image_id": image_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": str(file_path),
            "report_image_path": str(report_path),
            "report_bytes": report_bytes,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
        }
        db_store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
            upload_status="uploaded",
            artifact_path=str(file_path),
            metadata_json=meta,
        )
        _write_json(images_dir / f"{image_id}.meta.json", meta)
        _log_event(
            "IMAGE",
            "upload job=%s section=%s image=%s bytes=%s report_bytes=%s",
            job_id,
            section_id,
            image_id,
            len(payload),
            report_bytes,
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "image_id": image_id,
            "bytes": len(payload),
        }

    @app.patch("/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}")
    def patch_image(
        job_id: str,
        section_id: str,
        image_id: str,
        payload: dict[str, Any],
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Update image metadata (caption/GPS) for stored job photo."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        if section_id != JOB_PHOTOS_SECTION_ID:
            raise HTTPException(
                status_code=400,
                detail=f"Images must use section_id='{JOB_PHOTOS_SECTION_ID}'",
            )
        record = _ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        _assert_job_editable(record, auth, allow_correction=True)
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for image patch")
        existing = db_store.get_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
        )
        if not isinstance(existing, dict):
            raise HTTPException(status_code=404, detail="Image not found")
        meta = dict(existing.get("metadata_json") or {})
        meta.update(payload)
        meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
        db_store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
            upload_status=str(existing.get("upload_status") or "uploaded"),
            caption=str(payload.get("caption") or meta.get("caption") or "").strip() or None,
            latitude=str((payload.get("gps") or {}).get("latitude") or payload.get("latitude") or meta.get("latitude") or "").strip() or None,
            longitude=str((payload.get("gps") or {}).get("longitude") or payload.get("longitude") or meta.get("longitude") or "").strip() or None,
            artifact_path=str(existing.get("artifact_path") or meta.get("stored_path") or "").strip() or None,
            metadata_json=meta,
        )
        images_dir = _section_dir(job_id, section_id) / "images"
        _write_json(images_dir / f"{image_id}.meta.json", meta)
        _log_event(
            "IMAGE",
            "patch job=%s section=%s image=%s keys=%s",
            job_id,
            section_id,
            image_id,
            sorted(payload.keys()),
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "image_id": image_id,
            "payload": payload,
        }

    @app.get("/v1/jobs/{job_id}/rounds/{round_id}/review")
    def get_review(
        job_id: str,
        round_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return cached/normalized review payload for a processed round."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record = _ensure_job_record(job_id)
        if not record or round_id not in record.rounds:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds[round_id]
        if not round_record.server_revision_id:
            round_record.server_revision_id = f"rev_{round_id}"
        record.latest_round_status = "REVIEW_RETURNED"
        record.status = "REVIEW_RETURNED"
        round_record.status = "REVIEW_RETURNED"
        _save_job_record(record)
        persisted_round = db_store.get_job_round(job_id, round_id)
        payload = (persisted_round or {}).get("review_payload")
        if isinstance(payload, dict):
            logger.info("GET /v1/jobs/%s/rounds/%s/review (cached)", job_id, round_id)
            payload = dict(payload)
            if "form" not in payload:
                draft_form = payload.get("draft_form") or {}
                if isinstance(draft_form, dict):
                    payload["form"] = draft_form.get("data", {})
            if isinstance(payload.get("draft_form"), dict):
                draft_form = dict(payload.get("draft_form") or {})
                draft_data = _normalize_form_schema(dict(draft_form.get("data") or {}))
                draft_data = dict(draft_data)
                client_tree_details = dict(draft_data.get("client_tree_details") or {})
                if record.tree_number is not None:
                    client_tree_details["tree_number"] = str(record.tree_number)
                    draft_data["client_tree_details"] = client_tree_details
                draft_form["data"] = draft_data
                payload["draft_form"] = draft_form
                payload["form"] = draft_data
            elif isinstance(payload.get("form"), dict):
                form_data = _normalize_form_schema(dict(payload.get("form") or {}))
                form_data = dict(form_data)
                client_tree_details = dict(form_data.get("client_tree_details") or {})
                if record.tree_number is not None:
                    client_tree_details["tree_number"] = str(record.tree_number)
                    form_data["client_tree_details"] = client_tree_details
                payload["form"] = form_data
            if "narrative" not in payload:
                payload["narrative"] = payload.get("draft_narrative") or ""
            payload["tree_number"] = record.tree_number
            return payload
        payload = {
            "round_id": round_id,
            "server_revision_id": round_record.server_revision_id,
            "transcript": "Transcript ready.",
            "section_recordings": {},
            "section_transcripts": {},
            "draft_form": {"schema_name": "demo", "schema_version": "0.0", "data": {}},
            "draft_narrative": "Demo narrative.",
            "form": {},
            "narrative": "Demo narrative.",
            "tree_number": record.tree_number,
            "images": [],
        }
        _save_round_record(job_id, round_record, review_payload=payload)
        logger.info("GET /v1/jobs/%s/rounds/%s/review", job_id, round_id)
        return payload

    @app.post("/v1/jobs/{job_id}/final")
    def submit_final(
        job_id: str,
        payload: FinalSubmitRequest,
        x_api_key: str | None = Header(default=None),
    ) -> FileResponse:
        """Finalize job and generate final artifacts.

        Writes:
            - `final.json`
            - `final_traq_page1.pdf`
            - `final_report_letter.pdf`
            - `final_report_letter.docx`
            - `final.geojson`
        """
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        record = _ensure_job_record(job_id)
        if not record:
            persisted_round = db_store.get_job_round(job_id, payload.round_id)
            if isinstance((persisted_round or {}).get("review_payload"), dict):
                record = JobRecord(
                    job_id=job_id,
                    job_number=job_id,
                    status="DRAFT",
                )
                jobs[job_id] = record
            else:
                raise HTTPException(status_code=404, detail="Job not found")
        correction_mode = _is_correction_mode(job_id, record)
        logger.info("POST /v1/jobs/%s/final correction_mode=%s", job_id, correction_mode)
        def _ensure_risk_defaults(form: dict[str, Any]) -> dict[str, Any]:
            data = _normalize_form_schema(dict(form.get("data") or {}))
            rows = list(data.get("risk_categorization") or [])
            data["risk_categorization"] = rows
            notes_section = data.get("notes_explanations_descriptions")
            if isinstance(notes_section, dict):
                notes_val = notes_section.get("notes")
                if isinstance(notes_val, str):
                    notes_clean = " ".join(notes_val.split())
                    if len(notes_clean) > 230:
                        trimmed = notes_clean[:230].rstrip()
                        if " " in trimmed:
                            trimmed = trimmed.rsplit(" ", 1)[0]
                        notes_section["notes"] = trimmed
            form["data"] = data
            return form
        transcript = ""
        persisted_round = db_store.get_job_round(job_id, payload.round_id)
        review_payload = (persisted_round or {}).get("review_payload")
        if isinstance(review_payload, dict):
            transcript = review_payload.get("transcript", "") or ""
        pdf_name = "final_traq_page1_correction.pdf" if correction_mode else "final_traq_page1.pdf"
        report_name = "final_report_letter_correction.pdf" if correction_mode else "final_report_letter.pdf"
        report_docx_name = "final_report_letter_correction.docx" if correction_mode else "final_report_letter.docx"
        final_json_name = "final_correction.json" if correction_mode else "final.json"
        geojson_name = "final_correction.geojson" if correction_mode else "final.geojson"
        pdf_path = _job_dir(job_id) / pdf_name
        requested_tree_number = requested_tree_number_from_form(payload.form)
        record.tree_number = _resolve_server_tree_number(
            record,
            requested_tree_number=requested_tree_number,
        )
        payload.form = _ensure_risk_defaults(payload.form)
        payload.form = apply_tree_number_to_form(payload.form, record.tree_number)
        _save_job_record(record)
        try:
            from . import report_letter

            job_info = {
                "job_address": record.job_address,
                "address": record.address,
                "billing_name": record.billing_name,
                "billing_address": record.billing_address,
                "billing_contact_name": record.billing_contact_name,
            }
            narrative_text = ""
            if isinstance(payload.narrative, dict):
                narrative_text = payload.narrative.get("text") or ""
            else:
                narrative_text = str(payload.narrative or "")
            profile_payload = payload.profile.model_dump() if payload.profile else None
            if not profile_payload:
                try:
                    profile_payload = _load_runtime_profile(_identity_key(auth, x_api_key))
                except Exception:
                    profile_payload = None
            polished_summary = report_letter.polish_summary(
                narrative_text,
                form_data=payload.form,
                transcript=transcript,
            )
            letter_text = report_letter.build_report_letter(
                profile=profile_payload,
                job=job_info,
                summary=polished_summary,
                form_data=payload.form,
            )
            report_path = _job_dir(job_id) / report_name
            report_docx_path = _job_dir(job_id) / report_docx_name
            sender_name = ""
            if isinstance(profile_payload, dict):
                sender_name = str(profile_payload.get("name") or "").strip()
            customer_name = str(
                record.billing_name
                or record.customer_name
                or ""
            ).strip()
            signature_isa = (
                f"ISA - {str(profile_payload.get('isa_number') or '').strip()}"
                if isinstance(profile_payload, dict)
                and str(profile_payload.get("isa_number") or "").strip()
                else None
            )
            report_images = _load_job_report_images(job_id)
            report_letter.generate_report_letter_pdf(
                letter_text,
                str(report_path),
                sender_name=sender_name or None,
                customer_name=customer_name or None,
                signature_name=sender_name or None,
                signature_isa=signature_isa,
                job_number=record.job_number,
                report_images=report_images,
            )
            report_letter.generate_report_letter_docx(
                letter_text,
                str(report_docx_path),
            )
        except Exception as exc:
            logger.exception("Failed to generate report letter artifacts")
            raise HTTPException(
                status_code=500,
                detail="Report letter generation failed",
            ) from exc
        record.status = "ARCHIVED"
        record.latest_round_status = "REVIEW_RETURNED"
        _save_job_record(record)
        archived_at = datetime.utcnow().isoformat() + "Z"
        user_name = (
            str(profile_payload.get("name") or "").strip()
            if isinstance(profile_payload, dict)
            else None
        ) or None
        final_payload = {
            "job_id": job_id,
            "round_id": payload.round_id,
            "server_revision_id": payload.server_revision_id,
            "client_revision_id": payload.client_revision_id,
            "archived_at": archived_at,
            "transcript": transcript,
            "form": payload.form,
            "narrative": payload.narrative,
            "user_name": user_name,
            "report_images": report_images,
        }
        _write_json(_job_dir(job_id) / final_json_name, final_payload)
        # Generate the TRAQ PDF from the persisted final payload to keep
        # server and offline tool output aligned to the same canonical source.
        _generate_traq_pdf(form_data=final_payload["form"], output_path=pdf_path)
        try:
            from . import geojson_export

            form_data = payload.form.get("data") if isinstance(payload.form.get("data"), dict) else payload.form
            if not isinstance(form_data, dict):
                form_data = {}
            geojson_export.write_final_geojson(
                output_path=_job_dir(job_id) / geojson_name,
                job_number=record.job_number,
                user_name=user_name,
                form_data=form_data,
                report_images=report_images,
            )
        except Exception as exc:
            logger.exception("Failed to generate final.geojson")
            raise HTTPException(
                status_code=500,
                detail="Final GeoJSON generation failed",
            ) from exc
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename="traq_page1.pdf",
        )

    @app.get("/v1/jobs/{job_id}/final/report")
    def get_final_report_letter(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> FileResponse:
        """Download generated final report letter PDF for a job."""
        auth = require_api_key(x_api_key)
        _assert_job_assignment(job_id, auth)
        correction_path = _job_dir(job_id) / "final_report_letter_correction.pdf"
        report_path = correction_path if correction_path.exists() else (_job_dir(job_id) / "final_report_letter.pdf")
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report letter not found")
        return FileResponse(
            path=str(report_path),
            media_type="application/pdf",
            filename="report_letter.pdf",
        )

    @app.post("/v1/extract/site_factors")
    def extract_site_factors(
        payload: SiteFactorsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for site_factors section transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("site_factors", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/client_tree_details")
    def extract_client_tree_details(
        payload: ClientTreeDetailsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for client_tree_details transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("client_tree_details", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/load_factors")
    def extract_load_factors(
        payload: LoadFactorsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for load_factors transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("load_factors", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/crown_and_branches")
    def extract_crown_and_branches(
        payload: CrownAndBranchesRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for crown_and_branches transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("crown_and_branches", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/trunk")
    def extract_trunk(
        payload: TrunkRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for trunk transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("trunk", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/roots_and_root_collar")
    def extract_roots_and_root_collar(
        payload: RootsAndRootCollarRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for roots_and_root_collar transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("roots_and_root_collar", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/tree_health_and_species")
    def extract_tree_health_and_species(
        payload: TreeHealthAndSpeciesRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for tree_health_and_species transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("tree_health_and_species", payload.transcript)
        return result.model_dump()

    @app.post("/v1/extract/target_assessment")
    def extract_target_assessment(
        payload: TargetAssessmentRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for target_assessment transcript."""
        require_api_key(x_api_key)
        result = _run_extraction_logged("target_assessment", payload.transcript)
        return result.model_dump()

    @app.post("/v1/summary")
    def generate_summary(
        payload: SummaryRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Generate narrative summary from supplied form/transcript payload."""
        require_api_key(x_api_key)
        summary = _generate_summary(
            form_data=payload.form,
            transcript=payload.transcript,
        )
        return {"summary": summary}

    print("Demo server initialized.")
    logger.info("Demo server initialized.")

    @app.on_event("startup")
    def _startup_log() -> None:
        """Startup hook for explicit operational log marker."""
        print("Demo server startup event.")
        logger.info("Demo server startup event.")
        advertiser.start_in_background()

    @app.on_event("shutdown")
    def _shutdown_log() -> None:
        """Shutdown hook for explicit operational log marker."""
        try:
            advertiser.stop()
        except Exception:
            logger.exception("[DISCOVERY] shutdown cleanup failed")

    return app


app = create_app()
