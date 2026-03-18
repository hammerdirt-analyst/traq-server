"""Artifact storage backends for runtime media and generated outputs.

Runtime state is DB-authoritative. Artifact bytes still live outside the DB.
This module defines the storage interface used by runtime flows so the server
can switch between local filesystem storage and Google Cloud Storage.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Protocol


class ArtifactStore(Protocol):
    def resolve_key(self, *parts: str) -> str: ...
    def materialize_path(self, key: str) -> Path: ...
    def write_bytes(self, key: str, payload: bytes) -> Path: ...
    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path: ...
    def stage_output(self, key: str) -> Path: ...
    def commit_output(self, key: str, local_path: Path) -> Path: ...
    def exists(self, key: str) -> bool: ...


class BaseArtifactStore:
    """Shared helpers for artifact backends."""

    @staticmethod
    def normalize_key(key: str) -> str:
        return PurePosixPath(str(key).replace("\\", "/")).as_posix()

    def resolve_key(self, *parts: str) -> str:
        return PurePosixPath(*[str(part).strip("/") for part in parts if str(part)]).as_posix()


class LocalArtifactStore(BaseArtifactStore):
    """Local filesystem artifact backend rooted under the configured storage root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def path_for_key(self, key: str) -> Path:
        candidate = Path(str(key))
        if candidate.is_absolute():
            return candidate
        return self.root / self.normalize_key(key)

    def materialize_path(self, key: str) -> Path:
        return self.path_for_key(key)

    def write_bytes(self, key: str, payload: bytes) -> Path:
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding=encoding)
        return path

    def stage_output(self, key: str) -> Path:
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def commit_output(self, key: str, local_path: Path) -> Path:
        del key
        return local_path

    def exists(self, key: str) -> bool:
        return self.path_for_key(key).exists()


class GCSArtifactStore(BaseArtifactStore):
    """Google Cloud Storage artifact backend with a local materialization cache."""

    def __init__(
        self,
        *,
        bucket_name: str,
        prefix: str | None,
        cache_root: Path,
        client: Any | None = None,
    ) -> None:
        self.bucket_name = bucket_name.strip()
        self.prefix = self.normalize_key(prefix or "").strip(".") if prefix else ""
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._client = client

    def _blob_name(self, key: str) -> str:
        normalized = self.normalize_key(key)
        if self.prefix:
            return f"{self.prefix}/{normalized}".strip("/")
        return normalized

    def _cache_path(self, key: str) -> Path:
        return self.cache_root / self.normalize_key(key)

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import storage  # type: ignore

            self._client = storage.Client()
        return self._client

    def _bucket(self) -> Any:
        return self._get_client().bucket(self.bucket_name)

    def materialize_path(self, key: str) -> Path:
        path = self._cache_path(key)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket().blob(self._blob_name(key))
        blob.download_to_filename(str(path))
        return path

    def write_bytes(self, key: str, payload: bytes) -> Path:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        blob = self._bucket().blob(self._blob_name(key))
        blob.upload_from_filename(str(path))
        return path

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        return self.write_bytes(key, payload.encode(encoding))

    def stage_output(self, key: str) -> Path:
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def commit_output(self, key: str, local_path: Path) -> Path:
        blob = self._bucket().blob(self._blob_name(key))
        blob.upload_from_filename(str(local_path))
        cache_path = self._cache_path(key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path != cache_path:
            cache_path.write_bytes(local_path.read_bytes())
            return cache_path
        return local_path

    def exists(self, key: str) -> bool:
        cache_path = self._cache_path(key)
        if cache_path.exists():
            return True
        blob = self._bucket().blob(self._blob_name(key))
        return bool(blob.exists())
