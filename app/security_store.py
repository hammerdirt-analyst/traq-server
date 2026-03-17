"""File-backed device auth and job-assignment store.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provide lightweight server-side security state without external services:
    - device registration/approval/revocation
    - bearer token issuance/validation
    - job-to-device assignment tracking

Storage model:
    JSON files under the configured security root:
    - `devices.json`
    - `tokens.json`
    - `job_assignments.json`

Design notes:
    - Intended for small-team/field deployment workflow.
    - Simple file persistence favors inspectability and operational simplicity.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
from typing import Any


UTC = timezone.utc


def _utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(tz=UTC)


def _iso(dt: datetime) -> str:
    """Format datetime as UTC ISO8601 with trailing `Z`."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(text: str | None) -> datetime | None:
    """Parse UTC ISO8601 (`Z` accepted) into aware datetime."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


@dataclass
class AuthContext:
    """Validated auth context returned by token checks."""

    device_id: str | None
    role: str
    is_admin: bool
    source: str


class SecurityStore:
    """JSON-backed store for auth state and assignment metadata."""

    def __init__(self, root: Path) -> None:
        """Initialize store paths and ensure root directory exists."""
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.devices_path = self.root / "devices.json"
        self.tokens_path = self.root / "tokens.json"
        self.assignments_path = self.root / "job_assignments.json"

    def _read_json(self, path: Path, default: dict[str, Any]) -> dict[str, Any]:
        """Read JSON dict from disk, returning `default` on failure."""
        if not path.exists():
            return default
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
        return default

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Write JSON payload to disk (pretty-printed UTF-8)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _devices_payload(self) -> dict[str, Any]:
        """Load devices payload with guaranteed `devices` list key."""
        payload = self._read_json(self.devices_path, {"devices": []})
        if not isinstance(payload.get("devices"), list):
            payload["devices"] = []
        return payload

    def _tokens_payload(self) -> dict[str, Any]:
        """Load tokens payload with guaranteed `tokens` list key."""
        payload = self._read_json(self.tokens_path, {"tokens": []})
        if not isinstance(payload.get("tokens"), list):
            payload["tokens"] = []
        return payload

    def _assignments_payload(self) -> dict[str, Any]:
        """Load assignments payload with guaranteed `assignments` list key."""
        payload = self._read_json(self.assignments_path, {"assignments": []})
        if not isinstance(payload.get("assignments"), list):
            payload["assignments"] = []
        return payload

    def list_devices(self, status: str | None = None) -> list[dict[str, Any]]:
        """List registered devices, optionally filtered by status."""
        payload = self._devices_payload()
        devices = [d for d in payload["devices"] if isinstance(d, dict)]
        if status:
            devices = [d for d in devices if str(d.get("status") or "").lower() == status.lower()]
        return devices

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Fetch a single device by exact `device_id`."""
        for device in self.list_devices():
            if str(device.get("device_id")) == device_id:
                return device
        return None

    def register_device(
        self,
        *,
        device_id: str,
        device_name: str | None,
        app_version: str | None,
        profile_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Register or refresh a device record.

        New devices start in `pending` state and require admin approval.
        Existing revoked devices remain revoked until explicit admin action.
        """
        payload = self._devices_payload()
        devices = payload["devices"]
        now = _iso(_utc_now())
        existing = None
        for device in devices:
            if isinstance(device, dict) and str(device.get("device_id")) == device_id:
                existing = device
                break
        if existing is None:
            existing = {
                "device_id": device_id,
                "device_name": device_name,
                "app_version": app_version,
                "status": "pending",
                "role": "arborist",
                "created_at": now,
                "updated_at": now,
                "approved_at": None,
                "revoked_at": None,
                "last_seen_at": None,
                "profile_summary": profile_summary or {},
            }
            devices.append(existing)
        else:
            existing["device_name"] = device_name or existing.get("device_name")
            existing["app_version"] = app_version or existing.get("app_version")
            existing["updated_at"] = now
            if profile_summary:
                existing["profile_summary"] = profile_summary
            if existing.get("status") == "revoked":
                # Keep revoked status until explicit admin action.
                pass
        self._write_json(self.devices_path, payload)
        return existing

    def approve_device(self, device_id: str, role: str = "arborist") -> dict[str, Any]:
        """Approve a pending/revoked device and assign role.

        Args:
            device_id: Target device identifier.
            role: One of `arborist` or `admin`.
        """
        role = role.lower().strip()
        if role not in {"arborist", "admin"}:
            raise ValueError("role must be 'arborist' or 'admin'")
        payload = self._devices_payload()
        now = _iso(_utc_now())
        for device in payload["devices"]:
            if not isinstance(device, dict):
                continue
            if str(device.get("device_id")) != device_id:
                continue
            device["status"] = "approved"
            device["role"] = role
            device["approved_at"] = now
            device["revoked_at"] = None
            device["updated_at"] = now
            self._write_json(self.devices_path, payload)
            return device
        raise KeyError(f"Device not found: {device_id}")

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        """Revoke a device and invalidate its active tokens."""
        payload = self._devices_payload()
        now = _iso(_utc_now())
        found = None
        for device in payload["devices"]:
            if not isinstance(device, dict):
                continue
            if str(device.get("device_id")) != device_id:
                continue
            device["status"] = "revoked"
            device["revoked_at"] = now
            device["updated_at"] = now
            found = device
            break
        if found is None:
            raise KeyError(f"Device not found: {device_id}")
        self._write_json(self.devices_path, payload)

        tokens_payload = self._tokens_payload()
        for token in tokens_payload["tokens"]:
            if not isinstance(token, dict):
                continue
            if str(token.get("device_id")) == device_id:
                token["revoked"] = True
                token["updated_at"] = now
        self._write_json(self.tokens_path, tokens_payload)
        return found

    def issue_token(self, device_id: str, ttl_seconds: int = 900) -> dict[str, Any]:
        """Issue a new bearer token for an approved device.

        Notes:
            - Previous non-revoked tokens for the same device are retired.
            - TTL has a minimum effective floor of 60 seconds.
        """
        device = self.get_device(device_id)
        if not device:
            raise KeyError(f"Device not found: {device_id}")
        if str(device.get("status")) != "approved":
            raise PermissionError("Device is not approved")

        token = secrets.token_urlsafe(32)
        now = _utc_now()
        expires = now + timedelta(seconds=max(60, int(ttl_seconds)))
        row = {
            "token": token,
            "device_id": device_id,
            "role": device.get("role") or "arborist",
            "issued_at": _iso(now),
            "expires_at": _iso(expires),
            "revoked": False,
            "updated_at": _iso(now),
        }
        payload = self._tokens_payload()
        payload["tokens"] = [
            t for t in payload["tokens"]
            if not (
                isinstance(t, dict)
                and str(t.get("device_id")) == device_id
                and not bool(t.get("revoked"))
            )
        ]
        payload["tokens"].append(row)
        self._write_json(self.tokens_path, payload)

        devices_payload = self._devices_payload()
        now_iso = _iso(now)
        for d in devices_payload["devices"]:
            if isinstance(d, dict) and str(d.get("device_id")) == device_id:
                d["last_seen_at"] = now_iso
                d["updated_at"] = now_iso
                break
        self._write_json(self.devices_path, devices_payload)

        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": _iso(expires),
            "device_id": device_id,
            "role": row["role"],
        }

    def validate_token(self, token: str) -> AuthContext | None:
        """Validate bearer token and return auth context when active."""
        payload = self._tokens_payload()
        now = _utc_now()
        for row in payload["tokens"]:
            if not isinstance(row, dict):
                continue
            if str(row.get("token")) != token:
                continue
            if bool(row.get("revoked")):
                return None
            expires = _parse_iso(str(row.get("expires_at") or ""))
            if expires is None or expires <= now:
                return None
            role = str(row.get("role") or "arborist")
            return AuthContext(
                device_id=str(row.get("device_id") or "") or None,
                role=role,
                is_admin=(role == "admin"),
                source="device_token",
            )
        return None

    def list_job_assignments(self) -> list[dict[str, Any]]:
        """Return all current job assignments."""
        payload = self._assignments_payload()
        return [row for row in payload["assignments"] if isinstance(row, dict)]

    def get_job_assignment(self, job_id: str) -> dict[str, Any] | None:
        """Fetch assignment row for a job id, if present."""
        for row in self.list_job_assignments():
            if str(row.get("job_id")) == job_id:
                return row
        return None

    def is_job_assigned_to_device(self, job_id: str, device_id: str | None) -> bool:
        """Check whether a job is assigned to the provided device id."""
        if not device_id:
            return False
        row = self.get_job_assignment(job_id)
        if row is None:
            return False
        return str(row.get("device_id") or "") == device_id

    def assign_job(
        self,
        *,
        job_id: str,
        device_id: str,
        assigned_by: str | None = None,
    ) -> dict[str, Any]:
        """Assign or reassign a job to an approved device."""
        device = self.get_device(device_id)
        if not device:
            raise KeyError(f"Device not found: {device_id}")
        if str(device.get("status") or "").lower() != "approved":
            raise PermissionError("Device must be approved before job assignment")
        payload = self._assignments_payload()
        now = _iso(_utc_now())
        for row in payload["assignments"]:
            if not isinstance(row, dict):
                continue
            if str(row.get("job_id")) != job_id:
                continue
            row["device_id"] = device_id
            row["assigned_at"] = now
            row["assigned_by"] = assigned_by
            self._write_json(self.assignments_path, payload)
            return row
        row = {
            "job_id": job_id,
            "device_id": device_id,
            "assigned_at": now,
            "assigned_by": assigned_by,
        }
        payload["assignments"].append(row)
        self._write_json(self.assignments_path, payload)
        return row

    def unassign_job(self, job_id: str) -> dict[str, Any]:
        """Remove job assignment and return removed row."""
        payload = self._assignments_payload()
        kept: list[dict[str, Any]] = []
        removed: dict[str, Any] | None = None
        for row in payload["assignments"]:
            if not isinstance(row, dict):
                continue
            if removed is None and str(row.get("job_id")) == job_id:
                removed = row
                continue
            kept.append(row)
        if removed is None:
            raise KeyError(f"Job assignment not found: {job_id}")
        payload["assignments"] = kept
        self._write_json(self.assignments_path, payload)
        return removed
