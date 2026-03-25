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
import uuid
from urllib import error, request

from app.cli.artifact_commands import (
    cmd_artifact_fetch as _cmd_artifact_fetch,
    register_artifact_commands,
)
from app.cli.customer_commands import (
    cmd_billing_create as _cmd_billing_create,
    cmd_billing_delete as _cmd_billing_delete,
    cmd_billing_duplicates as _cmd_billing_duplicates,
    cmd_billing_list as _cmd_billing_list,
    cmd_billing_merge as _cmd_billing_merge,
    cmd_billing_update as _cmd_billing_update,
    cmd_billing_usage as _cmd_billing_usage,
    cmd_customer_create as _cmd_customer_create,
    cmd_customer_delete as _cmd_customer_delete,
    cmd_customer_duplicates as _cmd_customer_duplicates,
    cmd_customer_list as _cmd_customer_list,
    cmd_customer_merge as _cmd_customer_merge,
    cmd_customer_update as _cmd_customer_update,
    cmd_customer_usage as _cmd_customer_usage,
    register_customer_commands,
)
from app.cli.device_commands import (
    cmd_device_approve as _cmd_device_approve,
    cmd_device_issue_token as _cmd_device_issue_token,
    cmd_device_list as _cmd_device_list,
    cmd_device_pending as _cmd_device_pending,
    cmd_device_revoke as _cmd_device_revoke,
    cmd_device_validate as _cmd_device_validate,
    register_device_commands,
)
from app.cli.export_commands import (
    cmd_export_changes as _cmd_export_changes,
    cmd_export_geojson_fetch as _cmd_export_geojson_fetch,
    cmd_export_image_fetch as _cmd_export_image_fetch,
    register_export_commands,
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
    cmd_job_assign as _cmd_job_assign,
    cmd_job_create as _cmd_job_create,
    cmd_job_list_assignments as _cmd_job_list_assignments,
    cmd_job_set_status as _cmd_job_set_status,
    cmd_job_unassign as _cmd_job_unassign,
    cmd_job_unlock as _cmd_job_unlock,
    cmd_job_update as _cmd_job_update,
    register_job_commands,
)
from app.cli.net_commands import (
    cmd_net_ipv4 as _cmd_net_ipv4_impl,
    cmd_net_ipv6 as _cmd_net_ipv6_impl,
    register_net_commands,
)
from app.cli.round_commands import (
    cmd_round_create as _cmd_round_create,
    cmd_round_manifest_get as _cmd_round_manifest_get,
    cmd_round_manifest_set as _cmd_round_manifest_set,
    cmd_round_reprocess as _cmd_round_reprocess,
    cmd_round_submit as _cmd_round_submit,
    cmd_round_reopen as _cmd_round_reopen,
    register_round_commands,
)
from app.cli.tree_commands import cmd_tree_identify as _cmd_tree_identify, register_tree_commands
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.config import load_settings
from app.services.artifact_fetch_service import ArtifactFetchService
from app.services.customer_service import CustomerService
from app.services.final_mutation_service import FinalMutationService
from app.services.inspection_service import InspectionService
from app.services.job_mutation_service import JobMutationService
from app.artifact_storage import create_artifact_store

_HISTORY_PATH = Path.home() / ".traq_admin_history"
_CONTEXT_NAMES = {"local", "cloud", "remote"}


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


def _artifact_fetch_service() -> ArtifactFetchService:
    settings = _settings()
    init_database(settings)
    create_schema()
    return ArtifactFetchService(
        settings=settings,
        db_store=DatabaseStore(),
        artifact_store=create_artifact_store(settings),
    )


def _context_defaults(name: str) -> tuple[str | None, str | None]:
    settings = _settings()
    if name == "local":
        return settings.admin_base_url, settings.api_key
    if name in {"cloud", "remote"}:
        host = settings.cloud_admin_base_url
        api_key = settings.cloud_api_key
        if not host or not api_key:
            raise RuntimeError(
                "Remote context requires TRAQ_CLOUD_ADMIN_BASE_URL and TRAQ_CLOUD_API_KEY."
            )
        return host, api_key
    raise RuntimeError(f"Unknown context: {name}")


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2))


