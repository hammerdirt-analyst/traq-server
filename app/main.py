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
import json
import logging
import logging.config
import logging.handlers
import os
from pathlib import Path
from typing import Any
import re
import uuid

from fastapi import Body, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from .api.admin_routes import build_admin_router
from .api.core_routes import build_core_router
from .api.extraction_routes import build_extraction_router
from .api.final_routes import build_final_router
from .api.image_routes import build_image_router
from .api.job_read_routes import build_job_read_router
from .api.job_write_routes import build_job_write_router
from .api.recording_routes import build_recording_router
from .api.round_manifest_routes import build_round_manifest_router
from .api.round_reprocess_routes import build_round_reprocess_router
from .api.round_submit_routes import build_round_submit_router
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
from .services.assigned_job_service import AssignedJobService
from .services.round_processing_service import RoundProcessingService
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
    device_profile_service = runtime.device_profile_service
    final_mutation_service = runtime.final_mutation_service
    finalization_service = runtime.finalization_service
    job_mutation_service = runtime.job_mutation_service
    media_runtime_service = runtime.media_runtime_service
    review_form_service = runtime.review_form_service
    review_payload_service = runtime.review_payload_service
    round_submit_service = runtime.round_submit_service
    runtime_state_service = runtime.runtime_state_service
    assigned_job_service = AssignedJobService(
        db_store=db_store,
        review_payload_service=review_payload_service,
        normalize_form_schema=review_form_service.normalize_form_schema,
        assigned_job_factory=AssignedJob,
    )
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

    _to_assigned_job = assigned_job_service.to_assigned_job

    def _resolve_assigned_job(job_id: str) -> AssignedJob | None:
        """Resolve assigned job object from the latest persisted runtime state."""
        return assigned_job_service.resolve_assigned_job(
            job_id,
            refresh_job_record_from_store=_refresh_job_record_from_store,
            jobs_cache=jobs,
        )

    _register_device_record = device_profile_service.register_device_record
    _get_device_record = device_profile_service.get_device_record
    _issue_device_token_record = device_profile_service.issue_device_token_record

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

    _load_runtime_profile = device_profile_service.load_runtime_profile
    _save_runtime_profile = device_profile_service.save_runtime_profile

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

    _recording_meta = media_runtime_service.recording_meta

    def _build_reprocess_manifest(
        job_id: str,
        round_record: RoundRecord,
        round_review: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build server-side manifest for forced reprocess from recording metadata."""
        return media_runtime_service.build_reprocess_manifest(
            job_id=job_id,
            round_record=round_record,
            round_review=round_review,
        )
    _merge_flat_section = review_form_service.merge_flat_section
    _merge_notes_explanations_descriptions = (
        review_form_service.merge_notes_explanations_descriptions
    )
    _merge_mitigation_options = review_form_service.merge_mitigation_options
    _apply_form_patch = review_form_service.apply_form_patch
    _normalize_form_schema = review_form_service.normalize_form_schema
    _merge_site_factors = review_form_service.merge_site_factors
    _merge_client_tree_details = review_form_service.merge_client_tree_details
    _merge_target_assessment = review_form_service.merge_target_assessment
    _merge_tree_health_and_species = review_form_service.merge_tree_health_and_species
    _merge_load_factors = review_form_service.merge_load_factors
    _merge_crown_and_branches = review_form_service.merge_crown_and_branches
    _merge_trunk = review_form_service.merge_trunk
    _merge_roots_and_root_collar = review_form_service.merge_roots_and_root_collar

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
        return media_runtime_service.build_section_transcript(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            manifest=manifest,
            issue_id=issue_id,
            seen_recordings=seen_recordings or set(),
            force_reprocess=force_reprocess,
            force_transcribe=force_transcribe,
            materialize_artifact_path=_materialize_artifact_path,
            job_artifact_key=_job_artifact_key,
            log_event=_log_event,
        )

    round_processing_service = RoundProcessingService(
        db_store=db_store,
        review_form_service=review_form_service,
        review_payload_service=review_payload_service,
        build_section_transcript=_build_section_transcript,
        load_latest_review=_load_latest_review,
        run_extraction_logged=_run_extraction_logged,
        generate_summary=_generate_summary,
        save_round_record=_save_round_record,
        logger=logger,
    )

    _process_round = round_processing_service.process_round

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

    app.include_router(
        build_round_submit_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_round_record=_ensure_round_record,
            assert_round_editable=_assert_round_editable,
            save_job_record=_save_job_record,
            save_round_record=_save_round_record,
            requested_tree_number_from_form=requested_tree_number_from_form,
            resolve_server_tree_number=_resolve_server_tree_number,
            apply_tree_number_to_form=apply_tree_number_to_form,
            db_store=db_store,
            build_reprocess_manifest=_build_reprocess_manifest,
            load_latest_review=_load_latest_review,
            apply_form_patch=_apply_form_patch,
            normalize_form_schema=_normalize_form_schema,
            process_round=_process_round,
            round_submit_service=round_submit_service,
            logger=logger,
        )
    )

    app.include_router(
        build_round_reprocess_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_round_record=_ensure_round_record,
            db_store=db_store,
            build_reprocess_manifest=_build_reprocess_manifest,
            save_job_record=_save_job_record,
            load_latest_review=_load_latest_review,
            process_round=_process_round,
            logger=logger,
        )
    )

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

    app.include_router(
        build_recording_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_job_record=_ensure_job_record,
            assert_job_editable=_assert_job_editable,
            media_runtime_service=media_runtime_service,
            job_artifact_key=_job_artifact_key,
            artifact_store=artifact_store,
            db_store=db_store,
            write_json=_write_json,
            section_dir=_section_dir,
            log_event=_log_event,
        )
    )
    app.include_router(
        build_image_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_job_record=_ensure_job_record,
            assert_job_editable=_assert_job_editable,
            media_runtime_service=media_runtime_service,
            job_artifact_key=_job_artifact_key,
            materialize_artifact_path=_materialize_artifact_path,
            artifact_store=artifact_store,
            db_store=db_store,
            write_json=_write_json,
            section_dir=_section_dir,
            log_event=_log_event,
            job_photos_section_id=JOB_PHOTOS_SECTION_ID,
        )
    )
    app.include_router(
        build_final_router(
            require_api_key=require_api_key,
            assert_job_assignment=_assert_job_assignment,
            ensure_job_record=_ensure_job_record,
            job_record_factory=JobRecord,
            jobs=jobs,
            db_store=db_store,
            is_correction_mode=_is_correction_mode,
            logger=logger,
            finalization_service=finalization_service,
            artifact_store=artifact_store,
            job_artifact_key=_job_artifact_key,
            requested_tree_number_from_form=requested_tree_number_from_form,
            resolve_server_tree_number=_resolve_server_tree_number,
            normalize_form_schema=_normalize_form_schema,
            apply_tree_number_to_form=apply_tree_number_to_form,
            save_job_record=_save_job_record,
            identity_key=_identity_key,
            load_runtime_profile=_load_runtime_profile,
            media_runtime_service=media_runtime_service,
            generate_traq_pdf=_generate_traq_pdf,
            write_json=_write_json,
            read_json=_read_json,
            final_mutation_service=final_mutation_service,
            unassign_job_record=_unassign_job_record,
            materialize_artifact_path=_materialize_artifact_path,
        )
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
