"""Artifact storage boundary for runtime media and generated outputs.

Runtime state is DB-authoritative. Artifact bytes still live outside the DB.
This module defines the minimal storage interface the live server uses so the
local filesystem backend can later be replaced with Cloud Storage without
rewriting endpoint logic again.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class LocalArtifactStore:
    """Local filesystem artifact backend rooted under the configured storage root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @staticmethod
    def _normalize_key(key: str) -> str:
        return PurePosixPath(str(key).replace("\\", "/")).as_posix()

    def resolve_key(self, *parts: str) -> str:
        """Build a normalized artifact key relative to the storage root."""
        return PurePosixPath(*[str(part).strip("/") for part in parts if str(part)]).as_posix()

    def path_for_key(self, key: str) -> Path:
        """Resolve an artifact key to a local filesystem path.

        Absolute paths are passed through for compatibility with older stored
        metadata created before the artifact boundary existed.
        """
        candidate = Path(str(key))
        if candidate.is_absolute():
            return candidate
        return self.root / self._normalize_key(key)

    def materialize_path(self, key: str) -> Path:
        """Return a readable local path for the artifact key.

        For the local backend this is just the filesystem path. Future cloud
        backends can use this contract to download to a temp file if needed.
        """
        return self.path_for_key(key)

    def write_bytes(self, key: str, payload: bytes) -> Path:
        """Persist artifact bytes for one key and return the local path."""
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        """Persist text for one key and return the local path."""
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding=encoding)
        return path

    def exists(self, key: str) -> bool:
        """Return True when the artifact exists in storage."""
        return self.path_for_key(key).exists()
