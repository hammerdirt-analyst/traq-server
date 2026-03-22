"""Final and correction mutation CLI handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def _read_json(path: str | None) -> dict[str, Any] | None:
    """Load an optional JSON object from disk for final/correction writes."""
    if not path:
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON payload must be an object: {path}")
    return payload


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
    """Execute one final mutation with shared CLI error handling."""
    try:
        payload = action()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_final_set_final(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Write an original final snapshot into the database."""
    return _wrap(
        lambda: backend.final.set_final(
            job_ref=args.job,
            payload=_read_json(args.from_json) or {},
            geojson_payload=_read_json(args.geojson_json),
        ),
        print_json,
    )


def cmd_final_set_correction(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Write or replace a correction snapshot in the database."""
    return _wrap(
        lambda: backend.final.set_correction(
            job_ref=args.job,
            payload=_read_json(args.from_json) or {},
            geojson_payload=_read_json(args.geojson_json),
        ),
        print_json,
    )


def register_final_mutation_commands(final_subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]]) -> None:
    """Register final/correction mutation subcommands."""
    set_final_cmd = final_subparsers.add_parser("set-final", help="Write original final snapshot to the database")
    set_final_cmd.add_argument("--job", required=True, help="job_id or job_number")
    set_final_cmd.add_argument("--from-json", required=True, help="Path to final JSON payload")
    set_final_cmd.add_argument("--geojson-json", help="Optional path to GeoJSON payload")
    set_final_cmd.set_defaults(func=handlers["set_final"])

    set_correction_cmd = final_subparsers.add_parser("set-correction", help="Write or replace correction snapshot in the database")
    set_correction_cmd.add_argument("--job", required=True, help="job_id or job_number")
    set_correction_cmd.add_argument("--from-json", required=True, help="Path to correction JSON payload")
    set_correction_cmd.add_argument("--geojson-json", help="Optional path to GeoJSON payload")
    set_correction_cmd.set_defaults(func=handlers["set_correction"])


def register_final_commands(subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]]) -> None:
    """Attach final mutation subcommands to the existing final command group."""
    final_cmd = subparsers.choices["final"]
    final_sub = next(action for action in final_cmd._actions if isinstance(action, argparse._SubParsersAction))
    register_final_mutation_commands(final_sub, handlers)