def _http(
    method: str,
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any] | None = None,
    files: list[tuple[str, str, bytes, str]] | None = None,
    timeout: int = 20,
) -> tuple[int, Any]:
    data = None
    headers = {"x-api-key": api_key}
    if files:
        data, content_type = _encode_multipart(payload or {}, files)
        headers["Content-Type"] = content_type
    elif payload is not None:
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


def _encode_multipart(
    fields: dict[str, Any],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----traq-cli-{uuid.uuid4().hex}"
    body: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        body.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list):
            for item in value:
                add_field(key, str(item))
            continue
        if isinstance(value, bool):
            add_field(key, "true" if value else "false")
            continue
        add_field(key, str(value))

    for field_name, filename, content, content_type in files:
        body.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )

    body.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(body), f"multipart/form-data; boundary={boundary}"


def _build_backend(*, context_name: str, host: str | None = None, api_key: str | None = None):
    if context_name == "local":
        from app.cli.local_backend import build_local_backend

        return build_local_backend(http=_http)
    from app.cli.remote_backend import build_remote_backend

    if host and api_key:
        resolved_host, resolved_api_key = host, api_key
    else:
        resolved_host, resolved_api_key = _context_defaults(context_name)
    return build_remote_backend(
        host=(host or resolved_host or "").rstrip("/"),
        api_key=api_key or resolved_api_key or "",
        http=_http,
    )


def _pending_devices() -> list[dict[str, Any]]:
    rows = _store().list_devices(status="pending")
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""))
    return rows


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


def _resolve_job_id(host: str, api_key: str, job_ref: str) -> str:
    del host, api_key
    if job_ref.startswith("job_"):
        return job_ref
    return _inspection_service().resolve_job_id(job_ref)


def _inject_http_defaults(tokens: list[str], *, host: str, api_key: str) -> list[str]:
    if not tokens:
        return tokens
    top = tokens[0]
    sub = tokens[1] if len(tokens) > 1 else ""
    augmented = list(tokens)
    needs_http_defaults = (
        (top == "device" and sub in {"list", "pending", "validate", "approve", "revoke", "issue-token"})
        or (top == "customer" and sub in {"list", "duplicates", "create", "update", "usage", "merge", "delete", "billing"})
        or (top == "job" and sub in {"assign", "unassign", "list-assignments", "set-status", "unlock"})
        or (top == "job" and sub in {"create", "update", "inspect"})
        or (top == "round" and sub in {"create", "reopen", "manifest", "submit", "reprocess"})
        or (top == "round" and sub == "inspect")
        or (top == "review" and sub == "inspect")
        or (top == "final" and sub == "inspect")
        or (top == "tree" and sub == "identify")
        or (top == "artifact" and sub == "fetch")
        or (top == "export" and sub in {"changes", "image-fetch", "geojson-fetch"})
    )
    if needs_http_defaults:
        if "--host" not in augmented:
            augmented.extend(["--host", host])
        if "--api-key" not in augmented:
            augmented.extend(["--api-key", api_key])
    return augmented


def _make_handlers(backend):
    return {
        "device_list": cmd_device_list,
        "device_pending": cmd_device_pending,
        "device_validate": cmd_device_validate,
        "device_approve": cmd_device_approve,
        "device_revoke": cmd_device_revoke,
        "device_issue_token": cmd_device_issue_token,
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
        "job_create": cmd_job_create,
        "job_update": cmd_job_update,
        "job_list_assignments": cmd_job_list_assignments,
        "job_assign": cmd_job_assign,
        "job_unassign": cmd_job_unassign,
        "job_set_status": cmd_job_set_status,
        "job_unlock": cmd_job_unlock,
        "job_inspect": cmd_job_inspect,
        "round_create": cmd_round_create,
        "round_manifest_get": cmd_round_manifest_get,
        "round_manifest_set": cmd_round_manifest_set,
        "round_submit": cmd_round_submit,
        "round_reprocess": cmd_round_reprocess,
        "round_reopen": cmd_round_reopen,
        "round_inspect": cmd_round_inspect,
        "review_inspect": cmd_review_inspect,
        "final_inspect": cmd_final_inspect,
        "final_set_final": cmd_final_set_final,
        "final_set_correction": cmd_final_set_correction,
        "tree_identify": cmd_tree_identify,
        "artifact_fetch": cmd_artifact_fetch,
        "export_changes": cmd_export_changes,
        "export_image_fetch": cmd_export_image_fetch,
        "export_geojson_fetch": cmd_export_geojson_fetch,
        "net_ipv4": cmd_net_ipv4,
        "net_ipv6": cmd_net_ipv6,
    }


