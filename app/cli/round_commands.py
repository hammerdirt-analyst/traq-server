"""Round admin CLI command handlers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
    """Execute one round action with shared CLI error handling."""
    try:
        payload = action()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_round_create(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Create a new draft round for one job."""
    return _wrap(lambda: backend.round.create(job_ref=args.job), print_json)


def cmd_round_reopen(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Reopen one round to DRAFT through the admin API."""
    return _wrap(lambda: backend.round.reopen(job_id=args.job_id, round_id=args.round_id), print_json)


def cmd_round_manifest_get(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Fetch one round manifest payload."""
    return _wrap(
        lambda: backend.round.manifest_get(job_ref=args.job, round_id=args.round_id),
        print_json,
    )


def cmd_round_manifest_set(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Replace one round manifest payload from a JSON file."""

    def action() -> object:
        path = Path(args.file)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError("Manifest file must contain a JSON list")
        items = [item for item in payload if isinstance(item, dict)]
        if len(items) != len(payload):
            raise RuntimeError("Manifest file must contain only JSON objects")
        return backend.round.manifest_set(job_ref=args.job, round_id=args.round_id, items=items)

    return _wrap(action, print_json)


def register_round_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register round command group."""
    round_cmd = subparsers.add_parser("round", help="Round admin operations")
    round_sub = round_cmd.add_subparsers(dest="round_cmd", required=True)

    create_cmd = round_sub.add_parser("create", help="Create a new draft round")
    create_cmd.add_argument("--job", required=True, help="job_id or job_number")
    create_cmd.add_argument("--host", default=default_host)
    create_cmd.add_argument("--api-key", default=default_api_key)
    create_cmd.set_defaults(func=handlers["create"])

    reopen_cmd = round_sub.add_parser("reopen", help="Reopen a round to DRAFT")
    reopen_cmd.add_argument("--job-id", required=True)
    reopen_cmd.add_argument("--round-id", required=True)
    reopen_cmd.add_argument("--host", default=default_host)
    reopen_cmd.add_argument("--api-key", default=default_api_key)
    reopen_cmd.set_defaults(func=handlers["reopen"])

    manifest_cmd = round_sub.add_parser("manifest", help="Round manifest operations")
    manifest_sub = manifest_cmd.add_subparsers(dest="round_manifest_cmd", required=True)

    manifest_get_cmd = manifest_sub.add_parser("get", help="Fetch one round manifest")
    manifest_get_cmd.add_argument("--job", required=True, help="job_id or job_number")
    manifest_get_cmd.add_argument("--round-id", required=True)
    manifest_get_cmd.add_argument("--host", default=default_host)
    manifest_get_cmd.add_argument("--api-key", default=default_api_key)
    manifest_get_cmd.set_defaults(func=handlers["manifest_get"])

    manifest_set_cmd = manifest_sub.add_parser("set", help="Replace one round manifest from JSON")
    manifest_set_cmd.add_argument("--job", required=True, help="job_id or job_number")
    manifest_set_cmd.add_argument("--round-id", required=True)
    manifest_set_cmd.add_argument("--file", required=True, help="path to manifest JSON array")
    manifest_set_cmd.add_argument("--host", default=default_host)
    manifest_set_cmd.add_argument("--api-key", default=default_api_key)
    manifest_set_cmd.set_defaults(func=handlers["manifest_set"])
