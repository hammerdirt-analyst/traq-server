"""Device registration, token issuance, and runtime profile helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..db_store import DatabaseStore


class DeviceProfileService:
    """Wrap device auth/profile persistence behind one tested boundary."""

    def __init__(
        self,
        *,
        storage_root: Path,
        db_store: DatabaseStore,
        write_json: Any,
        logger: Any,
    ) -> None:
        """Bind storage, DB, and debug-export dependencies."""
        self._storage_root = storage_root
        self._db_store = db_store
        self._write_json = write_json
        self._logger = logger

    def register_device_record(
        self,
        *,
        device_id: str,
        device_name: str | None,
        app_version: str | None,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Persist a device registration row or raise an HTTP 500 on failure."""
        try:
            return self._db_store.register_device(
                device_id=device_id,
                device_name=device_name,
                app_version=app_version,
                profile_summary=profile_summary,
            )
        except Exception as exc:
            self._logger.exception("DB device registration failed for %s", device_id)
            raise HTTPException(status_code=500, detail="Device registration failed") from exc

    def get_device_record(self, device_id: str) -> dict[str, Any] | None:
        """Return one device registration row, suppressing lookup failures."""
        try:
            return self._db_store.get_device(device_id)
        except Exception:
            self._logger.exception("DB device lookup failed for %s", device_id)
            return None

    def issue_device_token_record(self, device_id: str, ttl_seconds: int) -> dict[str, Any]:
        """Issue a device token through the DB-backed security store."""
        try:
            return self._db_store.issue_token(
                device_id=device_id,
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            self._logger.exception("DB token issuance failed for %s", device_id)
            raise

    def load_runtime_profile(self, identity_key: str) -> dict[str, Any] | None:
        """Load one runtime profile payload from the authoritative DB store."""
        payload = self._db_store.get_runtime_profile(identity_key)
        if isinstance(payload, dict):
            return dict(payload)
        return None

    def save_runtime_profile(self, identity_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a runtime profile and export a debug copy under storage root."""
        stored = self._db_store.upsert_runtime_profile(
            identity_key=identity_key,
            profile_payload=dict(payload or {}),
        )
        self._write_json(self.profile_path(identity_key), stored)
        return stored

    def profile_dir(self) -> Path:
        """Return and ensure the debug profile export directory."""
        path = self._storage_root / "profiles"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def profile_path(self, identity_key: str) -> Path:
        """Return the hashed debug-export path for one identity key."""
        digest = hashlib.sha256(identity_key.encode("utf-8")).hexdigest()
        return self.profile_dir() / f"{digest}.json"
