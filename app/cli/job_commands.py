"""Job and round admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
    """Execute one job mutation action with shared CLI error handling."""
    try:
        payload = action()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_job_create(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Create one operational job record directly in the database."""
    return _wrap(
        lambda: backend.job.create(
            job_id=args.job_id,
            job_number=args.job_number,
            status=args.status,
            customer_id=args.customer_id,
            billing_profile_id=args.billing_profile_id,
            tree_number=args.tree_number,
            job_name=args.job_name,
            job_address=args.job_address,
            reason=args.reason,
            location_notes=args.location_notes,
            tree_species=args.tree_species,
        ),
        print_json,
    )


def cmd_job_update(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Update one operational job record directly in the database."""
    return _wrap(
        lambda: backend.job.update(
            args.job,
            customer_id=args.customer_id,
            billing_profile_id=args.billing_profile_id,
            tree_number=args.tree_number,
            job_name=args.job_name,
            job_address=args.job_address,
            reason=args.reason,
            location_notes=args.location_notes,
            tree_species=args.tree_species,
            status=args.status,
        ),
        print_json,
    )


def cmd_job_list_assignments(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """List current job-to-device assignments from the admin API."""
    return _wrap(lambda: backend.job.list_assignments(raw=args.raw), print_json)


def cmd_job_assign(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Assign one job to a device through the admin API."""
    return _wrap(lambda: backend.job.assign(job_ref=args.job, device_id=args.device_id), print_json)


def cmd_job_unassign(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Remove the current assignment for one job."""
    return _wrap(lambda: backend.job.unassign(job_ref=args.job), print_json)


def cmd_job_set_status(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Force one server-side job or round status through the admin API."""
    return _wrap(
        lambda: backend.job.set_status(
            job_ref=args.job,
            status=args.status,
            round_id=args.round_id,
            round_status=args.round_status,
        ),
        print_json,
    )


def cmd_job_unlock(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Reopen a finalized job and optionally reassign it to a device."""
    return _wrap(
        lambda: backend.job.unlock(
            job_ref=args.job,
            round_id=args.round_id,
            device_id=args.device_id,
        ),
        print_json,
    )


def cmd_round_reopen(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Reopen one round to DRAFT through the admin API."""
    return _wrap(lambda: backend.round.reopen(job_id=args.job_id, round_id=args.round_id), print_json)


def register_job_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register job command group."""
    job = subparsers.add_parser("job", help="Job assignment/status operations")
    job_sub = job.add_subparsers(dest="job_cmd", required=True)

    create_cmd = job_sub.add_parser("create", help="Create an operational job record")
    create_cmd.add_argument("--job-id", required=True)
    create_cmd.add_argument("--job-number", required=True)
    create_cmd.add_argument("--customer-id")
    create_cmd.add_argument("--billing-profile-id")
    create_cmd.add_argument("--tree-number")
    create_cmd.add_argument("--job-name")
    create_cmd.add_argument("--job-address")
    create_cmd.add_argument("--reason")
    create_cmd.add_argument("--location-notes")
    create_cmd.add_argument("--tree-species")
    create_cmd.add_argument("--host", default=default_host)
    create_cmd.add_argument("--api-key", default=default_api_key)
    create_cmd.add_argument(
        "--status",
        default="DRAFT",
        choices=[
            "NOT_STARTED",
            "DRAFT",
            "SUBMITTED_FOR_PROCESSING",
            "REVIEW_RETURNED",
            "ARCHIVED",
            "FAILED",
        ],
    )
    create_cmd.set_defaults(func=handlers["create"])

    update_cmd = job_sub.add_parser("update", help="Update operational job metadata")
    update_cmd.add_argument("--job", required=True, help="job_id or job_number")
    update_cmd.add_argument("--customer-id")
    update_cmd.add_argument("--billing-profile-id")
    update_cmd.add_argument("--tree-number")
    update_cmd.add_argument("--job-name")
    update_cmd.add_argument("--job-address")
    update_cmd.add_argument("--reason")
    update_cmd.add_argument("--location-notes")
    update_cmd.add_argument("--tree-species")
    update_cmd.add_argument("--host", default=default_host)
    update_cmd.add_argument("--api-key", default=default_api_key)
    update_cmd.add_argument(
        "--status",
        choices=[
            "NOT_STARTED",
            "DRAFT",
            "SUBMITTED_FOR_PROCESSING",
            "REVIEW_RETURNED",
            "ARCHIVED",
            "FAILED",
        ],
    )
    update_cmd.set_defaults(func=handlers["update"])

    assign_cmd = job_sub.add_parser("assign", help="Assign or reassign a job to a device")
    assign_cmd.add_argument("--job", required=True, help="job_id or job_number")
    assign_cmd.add_argument("--device-id", required=True)
    assign_cmd.add_argument("--host", default=default_host)
    assign_cmd.add_argument("--api-key", default=default_api_key)
    assign_cmd.set_defaults(func=handlers["assign"])

    unlock_cmd = job_sub.add_parser("unlock", help="Reopen a finalized job and optionally reassign it")
    unlock_cmd.add_argument("--job", required=True, help="job_id or job_number")
    unlock_cmd.add_argument("--round-id")
    unlock_cmd.add_argument("--device-id")
    unlock_cmd.add_argument("--host", default=default_host)
    unlock_cmd.add_argument("--api-key", default=default_api_key)
    unlock_cmd.set_defaults(func=handlers["unlock"])

    unassign_cmd = job_sub.add_parser("unassign", help="Remove assignment from a job")
    unassign_cmd.add_argument("--job", required=True, help="job_id or job_number")
    unassign_cmd.add_argument("--host", default=default_host)
    unassign_cmd.add_argument("--api-key", default=default_api_key)
    unassign_cmd.set_defaults(func=handlers["unassign"])

    list_assign_cmd = job_sub.add_parser("list-assignments", help="List job assignments")
    list_assign_cmd.add_argument("--host", default=default_host)
    list_assign_cmd.add_argument("--api-key", default=default_api_key)
    list_assign_cmd.add_argument("--raw", action="store_true")
    list_assign_cmd.set_defaults(func=handlers["list_assignments"])

    status_cmd = job_sub.add_parser("set-status", help="Set job status (and optionally round status)")
    status_cmd.add_argument("--job", required=True, help="job_id or job_number")
    status_cmd.add_argument(
        "--status",
        required=True,
        choices=[
            "NOT_STARTED",
            "DRAFT",
            "SUBMITTED_FOR_PROCESSING",
            "REVIEW_RETURNED",
            "ARCHIVED",
            "FAILED",
        ],
    )
    status_cmd.add_argument("--round-id")
    status_cmd.add_argument(
        "--round-status",
        choices=["DRAFT", "SUBMITTED_FOR_PROCESSING", "REVIEW_RETURNED", "FAILED"],
    )
    status_cmd.add_argument("--host", default=default_host)
    status_cmd.add_argument("--api-key", default=default_api_key)
    status_cmd.set_defaults(func=handlers["set_status"])


def register_round_commands(subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]], *, default_host: str, default_api_key: str) -> None:
    """Register round command group."""
    round_cmd = subparsers.add_parser("round", help="Round admin operations")
    round_sub = round_cmd.add_subparsers(dest="round_cmd", required=True)

    reopen_cmd = round_sub.add_parser("reopen", help="Reopen a round to DRAFT")
    reopen_cmd.add_argument("--job-id", required=True)
    reopen_cmd.add_argument("--round-id", required=True)
    reopen_cmd.add_argument("--host", default=default_host)
    reopen_cmd.add_argument("--api-key", default=default_api_key)
    reopen_cmd.set_defaults(func=handlers["reopen"])
