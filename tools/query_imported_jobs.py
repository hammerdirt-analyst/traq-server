#!/usr/bin/env python3
"""Read-only query tool for imported TRAQ PostgreSQL data.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This tool exercises the imported schema without touching the live runtime path.
It is meant for schema validation, pruning discussions, and reporting design.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.config import load_settings
from app.services.archive_policy import build_archive_retention_decision
from app.db import init_database, session_scope
from app.db_models import Artifact, BillingProfile, Customer, Job, JobFinal, JobGeoJSONExport, JobRound, JobStatus, Operator, RoundImage, RoundRecording, Tree


def query_summary() -> dict:
    with session_scope() as session:
        jobs = session.scalar(select(func.count()).select_from(Job)) or 0
        rounds = session.scalar(select(func.count()).select_from(JobRound)) or 0
        recordings = session.scalar(select(func.count()).select_from(RoundRecording)) or 0
        images = session.scalar(select(func.count()).select_from(RoundImage)) or 0
        finals = session.scalar(select(func.count()).select_from(JobFinal)) or 0
        artifacts = session.scalar(select(func.count()).select_from(Artifact)) or 0
        statuses = session.execute(
            select(Job.status, func.count()).group_by(Job.status).order_by(Job.status)
        ).all()
    return {
        "jobs": jobs,
        "rounds": rounds,
        "recordings": recordings,
        "images": images,
        "finals": finals,
        "artifacts": artifacts,
        "job_statuses": [{"status": str(status.value), "count": count} for status, count in statuses],
    }


def query_archived_finals() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Job.job_number, Job.job_id, Job.status, JobFinal.kind, JobFinal.round_id)
            .join(JobFinal, JobFinal.job_id == Job.id)
            .order_by(Job.job_number, JobFinal.kind)
        ).all()
    return [
        {
            "job_number": job_number,
            "job_id": job_id,
            "status": status.value,
            "kind": kind,
            "round_id": round_id,
        }
        for job_number, job_id, status, kind, round_id in rows
    ]


def query_round_mismatches() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Job.job_number, Job.job_id, Job.latest_round_id, JobFinal.kind, JobFinal.round_id)
            .join(JobFinal, JobFinal.job_id == Job.id)
            .where(Job.latest_round_id.is_not(None))
            .where(Job.latest_round_id != JobFinal.round_id)
            .order_by(Job.job_number, JobFinal.kind)
        ).all()
    return [
        {
            "job_number": job_number,
            "job_id": job_id,
            "latest_round_id": latest_round_id,
            "kind": kind,
            "final_round_id": final_round_id,
        }
        for job_number, job_id, latest_round_id, kind, final_round_id in rows
    ]


def query_media_by_job() -> list[dict]:
    recording_counts = (
        select(Job.id.label("job_pk"), func.count(RoundRecording.id).label("recordings"))
        .join(JobRound, JobRound.job_id == Job.id)
        .join(RoundRecording, RoundRecording.round_pk == JobRound.id)
        .group_by(Job.id)
        .subquery()
    )
    image_counts = (
        select(Job.id.label("job_pk"), func.count(RoundImage.id).label("images"))
        .join(JobRound, JobRound.job_id == Job.id)
        .join(RoundImage, RoundImage.round_pk == JobRound.id)
        .group_by(Job.id)
        .subquery()
    )
    with session_scope() as session:
        rows = session.execute(
            select(
                Job.job_number,
                func.coalesce(recording_counts.c.recordings, 0),
                func.coalesce(image_counts.c.images, 0),
            )
            .outerjoin(recording_counts, recording_counts.c.job_pk == Job.id)
            .outerjoin(image_counts, image_counts.c.job_pk == Job.id)
            .order_by(Job.job_number)
        ).all()
    return [
        {"job_number": job_number, "recordings": recordings, "images": images}
        for job_number, recordings, images in rows
    ]


def query_pruning_candidates() -> list[dict]:
    FinalRow = aliased(JobFinal)
    with session_scope() as session:
        rows = session.execute(
            select(Job.job_number, Job.job_id, JobRound.round_id, FinalRow.round_id)
            .join(JobRound, JobRound.job_id == Job.id)
            .join(FinalRow, FinalRow.job_id == Job.id)
            .where(Job.status == JobStatus.archived)
            .where(FinalRow.kind == "final")
            .where(JobRound.round_id != FinalRow.round_id)
            .order_by(Job.job_number, JobRound.round_id)
        ).all()
    return [
        {
            "job_number": job_number,
            "job_id": job_id,
            "candidate_round_id": round_id,
            "final_round_id": final_round_id,
        }
        for job_number, job_id, round_id, final_round_id in rows
    ]


def query_report_projection() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Job.job_number, Job.job_id, Job.status, JobFinal.kind, JobFinal.payload)
            .join(JobFinal, JobFinal.job_id == Job.id)
            .where(JobFinal.kind == "final")
            .order_by(Job.job_number)
        ).all()
    projected = []
    for job_number, job_id, status, kind, payload in rows:
        form = (payload or {}).get("form") or {}
        form_data = form.get("data") if isinstance(form, dict) else None
        projected.append(
            {
                "job_number": job_number,
                "job_id": job_id,
                "status": status.value,
                "kind": kind,
                "round_id": (payload or {}).get("round_id"),
                "user_name": (payload or {}).get("user_name"),
                "has_form_data": isinstance(form_data, dict),
                "transcript_chars": len((payload or {}).get("transcript") or ""),
                "image_count": len((payload or {}).get("report_images") or []),
            }
        )
    return projected


def query_archive_retention() -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(Job).where(Job.status == JobStatus.archived).order_by(Job.job_number)
        ).all()
        result = []
        for job in rows:
            _ = job.rounds, job.finals, job.artifacts
            decision = build_archive_retention_decision(job)
            result.append(
                {
                    "job_number": job.job_number,
                    "job_id": job.job_id,
                    "final_round_id": decision.final_round_id,
                    "correction_round_id": decision.correction_round_id,
                    "retained_round_ids": list(decision.retained_round_ids),
                    "prunable_round_ids": list(decision.prunable_round_ids),
                    "retained_artifact_count": len(decision.retained_artifact_paths),
                    "prunable_artifact_count": len(decision.prunable_artifact_paths),
                }
            )
    return result


def query_normalized_entities() -> dict:
    with session_scope() as session:
        customers = session.scalar(select(func.count()).select_from(Customer)) or 0
        billing_profiles = session.scalar(select(func.count()).select_from(BillingProfile)) or 0
        operators = session.scalar(select(func.count()).select_from(Operator)) or 0
        job_links = session.execute(
            select(
                Job.job_number,
                Customer.name,
                BillingProfile.billing_name,
                Operator.name,
            )
            .outerjoin(Customer, Job.customer_id == Customer.id)
            .outerjoin(BillingProfile, Job.billing_profile_id == BillingProfile.id)
            .outerjoin(Operator, Job.operator_id == Operator.id)
            .order_by(Job.job_number)
        ).all()
    return {
        "customers": customers,
        "billing_profiles": billing_profiles,
        "operators": operators,
        "jobs": [
            {
                "job_number": job_number,
                "customer_name": customer_name,
                "billing_name": billing_name,
                "operator_name": operator_name,
            }
            for job_number, customer_name, billing_name, operator_name in job_links
        ],
    }


def query_geojson_exports() -> list[dict]:
    with session_scope() as session:
        rows = session.execute(
            select(Job.job_number, Job.job_id, JobGeoJSONExport.kind, JobGeoJSONExport.payload)
            .join(JobGeoJSONExport, JobGeoJSONExport.job_id == Job.id)
            .order_by(Job.job_number, JobGeoJSONExport.kind)
        ).all()
    result = []
    for job_number, job_id, kind, payload in rows:
        features = payload.get("features") if isinstance(payload, dict) else None
        first_feature = features[0] if isinstance(features, list) and features else {}
        geometry = first_feature.get("geometry") if isinstance(first_feature, dict) else None
        properties = first_feature.get("properties") if isinstance(first_feature, dict) else {}
        result.append(
            {
                "job_number": job_number,
                "job_id": job_id,
                "kind": kind,
                "feature_count": len(features) if isinstance(features, list) else 0,
                "geometry_type": geometry.get("type") if isinstance(geometry, dict) else None,
                "has_form_data": isinstance(properties.get("form_data"), dict),
                "image_count": len(properties.get("images") or []) if isinstance(properties, dict) else 0,
            }
        )
    return result


def query_tree_identity() -> dict:
    with session_scope() as session:
        tree_count = session.scalar(select(func.count()).select_from(Tree)) or 0
        rows = session.execute(
            select(Job.job_number, Customer.name, Job.tree_number)
            .outerjoin(Customer, Job.customer_id == Customer.id)
            .order_by(Job.job_number)
        ).all()
    return {
        "trees": tree_count,
        "jobs": [
            {
                "job_number": job_number,
                "customer_name": customer_name,
                "tree_number": tree_number,
            }
            for job_number, customer_name, tree_number in rows
        ],
    }


QUERIES = {
    "summary": query_summary,
    "archived-finals": query_archived_finals,
    "round-mismatches": query_round_mismatches,
    "media-by-job": query_media_by_job,
    "pruning-candidates": query_pruning_candidates,
    "report-projection": query_report_projection,
    "archive-retention": query_archive_retention,
    "normalized-entities": query_normalized_entities,
    "geojson-exports": query_geojson_exports,
    "tree-identity": query_tree_identity,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only queries against imported TRAQ jobs")
    parser.add_argument("query", choices=sorted(QUERIES.keys()))
    args = parser.parse_args()

    init_database(load_settings())
    result = QUERIES[args.query]()
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
