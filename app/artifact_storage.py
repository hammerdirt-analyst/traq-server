"""Artifact storage backends for runtime media and generated outputs.

Runtime state is DB-authoritative. Artifact bytes still live outside the DB.
This module defines the storage interface used by runtime flows so the server
can switch between local filesystem storage and Google Cloud Storage.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Protocol


class ArtifactStore(Protocol):
    """Protocol implemented by runtime artifact storage backends."""

    def resolve_key(self, *parts: str) -> str:
        """Build one stable artifact key from path-like components."""
        ...

    def materialize_path(self, key: str) -> Path:
        """Return a local readable path for the given artifact key."""
        ...

    def write_bytes(self, key: str, payload: bytes) -> Path:
        """Persist raw bytes for one artifact key and return the local path."""
        ...

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        """Persist text content for one artifact key and return the local path."""
        ...

    def stage_output(self, key: str) -> Path:
        """Return a writable local path for generated artifact output."""
        ...

    def commit_output(self, key: str, local_path: Path) -> Path:
        """Publish a staged artifact and return its materialized local path."""
        ...

    def exists(self, key: str) -> bool:
        """Return whether the backend already contains the given artifact."""
        ...


class BaseArtifactStore:
    """Shared helpers for artifact backends."""

    @staticmethod
    def normalize_key(key: str) -> str:
        """Normalize an artifact key into a POSIX-style storage identifier."""
        return PurePosixPath(str(key).replace("\\", "/")).as_posix()

    def resolve_key(self, *parts: str) -> str:
        """Build one normalized artifact key from path-like components."""
        return PurePosixPath(*[str(part).strip("/") for part in parts if str(part)]).as_posix()


class LocalArtifactStore(BaseArtifactStore):
    """Local filesystem artifact backend rooted under the configured storage root."""

    def __init__(self, root: Path) -> None:
        """Bind the local backend to one filesystem root."""
        self.root = root

    def path_for_key(self, key: str) -> Path:
        """Resolve an artifact key to an on-disk path under the local root."""
        candidate = Path(str(key))
        if candidate.is_absolute():
            return candidate
        return self.root / self.normalize_key(key)

    def materialize_path(self, key: str) -> Path:
        """Return the local filesystem path for an artifact key."""
        return self.path_for_key(key)

    def write_bytes(self, key: str, payload: bytes) -> Path:
        """Persist raw artifact bytes under the local storage root."""
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        """Persist text content under the local storage root."""
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding=encoding)
        return path

    def stage_output(self, key: str) -> Path:
        """Prepare a writable local path for generated artifact output."""
        path = self.path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def commit_output(self, key: str, local_path: Path) -> Path:
        """Finalize a staged local artifact without additional copy steps."""
        del key
        return local_path

    def exists(self, key: str) -> bool:
        """Return whether the local backend already has the artifact."""
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
        """Bind the GCS backend to one bucket and local cache root."""
        self.bucket_name = bucket_name.strip()
        self.prefix = self.normalize_key(prefix or "").strip(".") if prefix else ""
        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._client = client

    def _blob_name(self, key: str) -> str:
        """Translate one artifact key to a bucket object name."""
        normalized = self.normalize_key(key)
        if self.prefix:
            return f"{self.prefix}/{normalized}".strip("/")
        return normalized

    def _cache_path(self, key: str) -> Path:
        """Return the local cache path for one artifact key."""
        return self.cache_root / self.normalize_key(key)

    def _get_client(self) -> Any:
        """Return the lazily-initialized Google Cloud Storage client."""
        if self._client is None:
            from google.cloud import storage  # type: ignore

            self._client = storage.Client()
        return self._client

    def _bucket(self) -> Any:
        """Return the configured GCS bucket handle."""
        return self._get_client().bucket(self.bucket_name)

    def materialize_path(self, key: str) -> Path:
        """Download one artifact into the local cache if needed and return its path."""
        path = self._cache_path(key)
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        blob = self._bucket().blob(self._blob_name(key))
        blob.download_to_filename(str(path))
        return path

    def write_bytes(self, key: str, payload: bytes) -> Path:
        """Write artifact bytes to cache and upload them to GCS."""
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        blob = self._bucket().blob(self._blob_name(key))
        blob.upload_from_filename(str(path))
        return path

    def write_text(self, key: str, payload: str, *, encoding: str = "utf-8") -> Path:
        """Write text content through the byte-oriented GCS upload path."""
        return self.write_bytes(key, payload.encode(encoding))

    def stage_output(self, key: str) -> Path:
        """Return a local cache path for generated artifact output."""
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def commit_output(self, key: str, local_path: Path) -> Path:
        """Upload a staged artifact to GCS and retain a cached local copy."""
        blob = self._bucket().blob(self._blob_name(key))
        blob.upload_from_filename(str(local_path))
        cache_path = self._cache_path(key)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path != cache_path:
            cache_path.write_bytes(local_path.read_bytes())
            return cache_path
        return local_path

    def exists(self, key: str) -> bool:
        """Return whether the artifact exists in cache or in GCS."""
        cache_path = self._cache_path(key)
        if cache_path.exists():
            return True
        blob = self._bucket().blob(self._blob_name(key))
        return bool(blob.exists())
