"""Runtime helpers for report-image generation and lookup."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..artifact_storage import ArtifactStore
from ..db_store import DatabaseStore


class ReportImageRuntimeService:
    """Handle report-image variants and archived/current report-image lookup."""

    def __init__(
        self,
        *,
        db_store: DatabaseStore,
        artifact_store: ArtifactStore,
    ) -> None:
        """Bind DB and artifact storage for report-image operations."""
        self._db_store = db_store
        self._artifact_store = artifact_store

    @staticmethod
    def build_report_image_variant(source_path: Path, report_path: Path) -> tuple[Path, int]:
        """Build compressed report-image variant for PDF embedding."""
        try:
            from PIL import Image, ImageOps  # type: ignore

            with Image.open(source_path) as image:
                image = ImageOps.exif_transpose(image)
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                elif image.mode == "L":
                    image = image.convert("RGB")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                image.save(
                    report_path,
                    format="JPEG",
                    quality=72,
                    optimize=True,
                    progressive=False,
                )
        except Exception:
            shutil.copyfile(source_path, report_path)
        return report_path, report_path.stat().st_size

    def load_job_report_images(
        self,
        *,
        job_id: str,
        round_id: str,
    ) -> list[dict[str, str]]:
        """Load report-image metadata for one round from DB-backed image state."""
        return self._report_images_for_rows(
            self._db_store.list_round_images(job_id, round_id=round_id)
        )

    def load_effective_job_report_images(
        self,
        *,
        job_id: str,
        preferred_round_id: str | None = None,
    ) -> list[dict[str, str]]:
        """Load effective report images for a job across rounds."""
        round_rows = list(self._db_store.list_job_rounds(job_id) or [])
        ordered_round_ids: list[str] = []
        if preferred_round_id:
            ordered_round_ids.append(str(preferred_round_id))
        for row in reversed(round_rows):
            round_id = str(row.get("round_id") or "").strip()
            if round_id and round_id not in ordered_round_ids:
                ordered_round_ids.append(round_id)
        image_lists: list[list[dict[str, str]]] = []
        for round_id in ordered_round_ids:
            image_lists.append(
                self._report_images_for_rows(
                    self._db_store.list_round_images(job_id, round_id=round_id)
                )
            )
        return self.merge_report_images(*image_lists)

    def _report_images_for_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Normalize stored round-image rows into report-image inputs."""
        images: list[dict[str, str]] = []
        for row in rows:
            meta = dict(row.get("metadata_json") or {})
            report_path = str(meta.get("report_image_path") or "").strip()
            stored_path = str(meta.get("stored_path") or row.get("artifact_path") or "").strip()
            candidate_key = report_path or stored_path
            if not candidate_key:
                continue
            candidate = self._artifact_store.materialize_path(candidate_key)
            if not candidate.exists():
                continue
            caption = str(
                row.get("caption")
                or meta.get("caption")
                or meta.get("caption_text")
                or ""
            ).strip()
            uploaded_at = str(meta.get("uploaded_at") or "").strip()
            images.append(
                {
                    "path": str(candidate),
                    "stored_path": candidate_key,
                    "caption": caption,
                    "uploaded_at": uploaded_at,
                }
            )
        images.sort(key=lambda item: item.get("uploaded_at", ""))
        return images[:5]

    @staticmethod
    def merge_report_images(*image_lists: list[dict[str, Any]] | None) -> list[dict[str, str]]:
        """Merge archived/current report images without dropping earlier entries."""
        merged: list[dict[str, str]] = []
        by_key: dict[str, int] = {}
        for images in image_lists:
            for item in images or []:
                path = str(item.get("path") or "").strip()
                stored_path = str(item.get("stored_path") or "").strip()
                dedupe_key = stored_path or path
                if not dedupe_key:
                    continue
                normalized = {
                    "path": path,
                    "stored_path": stored_path,
                    "caption": str(item.get("caption") or "").strip(),
                    "uploaded_at": str(item.get("uploaded_at") or "").strip(),
                }
                existing_index = by_key.get(dedupe_key)
                if existing_index is not None:
                    merged[existing_index] = normalized
                    continue
                by_key[dedupe_key] = len(merged)
                merged.append(normalized)
        return merged[:5]
