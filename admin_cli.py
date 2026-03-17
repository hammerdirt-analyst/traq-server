#!/usr/bin/env python3
"""Admin CLI entrypoint for server operator workflows."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
try:
    import readline
except ImportError:  # pragma: no cover
    readline = None
import shlex
import sys
from typing import Any
from urllib import error, request

from app.cli.device_commands import (
    cmd_device_approve as _cmd_device_approve,
    cmd_device_issue_token as _cmd_device_issue_token,
    cmd_device_list as _cmd_device_list,
    cmd_device_pending as _cmd_device_pending,
    cmd_device_revoke as _cmd_device_revoke,
    cmd_device_validate as _cmd_device_validate,
    register_device_commands,
)
from app.cli.customer_commands import (
    cmd_billing_duplicates as _cmd_billing_duplicates,
    cmd_billing_create as _cmd_billing_create,
    cmd_billing_delete as _cmd_billing_delete,
    cmd_billing_list as _cmd_billing_list,
    cmd_billing_merge as _cmd_billing_merge,
    cmd_billing_update as _cmd_billing_update,
    cmd_billing_usage as _cmd_billing_usage,
    cmd_customer_duplicates as _cmd_customer_duplicates,
    cmd_customer_create as _cmd_customer_create,
    cmd_customer_delete as _cmd_customer_delete,
    cmd_customer_list as _cmd_customer_list,
    cmd_customer_merge as _cmd_customer_merge,
    cmd_customer_update as _cmd_customer_update,
    cmd_customer_usage as _cmd_customer_usage,
    register_customer_commands,
)
from app.cli.final_commands import (
    cmd_final_set_correction as _cmd_final_set_correction,
    cmd_final_set_final as _cmd_final_set_final,
    register_final_commands,
)
from app.cli.inspect_commands import (
    cmd_final_inspect as _cmd_final_inspect,
    cmd_job_inspect as _cmd_job_inspect,
    cmd_review_inspect as _cmd_review_inspect,
    cmd_round_inspect as _cmd_round_inspect,
    register_inspect_commands,
)
from app.cli.job_commands import (
    cmd_job_create as _cmd_job_create,
    cmd_job_assign as _cmd_job_assign,
    cmd_job_list_assignments as _cmd_job_list_assignments,
    cmd_job_set_status as _cmd_job_set_status,
    cmd_job_unassign as _cmd_job_unassign,
    cmd_job_update as _cmd_job_update,
    cmd_round_reopen as _cmd_round_reopen,
    register_job_commands,
    register_round_commands,
)
from app.cli.net_commands import (
    cmd_net_ipv4 as _cmd_net_ipv4,
    cmd_net_ipv6 as _cmd_net_ipv6,
    register_net_commands,
)
from app.config import load_settings
from app.services.customer_service import CustomerService
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.final_mutation_service import FinalMutationService
from app.services.inspection_service import InspectionService
from app.services.job_mutation_service import JobMutationService

_HISTORY_PATH = Path.home() / ".traq_admin_history"


def _settings():
    return load_settings()


def _store() -> DatabaseStore:
    settings = _settings()
    init_database(settings)
    create_schema()
    return DatabaseStore()


def _inspection_service() -> InspectionService:
    settings = _settings()
    init_database(settings)
    create_schema()
    return InspectionService(settings=settings, db_store=DatabaseStore())


def _customer_service() -> CustomerService:
    settings = _settings()
    init_database(settings)
    create_schema()
    return CustomerService()


def _job_mutation_service() -> JobMutationService:
    settings = _settings()
    init_database(settings)
    create_schema()
    return JobMutationService()


def _final_mutation_service() -> FinalMutationService:
    settings = _settings()
    init_database(settings)
    create_schema()
    return FinalMutationService()


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _http(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    timeout: int = 20,
) -> tuple[int, Any]:
    data = None
    headers = {"x-api-key": api_key}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, method=method, headers=headers, data=data)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"detail": raw}
        return int(exc.code), body


def _resolve_job_id(host: str, api_key: str, job_ref: str) -> str:
    if job_ref.startswith("job_"):
        return job_ref
    return _inspection_service().resolve_job_id(job_ref)


def _resolve_device_id(device_ref: str) -> str:
    normalized = (device_ref or "").strip()
    if not normalized:
        raise RuntimeError("Device id is required")
    rows = _store().list_devices()
    exact = [row for row in rows if str(row.get("device_id") or "") == normalized]
    if exact:
        return normalized
    matches = [
        str(row.get("device_id") or "")
        for row in rows
        if str(row.get("device_id") or "").startswith(normalized)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError(f"Device not found: {device_ref}")
    raise RuntimeError(f"Device id prefix is ambiguous: {device_ref}")


def _pending_devices() -> list[dict[str, Any]]:
    rows = _store().list_devices(status="pending")
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""))
    return rows


def cmd_device_list(args: argparse.Namespace) -> int:
    return _cmd_device_list(args, store_factory=_store, print_json=_print_json)


def cmd_device_pending(args: argparse.Namespace) -> int:
    return _cmd_device_pending(args, pending_devices=_pending_devices, print_json=_print_json)


def cmd_device_validate(args: argparse.Namespace) -> int:
    return _cmd_device_validate(
        args,
        pending_devices=_pending_devices,
        store_factory=_store,
        print_json=_print_json,
    )


def cmd_device_approve(args: argparse.Namespace) -> int:
    try:
        args.device_id = _resolve_device_id(args.device_id)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return _cmd_device_approve(args, store_factory=_store, print_json=_print_json)


def cmd_device_revoke(args: argparse.Namespace) -> int:
    try:
        args.device_id = _resolve_device_id(args.device_id)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return _cmd_device_revoke(args, store_factory=_store, print_json=_print_json)


def cmd_device_issue_token(args: argparse.Namespace) -> int:
    try:
        args.device_id = _resolve_device_id(args.device_id)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return _cmd_device_issue_token(args, store_factory=_store, print_json=_print_json)


def cmd_customer_list(args: argparse.Namespace) -> int:
    return _cmd_customer_list(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_duplicates(args: argparse.Namespace) -> int:
    return _cmd_customer_duplicates(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_create(args: argparse.Namespace) -> int:
    return _cmd_customer_create(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_update(args: argparse.Namespace) -> int:
    return _cmd_customer_update(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_usage(args: argparse.Namespace) -> int:
    return _cmd_customer_usage(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_merge(args: argparse.Namespace) -> int:
    return _cmd_customer_merge(args, service_factory=_customer_service, print_json=_print_json)


def cmd_customer_delete(args: argparse.Namespace) -> int:
    return _cmd_customer_delete(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_list(args: argparse.Namespace) -> int:
    return _cmd_billing_list(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_duplicates(args: argparse.Namespace) -> int:
    return _cmd_billing_duplicates(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_create(args: argparse.Namespace) -> int:
    return _cmd_billing_create(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_update(args: argparse.Namespace) -> int:
    return _cmd_billing_update(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_usage(args: argparse.Namespace) -> int:
    return _cmd_billing_usage(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_merge(args: argparse.Namespace) -> int:
    return _cmd_billing_merge(args, service_factory=_customer_service, print_json=_print_json)


def cmd_billing_delete(args: argparse.Namespace) -> int:
    return _cmd_billing_delete(args, service_factory=_customer_service, print_json=_print_json)


def cmd_job_list_assignments(args: argparse.Namespace) -> int:
    return _cmd_job_list_assignments(args, http=_http, print_json=_print_json)


def cmd_job_create(args: argparse.Namespace) -> int:
    return _cmd_job_create(args, job_service_factory=_job_mutation_service, print_json=_print_json)


def cmd_job_update(args: argparse.Namespace) -> int:
    return _cmd_job_update(args, job_service_factory=_job_mutation_service, print_json=_print_json)


def cmd_job_assign(args: argparse.Namespace) -> int:
    try:
        args.device_id = _resolve_device_id(args.device_id)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    return _cmd_job_assign(args, http=_http, resolve_job_id=_resolve_job_id, print_json=_print_json)


def cmd_job_unassign(args: argparse.Namespace) -> int:
    return _cmd_job_unassign(args, http=_http, resolve_job_id=_resolve_job_id, print_json=_print_json)


def cmd_job_set_status(args: argparse.Namespace) -> int:
    return _cmd_job_set_status(args, http=_http, resolve_job_id=_resolve_job_id, print_json=_print_json)


def cmd_job_inspect(args: argparse.Namespace) -> int:
    return _cmd_job_inspect(args, inspection_service=_inspection_service, print_json=_print_json)


def cmd_round_reopen(args: argparse.Namespace) -> int:
    return _cmd_round_reopen(args, http=_http, print_json=_print_json)


def cmd_round_inspect(args: argparse.Namespace) -> int:
    return _cmd_round_inspect(args, inspection_service=_inspection_service, print_json=_print_json)


def cmd_review_inspect(args: argparse.Namespace) -> int:
    return _cmd_review_inspect(args, inspection_service=_inspection_service, print_json=_print_json)


def cmd_final_inspect(args: argparse.Namespace) -> int:
    return _cmd_final_inspect(args, inspection_service=_inspection_service, print_json=_print_json)


def cmd_final_set_final(args: argparse.Namespace) -> int:
    return _cmd_final_set_final(args, service_factory=_final_mutation_service, print_json=_print_json)


def cmd_final_set_correction(args: argparse.Namespace) -> int:
    return _cmd_final_set_correction(args, service_factory=_final_mutation_service, print_json=_print_json)


def cmd_net_ipv4(args: argparse.Namespace) -> int:
    return _cmd_net_ipv4(args, print_json=_print_json)


def cmd_net_ipv6(args: argparse.Namespace) -> int:
    return _cmd_net_ipv6(args, print_json=_print_json)


def build_parser() -> argparse.ArgumentParser:
    settings = _settings()
    parser = argparse.ArgumentParser(description="TRAQ admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    register_device_commands(
        sub,
        {
            "list": cmd_device_list,
            "pending": cmd_device_pending,
            "validate": cmd_device_validate,
            "approve": cmd_device_approve,
            "revoke": cmd_device_revoke,
            "issue_token": cmd_device_issue_token,
        },
    )
    register_customer_commands(
        sub,
        {
            "customer_list": cmd_customer_list,
            "customer_duplicates": cmd_customer_duplicates,
            "customer_create": cmd_customer_create,
            "customer_update": cmd_customer_update,
            "customer_usage": cmd_customer_usage,
            "customer_merge": cmd_customer_merge,
            "customer_delete": cmd_customer_delete,
            "billing_list": cmd_billing_list,
            "billing_duplicates": cmd_billing_duplicates,
            "billing_create": cmd_billing_create,
            "billing_update": cmd_billing_update,
            "billing_usage": cmd_billing_usage,
            "billing_merge": cmd_billing_merge,
            "billing_delete": cmd_billing_delete,
        },
    )
    register_job_commands(
        sub,
        {
            "create": cmd_job_create,
            "update": cmd_job_update,
            "list_assignments": cmd_job_list_assignments,
            "assign": cmd_job_assign,
            "unassign": cmd_job_unassign,
            "set_status": cmd_job_set_status,
        },
        default_host=settings.admin_base_url,
        default_api_key=settings.api_key,
    )
    register_round_commands(
        sub,
        {"reopen": cmd_round_reopen},
        default_host=settings.admin_base_url,
        default_api_key=settings.api_key,
    )
    register_inspect_commands(
        sub,
        {
            "job_inspect": cmd_job_inspect,
            "round_inspect": cmd_round_inspect,
            "review_inspect": cmd_review_inspect,
            "final_inspect": cmd_final_inspect,
        },
    )
    register_final_commands(
        sub,
        {
            "set_final": cmd_final_set_final,
            "set_correction": cmd_final_set_correction,
        },
    )
    register_net_commands(
        sub,
        {
            "ipv4": cmd_net_ipv4,
            "ipv6": cmd_net_ipv6,
        },
    )
    return parser


def _normalize_repl_tokens(raw: str) -> list[str]:
    normalized = raw.lstrip()
    if normalized.startswith("/"):
        normalized = normalized[1:].lstrip()
    return shlex.split(normalized)


def _inject_repl_defaults(tokens: list[str], *, host: str, api_key: str) -> list[str]:
    if not tokens:
        return tokens
    top = tokens[0]
    sub = tokens[1] if len(tokens) > 1 else ""
    augmented = list(tokens)
    needs_http_defaults = (
        (top == "job" and sub in {"assign", "unassign", "list-assignments", "set-status"})
        or (top == "round" and sub == "reopen")
    )
    if needs_http_defaults:
        if "--host" not in augmented:
            augmented.extend(["--host", host])
        if "--api-key" not in augmented:
            augmented.extend(["--api-key", api_key])
    return augmented


def _repl_command_catalog() -> list[str]:
    return sorted(
        [
            "device list",
            "device pending",
            "device validate",
            "device approve",
            "device revoke",
            "device issue-token",
            "customer list",
            "customer duplicates",
            "customer create",
            "customer update",
            "customer usage",
            "customer merge",
            "customer delete",
            "customer billing list",
            "customer billing duplicates",
            "customer billing create",
            "customer billing update",
            "customer billing usage",
            "customer billing merge",
            "customer billing delete",
            "job create",
            "job update",
            "job list-assignments",
            "job assign",
            "job unassign",
            "job set-status",
            "job inspect",
            "round reopen",
            "round inspect",
            "review inspect",
            "final inspect",
            "final set-final",
            "final set-correction",
            "net ipv4",
            "net ipv6",
            "show",
            "help",
            "exit",
            "quit",
            "set host",
            "set api-key",
        ]
    )


def _setup_repl_readline() -> None:
    if readline is None:
        return
    try:
        readline.read_history_file(str(_HISTORY_PATH))
    except FileNotFoundError:
        pass

    commands = _repl_command_catalog()

    def completer(text: str, state: int) -> str | None:
        buffer = readline.get_line_buffer().lstrip("/")
        prefix = buffer if buffer else text
        matches = [cmd for cmd in commands if cmd.startswith(prefix)]
        if state >= len(matches):
            return None
        return matches[state]

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def _save_repl_history() -> None:
    if readline is None:
        return
    try:
        readline.write_history_file(str(_HISTORY_PATH))
    except OSError:
        pass


def _run_repl(parser: argparse.ArgumentParser) -> int:
    settings = _settings()
    host = settings.admin_base_url
    api_key = settings.api_key
    _setup_repl_readline()
    print("TRAQ admin CLI interactive mode")
    print("Type 'help' for commands, 'exit' to quit.")
    print(f"default host={host} api_key={'*' * len(api_key) if api_key else '(empty)'}")
    while True:
        try:
            raw = input("traq-admin> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            _save_repl_history()
            return 0
        if not raw:
            continue
        if raw in {"exit", "quit"}:
            _save_repl_history()
            return 0
        if raw == "help":
            print("Meta commands:")
            print("  set host <url>")
            print("  set api-key <key>")
            print("  show")
            print("  help")
            print("  exit")
            print("CLI commands (same as one-shot; optional leading '/'): ")
            print("  /net ipv4")
            print("  /net ipv6")
            print("  /device pending")
            print("  /device validate --index 1 --role arborist")
            print("  /device list --status approved")
            print("  /device issue-token <device_id> --ttl 900")
            print("  /customer billing delete B0001")
            print("  /job assign --job J0001 --device-id <device_id>")
            print("  /job list-assignments")
            print("  /job set-status --job J0001 --status DRAFT")
            print("  /round reopen --job-id job_1 --round-id round_1")
            continue
        if raw == "show":
            masked = "*" * len(api_key) if api_key else "(empty)"
            print(f"host={host}")
            print(f"api_key={masked}")
            continue
        if raw.startswith("set "):
            parts = raw.split(" ", 2)
            if len(parts) < 3:
                print("Usage: set host <url> | set api-key <key>")
                continue
            key = parts[1].strip().lower()
            value = parts[2].strip()
            if key == "host":
                host = value.rstrip("/")
                print(f"host={host}")
                continue
            if key in {"api-key", "apikey", "key"}:
                api_key = value
                print("api_key updated")
                continue
            print("Unknown setting. Use 'host' or 'api-key'.")
            continue
        try:
            tokens = _normalize_repl_tokens(raw)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            continue
        tokens = _inject_repl_defaults(tokens, host=host, api_key=api_key)
        try:
            args = parser.parse_args(tokens)
            code = int(args.func(args))
            if code != 0:
                print(f"(exit {code})")
        except SystemExit:
            continue
        except Exception as exc:
            print(f"ERROR: {exc}")


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        return _run_repl(parser)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
