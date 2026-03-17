"""Database-backed auth, assignment, and job metadata store.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This module mirrors the current file-backed operational store closely enough to
preserve existing API and CLI contracts while moving the source of truth into
PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import secrets
from typing import Any

from sqlalchemy import select

from .db import session_scope
from .db_models import (
    Device,
    DeviceRole,
    DeviceStatus,
    DeviceToken,
    Job,
    JobAssignment,
    JobRound,
    JobStatus,
    RoundImage,
    RoundRecording,
    RoundStatus,
    RuntimeProfile,
    UploadStatus,
)
from .security_store import AuthContext

UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class DatabaseStore:
    """PostgreSQL-backed replacement for device/auth/job-assignment metadata."""

    @staticmethod
    def _device_to_dict(device: Device) -> dict[str, Any]:
        return {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "app_version": device.app_version,
            "status": device.status.value,
            "role": device.role.value,
            "created_at": _iso(device.created_at),
            "updated_at": _iso(device.updated_at),
            "approved_at": _iso(device.approved_at),
            "revoked_at": _iso(device.revoked_at),
            "last_seen_at": _iso(device.last_seen_at),
            "profile_summary": device.profile_summary or {},
        }

    @staticmethod
    def _assignment_to_dict(row: JobAssignment) -> dict[str, Any]:
        return {
            "job_id": row.job.job_id,
            "device_id": row.device.device_id,
            "assigned_at": _iso(row.assigned_at),
            "assigned_by": row.assigned_by,
        }

    @staticmethod
    def _job_to_dict(job: Job) -> dict[str, Any]:
        payload = dict(job.details_json or {})
        payload.update(
            {
                "job_id": job.job_id,
                "job_number": job.job_number,
                "status": job.status.value,
                "customer_id": str(job.customer_id) if job.customer_id else None,
                "customer_code": job.customer.customer_code if job.customer else None,
                "customer_name": job.customer.name if job.customer else None,
                "billing_profile_id": str(job.billing_profile_id) if job.billing_profile_id else None,
                "billing_code": job.billing_profile.billing_code if job.billing_profile else None,
                "billing_name": job.billing_profile.billing_name if job.billing_profile else None,
                "latest_round_id": job.latest_round_id,
                "latest_round_status": job.latest_round_status.value if job.latest_round_status else None,
            }
        )
        return payload

    def get_runtime_profile(self, identity_key: str) -> dict[str, Any] | None:
        """Return the DB-authoritative runtime profile for one identity."""
        with session_scope() as session:
            row = session.scalar(
                select(RuntimeProfile).where(RuntimeProfile.identity_key == identity_key)
            )
            if row is None:
                return None
            return dict(row.profile_payload or {})

    def upsert_runtime_profile(
        self,
        *,
        identity_key: str,
        profile_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist the DB-authoritative runtime profile for one identity."""
        with session_scope() as session:
            row = session.scalar(
                select(RuntimeProfile).where(RuntimeProfile.identity_key == identity_key)
            )
            if row is None:
                row = RuntimeProfile(
                    identity_key=identity_key,
                    profile_payload=dict(profile_payload or {}),
                )
                session.add(row)
            else:
                row.profile_payload = dict(profile_payload or {})
            session.flush()
            return dict(row.profile_payload or {})

    def list_devices(self, status: str | None = None) -> list[dict[str, Any]]:
        with session_scope() as session:
            stmt = select(Device).order_by(Device.created_at)
            if status:
                stmt = stmt.where(Device.status == DeviceStatus(status.lower()))
            rows = session.scalars(stmt).all()
            return [self._device_to_dict(row) for row in rows]

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.scalar(select(Device).where(Device.device_id == device_id))
            return None if row is None else self._device_to_dict(row)

    def register_device(
        self,
        *,
        device_id: str,
        device_name: str | None,
        app_version: str | None,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            row = session.scalar(select(Device).where(Device.device_id == device_id))
            if row is None:
                row = Device(
                    device_id=device_id,
                    device_name=device_name,
                    app_version=app_version,
                    profile_summary=profile_summary or {},
                    status=DeviceStatus.pending,
                    role=DeviceRole.arborist,
                )
                session.add(row)
            else:
                row.device_name = device_name or row.device_name
                row.app_version = app_version or row.app_version
                if profile_summary:
                    row.profile_summary = profile_summary
            session.flush()
            return self._device_to_dict(row)

    def approve_device(self, device_id: str, role: str = "arborist") -> dict[str, Any]:
        role_enum = DeviceRole(role.lower().strip())
        with session_scope() as session:
            row = session.scalar(select(Device).where(Device.device_id == device_id))
            if row is None:
                raise KeyError(f"Device not found: {device_id}")
            now = _utc_now()
            row.status = DeviceStatus.approved
            row.role = role_enum
            row.approved_at = now
            row.revoked_at = None
            session.flush()
            return self._device_to_dict(row)

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        with session_scope() as session:
            row = session.scalar(select(Device).where(Device.device_id == device_id))
            if row is None:
                raise KeyError(f"Device not found: {device_id}")
            now = _utc_now()
            row.status = DeviceStatus.revoked
            row.revoked_at = now
            for token in row.tokens:
                token.revoked = True
                token.updated_at = now
            session.flush()
            return self._device_to_dict(row)

    def issue_token(self, device_id: str, ttl_seconds: int = 900) -> dict[str, Any]:
        with session_scope() as session:
            device = session.scalar(select(Device).where(Device.device_id == device_id))
            if device is None:
                raise KeyError(f"Device not found: {device_id}")
            if device.status != DeviceStatus.approved:
                raise PermissionError("Device is not approved")
            now = _utc_now()
            expires = now + timedelta(seconds=max(60, int(ttl_seconds)))
            for token in device.tokens:
                if not token.revoked:
                    token.revoked = True
                    token.updated_at = now
            raw_token = secrets.token_urlsafe(32)
            token_row = DeviceToken(
                token=raw_token,
                device=device,
                role=device.role,
                expires_at=expires,
                revoked=False,
            )
            device.last_seen_at = now
            session.add(token_row)
            session.flush()
            return {
                "access_token": raw_token,
                "token_type": "bearer",
                "expires_at": _iso(expires),
                "device_id": device.device_id,
                "role": device.role.value,
            }

    def validate_token(self, token: str) -> AuthContext | None:
        with session_scope() as session:
            row = session.scalar(select(DeviceToken).where(DeviceToken.token == token))
            expires_at = row.expires_at if row is not None else None
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if row is None or row.revoked or expires_at is None or expires_at <= _utc_now():
                return None
            return AuthContext(
                device_id=row.device.device_id,
                role=row.role.value,
                is_admin=(row.role == DeviceRole.admin),
                source="device_token",
            )

    def list_job_assignments(self) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = session.scalars(select(JobAssignment).order_by(JobAssignment.assigned_at)).all()
            return [self._assignment_to_dict(row) for row in rows]

    def get_job_assignment(self, job_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.scalar(
                select(JobAssignment).join(Job).where(Job.job_id == job_id)
            )
            return None if row is None else self._assignment_to_dict(row)

    def is_job_assigned_to_device(self, job_id: str, device_id: str | None) -> bool:
        if not device_id:
            return False
        row = self.get_job_assignment(job_id)
        return row is not None and str(row.get("device_id") or "") == device_id

    def assign_job(self, *, job_id: str, device_id: str, assigned_by: str | None = None) -> dict[str, Any]:
        with session_scope() as session:
            job = session.scalar(select(Job).where(Job.job_id == job_id))
            if job is None:
                raise KeyError(f"Job not found: {job_id}")
            device = session.scalar(select(Device).where(Device.device_id == device_id))
            if device is None:
                raise KeyError(f"Device not found: {device_id}")
            if device.status != DeviceStatus.approved:
                raise PermissionError("Device must be approved before job assignment")
            row = session.scalar(select(JobAssignment).where(JobAssignment.job_id == job.id))
            now = _utc_now()
            if row is None:
                row = JobAssignment(job=job, device=device, assigned_by=assigned_by, assigned_at=now)
                session.add(row)
            else:
                row.device = device
                row.assigned_by = assigned_by
                row.assigned_at = now
            session.flush()
            return self._assignment_to_dict(row)

    def unassign_job(self, job_id: str) -> dict[str, Any]:
        with session_scope() as session:
            row = session.scalar(select(JobAssignment).join(Job).where(Job.job_id == job_id))
            if row is None:
                raise KeyError(f"Job assignment not found: {job_id}")
            payload = self._assignment_to_dict(row)
            session.delete(row)
            return payload

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.scalar(select(Job).where(Job.job_id == job_id))
            return None if row is None else self._job_to_dict(row)

    def get_job_by_number(self, job_number: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.scalar(select(Job).where(Job.job_number == job_number))
            return None if row is None else self._job_to_dict(row)

    def list_job_rounds(self, job_id: str) -> list[dict[str, Any]]:
        with session_scope() as session:
            job = session.scalar(select(Job).where(Job.job_id == job_id))
            if job is None:
                return []
            rows = session.scalars(
                select(JobRound).where(JobRound.job_id == job.id).order_by(JobRound.created_at, JobRound.round_id)
            ).all()
            return [
                {
                    "round_id": row.round_id,
                    "status": row.status.value,
                    "server_revision_id": row.server_revision_id,
                    "manifest": list(row.manifest or []),
                    "review_payload": row.review_payload,
                }
                for row in rows
            ]

    def get_job_round(self, job_id: str, round_id: str) -> dict[str, Any] | None:
        with session_scope() as session:
            row = session.scalar(
                select(JobRound)
                .join(Job)
                .where(Job.job_id == job_id, JobRound.round_id == round_id)
            )
            if row is None:
                return None
            return {
                "round_id": row.round_id,
                "status": row.status.value,
                "server_revision_id": row.server_revision_id,
                "manifest": list(row.manifest or []),
                "review_payload": row.review_payload,
            }

    def upsert_job_round(
        self,
        *,
        job_id: str,
        round_id: str,
        status: str,
        server_revision_id: str | None = None,
        manifest: list[dict[str, Any]] | None = None,
        review_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            job = session.scalar(select(Job).where(Job.job_id == job_id))
            if job is None:
                raise KeyError(f"Job not found: {job_id}")
            row = session.scalar(
                select(JobRound).where(JobRound.job_id == job.id, JobRound.round_id == round_id)
            )
            if row is None:
                row = JobRound(job=job, round_id=round_id, status=RoundStatus(status.strip().upper()))
                session.add(row)
            row.status = RoundStatus(status.strip().upper())
            if server_revision_id is not None:
                row.server_revision_id = server_revision_id
            if manifest is not None:
                row.manifest = manifest
            if review_payload is not None:
                row.review_payload = review_payload
            session.flush()
            return {
                "round_id": row.round_id,
                "status": row.status.value,
                "server_revision_id": row.server_revision_id,
                "manifest": list(row.manifest or []),
                "review_payload": row.review_payload,
            }

    def list_round_recordings(self, job_id: str, round_id: str) -> list[dict[str, Any]]:
        """Return DB-authoritative recording metadata for one round."""
        with session_scope() as session:
            rows = session.scalars(
                select(RoundRecording)
                .join(JobRound)
                .join(Job)
                .where(Job.job_id == job_id, JobRound.round_id == round_id)
                .order_by(RoundRecording.section_id, RoundRecording.recording_id)
            ).all()
            return [
                {
                    "section_id": row.section_id,
                    "recording_id": row.recording_id,
                    "upload_status": row.upload_status.value,
                    "content_type": row.content_type,
                    "duration_ms": row.duration_ms,
                    "artifact_path": row.artifact_path,
                    "metadata_json": row.metadata_json or {},
                }
                for row in rows
            ]

    def get_round_recording(
        self,
        *,
        job_id: str,
        round_id: str,
        section_id: str,
        recording_id: str,
    ) -> dict[str, Any] | None:
        """Return DB-authoritative recording metadata for one uploaded recording."""
        with session_scope() as session:
            row = session.scalar(
                select(RoundRecording)
                .join(JobRound)
                .join(Job)
                .where(
                    Job.job_id == job_id,
                    JobRound.round_id == round_id,
                    RoundRecording.section_id == section_id,
                    RoundRecording.recording_id == recording_id,
                )
            )
            if row is None:
                return None
            return {
                "section_id": row.section_id,
                "recording_id": row.recording_id,
                "upload_status": row.upload_status.value,
                "content_type": row.content_type,
                "duration_ms": row.duration_ms,
                "artifact_path": row.artifact_path,
                "metadata_json": row.metadata_json or {},
            }

    def upsert_round_recording(
        self,
        *,
        job_id: str,
        round_id: str,
        section_id: str,
        recording_id: str,
        upload_status: str,
        content_type: str | None = None,
        duration_ms: int | None = None,
        artifact_path: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist DB-authoritative recording metadata for one round recording."""
        with session_scope() as session:
            round_row = session.scalar(
                select(JobRound)
                .join(Job)
                .where(Job.job_id == job_id, JobRound.round_id == round_id)
            )
            if round_row is None:
                raise KeyError(f"Round not found: {job_id}/{round_id}")
            row = session.scalar(
                select(RoundRecording).where(
                    RoundRecording.round_pk == round_row.id,
                    RoundRecording.section_id == section_id,
                    RoundRecording.recording_id == recording_id,
                )
            )
            if row is None:
                row = RoundRecording(
                    round=round_row,
                    section_id=section_id,
                    recording_id=recording_id,
                    upload_status=UploadStatus(upload_status.strip().lower()),
                )
                session.add(row)
            row.upload_status = UploadStatus(upload_status.strip().lower())
            row.content_type = content_type
            row.duration_ms = duration_ms
            row.artifact_path = artifact_path
            row.metadata_json = dict(metadata_json or {})
            session.flush()
            return {
                "section_id": row.section_id,
                "recording_id": row.recording_id,
                "upload_status": row.upload_status.value,
                "content_type": row.content_type,
                "duration_ms": row.duration_ms,
                "artifact_path": row.artifact_path,
                "metadata_json": row.metadata_json or {},
            }

    def list_round_images(self, job_id: str, round_id: str) -> list[dict[str, Any]]:
        """Return DB-authoritative image metadata for one round."""
        with session_scope() as session:
            rows = session.scalars(
                select(RoundImage)
                .join(JobRound)
                .join(Job)
                .where(Job.job_id == job_id, JobRound.round_id == round_id)
                .order_by(RoundImage.section_id, RoundImage.image_id)
            ).all()
            return [
                {
                    "section_id": row.section_id,
                    "image_id": row.image_id,
                    "upload_status": row.upload_status.value,
                    "caption": row.caption,
                    "latitude": row.latitude,
                    "longitude": row.longitude,
                    "artifact_path": row.artifact_path,
                    "metadata_json": row.metadata_json or {},
                }
                for row in rows
            ]

    def get_round_image(
        self,
        *,
        job_id: str,
        round_id: str,
        section_id: str,
        image_id: str,
    ) -> dict[str, Any] | None:
        """Return DB-authoritative image metadata for one uploaded image."""
        with session_scope() as session:
            row = session.scalar(
                select(RoundImage)
                .join(JobRound)
                .join(Job)
                .where(
                    Job.job_id == job_id,
                    JobRound.round_id == round_id,
                    RoundImage.section_id == section_id,
                    RoundImage.image_id == image_id,
                )
            )
            if row is None:
                return None
            return {
                "section_id": row.section_id,
                "image_id": row.image_id,
                "upload_status": row.upload_status.value,
                "caption": row.caption,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "artifact_path": row.artifact_path,
                "metadata_json": row.metadata_json or {},
            }

    def upsert_round_image(
        self,
        *,
        job_id: str,
        round_id: str,
        section_id: str,
        image_id: str,
        upload_status: str,
        caption: str | None = None,
        latitude: str | None = None,
        longitude: str | None = None,
        artifact_path: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist DB-authoritative image metadata for one round image."""
        with session_scope() as session:
            round_row = session.scalar(
                select(JobRound)
                .join(Job)
                .where(Job.job_id == job_id, JobRound.round_id == round_id)
            )
            if round_row is None:
                raise KeyError(f"Round not found: {job_id}/{round_id}")
            row = session.scalar(
                select(RoundImage).where(
                    RoundImage.round_pk == round_row.id,
                    RoundImage.section_id == section_id,
                    RoundImage.image_id == image_id,
                )
            )
            if row is None:
                row = RoundImage(
                    round=round_row,
                    section_id=section_id,
                    image_id=image_id,
                    upload_status=UploadStatus(upload_status.strip().lower()),
                )
                session.add(row)
            row.upload_status = UploadStatus(upload_status.strip().lower())
            row.caption = caption
            row.latitude = latitude
            row.longitude = longitude
            row.artifact_path = artifact_path
            row.metadata_json = dict(metadata_json or {})
            session.flush()
            return {
                "section_id": row.section_id,
                "image_id": row.image_id,
                "upload_status": row.upload_status.value,
                "caption": row.caption,
                "latitude": row.latitude,
                "longitude": row.longitude,
                "artifact_path": row.artifact_path,
                "metadata_json": row.metadata_json or {},
            }

    def list_jobs(self, status: str | None = None) -> list[dict[str, Any]]:
        with session_scope() as session:
            stmt = select(Job).order_by(Job.job_number)
            if status:
                stmt = stmt.where(Job.status == JobStatus(status.strip().upper()))
            rows = session.scalars(stmt).all()
            return [self._job_to_dict(row) for row in rows]

    def upsert_job(
        self,
        *,
        job_id: str,
        job_number: str,
        status: str,
        latest_round_id: str | None = None,
        latest_round_status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with session_scope() as session:
            row = session.scalar(select(Job).where(Job.job_id == job_id))
            if row is None:
                row = Job(job_id=job_id, job_number=job_number, status=JobStatus(status.strip().upper()))
                session.add(row)
            row.job_number = job_number
            row.status = JobStatus(status.strip().upper())
            row.latest_round_id = latest_round_id
            row.latest_round_status = RoundStatus(latest_round_status.strip().upper()) if latest_round_status else None
            if details:
                row.details_json = details
                if "tree_number" in details:
                    tree_number = details.get("tree_number")
                    row.tree_number = tree_number if isinstance(tree_number, int) else None
                for attr, key in (
                    ("job_name", "job_name"),
                    ("job_address", "job_address"),
                    ("reason", "reason"),
                    ("location_notes", "location_notes"),
                    ("tree_species", "tree_species"),
                ):
                    if key in details:
                        setattr(row, attr, details.get(key))
            session.flush()
            return self._job_to_dict(row)
