"""Device-related admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Any, Callable


StoreFactory = Callable[[], Any]
JsonPrinter = Callable[[object], None]
PendingDevices = Callable[[], list[dict[str, Any]]]


def print_device_rows(rows: list[dict[str, Any]]) -> None:
    """Render device rows for human-readable CLI output."""
    if not rows:
        print("No devices.")
        return
    for idx, row in enumerate(rows, start=1):
        device_id = str(row.get("device_id") or "")
        short_id = device_id[:8] if device_id else "unknown"
        status = str(row.get("status") or "")
        role = str(row.get("role") or "")
        name = str(row.get("device_name") or "")
        updated = str(row.get("updated_at") or row.get("created_at") or "")
        print(f"{idx:>2}. {short_id}  status={status:<9} role={role:<8} name={name} updated={updated}")


def cmd_device_list(
    args: argparse.Namespace,
    *,
    store_factory: StoreFactory,
    print_json: JsonPrinter,
) -> int:
    rows = store_factory().list_devices(status=args.status)
    if args.json:
        print_json(rows)
    else:
        print_device_rows(rows)
    return 0


def cmd_device_pending(
    args: argparse.Namespace,
    *,
    pending_devices: PendingDevices,
    print_json: JsonPrinter,
) -> int:
    rows = pending_devices()
    if args.json:
        print_json(rows)
    else:
        print_device_rows(rows)
    return 0


def cmd_device_validate(
    args: argparse.Namespace,
    *,
    pending_devices: PendingDevices,
    store_factory: StoreFactory,
    print_json: JsonPrinter,
) -> int:
    rows = pending_devices()
    if not rows:
        print("No pending devices.")
        return 1
    index = max(1, int(args.index))
    if index > len(rows):
        print(f"Invalid index {index}; pending count={len(rows)}")
        return 1
    target = rows[index - 1]
    device_id = str(target.get("device_id") or "")
    try:
        approved = store_factory().approve_device(device_id, role=args.role)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Validated device {device_id[:8]} as role={args.role}")
    print_json(approved)
    return 0


def cmd_device_approve(
    args: argparse.Namespace,
    *,
    store_factory: StoreFactory,
    print_json: JsonPrinter,
) -> int:
    try:
        row = store_factory().approve_device(args.device_id, role=args.role)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(row)
    return 0


def cmd_device_revoke(
    args: argparse.Namespace,
    *,
    store_factory: StoreFactory,
    print_json: JsonPrinter,
) -> int:
    try:
        row = store_factory().revoke_device(args.device_id)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(row)
    return 0


def cmd_device_issue_token(
    args: argparse.Namespace,
    *,
    store_factory: StoreFactory,
    print_json: JsonPrinter,
) -> int:
    try:
        row = store_factory().issue_token(args.device_id, ttl_seconds=args.ttl)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(row)
    return 0


def register_device_commands(subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]]) -> None:
    """Register the device command group on the main parser."""
    device = subparsers.add_parser("device", help="Device approval and token operations")
    device_sub = device.add_subparsers(dest="device_cmd", required=True)

    list_cmd = device_sub.add_parser("list", help="List devices")
    list_cmd.add_argument("--status", choices=["pending", "approved", "revoked"], default=None)
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.set_defaults(func=handlers["list"])

    pending_cmd = device_sub.add_parser("pending", help="List pending devices")
    pending_cmd.add_argument("--json", action="store_true")
    pending_cmd.set_defaults(func=handlers["pending"])

    validate_cmd = device_sub.add_parser(
        "validate",
        help="Validate one pending device by index (default: first pending)",
    )
    validate_cmd.add_argument("--index", type=int, default=1)
    validate_cmd.add_argument("--role", choices=["arborist", "admin"], default="arborist")
    validate_cmd.set_defaults(func=handlers["validate"])

    approve_cmd = device_sub.add_parser("approve", help="Approve a specific device id")
    approve_cmd.add_argument("device_id")
    approve_cmd.add_argument("--role", choices=["arborist", "admin"], default="arborist")
    approve_cmd.set_defaults(func=handlers["approve"])

    revoke_cmd = device_sub.add_parser("revoke", help="Revoke a specific device id")
    revoke_cmd.add_argument("device_id")
    revoke_cmd.set_defaults(func=handlers["revoke"])

    token_cmd = device_sub.add_parser("issue-token", help="Issue access token for approved device")
    token_cmd.add_argument("device_id")
    token_cmd.add_argument("--ttl", type=int, default=604800)
    token_cmd.set_defaults(func=handlers["issue_token"])
