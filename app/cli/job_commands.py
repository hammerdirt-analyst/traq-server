"""Job and round admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Any, Callable
from urllib import parse


HttpCaller = Callable[..., tuple[int, Any]]
JsonPrinter = Callable[[object], None]
JobResolver = Callable[[str, str, str], str]
JobMutationFactory = Callable[[], Any]


def _print_http_result(code: int, body: Any, print_json: JsonPrinter) -> int:
    if code != 200:
        print(f"HTTP {code}: {body}")
        return 1
    print_json(body)
    return 0


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
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
    job_service_factory: JobMutationFactory,
    print_json: JsonPrinter,
) -> int:
    return _wrap(
        lambda: job_service_factory().create_job(
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
    job_service_factory: JobMutationFactory,
    print_json: JsonPrinter,
) -> int:
    return _wrap(
        lambda: job_service_factory().update_job(
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
    http: HttpCaller,
    print_json: JsonPrinter,
) -> int:
    code, body = http(
        "GET",
        f"{args.host.rstrip('/')}/v1/admin/jobs/assignments",
        api_key=args.api_key,
    )
    if code != 200:
        print(f"HTTP {code}: {body}")
        return 1
    assignments = body.get("assignments", []) if isinstance(body, dict) else []
    print_json(assignments if args.raw else body)
    return 0


def cmd_job_assign(
    args: argparse.Namespace,
    *,
    http: HttpCaller,
    resolve_job_id: JobResolver,
    print_json: JsonPrinter,
) -> int:
    try:
        job_id = resolve_job_id(args.host, args.api_key, args.job)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    code, body = http(
        "POST",
        f"{args.host.rstrip('/')}/v1/admin/jobs/{parse.quote(job_id)}/assign",
        api_key=args.api_key,
        payload={"device_id": args.device_id},
    )
    return _print_http_result(code, body, print_json)


def cmd_job_unassign(
    args: argparse.Namespace,
    *,
    http: HttpCaller,
    resolve_job_id: JobResolver,
    print_json: JsonPrinter,
) -> int:
    try:
        job_id = resolve_job_id(args.host, args.api_key, args.job)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    code, body = http(
        "POST",
        f"{args.host.rstrip('/')}/v1/admin/jobs/{parse.quote(job_id)}/unassign",
        api_key=args.api_key,
        payload={},
    )
    return _print_http_result(code, body, print_json)


def cmd_job_set_status(
    args: argparse.Namespace,
    *,
    http: HttpCaller,
    resolve_job_id: JobResolver,
    print_json: JsonPrinter,
) -> int:
    try:
        job_id = resolve_job_id(args.host, args.api_key, args.job)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    payload: dict[str, Any] = {"status": args.status}
    if args.round_id:
        payload["round_id"] = args.round_id
    if args.round_status:
        payload["round_status"] = args.round_status
    code, body = http(
        "POST",
        f"{args.host.rstrip('/')}/v1/admin/jobs/{parse.quote(job_id)}/status",
        api_key=args.api_key,
        payload=payload,
    )
    return _print_http_result(code, body, print_json)


def cmd_round_reopen(
    args: argparse.Namespace,
    *,
    http: HttpCaller,
    print_json: JsonPrinter,
) -> int:
    code, body = http(
        "POST",
        f"{args.host.rstrip('/')}/v1/admin/jobs/{args.job_id}/rounds/{args.round_id}/reopen",
        api_key=args.api_key,
        payload={},
    )
    return _print_http_result(code, body, print_json)


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
