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
      (`app/traq_2_schema/traq_full_map.json`)
    - Registry-driven section extraction (`extractors/registry.py`)
    - DB-backed device auth, assignment, and runtime state
    - Local artifact storage under the configured storage root for uploaded
      media and generated outputs

Operational notes:
    - Logging is configured here (console + rotating file under
      `<storage_root>/logs/server.log`).
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
from pathlib import Path
from typing import Any
import re
import hashlib
import uuid

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from .api.admin_routes import build_admin_router
from .api.core_routes import build_core_router
from .api.extraction_routes import build_extraction_router
from .api.job_read_routes import build_job_read_router
from .api.job_write_routes import build_job_write_router
from .api.round_manifest_routes import build_round_manifest_router
from .api.models import (
    AdminJobStatusRequest,
    AssignJobRequest,
    AssignedJob,
    BillingProfileLookupRow,
    ClientTreeDetailsRequest,
    CreateJobRequest,
    CreateJobResponse,
    CreateRoundResponse,
    CrownAndBranchesRequest,
    CustomerLookupRow,
    FinalSubmitRequest,
    IssueTokenRequest,
    LoadFactorsRequest,
    ManifestItem,
    ProfilePayload,
    RegisterDeviceRequest,
    RootsAndRootCollarRequest,
    SiteFactorsRequest,
    StatusResponse,
    SubmitRoundRequest,
    SummaryRequest,
    TargetAssessmentRequest,
    TreeHealthAndSpeciesRequest,
    TrunkRequest,
)
from .config import load_settings
from .db import create_schema, init_database, session_scope
from .extractors.registry import run_extraction as _run_extraction_core
from .runtime_context import RuntimeContext
from .security_store import AuthContext
from .services.tree_store import (
    apply_tree_number_to_form,
    get_or_create_customer,
    parse_tree_number,
    requested_tree_number_from_form,
    resolve_tree,
)

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


