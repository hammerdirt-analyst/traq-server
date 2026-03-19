"""Read helpers for manifests and review payload baselines."""

from __future__ import annotations

from typing import Any


class ReviewStateService:
    """Load persisted round/review state used during submit and reprocess flows."""

    def __init__(self, *, db_store: Any) -> None:
        """Bind the DB store used for persisted review/manifest lookups."""
        self._db_store = db_store

    def load_round_manifest(self, job_id: str, round_id: str) -> list[dict[str, Any]]:
        """Load one round manifest payload from the authoritative DB store."""
        payload = (self._db_store.get_job_round(job_id, round_id) or {}).get("manifest")
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def load_all_manifests(self, job_id: str) -> list[dict[str, Any]]:
        """Load and de-duplicate manifests across all rounds for a job."""
        manifest_items: list[dict[str, Any]] = []
        for row in self._db_store.list_job_rounds(job_id):
            manifest_items.extend(list(row.get("manifest") or []))
        seen: set[tuple[str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for item in manifest_items:
            artifact_id = item.get("artifact_id") or ""
            section_id = item.get("section_id") or ""
            kind = item.get("kind") or ""
            key = (artifact_id, section_id, kind)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def load_latest_review(
        self,
        job_id: str,
        exclude_round_id: str | None = None,
    ) -> dict[str, Any]:
        """Load the latest persisted review payload for baseline merges."""
        for row in reversed(self._db_store.list_job_rounds(job_id)):
            if exclude_round_id and row.get("round_id") == exclude_round_id:
                continue
            payload = row.get("review_payload")
            if isinstance(payload, dict):
                return dict(payload)
        return {}