def _legacy_backend_for_args(args: argparse.Namespace):
    host = getattr(args, "host", None)
    api_key = getattr(args, "api_key", None)
    if host and api_key:
        return _build_backend(context_name="cloud", host=host, api_key=api_key)
    return _build_backend(context_name="local")


def cmd_device_list(args: argparse.Namespace) -> int:
    return _cmd_device_list(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_device_pending(args: argparse.Namespace) -> int:
    return _cmd_device_pending(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_device_validate(args: argparse.Namespace) -> int:
    backend = _legacy_backend_for_args(args)
    if backend.mode_name == "remote":
        rc = _cmd_device_validate(args, backend=backend, print_json=_print_json)
        if rc == 0:
            print(f"Validated device using remote admin API as role={args.role}")
        return rc
    rows = _pending_devices()
    if not rows:
        print("No pending devices.")
        return 1
    index = max(1, int(args.index))
    if index > len(rows):
        print(f"Invalid index {index}; pending count={len(rows)}")
        return 1
    target = rows[index - 1]
    device_id = str(target.get("device_id") or "")
    rc = _cmd_device_validate(args, backend=backend, print_json=_print_json)
    if rc == 0:
        print(f"Validated device {device_id[:8]} as role={args.role}")
    return rc


def cmd_device_approve(args: argparse.Namespace) -> int:
    return _cmd_device_approve(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_device_revoke(args: argparse.Namespace) -> int:
    return _cmd_device_revoke(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_device_issue_token(args: argparse.Namespace) -> int:
    return _cmd_device_issue_token(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_list(args: argparse.Namespace) -> int:
    return _cmd_customer_list(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_duplicates(args: argparse.Namespace) -> int:
    return _cmd_customer_duplicates(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_create(args: argparse.Namespace) -> int:
    return _cmd_customer_create(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_update(args: argparse.Namespace) -> int:
    return _cmd_customer_update(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_usage(args: argparse.Namespace) -> int:
    return _cmd_customer_usage(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_merge(args: argparse.Namespace) -> int:
    return _cmd_customer_merge(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_customer_delete(args: argparse.Namespace) -> int:
    return _cmd_customer_delete(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_list(args: argparse.Namespace) -> int:
    return _cmd_billing_list(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_duplicates(args: argparse.Namespace) -> int:
    return _cmd_billing_duplicates(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_create(args: argparse.Namespace) -> int:
    return _cmd_billing_create(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_update(args: argparse.Namespace) -> int:
    return _cmd_billing_update(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_usage(args: argparse.Namespace) -> int:
    return _cmd_billing_usage(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_merge(args: argparse.Namespace) -> int:
    return _cmd_billing_merge(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_billing_delete(args: argparse.Namespace) -> int:
    return _cmd_billing_delete(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_create(args: argparse.Namespace) -> int:
    return _cmd_job_create(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_update(args: argparse.Namespace) -> int:
    return _cmd_job_update(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_list_assignments(args: argparse.Namespace) -> int:
    return _cmd_job_list_assignments(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_assign(args: argparse.Namespace) -> int:
    return _cmd_job_assign(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_unassign(args: argparse.Namespace) -> int:
    return _cmd_job_unassign(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_set_status(args: argparse.Namespace) -> int:
    return _cmd_job_set_status(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_unlock(args: argparse.Namespace) -> int:
    return _cmd_job_unlock(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_job_inspect(args: argparse.Namespace) -> int:
    return _cmd_job_inspect(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_create(args: argparse.Namespace) -> int:
    return _cmd_round_create(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_manifest_get(args: argparse.Namespace) -> int:
    return _cmd_round_manifest_get(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_manifest_set(args: argparse.Namespace) -> int:
    return _cmd_round_manifest_set(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_submit(args: argparse.Namespace) -> int:
    return _cmd_round_submit(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_reprocess(args: argparse.Namespace) -> int:
    return _cmd_round_reprocess(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_reopen(args: argparse.Namespace) -> int:
    return _cmd_round_reopen(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_round_inspect(args: argparse.Namespace) -> int:
    return _cmd_round_inspect(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_review_inspect(args: argparse.Namespace) -> int:
    return _cmd_review_inspect(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_final_inspect(args: argparse.Namespace) -> int:
    return _cmd_final_inspect(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_final_set_final(args: argparse.Namespace) -> int:
    return _cmd_final_set_final(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_final_set_correction(args: argparse.Namespace) -> int:
    return _cmd_final_set_correction(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_tree_identify(args: argparse.Namespace) -> int:
    return _cmd_tree_identify(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_artifact_fetch(args: argparse.Namespace) -> int:
    return _cmd_artifact_fetch(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_export_changes(args: argparse.Namespace) -> int:
    return _cmd_export_changes(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_export_image_fetch(args: argparse.Namespace) -> int:
    return _cmd_export_image_fetch(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_export_geojson_fetch(args: argparse.Namespace) -> int:
    return _cmd_export_geojson_fetch(args, backend=_legacy_backend_for_args(args), print_json=_print_json)


def cmd_net_ipv4(args: argparse.Namespace) -> int:
    return _cmd_net_ipv4_impl(args, print_json=_print_json)


def cmd_net_ipv6(args: argparse.Namespace) -> int:
    return _cmd_net_ipv6_impl(args, print_json=_print_json)


def build_parser(*, backend=None) -> argparse.ArgumentParser:
    settings = _settings()
    backend = backend or _build_backend(context_name="local")
    default_host = settings.admin_base_url
    default_api_key = settings.api_key
    if getattr(backend, "mode_name", "local") == "remote":
        default_host = getattr(getattr(backend, "device", None), "_host", default_host)
        default_api_key = getattr(getattr(backend, "device", None), "_api_key", default_api_key)
    handlers = _make_handlers(backend)
    parser = argparse.ArgumentParser(description="TRAQ admin CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    register_device_commands(
        sub,
        {
            "list": handlers["device_list"],
            "pending": handlers["device_pending"],
            "validate": handlers["device_validate"],
            "approve": handlers["device_approve"],
            "revoke": handlers["device_revoke"],
            "issue_token": handlers["device_issue_token"],
        },
    )
    register_customer_commands(
        sub,
        {
            "customer_list": handlers["customer_list"],
            "customer_duplicates": handlers["customer_duplicates"],
            "customer_create": handlers["customer_create"],
            "customer_update": handlers["customer_update"],
            "customer_usage": handlers["customer_usage"],
            "customer_merge": handlers["customer_merge"],
            "customer_delete": handlers["customer_delete"],
            "billing_list": handlers["billing_list"],
            "billing_duplicates": handlers["billing_duplicates"],
            "billing_create": handlers["billing_create"],
            "billing_update": handlers["billing_update"],
            "billing_usage": handlers["billing_usage"],
            "billing_merge": handlers["billing_merge"],
            "billing_delete": handlers["billing_delete"],
        },
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_job_commands(
        sub,
        {
            "create": handlers["job_create"],
            "update": handlers["job_update"],
            "list_assignments": handlers["job_list_assignments"],
            "assign": handlers["job_assign"],
            "unlock": handlers["job_unlock"],
            "unassign": handlers["job_unassign"],
            "set_status": handlers["job_set_status"],
        },
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_round_commands(
        sub,
        {
            "create": handlers["round_create"],
            "manifest_get": handlers["round_manifest_get"],
            "manifest_set": handlers["round_manifest_set"],
            "submit": handlers["round_submit"],
            "reprocess": handlers["round_reprocess"],
            "reopen": handlers["round_reopen"],
        },
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_inspect_commands(
        sub,
        {
            "job_inspect": handlers["job_inspect"],
            "round_inspect": handlers["round_inspect"],
            "review_inspect": handlers["review_inspect"],
            "final_inspect": handlers["final_inspect"],
        },
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_final_commands(
        sub,
        {
            "set_final": handlers["final_set_final"],
            "set_correction": handlers["final_set_correction"],
        },
    )
    register_net_commands(
        sub,
        {
            "ipv4": handlers["net_ipv4"],
            "ipv6": handlers["net_ipv6"],
        },
    )
    register_tree_commands(
        sub,
        {"identify": handlers["tree_identify"]},
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_artifact_commands(
        sub,
        {"fetch": handlers["artifact_fetch"]},
        default_host=default_host,
        default_api_key=default_api_key,
    )
    register_export_commands(
        sub,
        {
            "changes": handlers["export_changes"],
            "image_fetch": handlers["export_image_fetch"],
            "geojson_fetch": handlers["export_geojson_fetch"],
        },
        default_host=default_host,
        default_api_key=default_api_key,
    )
    return parser


def _normalize_repl_tokens(raw: str) -> list[str]:
    normalized = raw.lstrip()
    if normalized.startswith("/"):
        normalized = normalized[1:].lstrip()
    return shlex.split(normalized)


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
            "job unlock",
            "job unassign",
            "job set-status",
            "job inspect",
            "round reopen",
            "round inspect",
            "review inspect",
            "final inspect",
            "final set-final",
            "final set-correction",
            "artifact fetch",
            "export changes",
            "export image-fetch",
            "export geojson-fetch",
            "tree identify",
            "net ipv4",
            "net ipv6",
            "show",
            "help",
            "exit",
            "quit",
            "set host",
            "set api-key",
            "use local",
            "use cloud",
            "use remote",
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


def _run_repl(parser: argparse.ArgumentParser | None = None, *, context_name: str | None = None) -> int:
    active_context = context_name or "local"
    host, api_key = _context_defaults(active_context)
    backend = _build_backend(context_name=active_context, host=host, api_key=api_key)
    parser = build_parser(backend=backend)
    _setup_repl_readline()
    print("TRAQ admin CLI interactive mode")
    print("Type 'help' for commands, 'exit' to quit.")
    print(f"context={active_context}")
    print(f"mode={backend.mode_name}")
    print(f"host={host or '(n/a)'}")
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
            print("  use local")
            print("  use cloud")
            print("  use remote")
            print("  show")
            print("  help")
            print("  exit")
            print("CLI commands (same as one-shot; optional leading '/').")
            continue
        if raw == "show":
            masked = "*" * len(api_key or "") if api_key else "(empty)"
            print(f"context={active_context}")
            print(f"mode={backend.mode_name}")
            print(f"host={host or '(n/a)'}")
            print(f"api_key={masked}")
            continue
        if raw in {"use local", "use cloud", "use remote"}:
            active_context = raw.split()[1]
            host, api_key = _context_defaults(active_context)
            backend = _build_backend(context_name=active_context, host=host, api_key=api_key)
            parser = build_parser(backend=backend)
            print(f"context={active_context}")
            print(f"mode={backend.mode_name}")
            print(f"host={host or '(n/a)'}")
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
                backend = _build_backend(context_name=active_context, host=host, api_key=api_key)
                parser = build_parser(backend=backend)
                print(f"host={host}")
                continue
            if key in {"api-key", "apikey", "key"}:
                api_key = value
                backend = _build_backend(context_name=active_context, host=host, api_key=api_key)
                parser = build_parser(backend=backend)
                print("api_key updated")
                continue
            print("Unknown setting. Use 'host' or 'api-key'.")
            continue
        try:
            tokens = _normalize_repl_tokens(raw)
        except ValueError as exc:
            print(f"Parse error: {exc}")
            continue
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
    argv = list(sys.argv[1:])
    context_name = "local"
    if argv and argv[0] in _CONTEXT_NAMES:
        raw_context = argv.pop(0)
        context_name = "cloud" if raw_context == "remote" else raw_context
    if not argv:
        return _run_repl(context_name=context_name)
    host, api_key = _context_defaults(context_name)
    if context_name != "local":
        argv = _inject_http_defaults(argv, host=host or "", api_key=api_key or "")
    backend = _build_backend(context_name=context_name, host=host, api_key=api_key)
    parser = build_parser(backend=backend)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
