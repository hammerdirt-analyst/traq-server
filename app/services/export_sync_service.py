"""Incremental export helpers for downstream reporting clients."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..db import session_scope
from ..db_models import Job, JobFinal, JobGeoJSONExport, JobRound, JobStatus, RoundImage
from .final_report_images_service import (
    completed_report_image_exports,
    resolve_completed_report_image_path,
)

UTC = timezone.utc


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ExportSyncService:
    """Build export-ready sync payloads from persisted job state."""

    def __init__(
        self,
        *,
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
        materialize_artifact_path: Callable[[str], Path],
    ) -> None:
        self._normalize_form_schema = normalize_form_schema
        self._materialize_artifact_path = materialize_artifact_path

    @staticmethod
    def parse_cursor(cursor: str | None) -> datetime | None:
        """Parse an ISO-8601 cursor into a timezone-aware UTC datetime."""
        raw = str(cursor or "").strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid cursor format; expected ISO-8601 datetime") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def build_changes(
        self,
        *,
        cursor: str | None,
        build_image_url: Callable[[str, str], str],
        build_geojson_url: Callable[[str], str],
    ) -> dict[str, Any]:
        """Return changed export-visible job state since the provided cursor."""
        since = self.parse_cursor(cursor)
        now = datetime.now(tz=UTC)
        in_process: list[dict[str, Any]] = []
        completed: list[dict[str, Any]] = []
        transitioned_to_completed: list[dict[str, Any]] = []
        latest_seen = since or datetime.fromtimestamp(0, tz=UTC)

        with session_scope() as session:
            jobs = session.scalars(
                select(Job).options(
                    selectinload(Job.customer),
                    selectinload(Job.billing_profile),
                    selectinload(Job.project),
                    selectinload(Job.rounds).selectinload(JobRound.images),
                    selectinload(Job.finals),
                    selectinload(Job.geojson_exports),
                )
            ).all()

        for job in jobs:
            latest_round = self._latest_round(job)
            preferred_final = self._preferred_final(job)
            preferred_geojson = self._preferred_geojson(job, preferred_final)
            changed_at = self._changed_at(
                job,
                latest_round=latest_round,
                preferred_final=preferred_final,
                preferred_geojson=preferred_geojson,
            )
            if changed_at > latest_seen:
                latest_seen = changed_at
            if since is not None and changed_at <= since:
                continue

            if job.status == JobStatus.archived and preferred_final is not None:
                completed.append(
                    self._build_completed_item(
                        job,
                        preferred_final=preferred_final,
                        preferred_geojson=preferred_geojson,
                        changed_at=changed_at,
                        build_image_url=build_image_url,
                        build_geojson_url=build_geojson_url,
                    )
                )
                if since is not None and job.archived_at is not None and job.archived_at.astimezone(UTC) > since:
                    transitioned_to_completed.append(
                        {
                            "job_id": job.job_id,
                            "job_number": job.job_number,
                            "previous_category": "in_process",
                            "current_category": "completed",
                            "updated_at": _iso(changed_at),
                        }
                    )
                continue

            in_process.append(
                self._build_in_process_item(
                    job,
                    latest_round=latest_round,
                    changed_at=changed_at,
                    build_image_url=build_image_url,
                )
            )

        in_process.sort(key=lambda item: (item.get("updated_at") or "", item.get("job_number") or ""))
        completed.sort(key=lambda item: (item.get("updated_at") or "", item.get("job_number") or ""))
        transitioned_to_completed.sort(key=lambda item: (item.get("updated_at") or "", item.get("job_number") or ""))
        cursor_value = latest_seen if latest_seen > now else now
        return {
            "cursor": _iso(cursor_value),
            "server_time": _iso(now),
            "in_process": in_process,
            "completed": completed,
            "transitioned_to_completed": transitioned_to_completed,
        }

    def resolve_image_path(self, *, job_id: str, image_ref: str, variant: str = "auto") -> Path:
        """Resolve one export-visible image reference to a readable file path."""
        normalized_variant = (variant or "auto").strip().lower()
        if normalized_variant not in {"auto", "original", "report"}:
            raise ValueError("Unsupported image variant")
        with session_scope() as session:
            job = session.scalar(
                select(Job).options(
                    selectinload(Job.rounds).selectinload(JobRound.images),
                    selectinload(Job.finals),
                ).where(Job.job_id == job_id)
            )
            if job is None:
                raise KeyError("Job not found")
            if job.status == JobStatus.archived:
                final_row = self._preferred_final(job)
                payload = final_row.payload if final_row is not None else {}
                return resolve_completed_report_image_path(
                    job_id=job_id,
                    image_ref=image_ref,
                    payload=payload if isinstance(payload, dict) else {},
                    materialize_artifact_path=self._materialize_artifact_path,
                )

            round_row = self._latest_round(job)
            if round_row is None:
                raise KeyError("Image not found")
            for image in round_row.images:
                if image.image_id != image_ref:
                    continue
                key = self._resolve_round_image_key(image, variant=normalized_variant)
                if not key:
                    raise FileNotFoundError("Image artifact not found")
                return self._materialize_artifact_path(key)
        raise KeyError("Image not found")

    def resolve_geojson_payload(self, *, job_id: str) -> dict[str, Any]:
        """Return the preferred archived GeoJSON payload for one completed job."""
        with session_scope() as session:
            job = session.scalar(
                select(Job).options(
                    selectinload(Job.finals),
                    selectinload(Job.geojson_exports),
                ).where(Job.job_id == job_id)
            )
            if job is None:
                raise KeyError("Job not found")
            final_row = self._preferred_final(job)
            geojson_row = self._preferred_geojson(job, final_row)
            if geojson_row is None:
                raise KeyError("GeoJSON not found")
            return dict(geojson_row.payload or {})

    @staticmethod
    def _latest_round(job: Job) -> JobRound | None:
        if job.latest_round_id:
            for row in job.rounds:
                if row.round_id == job.latest_round_id:
                    return row
        if not job.rounds:
            return None
        return sorted(job.rounds, key=lambda row: (row.updated_at, row.round_id))[-1]

    @staticmethod
    def _preferred_final(job: Job) -> JobFinal | None:
        finals = list(job.finals or [])
        if not finals:
            return None
        corrections = [row for row in finals if row.kind == "correction"]
        if corrections:
            return sorted(corrections, key=lambda row: (row.updated_at, row.created_at))[-1]
        finalized = [row for row in finals if row.kind == "final"]
        if finalized:
            return sorted(finalized, key=lambda row: (row.updated_at, row.created_at))[-1]
        return sorted(finals, key=lambda row: (row.updated_at, row.created_at))[-1]

    @staticmethod
    def _preferred_geojson(job: Job, preferred_final: JobFinal | None) -> JobGeoJSONExport | None:
        exports = list(job.geojson_exports or [])
        if not exports:
            return None
        if preferred_final is not None:
            matches = [row for row in exports if row.kind == preferred_final.kind]
            if matches:
                return sorted(matches, key=lambda row: (row.updated_at, row.created_at))[-1]
        return sorted(exports, key=lambda row: (row.updated_at, row.created_at))[-1]

    def _changed_at(
        self,
        job: Job,
        *,
        latest_round: JobRound | None,
        preferred_final: JobFinal | None,
        preferred_geojson: JobGeoJSONExport | None,
    ) -> datetime:
        candidates = [job.updated_at]
        if latest_round is not None:
            candidates.append(latest_round.updated_at)
            candidates.extend(image.updated_at for image in latest_round.images)
        if preferred_final is not None:
            candidates.append(preferred_final.updated_at)
        if preferred_geojson is not None:
            candidates.append(preferred_geojson.updated_at)
        return max(dt.astimezone(UTC) for dt in candidates if dt is not None)

    def _build_in_process_item(
        self,
        job: Job,
        *,
        latest_round: JobRound | None,
        changed_at: datetime,
        build_image_url: Callable[[str, str], str],
    ) -> dict[str, Any]:
        review_payload = dict(latest_round.review_payload or {}) if latest_round is not None else {}
        form_payload = self._normalized_form(review_payload)
        transcript = str(review_payload.get("transcript") or "").strip()
        images = []
        if latest_round is not None:
            for image in sorted(latest_round.images, key=lambda row: (row.created_at, row.image_id)):
                meta = dict(image.metadata_json or {})
                image_payload = {
                    "image_ref": image.image_id,
                    "image_id": image.image_id,
                    "caption": str(image.caption or meta.get("caption") or meta.get("caption_text") or "").strip(),
                    "uploaded_at": str(meta.get("uploaded_at") or "").strip() or _iso(image.created_at),
                    "download_url": build_image_url(job.job_id, image.image_id),
                }
                report_key = str(meta.get("report_image_path") or "").strip()
                if report_key:
                    image_payload["report_download_url"] = f"{build_image_url(job.job_id, image.image_id)}?variant=report"
                gps: dict[str, str] = {}
                if image.latitude:
                    gps["latitude"] = image.latitude
                if image.longitude:
                    gps["longitude"] = image.longitude
                if gps:
                    image_payload["gps"] = gps
                images.append(image_payload)
        return {
            "job_id": job.job_id,
            "job_number": job.job_number,
            "project_id": job.project.project_id if job.project else None,
            "project": job.project.name if job.project else None,
            "project_slug": job.project.slug if job.project else None,
            "category": "in_process",
            "status": job.status.value,
            "updated_at": _iso(changed_at),
            "created_at": _iso(job.created_at),
            "profile": None,
            "server_revision_id": latest_round.server_revision_id if latest_round is not None else None,
            "review": {
                "round_id": latest_round.round_id if latest_round is not None else None,
                "transcript": transcript,
                "form": form_payload,
                "images": images,
            },
        }

    def _build_completed_item(
        self,
        job: Job,
        *,
        preferred_final: JobFinal,
        preferred_geojson: JobGeoJSONExport | None,
        changed_at: datetime,
        build_image_url: Callable[[str, str], str],
        build_geojson_url: Callable[[str], str],
    ) -> dict[str, Any]:
        payload = dict(preferred_final.payload or {})
        report_images = completed_report_image_exports(
            payload=payload,
            job_id=job.job_id,
            build_image_url=build_image_url,
        )
        return {
            "job_id": job.job_id,
            "job_number": job.job_number,
            "project_id": job.project.project_id if job.project else None,
            "project": job.project.name if job.project else None,
            "project_slug": job.project.slug if job.project else None,
            "category": "completed",
            "status": job.status.value,
            "updated_at": _iso(changed_at),
            "created_at": _iso(job.created_at),
            "archived_at": _iso(job.archived_at),
            "profile": dict(payload.get("profile") or {}) or None,
            "final": {
                "kind": preferred_final.kind,
                "round_id": payload.get("round_id") or preferred_final.round_id,
                "transcript": str(payload.get("transcript") or "").strip(),
                "form": self._normalized_form(payload),
                "report_images": report_images,
                "geojson_url": build_geojson_url(job.job_id) if preferred_geojson is not None else None,
            },
        }

    def _normalized_form(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {"data": {}}
        if isinstance(payload.get("form"), dict):
            form = dict(payload.get("form") or {})
            data = form.get("data") if isinstance(form.get("data"), dict) else form
            return {"data": self._normalize_form_schema(dict(data or {}))}
        draft_form = payload.get("draft_form")
        if isinstance(draft_form, dict):
            data = draft_form.get("data") if isinstance(draft_form.get("data"), dict) else {}
            return {"data": self._normalize_form_schema(dict(data or {}))}
        return {"data": {}}

    @staticmethod
    def _resolve_round_image_key(image: RoundImage, *, variant: str) -> str | None:
        meta = dict(image.metadata_json or {})
        report_key = str(meta.get("report_image_path") or "").strip()
        original_key = str(meta.get("stored_path") or image.artifact_path or "").strip()
        if variant == "report":
            return report_key or original_key or None
        if variant == "original":
            return original_key or report_key or None
        return report_key or original_key or None