def create_app() -> FastAPI:
    """Construct and configure the FastAPI app instance.

    Returns:
        Configured FastAPI application with all routes, helper closures,
        logging setup, and startup hook registered.
    """
    settings = load_settings()
    init_database(settings)
    # Local/dev deployments can still opt into additive schema bootstrap.
    # Production/cloud deployments should turn this off and run migrations
    # explicitly before the app starts.
    if settings.auto_create_schema:
        create_schema()
    logs_dir = settings.storage_root / "logs"
    log_path = logs_dir / "server.log"
    handler_names = ["console"]
    handlers: dict[str, dict[str, Any]] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "standard",
        },
    }
    if settings.enable_file_logging:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO",
            "formatter": "standard",
            "filename": str(log_path),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 5,
        }
        handler_names.append("file")
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": handlers,
            "root": {
                "level": "INFO",
                "handlers": handler_names,
            },
            "loggers": {
                # Keep Uvicorn output on the same formatter/handlers as app logs.
                "uvicorn": {
                    "level": "INFO",
                    "handlers": handler_names,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": handler_names,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": "INFO",
                    "handlers": handler_names,
                    "propagate": False,
                },
            },
        }
    )
    logger = logging.getLogger("traq_demo")
    app = FastAPI(title="Tree Risk Demo API")
    runtime = RuntimeContext(settings=settings, logger=logger)
    runtime.bind_runtime_state_service(
        parse_tree_number=parse_tree_number,
        job_record_factory=JobRecord,
        round_record_factory=RoundRecord,
        write_json=lambda path, payload: _write_json(path, payload),
    )
    jobs = runtime.jobs
    security = runtime.security
    db_store = runtime.db_store
    artifact_store = runtime.artifact_store
    access_control_service = runtime.access_control_service
    customer_service = runtime.customer_service
    final_mutation_service = runtime.final_mutation_service
    finalization_service = runtime.finalization_service
    job_mutation_service = runtime.job_mutation_service
    media_runtime_service = runtime.media_runtime_service
    review_payload_service = runtime.review_payload_service
    runtime_state_service = runtime.runtime_state_service
    advertiser = runtime.advertiser

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

    def _artifact_key(*parts: str) -> str:
        """Return a normalized artifact key relative to the storage root."""
        return artifact_store.resolve_key(*parts)

    def _materialize_artifact_path(key: str) -> Path:
        """Return a readable local path for one artifact key."""
        return artifact_store.materialize_path(key)

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
                review_payload = review_payload_service.normalize_payload(
                    review_data,
                    tree_number=record.tree_number,
                    normalize_form_schema=_normalize_form_schema,
                    hydrated_images=review_payload_service.build_round_images(
                        db_store.list_round_images(record.job_id, record.latest_round_id)
                    ),
                )
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
        return access_control_service.assign_job(
            job_id=job_id,
            device_id=device_id,
            assigned_by=assigned_by,
        )

    def _unassign_job_record(job_id: str) -> dict[str, Any]:
        """Remove job assignment from the DB store only."""
        return access_control_service.unassign_job(job_id)

    def require_api_key(
        x_api_key: str | None,
        *,
        required_role: str | None = None,
    ) -> AuthContext:
        """Authenticate request using server API key or device token."""
        return access_control_service.require_api_key(
            x_api_key,
            required_role=required_role,
        )

    def _identity_key(auth: AuthContext, x_api_key: str | None) -> str:
        """Build identity key used to scope profile persistence."""
        return access_control_service.identity_key(auth, x_api_key)

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
        access_control_service.assert_round_editable(
            record,
            round_id,
            auth,
            allow_correction=allow_correction,
        )

    def _assert_job_editable(
        record: JobRecord,
        auth: AuthContext,
        *,
        allow_correction: bool = False,
    ) -> None:
        """Enforce job-level edit lock rules for non-admin callers."""
        access_control_service.assert_job_editable(
            record,
            auth,
            allow_correction=allow_correction,
        )

    def _assert_job_assignment(job_id: str, auth: AuthContext) -> None:
        """Enforce caller authorization for target job id."""
        access_control_service.assert_job_assignment(
            job_id,
            auth,
            job_exists_in_memory=job_id in jobs,
        )

    def _job_dir(job_id: str) -> Path:
        """Return filesystem directory path for a job id."""
        return runtime_state_service.job_dir(job_id)

    def _job_artifact_key(job_id: str, *parts: str) -> str:
        """Return artifact key rooted under one job."""
        return runtime_state_service.job_artifact_key(job_id, *parts)

    def _job_record_path(job_id: str) -> Path:
        """Return path to compatibility/debug job record JSON file."""
        return runtime_state_service.job_record_path(job_id)

    def _save_job_record(record: JobRecord) -> None:
        """Persist authoritative job shell state to DB and export a file copy."""
        runtime_state_service.save_job_record(record)

    def _job_record_from_payload(payload: dict[str, Any], fallback_job_id: str) -> JobRecord:
        """Build JobRecord from normalized payload data."""
        return runtime_state_service.job_record_from_payload(payload, fallback_job_id)

    def _load_rounds_from_db(job_id: str) -> dict[str, RoundRecord]:
        """Load persisted round metadata from the authoritative DB store."""
        return runtime_state_service.load_rounds_from_db(job_id)

    def _load_job_record_from_db(job_id: str) -> JobRecord | None:
        """Load a job record from the authoritative DB store."""
        return runtime_state_service.load_job_record_from_db(job_id)

    def _load_job_record_from_disk(job_id: str) -> JobRecord | None:
        """Load compatibility/debug job record from disk."""
        return runtime_state_service.load_job_record_from_disk(job_id)

    def _load_job_record(job_id: str) -> JobRecord | None:
        """Load a job record, preferring the DB and falling back to disk."""
        return runtime_state_service.load_job_record(job_id)

    def _refresh_job_record_from_store(job_id: str) -> JobRecord | None:
        """Refresh cached runtime metadata from the authoritative store."""
        return runtime_state_service.refresh_job_record_from_store(job_id, jobs_cache=jobs)

    def _save_round_record(
        job_id: str,
        round_record: RoundRecord,
        *,
        review_payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist authoritative round state to DB and export compatibility files."""
        runtime_state_service.save_round_record(job_id, round_record, review_payload=review_payload)

    def _next_job_number() -> str:
        """Allocate next unique human-readable job number from PostgreSQL."""
        return runtime_state_service.next_job_number()

    def _round_dir(job_id: str, round_id: str) -> Path:
        """Return filesystem directory for a job round."""
        return runtime_state_service.round_dir(job_id, round_id)

    def _ensure_job_record(job_id: str) -> JobRecord | None:
        """Resolve job record from memory or storage."""
        return runtime_state_service.ensure_job_record(job_id, jobs_cache=jobs)

    def _ensure_round_record(job_id: str, round_id: str) -> tuple[JobRecord, RoundRecord]:
        """Resolve a persisted round from authoritative storage."""
        return runtime_state_service.ensure_round_record(job_id, round_id, jobs_cache=jobs)

    def _section_dir(job_id: str, section_id: str) -> Path:
        """Return filesystem directory for a section within a job."""
        return runtime_state_service.section_dir(job_id, section_id)

    def _round_manifest_path(job_id: str, round_id: str) -> Path:
        """Return path to round manifest JSON file."""
        return runtime_state_service.round_manifest_path(job_id, round_id)

    def _is_correction_mode(job_id: str, record: JobRecord | None) -> bool:
        """Return True when writes should target correction artifacts."""
        if record and (record.status or "").strip().upper() == "ARCHIVED":
            return True
        return artifact_store.exists(_job_artifact_key(job_id, "final.json"))

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
            stored_path = str(meta.get("stored_path") or "").strip()
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
                    transcript = media_runtime_service.transcribe_recording(
                        _materialize_artifact_path(stored_path),
                        probe=probe,
                        log_event=_log_event,
                    ).strip()
                    meta["transcript_text"] = transcript
                    meta["processed"] = True
                    meta.pop("transcription_error", None)
                    media_runtime_service.save_recording_runtime_state(
                        job_id=job_id,
                        round_id=round_id,
                        section_id=section_id,
                        recording_id=rec_id,
                        meta=meta,
                        job_artifact_key=_job_artifact_key,
                    )
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
                    media_runtime_service.save_recording_runtime_state(
                        job_id=job_id,
                        round_id=round_id,
                        section_id=section_id,
                        recording_id=rec_id,
                        meta=meta,
                        job_artifact_key=_job_artifact_key,
                    )
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
            "images": review_payload_service.build_round_images(
                db_store.list_round_images(job_id, round_id)
            ),
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

    app.include_router(
        build_core_router(
            settings=settings,
            logger=logger,
            require_api_key=require_api_key,
            register_device_record=_register_device_record,
            get_device_record=_get_device_record,
            issue_device_token_record=_issue_device_token_record,
            load_runtime_profile=_load_runtime_profile,
            save_runtime_profile=_save_runtime_profile,
            identity_key=_identity_key,
            customer_service=customer_service,
        )
    )

    app.include_router(
        build_job_write_router(
            require_api_key=require_api_key,
            jobs=jobs,
            next_job_number=_next_job_number,
            customer_service=customer_service,
            job_mutation_service=job_mutation_service,
            load_job_record=_load_job_record,
            assign_job_record=_assign_job_record,
            save_job_record=_save_job_record,
            save_round_record=_save_round_record,
            round_record_factory=RoundRecord,
            logger=logger,
            uuid_hex_supplier=lambda: uuid.uuid4().hex,
            assert_job_assignment=_assert_job_assignment,
            ensure_job_record=_ensure_job_record,
        )
    )

    app.include_router(
        build_job_read_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_job_record=_ensure_job_record,
            list_job_assignments=_list_job_assignments,
            resolve_assigned_job=_resolve_assigned_job,
            save_job_record=_save_job_record,
            save_round_record=_save_round_record,
            review_payload_service=review_payload_service,
            normalize_form_schema=_normalize_form_schema,
            db_store=db_store,
            logger=logger,
        )
    )

    app.include_router(
        build_round_manifest_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_round_record=_ensure_round_record,
            assert_round_editable=_assert_round_editable,
            save_round_record=_save_round_record,
            logger=logger,
        )
    )

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

    app.include_router(
        build_admin_router(
            require_api_key=require_api_key,
            ensure_job_record=_ensure_job_record,
            assign_job_record=_assign_job_record,
            unassign_job_record=_unassign_job_record,
            list_job_assignments=_list_job_assignments,
            save_job_record=_save_job_record,
            db_store=db_store,
            round_record_factory=RoundRecord,
            logger=logger,
        )
    )

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
        ext = media_runtime_service.guess_extension(content_type, ".m4a")
        artifact_key = _job_artifact_key(
            job_id,
            "sections",
            section_id,
            "recordings",
            f"{recording_id}{ext}",
        )
        file_path = artifact_store.write_bytes(artifact_key, payload)
        audio_probe = media_runtime_service.probe_audio_metadata(file_path)
        meta = {
            "recording_id": recording_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": artifact_key,
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
            artifact_path=artifact_key,
            metadata_json=meta,
        )
        _write_json(_section_dir(job_id, section_id) / "recordings" / f"{recording_id}.meta.json", meta)
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
        ext = media_runtime_service.guess_extension(content_type, ".jpg")
        artifact_key = _job_artifact_key(
            job_id,
            "sections",
            section_id,
            "images",
            f"{image_id}{ext}",
        )
        file_path = artifact_store.write_bytes(artifact_key, payload)
        report_key = _job_artifact_key(
            job_id,
            "sections",
            section_id,
            "images",
            f"{image_id}.report.jpg",
        )
        report_path, report_bytes = media_runtime_service.build_report_image_variant(
            file_path,
            _materialize_artifact_path(report_key),
        )
        meta = {
            "image_id": image_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": artifact_key,
            "report_image_path": report_key,
            "report_bytes": report_bytes,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
        }
        db_store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
            upload_status="uploaded",
            artifact_path=artifact_key,
            metadata_json=meta,
        )
        _write_json(_section_dir(job_id, section_id) / "images" / f"{image_id}.meta.json", meta)
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
        _write_json(_section_dir(job_id, section_id) / "images" / f"{image_id}.meta.json", meta)
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
        persisted_round = db_store.get_job_round(job_id, payload.round_id)
        review_payload = (persisted_round or {}).get("review_payload")
        transcript = finalization_service.transcript_from_review_payload(review_payload)
        artifact_names = finalization_service.artifact_names(correction_mode)
        pdf_key = _job_artifact_key(job_id, artifact_names.pdf_name)
        pdf_path = artifact_store.stage_output(pdf_key)
        requested_tree_number = requested_tree_number_from_form(payload.form)
        record.tree_number = _resolve_server_tree_number(
            record,
            requested_tree_number=requested_tree_number,
        )
        payload.form = finalization_service.ensure_risk_defaults(
            payload.form,
            normalize_form_schema=_normalize_form_schema,
        )
        payload.form = apply_tree_number_to_form(payload.form, record.tree_number)
        _save_job_record(record)
        try:
            from . import report_letter

            job_info = finalization_service.build_job_info(record)
            narrative_text = ""
            if isinstance(payload.narrative, dict):
                narrative_text = payload.narrative.get("text") or ""
            else:
                narrative_text = str(payload.narrative or "")
            profile_payload = payload.profile.model_dump() if payload.profile else None
            profile_payload = finalization_service.resolve_profile_payload(
                profile_payload,
                fallback_loader=lambda: _load_runtime_profile(_identity_key(auth, x_api_key)),
            )
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
            report_key = _job_artifact_key(job_id, artifact_names.report_name)
            report_docx_key = _job_artifact_key(job_id, artifact_names.report_docx_name)
            report_path = artifact_store.stage_output(report_key)
            report_docx_path = artifact_store.stage_output(report_docx_key)
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
            report_images = media_runtime_service.load_job_report_images(
                job_id=job_id,
                round_id=record.latest_round_id or "",
            )
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
        final_payload = finalization_service.build_final_payload(
            job_id=job_id,
            round_id=payload.round_id,
            server_revision_id=payload.server_revision_id,
            client_revision_id=payload.client_revision_id,
            archived_at=archived_at,
            transcript=transcript,
            form=payload.form,
            narrative=payload.narrative,
            user_name=user_name,
            report_images=report_images,
        )
        final_json_key = _job_artifact_key(job_id, artifact_names.final_json_name)
        final_json_path = artifact_store.stage_output(final_json_key)
        _write_json(final_json_path, final_payload)
        # Generate the TRAQ PDF from the persisted final payload to keep
        # server and offline tool output aligned to the same canonical source.
        _generate_traq_pdf(form_data=final_payload["form"], output_path=pdf_path)
        try:
            from . import geojson_export

            form_data = payload.form.get("data") if isinstance(payload.form.get("data"), dict) else payload.form
            if not isinstance(form_data, dict):
                form_data = {}
            geojson_key = _job_artifact_key(job_id, artifact_names.geojson_name)
            geojson_path = artifact_store.stage_output(geojson_key)
            geojson_export.write_final_geojson(
                output_path=geojson_path,
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
        try:
            geojson_payload = _read_json(geojson_path)
            if correction_mode:
                final_mutation_service.set_correction(
                    job_id,
                    payload=final_payload,
                    geojson_payload=geojson_payload if isinstance(geojson_payload, dict) else None,
                )
            else:
                final_mutation_service.set_final(
                    job_id,
                    payload=final_payload,
                    geojson_payload=geojson_payload if isinstance(geojson_payload, dict) else None,
                )
            pdf_path = artifact_store.commit_output(pdf_key, pdf_path)
            artifact_store.commit_output(report_key, report_path)
            artifact_store.commit_output(report_docx_key, report_docx_path)
            artifact_store.commit_output(final_json_key, final_json_path)
            artifact_store.commit_output(geojson_key, geojson_path)
            _unassign_job_record(job_id)
        except KeyError:
            logger.info("Finalized job %s had no assignment to remove", job_id)
        except Exception:
            logger.exception("Failed to unassign finalized job %s", job_id)
            raise HTTPException(
                status_code=500,
                detail="Finalization cleanup failed",
            )
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
        correction_path = _materialize_artifact_path(
            _job_artifact_key(job_id, "final_report_letter_correction.pdf")
        )
        report_path = (
            correction_path
            if correction_path.exists()
            else _materialize_artifact_path(_job_artifact_key(job_id, "final_report_letter.pdf"))
        )
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report letter not found")
        return FileResponse(
            path=str(report_path),
            media_type="application/pdf",
            filename="report_letter.pdf",
        )

    app.include_router(
        build_extraction_router(
            require_api_key=require_api_key,
            run_extraction_logged=_run_extraction_logged,
            generate_summary=_generate_summary,
        )
    )

    print("Demo server initialized.")
    logger.info("Demo server initialized.")

    @app.on_event("startup")
    def _startup_log() -> None:
        """Startup hook for explicit operational log marker."""
        print("Demo server startup event.")
        logger.info("Demo server startup event.")
        if settings.enable_discovery:
            advertiser.start_in_background()
        else:
            logger.info("[DISCOVERY] disabled by configuration")

    @app.on_event("shutdown")
    def _shutdown_log() -> None:
        """Shutdown hook for explicit operational log marker."""
        if settings.enable_discovery:
            try:
                advertiser.stop()
            except Exception:
                logger.exception("[DISCOVERY] shutdown cleanup failed")

    return app


app = create_app()
