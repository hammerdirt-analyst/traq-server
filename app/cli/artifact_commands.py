"""Artifact retrieval admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def cmd_artifact_fetch(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Export one customer-facing artifact for the provided job."""
    try:
        payload = backend.artifact.fetch(job_ref=args.job, kind=args.kind)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def register_artifact_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register the artifact command group."""
    artifact = subparsers.add_parser("artifact", help="Artifact retrieval operations")
    artifact_sub = artifact.add_subparsers(dest="artifact_cmd", required=True)

    fetch_cmd = artifact_sub.add_parser("fetch", help="Fetch one artifact into the local exports folder")
    fetch_cmd.add_argument("--job", required=True, help="job_id or job_number")
    fetch_cmd.add_argument(
        "--kind",
        required=True,
        choices=["report-pdf", "traq-pdf", "transcript", "final-json"],
    )
    fetch_cmd.add_argument("--host", default=default_host)
    fetch_cmd.add_argument("--api-key", default=default_api_key)
    fetch_cmd.set_defaults(func=handlers["fetch"])
