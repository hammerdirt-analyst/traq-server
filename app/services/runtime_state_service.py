"""Runtime job/round persistence helpers extracted from the HTTP entrypoint."""
from __future__ import annotations

import inspect
import json
import logging
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from ..artifact_storage import ArtifactStore
from ..db_store import DatabaseStore


class RuntimeStateService:
    """Manage job and round persistence across DB, disk, and in-memory cache."""

    def __init__(
        self,
        *,
        storage_root: Path,
        db_store: DatabaseStore,
        artifact_store: ArtifactStore,
        logger: logging.Logger,
        parse_tree_number: Callable[[Any], int | None],
        job_record_factory: Callable[..., Any],
        round_record_factory: Callable[..., Any],
        write_json: Callable[[Path, dict[str, Any]], None],
    ) -> None:
        """Store the persistence collaborators used by runtime route handlers."""
        self._storage_root = storage_root
        self._db_store = db_store
        self._artifact_store = artifact_store
        self._logger = logger
        self._parse_tree_number = parse_tree_number
        self._job_record_factory = job_record_factory
        self._round_record_factory = round_record_factory
        self._write_json = write_json

    def job_dir(self, job_id: str) -> Path:
        """Return filesystem directory path for a job id."""
        path = self._storage_root / "jobs" / job_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def job_artifact_key(self, job_id: str, *parts: str) -> str:
        """Return artifact key rooted under one job."""
        return self._artifact_store.resolve_key("jobs", job_id, *parts)

    def job_record_path(self, job_id: str) -> Path:
        """Return path to compatibility/debug job record JSON file."""
        return self.job_dir(job_id) / "job_record.json"

    def round_dir(self, job_id: str, round_id: str) -> Path:
        """Return filesystem directory for a job round."""
        path = self.job_dir(job_id) / "rounds" / round_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def round_manifest_path(self, job_id: str, round_id: str) -> Path:
        """Return path to round manifest JSON file."""
        return self.round_dir(job_id, round_id) / "manifest.json"

    def section_dir(self, job_id: str, section_id: str) -> Path:
        """Return filesystem directory for a section within a job."""
        path = self.job_dir(job_id) / "sections" / section_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_job_record(self, record: Any) -> None:
        """Persist authoritative job shell state to DB and export a file copy."""
        payload = {
            "job_id": record.job_id,
            "job_number": record.job_number,
            "status": record.status,
            "customer_name": record.customer_name,
            "project_id": getattr(record, "project_id", None),
            "project": getattr(record, "project", None),
            "project_slug": getattr(record, "project_slug", None),
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
            self._db_store.upsert_job(
                job_id=record.job_id,
                job_number=record.job_number,
                status=record.status,
                latest_round_id=record.latest_round_id,
                latest_round_status=record.latest_round_status,
                details=payload,
            )
        except Exception:
            self._logger.exception("DB job upsert failed for %s", record.job_id)
        self._write_json(self.job_record_path(record.job_id), payload)

    def job_record_from_payload(self, payload: dict[str, Any], fallback_job_id: str) -> Any:
        """Build an in-memory job record from normalized payload data."""
        kwargs = {
            "job_id": str(payload.get("job_id") or fallback_job_id),
            "job_number": str(payload.get("job_number") or fallback_job_id),
            "status": str(payload.get("status") or "DRAFT"),
            "customer_name": payload.get("customer_name"),
            "project_id": payload.get("project_id"),
            "project": payload.get("project"),
            "project_slug": payload.get("project_slug"),
            "tree_number": self._parse_tree_number(payload.get("tree_number")),
            "address": payload.get("address"),
            "tree_species": payload.get("tree_species"),
            "reason": payload.get("reason"),
            "job_name": payload.get("job_name"),
            "job_address": payload.get("job_address"),
            "job_phone": payload.get("job_phone"),
            "contact_preference": payload.get("contact_preference"),
            "billing_name": payload.get("billing_name"),
            "billing_address": payload.get("billing_address"),
            "billing_contact_name": payload.get("billing_contact_name"),
            "location_notes": payload.get("location_notes"),
            "latest_round_id": payload.get("latest_round_id"),
            "latest_round_status": payload.get("latest_round_status"),
        }
        return self._make_job_record(**kwargs)

    def _make_job_record(self, **kwargs: Any) -> Any:
        """Construct one job record while tolerating older test doubles."""
        try:
            params = inspect.signature(self._job_record_factory).parameters
        except (TypeError, ValueError):
            params = {}
        if params:
            kwargs = {key: value for key, value in kwargs.items() if key in params}
        return self._job_record_factory(**kwargs)

    def load_rounds_from_db(self, job_id: str) -> dict[str, Any]:
        """Load persisted round metadata from the authoritative DB store."""
        rounds: dict[str, Any] = {}
        try:
            for row in self._db_store.list_job_rounds(job_id):
                round_id = str(row.get("round_id") or "")
                if not round_id:
                    continue
                rounds[round_id] = self._round_record_factory(
                    round_id=round_id,
                    status=str(row.get("status") or "DRAFT"),
                    manifest=list(row.get("manifest") or []),
                    server_revision_id=row.get("server_revision_id"),
                    client_revision_id=row.get("client_revision_id"),
                )
        except Exception:
            self._logger.exception("DB round listing failed for %s", job_id)
        return rounds

    def load_job_record_from_db(self, job_id: str) -> Any | None:
        """Load a job record from the authoritative DB store."""
        payload = self._db_store.get_job(job_id)
        if not isinstance(payload, dict):
            return None
        return self.job_record_from_payload(payload, job_id)

    def load_job_record_from_disk(self, job_id: str) -> Any | None:
        """Load compatibility/debug job record from disk."""
        path = self.job_record_path(job_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return self.job_record_from_payload(payload, job_id)

    def load_job_record(self, job_id: str) -> Any | None:
        """Load a job record, preferring the DB and falling back to disk."""
        persisted = self.load_job_record_from_db(job_id)
        if persisted is not None:
            return persisted
        return self.load_job_record_from_disk(job_id)

    def refresh_job_record_from_store(self, job_id: str, *, jobs_cache: dict[str, Any]) -> Any | None:
        """Refresh cached runtime metadata from the authoritative store."""
        persisted = self.load_job_record(job_id)
        if persisted is None:
            return None
        persisted.rounds = self.load_rounds_from_db(job_id)
        existing = jobs_cache.get(job_id)
        if existing is not None:
            persisted.rounds.update(existing.rounds)
        jobs_cache[job_id] = persisted
        return persisted

    def save_round_record(
        self,
        job_id: str,
        round_record: Any,
        *,
        review_payload: dict[str, Any] | None = None,
    ) -> None:
        """Persist authoritative round state to DB and export compatibility files."""
        try:
            self._db_store.upsert_job_round(
                job_id=job_id,
                round_id=round_record.round_id,
                status=round_record.status,
                server_revision_id=round_record.server_revision_id,
                client_revision_id=getattr(round_record, "client_revision_id", None),
                manifest=list(round_record.manifest or []),
                review_payload=review_payload,
            )
        except Exception:
            self._logger.exception("DB round upsert failed for %s/%s", job_id, round_record.round_id)
        self._write_json(self.round_manifest_path(job_id, round_record.round_id), round_record.manifest)
        if review_payload is not None:
            self._write_json(self.round_dir(job_id, round_record.round_id) / "review.json", review_payload)

    def next_job_number(self) -> str:
        """Allocate next unique human-readable job number from the DB store."""
        try:
            return self._db_store.allocate_job_number()
        except Exception as exc:
            self._logger.exception("DB job number allocation failed")
            raise HTTPException(
                status_code=500,
                detail="Job number allocation failed",
            ) from exc

    def ensure_job_record(self, job_id: str, *, jobs_cache: dict[str, Any]) -> Any | None:
        """Resolve job record from memory or storage."""
        persisted = self.refresh_job_record_from_store(job_id, jobs_cache=jobs_cache)
        if persisted is not None:
            return persisted
        return jobs_cache.get(job_id)

    def ensure_round_record(
        self,
        job_id: str,
        round_id: str,
        *,
        jobs_cache: dict[str, Any],
    ) -> tuple[Any, Any]:
        """Resolve a persisted round from authoritative storage."""
        record = self.ensure_job_record(job_id, jobs_cache=jobs_cache)
        if record is None:
            raise HTTPException(status_code=404, detail="Round not found")
        round_record = record.rounds.get(round_id)
        if round_record is None:
            persisted_round = self._db_store.get_job_round(job_id, round_id)
            if not isinstance(persisted_round, dict):
                raise HTTPException(status_code=404, detail="Round not found")
            round_record = self._round_record_factory(
                round_id=round_id,
                status=str(persisted_round.get("status") or "DRAFT"),
                manifest=list(persisted_round.get("manifest") or []),
                server_revision_id=persisted_round.get("server_revision_id"),
                client_revision_id=persisted_round.get("client_revision_id"),
            )
            record.rounds[round_id] = round_record
        return record, round_record
