#!/usr/bin/env python3
"""Import legacy filesystem-backed jobs into PostgreSQL.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This tool imports the current on-disk TRAQ job layout into the initial
PostgreSQL schema without changing the live server runtime path.

Scope for the initial phase:
- import `job_record.json` into `jobs`
- import `rounds/*/manifest.json` and `review.json` into `job_rounds`
- import recording/image metadata into `round_recordings` and `round_images`
- import `final.json` and `final_correction.json` into `job_finals`
- index file artifacts by path in `artifacts`

This importer is intentionally idempotent at the job level for repeated testing:
it deletes any existing imported rows for a target job before re-importing that
job from disk.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.config import load_settings
from app.db import create_schema, init_database, session_scope
from app.db_models import (
    Artifact,
    ArtifactKind,
    BillingProfile,
    Customer,
    Job,
    JobFinal,
    JobGeoJSONExport,
    JobRound,
    JobStatus,
    Operator,
    RoundImage,
    RoundRecording,
    RoundStatus,
    UploadStatus,
)
from sqlalchemy import select
from app.services.tree_store import parse_tree_number, resolve_tree


@dataclass
class ImportStats:
    jobs: int = 0
    rounds: int = 0
    recordings: int = 0
    images: int = 0
    finals: int = 0
    artifacts: int = 0
    skipped: list[str] = field(default_factory=list)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _next_code(session, model, field_name: str, prefix: str) -> str:
    codes = session.scalars(select(getattr(model, field_name))).all()
    max_number = 0
    for code in codes:
        if not code or not str(code).startswith(prefix):
            continue
        suffix = str(code)[len(prefix):]
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))
    return f"{prefix}{max_number + 1:04d}"


def _parse_job_status(value: str | None) -> JobStatus:
    raw = (value or "DRAFT").strip().upper()
    for status in JobStatus:
        if status.value == raw:
            return status
    return JobStatus.draft


def _parse_round_status(value: str | None) -> RoundStatus:
    raw = (value or "DRAFT").strip().upper()
    for status in RoundStatus:
        if status.value == raw:
            return status
    return RoundStatus.draft


def _parse_upload_status(value: str | None) -> UploadStatus:
    raw = (value or "pending").strip().lower()
    for status in UploadStatus:
        if status.value == raw:
            return status
    return UploadStatus.pending


def _artifact_kind_for_suffix(path: Path) -> ArtifactKind | None:
    name = path.name
    if name.endswith(".wav"):
        return ArtifactKind.audio
    if name.endswith(".transcript.txt"):
        return ArtifactKind.transcript_txt
    if name.endswith(".jpg") or name.endswith(".jpeg") or name.endswith(".png"):
        return ArtifactKind.image
    if name == "review.json":
        return ArtifactKind.review_json
    if name == "final.json" or name == "final_correction.json":
        return ArtifactKind.final_json
    if name.endswith("report_letter.pdf") or name.endswith("report_letter_correction.pdf"):
        return ArtifactKind.report_pdf
    if name.endswith("report_letter.docx") or name.endswith("report_letter_correction.docx"):
        return ArtifactKind.report_docx
    if name.endswith("traq_page1.pdf") or name.endswith("traq_page1_correction.pdf"):
        return ArtifactKind.final_pdf
    if name.endswith(".geojson"):
        return ArtifactKind.geojson
    return None


def _record_artifact(
    *,
    path: Path,
    job: Job | None = None,
    round_row: JobRound | None = None,
    final: JobFinal | None = None,
) -> Artifact | None:
    if not path.exists():
        return None
    kind = _artifact_kind_for_suffix(path)
    if kind is None:
        return None
    return Artifact(
        job=job,
        round=round_row,
        final=final,
        kind=kind,
        path=str(path),
        metadata_json=None,
    )


def _purge_existing_job(job_id: str) -> None:
    with session_scope() as session:
        existing = session.query(Job).filter(Job.job_id == job_id).one_or_none()
        if existing is not None:
            session.delete(existing)


def _import_rounds(job_dir: Path, job: Job, stats: ImportStats) -> None:
    rounds_dir = job_dir / "rounds"
    if not rounds_dir.exists():
        return
    for round_dir in sorted(child for child in rounds_dir.iterdir() if child.is_dir()):
        manifest = _read_json(round_dir / "manifest.json", default=[])
        review = _read_json(round_dir / "review.json", default=None)
        review_status = None
        if isinstance(review, dict):
            review_status = review.get("status")
        round_row = JobRound(
            job=job,
            round_id=round_dir.name,
            status=_parse_round_status(review_status or (job.latest_round_status.value if job.latest_round_status else None)),
            server_revision_id=(review or {}).get("server_revision_id"),
            manifest=manifest or [],
            review_payload=review,
        )
        stats.rounds += 1
        job.rounds.append(round_row)

        review_artifact = _record_artifact(path=round_dir / "review.json", job=job, round_row=round_row)
        if review_artifact is not None:
            round_row.artifacts.append(review_artifact)
            stats.artifacts += 1


def _import_recordings(job_dir: Path, job: Job, stats: ImportStats) -> None:
    sections_dir = job_dir / "sections"
    if not sections_dir.exists():
        return
    round_lookup = {row.round_id: row for row in job.rounds}
    fallback_round = None
    if job.latest_round_id:
        fallback_round = round_lookup.get(job.latest_round_id)
    if fallback_round is None and job.rounds:
        fallback_round = sorted(job.rounds, key=lambda row: row.round_id)[-1]
    for section_dir in sorted(child for child in sections_dir.iterdir() if child.is_dir()):
        recordings_dir = section_dir / "recordings"
        if recordings_dir.exists():
            for meta_path in sorted(recordings_dir.glob("*.meta.json")):
                base_name = meta_path.name.removesuffix(".meta.json")
                meta = _read_json(meta_path, default={}) or {}
                round_row = fallback_round
                if round_row is None:
                    stats.skipped.append(f"recording:{meta_path}")
                    continue
                row = RoundRecording(
                    round=round_row,
                    section_id=section_dir.name,
                    recording_id=base_name,
                    upload_status=_parse_upload_status(meta.get("upload_status") or meta.get("status")),
                    content_type=meta.get("content_type"),
                    duration_ms=meta.get("duration_ms"),
                    artifact_path=str(recordings_dir / f"{base_name}.wav"),
                    metadata_json=meta,
                )
                stats.recordings += 1
                round_row.recordings.append(row)
                for artifact_path in (
                    recordings_dir / f"{base_name}.wav",
                    recordings_dir / f"{base_name}.transcript.txt",
                ):
                    artifact = _record_artifact(path=artifact_path, job=job, round_row=round_row)
                    if artifact is not None:
                        round_row.artifacts.append(artifact)
                        stats.artifacts += 1
        images_dir = section_dir / "images"
        if images_dir.exists():
            for meta_path in sorted(images_dir.glob("*.meta.json")):
                base_name = meta_path.name.removesuffix(".meta.json")
                meta = _read_json(meta_path, default={}) or {}
                round_row = fallback_round
                if round_row is None:
                    stats.skipped.append(f"image:{meta_path}")
                    continue
                row = RoundImage(
                    round=round_row,
                    section_id=section_dir.name,
                    image_id=base_name,
                    upload_status=_parse_upload_status(meta.get("upload_status") or meta.get("status")),
                    caption=meta.get("caption"),
                    latitude=str(meta.get("latitude")) if meta.get("latitude") is not None else None,
                    longitude=str(meta.get("longitude")) if meta.get("longitude") is not None else None,
                    artifact_path=str(images_dir / f"{base_name}.jpg"),
                    metadata_json=meta,
                )
                stats.images += 1
                round_row.images.append(row)
                for artifact_path in (
                    images_dir / f"{base_name}.jpg",
                    images_dir / f"{base_name}.report.jpg",
                ):
                    artifact = _record_artifact(path=artifact_path, job=job, round_row=round_row)
                    if artifact is not None:
                        round_row.artifacts.append(artifact)
                        stats.artifacts += 1


def _import_finals(job_dir: Path, job: Job, stats: ImportStats) -> None:
    final_specs = [
        ("final", job_dir / "final.json"),
        ("correction", job_dir / "final_correction.json"),
    ]
    for kind, final_path in final_specs:
        if not final_path.exists():
            continue
        payload = _read_json(final_path, default={}) or {}
        final_row = JobFinal(
            job=job,
            kind=kind,
            round_id=payload.get("round_id"),
            payload=payload,
        )
        job.finals.append(final_row)
        stats.finals += 1
        if kind == "final":
            job.final_snapshot = payload
        else:
            job.correction_snapshot = payload

        for artifact_path in sorted(job_dir.iterdir()):
            if artifact_path.is_dir():
                continue
            if kind == "final" and "correction" in artifact_path.name:
                continue
            if kind == "correction" and "correction" not in artifact_path.name:
                continue
            artifact = _record_artifact(path=artifact_path, job=job, final=final_row)
            if artifact is not None:
                final_row.artifacts.append(artifact)
                stats.artifacts += 1


def _import_geojson_exports(job_dir: Path, job: Job) -> None:
    geojson_specs = [
        ("final", job_dir / "final.geojson"),
        ("correction", job_dir / "final_correction.geojson"),
    ]
    for kind, path in geojson_specs:
        if not path.exists():
            continue
        payload = _read_json(path, default=None)
        if not isinstance(payload, dict):
            continue
        job.geojson_exports.append(
            JobGeoJSONExport(
                job=job,
                kind=kind,
                payload=payload,
            )
        )


def _build_job(job_dir: Path) -> Job | None:
    job_record_path = job_dir / "job_record.json"
    payload = _read_json(job_record_path, default=None)
    if payload is None:
        return None
    return Job(
        job_id=str(payload.get("job_id") or job_dir.name),
        job_number=str(payload.get("job_number") or ""),
        job_name=payload.get("job_name"),
        job_address=payload.get("job_address"),
        reason=payload.get("reason"),
        location_notes=payload.get("location_notes"),
        tree_species=payload.get("tree_species"),
        status=_parse_job_status(payload.get("status")),
        latest_round_id=payload.get("latest_round_id"),
        latest_round_status=_parse_round_status(payload.get("latest_round_status")) if payload.get("latest_round_status") else None,
        profile_identity=None,
        details_json=payload,
        archived_at=None,
    )


def _get_or_create_customer(session, payload: dict[str, Any]) -> Customer | None:
    name = (payload.get("customer_name") or "").strip()
    phone = (payload.get("job_phone") or "").strip() or None
    address = (payload.get("address") or "").strip() or None
    if not name:
        return None
    row = session.scalar(
        select(Customer).where(
            Customer.name == name,
            Customer.phone.is_(phone) if phone is None else Customer.phone == phone,
            Customer.address.is_(address) if address is None else Customer.address == address,
        )
    )
    if row is None:
        row = Customer(
            customer_code=_next_code(session, Customer, "customer_code", "C"),
            name=name,
            phone=phone,
            address=address,
        )
        session.add(row)
        session.flush()
    return row


def _get_or_create_billing_profile(session, payload: dict[str, Any]) -> BillingProfile | None:
    billing_name = (payload.get("billing_name") or "").strip() or None
    billing_contact_name = (payload.get("billing_contact_name") or "").strip() or None
    billing_address = (payload.get("billing_address") or "").strip() or None
    contact_preference = (payload.get("contact_preference") or "").strip() or None
    if not any([billing_name, billing_contact_name, billing_address, contact_preference]):
        return None
    stmt = select(BillingProfile).where(
        BillingProfile.billing_name.is_(billing_name) if billing_name is None else BillingProfile.billing_name == billing_name,
        BillingProfile.billing_contact_name.is_(billing_contact_name) if billing_contact_name is None else BillingProfile.billing_contact_name == billing_contact_name,
        BillingProfile.billing_address.is_(billing_address) if billing_address is None else BillingProfile.billing_address == billing_address,
        BillingProfile.contact_preference.is_(contact_preference) if contact_preference is None else BillingProfile.contact_preference == contact_preference,
    )
    row = session.scalar(stmt)
    if row is None:
        row = BillingProfile(
            billing_code=_next_code(session, BillingProfile, "billing_code", "B"),
            billing_name=billing_name,
            billing_contact_name=billing_contact_name,
            billing_address=billing_address,
            contact_preference=contact_preference,
        )
        session.add(row)
        session.flush()
    return row


def _get_or_create_operator(session, job_dir: Path) -> Operator | None:
    final_path = job_dir / "final.json"
    if not final_path.exists():
        return None
    payload = _read_json(final_path, default={}) or {}
    name = (payload.get("user_name") or "").strip()
    if not name:
        return None
    row = session.scalar(select(Operator).where(Operator.name == name))
    if row is None:
        row = Operator(name=name)
        session.add(row)
        session.flush()
    return row


def _legacy_tree_number(job: Job, job_dir: Path) -> int | None:
    from_details = parse_tree_number((job.details_json or {}).get("tree_number"))
    if from_details is not None:
        return from_details
    final_path = job_dir / "final.json"
    if not final_path.exists():
        return None
    payload = _read_json(final_path, default={}) or {}
    form_data = ((payload.get("form") or {}).get("data") or {})
    client_tree = form_data.get("client_tree_details") if isinstance(form_data, dict) else None
    if not isinstance(client_tree, dict):
        return None
    return parse_tree_number(client_tree.get("tree_number"))


def import_job(job_dir: Path, stats: ImportStats) -> None:
    job = _build_job(job_dir)
    if job is None:
        stats.skipped.append(str(job_dir))
        return
    _purge_existing_job(job.job_id)
    job_payload = dict(job.details_json or {})
    _import_rounds(job_dir, job, stats)
    _import_recordings(job_dir, job, stats)
    _import_finals(job_dir, job, stats)
    _import_geojson_exports(job_dir, job)
    with session_scope() as session:
        session.add(job)
        job.customer = _get_or_create_customer(session, job_payload)
        job.billing_profile = _get_or_create_billing_profile(session, job_payload)
        job.operator = _get_or_create_operator(session, job_dir)
        if job.customer is not None:
            requested_tree_number = _legacy_tree_number(job, job_dir)
            tree = resolve_tree(session, customer=job.customer, requested_tree_number=requested_tree_number)
            job.tree = tree
            job.tree_number = tree.tree_number
    stats.jobs += 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Import legacy TRAQ jobs into PostgreSQL")
    parser.add_argument(
        "--jobs-root",
        default=str(load_settings().storage_root / "jobs"),
        help="Legacy jobs root (default: TRAQ storage_root/jobs)",
    )
    parser.add_argument(
        "--job-id",
        action="append",
        default=[],
        help="Import only the specified job id(s)",
    )
    parser.add_argument(
        "--init-schema",
        action="store_true",
        help="Create tables before import using SQLAlchemy metadata",
    )
    args = parser.parse_args()

    settings = load_settings()
    init_database(settings)
    if args.init_schema:
        create_schema()

    jobs_root = Path(args.jobs_root)
    if not jobs_root.exists():
        print(f"Jobs root not found: {jobs_root}", file=sys.stderr)
        return 1

    stats = ImportStats()
    job_dirs = sorted(child for child in jobs_root.iterdir() if child.is_dir())
    if args.job_id:
        wanted = set(args.job_id)
        job_dirs = [child for child in job_dirs if child.name in wanted]

    for job_dir in job_dirs:
        import_job(job_dir, stats)

    print(json.dumps({
        "jobs": stats.jobs,
        "rounds": stats.rounds,
        "recordings": stats.recordings,
        "images": stats.images,
        "finals": stats.finals,
        "artifacts": stats.artifacts,
        "skipped": stats.skipped,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
