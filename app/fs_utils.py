"""Filesystem helpers for runtime compatibility exports."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_file(path: Path, payload: Any) -> None:
    """Write one JSON payload, creating parent directories when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
