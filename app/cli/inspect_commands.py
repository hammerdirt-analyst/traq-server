"""Inspection-related admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle


JsonPrinter = Callable[[object], None]


def _inspect(run: Callable[[], object], print_json: JsonPrinter) -> int:
    """Execute one inspection action with shared CLI error handling."""
    try:
        payload = run()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_job_inspect(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Inspect current operational state for one job."""
    return _inspect(lambda: backend.job.inspect(job_ref=args.job), print_json)


def cmd_round_inspect(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Inspect one round manifest and status view."""
    return _inspect(lambda: backend.round.inspect(job_ref=args.job, round_id=args.round_id), print_json)


def cmd_review_inspect(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Inspect one stored review payload."""
    return _inspect(lambda: backend.review.inspect(job_ref=args.job, round_id=args.round_id), print_json)


def cmd_final_inspect(args: argparse.Namespace, *, backend: CliBackendBundle, print_json: JsonPrinter) -> int:
    """Inspect archived final or correction outputs for one job."""
    return _inspect(lambda: backend.final.inspect(job_ref=args.job), print_json)


def register_inspect_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register inspection subcommands."""
    job = subparsers.choices["job"]
    job_sub = next(action for action in job._actions if isinstance(action, argparse._SubParsersAction))
    inspect_job_cmd = job_sub.add_parser("inspect", help="Inspect current job operational state")
    inspect_job_cmd.add_argument("--job", required=True, help="job_id or job_number")
    inspect_job_cmd.add_argument("--host", default=default_host)
    inspect_job_cmd.add_argument("--api-key", default=default_api_key)
    inspect_job_cmd.set_defaults(func=handlers["job_inspect"])

    round_cmd = subparsers.choices["round"]
    round_sub = next(action for action in round_cmd._actions if isinstance(action, argparse._SubParsersAction))
    inspect_round_cmd = round_sub.add_parser("inspect", help="Inspect round manifest/review state")
    inspect_round_cmd.add_argument("--job", required=True, help="job_id or job_number")
    inspect_round_cmd.add_argument("--round-id", required=True)
    inspect_round_cmd.add_argument("--host", default=default_host)
    inspect_round_cmd.add_argument("--api-key", default=default_api_key)
    inspect_round_cmd.set_defaults(func=handlers["round_inspect"])

    review_cmd = subparsers.add_parser("review", help="Review payload inspection")
    review_sub = review_cmd.add_subparsers(dest="review_cmd", required=True)
    inspect_review_cmd = review_sub.add_parser("inspect", help="Inspect one round review payload")
    inspect_review_cmd.add_argument("--job", required=True, help="job_id or job_number")
    inspect_review_cmd.add_argument("--round-id", required=True)
    inspect_review_cmd.add_argument("--host", default=default_host)
    inspect_review_cmd.add_argument("--api-key", default=default_api_key)
    inspect_review_cmd.set_defaults(func=handlers["review_inspect"])

    final_cmd = subparsers.add_parser("final", help="Final and correction inspection")
    final_sub = final_cmd.add_subparsers(dest="final_cmd", required=True)
    inspect_final_cmd = final_sub.add_parser("inspect", help="Inspect final/correction outputs for a job")
    inspect_final_cmd.add_argument("--job", required=True, help="job_id or job_number")
    inspect_final_cmd.add_argument("--host", default=default_host)
    inspect_final_cmd.add_argument("--api-key", default=default_api_key)
    inspect_final_cmd.set_defaults(func=handlers["final_inspect"])
