"""Authentication, assignment, and edit-lock helpers for the HTTP layer."""
from __future__ import annotations

import logging

from fastapi import HTTPException

from ..db_store import DatabaseStore
from ..security_store import AuthContext


class AccessControlService:
    """Encapsulate auth and job-access checks used across route handlers."""

    def __init__(self, *, api_key: str, db_store: DatabaseStore, logger: logging.Logger) -> None:
        self._api_key = api_key
        self._db_store = db_store
        self._logger = logger

    def assign_job(self, *, job_id: str, device_id: str, assigned_by: str | None) -> dict:
        """Assign a job in the DB-backed assignment store."""
        try:
            return self._db_store.assign_job(
                job_id=job_id,
                device_id=device_id,
                assigned_by=assigned_by,
            )
        except (KeyError, PermissionError) as exc:
            self._logger.warning("DB assignment failed for %s -> %s: %s", job_id, device_id, exc)
            raise
        except Exception:
            self._logger.exception("DB assignment failed for %s -> %s", job_id, device_id)
            raise

    def unassign_job(self, job_id: str) -> dict:
        """Remove one job assignment from the DB-backed assignment store."""
        try:
            return self._db_store.unassign_job(job_id)
        except Exception:
            self._logger.exception("DB unassign failed for %s", job_id)
            raise

    def require_api_key(
        self,
        x_api_key: str | None,
        *,
        required_role: str | None = None,
    ) -> AuthContext:
        """Authenticate request using the operator key or a device token."""
        if x_api_key and x_api_key == self._api_key:
            return AuthContext(
                device_id=None,
                role="admin",
                is_admin=True,
                source="server_api_key",
            )
        if x_api_key:
            auth = None
            try:
                auth = self._db_store.validate_token(x_api_key)
            except Exception:
                self._logger.exception("DB token validation failed")
            if auth is not None:
                if required_role == "admin" and not auth.is_admin:
                    raise HTTPException(status_code=403, detail="Admin role required")
                return auth
        raise HTTPException(status_code=401, detail="Invalid credentials")

    @staticmethod
    def identity_key(auth: AuthContext, x_api_key: str | None) -> str:
        """Build the profile-scope identity key for the current caller."""
        if auth.source == "device_token" and auth.device_id:
            return f"device:{auth.device_id}"
        return f"admin:{x_api_key or ''}"

    @staticmethod
    def assert_round_editable(
        record,
        round_id: str,
        auth: AuthContext,
        *,
        allow_correction: bool = False,
    ) -> None:
        """Reject non-admin edits to locked rounds."""
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

    @staticmethod
    def assert_job_editable(
        record,
        auth: AuthContext,
        *,
        allow_correction: bool = False,
    ) -> None:
        """Reject non-admin edits to locked jobs."""
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

    def assert_job_assignment(
        self,
        job_id: str,
        auth: AuthContext,
        *,
        job_exists_in_memory: bool = False,
    ) -> None:
        """Enforce assignment/ownership checks for one target job id."""
        if auth.is_admin:
            return
        if not auth.device_id:
            raise HTTPException(status_code=403, detail="Device identity required")
        assigned = self._db_store.get_job_assignment(job_id)
        if assigned is None:
            job_exists_in_db = self._db_store.get_job(job_id) is not None
            if job_exists_in_memory or job_exists_in_db:
                try:
                    self._db_store.assign_job(
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
