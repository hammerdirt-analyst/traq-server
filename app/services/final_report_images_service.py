"""Helpers for completed-final report image payload handling."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, Callable


def legacy_report_image_key(*, job_id: str, raw_path: str) -> str | None:
    """Rebuild one artifact key from a legacy cached report-image path."""

    path = PurePosixPath(str(raw_path or "").replace("\\", "/"))
    parts = path.parts
    try:
        artifact_index = parts.index("artifact_cache")
    except ValueError:
        return None
    key_parts = parts[artifact_index + 1 :]
    expected_prefix = ("jobs", job_id, "sections", "job_photos", "images")
    if len(key_parts) < len(expected_prefix) + 1:
        return None
    if tuple(key_parts[: len(expected_prefix)]) != expected_prefix:
        return None
    basename = key_parts[len(expected_prefix)]
    if not basename.endswith(".report.jpg"):
        return None
    return "/".join((*expected_prefix, basename))


def merge_completed_report_images(
    *,
    media_runtime_service: Any,
    current_report_images: list[dict[str, Any]],
    archived_final_payload: dict[str, Any] | None = None,
    archived_correction_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Merge archived/current completed report images using the runtime service when available."""

    merge_report_images = getattr(media_runtime_service, "merge_report_images", None)
    if callable(merge_report_images):
        return merge_report_images(
            (
                archived_final_payload.get("report_images")
                if isinstance(archived_final_payload, dict)
                else None
            ),
            (
                archived_correction_payload.get("report_images")
                if isinstance(archived_correction_payload, dict)
                else None
            ),
            current_report_images,
        )
    return current_report_images


def resolve_completed_report_image_path(
    *,
    job_id: str,
    image_ref: str,
    payload: dict[str, Any],
    materialize_artifact_path: Callable[[str], Path],
) -> Path:
    """Resolve one archived completed-job report image to a readable path."""

    report_images = payload.get("report_images") if isinstance(payload, dict) else []
    if not isinstance(report_images, list):
        raise KeyError("Image not found")
    for index, item in enumerate(report_images, start=1):
        if not isinstance(item, dict):
            continue
        ref = f"report_{index}"
        if image_ref != ref:
            continue
        key = str(item.get("stored_path") or "").strip()
        if key:
            materialized = materialize_artifact_path(key)
            if materialized.exists():
                return materialized
        legacy_key = legacy_report_image_key(
            job_id=job_id,
            raw_path=str(item.get("path") or "").strip(),
        )
        if legacy_key:
            materialized = materialize_artifact_path(legacy_key)
            if materialized.exists():
                return materialized
        path = Path(str(item.get("path") or "").strip())
        if path.exists():
            return path
        raise FileNotFoundError("Report image not found")
    raise KeyError("Image not found")


def completed_report_image_exports(
    *,
    payload: dict[str, Any],
    job_id: str,
    build_image_url: Callable[[str, str], str],
) -> list[dict[str, Any]]:
    """Build completed-job report image export entries from one final payload."""

    report_images: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("report_images") or [], start=1):
        if not isinstance(item, dict):
            continue
        report_images.append(
            {
                "image_ref": f"report_{index}",
                "caption": str(item.get("caption") or "").strip(),
                "uploaded_at": str(item.get("uploaded_at") or "").strip(),
                "download_url": build_image_url(job_id, f"report_{index}"),
            }
        )
    return report_images
