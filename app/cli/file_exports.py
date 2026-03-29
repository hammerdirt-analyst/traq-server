"""Shared helpers for CLI export and artifact file output."""

from __future__ import annotations

import json
from pathlib import Path


def filename_from_headers(headers: dict[str, str], *, fallback: str) -> str:
    """Return the preferred download filename from HTTP headers."""

    content_disposition = headers.get("Content-Disposition") or headers.get("content-disposition") or ""
    if "filename=" in content_disposition:
        candidate = content_disposition.split("filename=", 1)[1].strip().strip('"')
        if candidate:
            return candidate
    return fallback


def save_bytes_output(*, payload: bytes, output_path: str | None, default_path: Path) -> Path:
    """Persist one binary payload to the requested or default output path."""

    saved_path = Path(output_path) if output_path else default_path
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_bytes(payload)
    return saved_path


def save_json_output(*, payload: object, output_path: str | None, default_path: Path) -> Path:
    """Persist one JSON payload to the requested or default output path."""

    saved_path = Path(output_path) if output_path else default_path
    saved_path.parent.mkdir(parents=True, exist_ok=True)
    saved_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return saved_path
