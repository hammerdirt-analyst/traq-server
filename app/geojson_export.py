"""GeoJSON export utilities for finalized TRAQ jobs.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Build and persist a public-map-safe GeoJSON feature collection from the
    reviewed final form payload.

Privacy contract:
    - Export includes only scrubbed form data plus minimal metadata.
    - Client-identifying fields are removed before writing GeoJSON.
    - Image entries include caption/timestamp metadata only (no file paths).

Geometry contract:
    - If valid GPS exists in `client_tree_details.gps`, export geometry is a
      GeoJSON Point with coordinates `[longitude, latitude]`.
    - If GPS is missing/invalid, geometry is `null`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _coerce_float(value: Any) -> float | None:
    """Convert supported scalar values to float, else return ``None``."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _extract_point(form_data: dict[str, Any]) -> tuple[float, float] | None:
    """Extract `(lat, lon)` from form payload when valid and in range."""
    client_tree = form_data.get("client_tree_details")
    if not isinstance(client_tree, dict):
        return None
    gps = client_tree.get("gps")
    if not isinstance(gps, dict):
        return None
    lat = _coerce_float(gps.get("latitude"))
    lon = _coerce_float(gps.get("longitude"))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def _scrub_form_data(form_data: dict[str, Any]) -> dict[str, Any]:
    """Remove client-identifying fields for public-map export.

    Current scrub list is intentionally conservative and can be expanded with
    policy changes.
    """
    scrubbed = dict(form_data or {})
    client_tree = scrubbed.get("client_tree_details")
    if isinstance(client_tree, dict):
        client_tree_scrubbed = dict(client_tree)
        for key in (
            "client",
            "address_tree_location",
            "assessors",
            "date",
            "time",
        ):
            client_tree_scrubbed.pop(key, None)
        scrubbed["client_tree_details"] = client_tree_scrubbed
    return scrubbed


def build_final_geojson(
    *,
    job_number: str | None,
    user_name: str | None,
    form_data: dict[str, Any],
    report_images: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build GeoJSON FeatureCollection payload for a final job.

    Args:
        job_number: Human-readable job number for export metadata.
        user_name: Arborist/user name associated with final submission.
        form_data: Final normalized form data payload.
        report_images: Image metadata list from final processing.

    Returns:
        GeoJSON FeatureCollection with a single Feature.
    """
    scrubbed_form = _scrub_form_data(form_data)
    point = _extract_point(form_data)
    geometry: dict[str, Any] | None = None
    if point is not None:
        lat, lon = point
        geometry = {
            "type": "Point",
            "coordinates": [lon, lat],
        }

    images: list[dict[str, Any]] = []
    for image in report_images:
        if not isinstance(image, dict):
            continue
        images.append(
            {
                "caption": image.get("caption"),
                "uploaded_at": image.get("uploaded_at"),
            }
        )

    feature = {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "job_number": job_number,
            "user_name": user_name,
            "form_data": scrubbed_form,
            "images": images,
        },
    }

    return {
        "type": "FeatureCollection",
        "features": [feature],
    }


def write_final_geojson(
    *,
    output_path: Path,
    job_number: str | None,
    user_name: str | None,
    form_data: dict[str, Any],
    report_images: list[dict[str, Any]],
) -> None:
    """Write GeoJSON export payload to disk as UTF-8 JSON."""
    payload = build_final_geojson(
        job_number=job_number,
        user_name=user_name,
        form_data=form_data,
        report_images=report_images,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
