"""Final and correction mutation service for archived job outputs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..db import session_scope
from ..db_models import Job, JobFinal, JobGeoJSONExport, JobStatus


class FinalMutationService:
    """Write archived final and correction snapshots into the database."""

    @staticmethod
    def _job_to_dict(job: Job) -> dict[str, Any]:
        return {
            "job_id": job.job_id,
            "job_number": job.job_number,
            "status": job.status.value,
            "final_snapshot": job.final_snapshot,
            "correction_snapshot": job.correction_snapshot,
        }

    def set_final(
        self,
        job_ref: str,
        *,
        payload: dict[str, Any],
        geojson_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._upsert_snapshot(
            job_ref,
            kind="final",
            payload=payload,
            geojson_payload=geojson_payload,
            allow_overwrite=False,
        )

    def set_correction(
        self,
        job_ref: str,
        *,
        payload: dict[str, Any],
        geojson_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._upsert_snapshot(
            job_ref,
            kind="correction",
            payload=payload,
            geojson_payload=geojson_payload,
            allow_overwrite=True,
        )

    def _upsert_snapshot(
        self,
        job_ref: str,
        *,
        kind: str,
        payload: dict[str, Any],
        geojson_payload: dict[str, Any] | None,
        allow_overwrite: bool,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            raise ValueError("Snapshot payload must be a non-empty JSON object")
        with session_scope() as session:
            job = self._find_job(session, job_ref)
            if job is None:
                raise KeyError(f"Job not found: {job_ref}")
            existing = session.scalar(
                select(JobFinal).where(JobFinal.job_id == job.id, JobFinal.kind == kind)
            )
            if existing is not None and not allow_overwrite:
                raise ValueError(f"{kind.title()} snapshot already exists for {job_ref}")
            if existing is None:
                existing = JobFinal(job=job, kind=kind, payload=payload, round_id=payload.get("round_id"))
                session.add(existing)
            else:
                existing.payload = payload
                existing.round_id = payload.get("round_id")
            if kind == "final":
                job.final_snapshot = payload
            else:
                job.correction_snapshot = payload
            job.status = JobStatus.archived

            if geojson_payload is not None:
                geojson_row = session.scalar(
                    select(JobGeoJSONExport).where(JobGeoJSONExport.job_id == job.id, JobGeoJSONExport.kind == kind)
                )
                if geojson_row is None:
                    geojson_row = JobGeoJSONExport(job=job, kind=kind, payload=geojson_payload)
                    session.add(geojson_row)
                else:
                    geojson_row.payload = geojson_payload
            session.flush()
            return {
                "job": self._job_to_dict(job),
                "kind": kind,
                "round_id": existing.round_id,
                "has_geojson": geojson_payload is not None,
            }

    @staticmethod
    def _find_job(session, job_ref: str) -> Job | None:
        if job_ref.startswith("job_"):
            return session.scalar(select(Job).where(Job.job_id == job_ref))
        return session.scalar(select(Job).where(Job.job_number == job_ref))
