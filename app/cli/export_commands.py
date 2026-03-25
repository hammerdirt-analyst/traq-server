"""Export sync CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def cmd_export_changes(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Fetch export-visible job changes from the server."""
    try:
        payload = backend.export.changes(cursor=args.cursor)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_export_image_fetch(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Download one export-visible image artifact."""
    try:
        payload = backend.export.image_fetch(
            job_id=args.job_id,
            image_ref=args.image_ref,
            variant=args.variant,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_export_geojson_fetch(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Download one export-visible GeoJSON payload."""
    try:
        payload = backend.export.geojson_fetch(
            job_id=args.job_id,
            output_path=args.output,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def register_export_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register the export command group."""
    export = subparsers.add_parser("export", help="Incremental reporting export operations")
    export_sub = export.add_subparsers(dest="export_cmd", required=True)

    changes_cmd = export_sub.add_parser("changes", help="Fetch export-visible changes since a cursor")
    changes_cmd.add_argument("--cursor", default=None, help="ISO-8601 cursor from the previous sync")
    changes_cmd.add_argument("--host", default=default_host)
    changes_cmd.add_argument("--api-key", default=default_api_key)
    changes_cmd.set_defaults(func=handlers["changes"])

    image_cmd = export_sub.add_parser("image-fetch", help="Download one export image")
    image_cmd.add_argument("--job-id", required=True, help="Canonical job_id")
    image_cmd.add_argument("--image-ref", required=True, help="Image ref from export payload")
    image_cmd.add_argument(
        "--variant",
        default="auto",
        choices=["auto", "original", "report"],
        help="Preferred image variant",
    )
    image_cmd.add_argument("--output", default=None, help="Optional explicit output file path")
    image_cmd.add_argument("--host", default=default_host)
    image_cmd.add_argument("--api-key", default=default_api_key)
    image_cmd.set_defaults(func=handlers["image_fetch"])

    geojson_cmd = export_sub.add_parser("geojson-fetch", help="Download export GeoJSON")
    geojson_cmd.add_argument("--job-id", required=True, help="Canonical job_id")
    geojson_cmd.add_argument("--output", default=None, help="Optional explicit output file path")
    geojson_cmd.add_argument("--host", default=default_host)
    geojson_cmd.add_argument("--api-key", default=default_api_key)
    geojson_cmd.set_defaults(func=handlers["geojson_fetch"])
