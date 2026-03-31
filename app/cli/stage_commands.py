"""Staging CLI command handlers."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from app.services.staging_sync_service import StagingSyncService

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def cmd_stage_sync(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Stage completed-job bundles into a stable local directory tree."""
    try:
        service = StagingSyncService(
            backend=backend,
            root=Path(args.root),
        )
        result = service.sync(cursor_override=args.cursor)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(result.to_payload())
    return 0 if result.jobs_failed == 0 else 1


def cmd_stage_exclusions(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """List the locally excluded staged jobs."""
    del backend
    try:
        service = StagingSyncService(root=Path(args.root), backend=None)
        result = service.list_exclusions()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(result.to_payload())
    return 0


def cmd_stage_exclude(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Exclude one job from the local staging tree and remove its bundle."""
    del backend
    try:
        service = StagingSyncService(root=Path(args.root), backend=None)
        result = service.exclude_job(job_ref=args.job)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(result)
    return 0


def cmd_stage_include(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Remove one job from the local staging exclusion list."""
    del backend
    try:
        service = StagingSyncService(root=Path(args.root), backend=None)
        result = service.include_job(job_ref=args.job)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(result)
    return 0


def register_stage_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register the stage command group."""
    stage = subparsers.add_parser("stage", help="Stage completed-job bundles for local downstream use")
    stage_sub = stage.add_subparsers(dest="stage_cmd", required=True)

    sync_cmd = stage_sub.add_parser("sync", help="Sync completed jobs into the local staging tree")
    sync_cmd.add_argument("--root", default=str(Path.cwd() / "staging"), help="Local staging root directory")
    sync_cmd.add_argument("--cursor", default=None, help="Optional explicit export cursor override")
    sync_cmd.add_argument("--host", default=default_host)
    sync_cmd.add_argument("--api-key", default=default_api_key)
    sync_cmd.set_defaults(func=handlers["sync"])

    exclusions_cmd = stage_sub.add_parser("exclusions", help="List locally excluded staged jobs")
    exclusions_cmd.add_argument("--root", default=str(Path.cwd() / "staging"), help="Local staging root directory")
    exclusions_cmd.set_defaults(func=handlers["exclusions"])

    exclude_cmd = stage_sub.add_parser("exclude", help="Exclude one job from local staging and remove its bundle")
    exclude_cmd.add_argument("--job", required=True, help="Job number to exclude from local staging")
    exclude_cmd.add_argument("--root", default=str(Path.cwd() / "staging"), help="Local staging root directory")
    exclude_cmd.set_defaults(func=handlers["exclude"])

    include_cmd = stage_sub.add_parser("include", help="Remove one job from the local staging exclusion list")
    include_cmd.add_argument("--job", required=True, help="Job number to include again in local staging")
    include_cmd.add_argument("--root", default=str(Path.cwd() / "staging"), help="Local staging root directory")
    include_cmd.set_defaults(func=handlers["include"])
