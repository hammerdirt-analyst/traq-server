"""Admin-side staging helpers for local completed-job bundles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any


@dataclass(frozen=True)
class StagingSyncResult:
    """Summary of one manual staging sync run."""

    root: str
    previous_cursor: str | None
    next_cursor: str | None
    cursor_updated: bool
    jobs_seen: int
    jobs_staged: int
    jobs_failed: int
    staged_jobs: list[dict[str, Any]]
    failed_jobs: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        """Return JSON-serializable sync summary."""
        return {
            "root": self.root,
            "previous_cursor": self.previous_cursor,
            "next_cursor": self.next_cursor,
            "cursor_updated": self.cursor_updated,
            "jobs_seen": self.jobs_seen,
            "jobs_staged": self.jobs_staged,
            "jobs_failed": self.jobs_failed,
            "staged_jobs": self.staged_jobs,
            "failed_jobs": self.failed_jobs,
        }


@dataclass(frozen=True)
class StagingExclusionsResult:
    """Summary of the local staging exclusion file state."""

    root: str
    exclusions_path: str
    excluded_jobs: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "exclusions_path": self.exclusions_path,
            "excluded_jobs": self.excluded_jobs,
        }


class StagingSyncService:
    """Stage completed-job bundles into a stable local directory tree."""

    def __init__(self, *, backend: Any, root: Path) -> None:
        """Bind the CLI backend bundle and staging root."""
        self._backend = backend
        self._root = root

    def sync(self, *, cursor_override: str | None = None) -> StagingSyncResult:
        """Fetch changed completed jobs and stage local job bundles."""
        previous_cursor = cursor_override or self._load_cursor()
        changes = self._backend.export.changes(cursor=cursor_override or previous_cursor)
        completed_rows = list(changes.get("completed") or []) if isinstance(changes, dict) else []
        next_cursor = str(changes.get("cursor") or "").strip() or None if isinstance(changes, dict) else None
        excluded_jobs = self._load_excluded_jobs()

        staged_jobs: list[dict[str, Any]] = []
        failed_jobs: list[dict[str, Any]] = []
        for row in completed_rows:
            if not isinstance(row, dict):
                continue
            job_number = str(row.get("job_number") or "").strip().upper()
            if job_number and job_number in excluded_jobs:
                continue
            try:
                staged_jobs.append(self._stage_completed_row(row))
            except Exception as exc:
                failed_jobs.append(
                    {
                        "job_id": str(row.get("job_id") or "").strip() or None,
                        "job_number": str(row.get("job_number") or "").strip() or None,
                        "error": str(exc),
                    }
                )

        cursor_updated = not failed_jobs
        if cursor_updated and next_cursor:
            self._write_cursor(next_cursor)

        return StagingSyncResult(
            root=str(self._root),
            previous_cursor=previous_cursor,
            next_cursor=next_cursor,
            cursor_updated=cursor_updated,
            jobs_seen=len(completed_rows),
            jobs_staged=len(staged_jobs),
            jobs_failed=len(failed_jobs),
            staged_jobs=staged_jobs,
            failed_jobs=failed_jobs,
        )

    def list_exclusions(self) -> StagingExclusionsResult:
        """Return the current local exclusion list for staged jobs."""
        return StagingExclusionsResult(
            root=str(self._root),
            exclusions_path=str(self._exclusions_path()),
            excluded_jobs=sorted(self._load_excluded_jobs()),
        )

    def exclude_job(self, *, job_ref: str) -> dict[str, Any]:
        """Exclude one job from local staging and remove its bundle if present."""
        job_number = self._normalize_job_ref(job_ref)
        excluded = self._load_excluded_jobs()
        excluded.add(job_number)
        self._write_excluded_jobs(excluded)
        bundle_dir = self._jobs_root() / job_number
        removed_bundle = False
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
            removed_bundle = True
        return {
            "root": str(self._root),
            "job_number": job_number,
            "excluded": True,
            "removed_bundle": removed_bundle,
            "exclusions_path": str(self._exclusions_path()),
        }

    def include_job(self, *, job_ref: str) -> dict[str, Any]:
        """Remove one job from the local staging exclusion list."""
        job_number = self._normalize_job_ref(job_ref)
        excluded = self._load_excluded_jobs()
        was_excluded = job_number in excluded
        excluded.discard(job_number)
        self._write_excluded_jobs(excluded)
        return {
            "root": str(self._root),
            "job_number": job_number,
            "excluded": False,
            "was_excluded": was_excluded,
            "exclusions_path": str(self._exclusions_path()),
        }

    def _stage_completed_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Stage one completed-job bundle and write its manifest."""
        job_id = str(row.get("job_id") or "").strip()
        job_number = str(row.get("job_number") or "").strip()
        if not job_id or not job_number:
            raise RuntimeError("Completed export row is missing job_id or job_number")

        bundle_dir = self._jobs_root() / job_number
        images_dir = bundle_dir / "images"
        bundle_dir.mkdir(parents=True, exist_ok=True)
        images_dir.mkdir(parents=True, exist_ok=True)

        final_json_target = bundle_dir / "final.json"
        final_geojson_target = bundle_dir / "final.geojson"
        traq_pdf_target = bundle_dir / "traq_page1.pdf"

        final_json_fetch = self._backend.artifact.fetch(job_ref=job_number, kind="final-json")
        self._copy_into_bundle(Path(str(final_json_fetch.get("saved_path") or "")), final_json_target)

        geojson_fetch = self._backend.artifact.fetch(job_ref=job_number, kind="geo-json")
        self._copy_into_bundle(Path(str(geojson_fetch.get("saved_path") or "")), final_geojson_target)

        traq_fetch = self._backend.artifact.fetch(job_ref=job_number, kind="traq-pdf")
        self._copy_into_bundle(Path(str(traq_fetch.get("saved_path") or "")), traq_pdf_target)

        final_payload = json.loads(final_json_target.read_text(encoding="utf-8"))
        image_records: list[dict[str, Any]] = []
        report_images = ((row.get("final") or {}).get("report_images") or []) if isinstance(row.get("final"), dict) else []
        for image in report_images:
            if not isinstance(image, dict):
                continue
            image_ref = str(image.get("image_ref") or "").strip()
            if not image_ref:
                continue
            target_name = f"{image_ref}.jpg"
            image_target = images_dir / target_name
            self._backend.export.image_fetch(
                job_id=job_id,
                image_ref=image_ref,
                variant="report",
                output_path=str(image_target),
            )
            image_records.append(
                {
                    "image_ref": image_ref,
                    "variant": "report",
                    "source_path": self._relative_to_manifest(bundle_dir, image_target),
                    "caption": str(image.get("caption") or "").strip(),
                }
            )

        manifest = {
            "job_id": job_id,
            "job_number": job_number,
            "project_id": row.get("project_id"),
            "project": row.get("project"),
            "project_slug": row.get("project_slug"),
            "client_revision_id": final_payload.get("client_revision_id"),
            "archived_at": final_payload.get("archived_at") or row.get("archived_at"),
            "staged_at": self._now_iso(),
            "artifacts": {
                "final_json": self._relative_to_manifest(bundle_dir, final_json_target),
                "final_geojson": self._relative_to_manifest(bundle_dir, final_geojson_target),
                "traq_pdf": self._relative_to_manifest(bundle_dir, traq_pdf_target),
            },
            "images": image_records,
        }
        manifest_target = bundle_dir / "manifest.json"
        self._atomic_write_json(manifest_target, manifest)
        return {
            "job_id": job_id,
            "job_number": job_number,
            "bundle_dir": str(bundle_dir),
            "manifest_path": str(manifest_target),
            "image_count": len(image_records),
        }

    def _copy_into_bundle(self, source: Path, target: Path) -> None:
        """Copy a fetched artifact into its canonical staged location."""
        if not source.exists():
            raise RuntimeError(f"Fetched artifact not found: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=str(target.parent)) as tempdir:
            temp_path = Path(tempdir) / target.name
            shutil.copy2(source, temp_path)
            temp_path.replace(target)

    def _atomic_write_json(self, target: Path, payload: dict[str, Any]) -> None:
        """Write JSON atomically into the staged bundle."""
        target.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=str(target.parent)) as tempdir:
            temp_path = Path(tempdir) / target.name
            temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            temp_path.replace(target)

    def _load_cursor(self) -> str | None:
        """Load the persisted export cursor from staging state."""
        state_path = self._state_root() / "export_cursor.json"
        if not state_path.exists():
            return None
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        cursor = str(payload.get("cursor") or "").strip()
        return cursor or None

    def _write_cursor(self, cursor: str) -> None:
        """Persist the latest successful export cursor."""
        self._state_root().mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(self._state_root() / "export_cursor.json", {"cursor": cursor})

    def _load_excluded_jobs(self) -> set[str]:
        """Load manually editable excluded job numbers from local staging state."""
        path = self._exclusions_path()
        if not path.exists():
            return set()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            return set()
        return {
            str(job).strip().upper()
            for job in jobs
            if str(job).strip()
        }

    def _write_excluded_jobs(self, jobs: set[str]) -> None:
        """Persist the local manually editable excluded job list."""
        self._state_root().mkdir(parents=True, exist_ok=True)
        payload = {
            "jobs": sorted(jobs),
            "updated_at": self._now_iso(),
        }
        self._atomic_write_json(self._exclusions_path(), payload)

    def _exclusions_path(self) -> Path:
        return self._state_root() / "excluded_jobs.json"

    def _state_root(self) -> Path:
        return self._root / "state"

    def _jobs_root(self) -> Path:
        return self._root / "jobs"

    @staticmethod
    def _relative_to_manifest(bundle_dir: Path, target: Path) -> str:
        rel = target.relative_to(bundle_dir).as_posix()
        return f"./{rel}"

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _normalize_job_ref(job_ref: str) -> str:
        normalized = str(job_ref or "").strip().upper()
        if not normalized:
            raise RuntimeError("Job reference is required")
        return normalized
