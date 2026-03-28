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
