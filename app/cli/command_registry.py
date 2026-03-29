"""Registry metadata for CLI command groups and parser wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.cli.artifact_commands import register_artifact_commands
from app.cli.customer_commands import register_customer_commands
from app.cli.device_commands import register_device_commands
from app.cli.export_commands import register_export_commands
from app.cli.final_commands import register_final_commands
from app.cli.inspect_commands import register_inspect_commands
from app.cli.job_commands import register_job_commands
from app.cli.net_commands import register_net_commands
from app.cli.project_commands import register_project_commands
from app.cli.round_commands import register_round_commands
from app.cli.stage_commands import register_stage_commands
from app.cli.tree_commands import register_tree_commands


RegisterFn = Callable[..., None]


@dataclass(frozen=True)
class CommandGroupSpec:
    """Describe one CLI command group registration and dispatch contract."""

    name: str
    register_fn: RegisterFn
    handler_bindings: dict[str, str]
    command_paths: tuple[tuple[str, str], ...]
    uses_http_defaults: bool = False
    passes_register_defaults: bool = False


COMMAND_GROUP_SPECS: tuple[CommandGroupSpec, ...] = (
    CommandGroupSpec(
        name="device",
        register_fn=register_device_commands,
        handler_bindings={
            "list": "cmd_device_list",
            "pending": "cmd_device_pending",
            "validate": "cmd_device_validate",
            "approve": "cmd_device_approve",
            "revoke": "cmd_device_revoke",
            "issue_token": "cmd_device_issue_token",
        },
        command_paths=(
            ("device", "list"),
            ("device", "pending"),
            ("device", "validate"),
            ("device", "approve"),
            ("device", "revoke"),
            ("device", "issue-token"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=False,
    ),
    CommandGroupSpec(
        name="customer",
        register_fn=register_customer_commands,
        handler_bindings={
            "customer_list": "cmd_customer_list",
            "customer_duplicates": "cmd_customer_duplicates",
            "customer_create": "cmd_customer_create",
            "customer_update": "cmd_customer_update",
            "customer_usage": "cmd_customer_usage",
            "customer_merge": "cmd_customer_merge",
            "customer_delete": "cmd_customer_delete",
            "billing_list": "cmd_billing_list",
            "billing_duplicates": "cmd_billing_duplicates",
            "billing_create": "cmd_billing_create",
            "billing_update": "cmd_billing_update",
            "billing_usage": "cmd_billing_usage",
            "billing_merge": "cmd_billing_merge",
            "billing_delete": "cmd_billing_delete",
        },
        command_paths=(
            ("customer", "list"),
            ("customer", "duplicates"),
            ("customer", "create"),
            ("customer", "update"),
            ("customer", "usage"),
            ("customer", "merge"),
            ("customer", "delete"),
            ("customer", "billing"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="project",
        register_fn=register_project_commands,
        handler_bindings={
            "list": "cmd_project_list",
            "create": "cmd_project_create",
            "update": "cmd_project_update",
        },
        command_paths=(
            ("project", "list"),
            ("project", "create"),
            ("project", "update"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="job",
        register_fn=register_job_commands,
        handler_bindings={
            "create": "cmd_job_create",
            "update": "cmd_job_update",
            "list_assignments": "cmd_job_list_assignments",
            "assign": "cmd_job_assign",
            "unlock": "cmd_job_unlock",
            "unassign": "cmd_job_unassign",
            "set_status": "cmd_job_set_status",
        },
        command_paths=(
            ("job", "create"),
            ("job", "update"),
            ("job", "list-assignments"),
            ("job", "assign"),
            ("job", "unlock"),
            ("job", "unassign"),
            ("job", "set-status"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="round",
        register_fn=register_round_commands,
        handler_bindings={
            "create": "cmd_round_create",
            "manifest_get": "cmd_round_manifest_get",
            "manifest_set": "cmd_round_manifest_set",
            "submit": "cmd_round_submit",
            "reprocess": "cmd_round_reprocess",
            "reopen": "cmd_round_reopen",
        },
        command_paths=(
            ("round", "create"),
            ("round", "manifest"),
            ("round", "submit"),
            ("round", "reprocess"),
            ("round", "reopen"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="inspect",
        register_fn=register_inspect_commands,
        handler_bindings={
            "job_inspect": "cmd_job_inspect",
            "round_inspect": "cmd_round_inspect",
            "review_inspect": "cmd_review_inspect",
            "final_inspect": "cmd_final_inspect",
        },
        command_paths=(
            ("job", "inspect"),
            ("round", "inspect"),
            ("review", "inspect"),
            ("final", "inspect"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="final",
        register_fn=register_final_commands,
        handler_bindings={
            "set_final": "cmd_final_set_final",
            "set_correction": "cmd_final_set_correction",
        },
        command_paths=(),
        passes_register_defaults=False,
    ),
    CommandGroupSpec(
        name="net",
        register_fn=register_net_commands,
        handler_bindings={
            "ipv4": "cmd_net_ipv4",
            "ipv6": "cmd_net_ipv6",
        },
        command_paths=(),
        passes_register_defaults=False,
    ),
    CommandGroupSpec(
        name="stage",
        register_fn=register_stage_commands,
        handler_bindings={"sync": "cmd_stage_sync"},
        command_paths=(("stage", "sync"),),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="tree",
        register_fn=register_tree_commands,
        handler_bindings={"identify": "cmd_tree_identify"},
        command_paths=(("tree", "identify"),),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="artifact",
        register_fn=register_artifact_commands,
        handler_bindings={"fetch": "cmd_artifact_fetch"},
        command_paths=(("artifact", "fetch"),),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
    CommandGroupSpec(
        name="export",
        register_fn=register_export_commands,
        handler_bindings={
            "changes": "cmd_export_changes",
            "image_fetch": "cmd_export_image_fetch",
            "geojson_fetch": "cmd_export_geojson_fetch",
            "images_fetch_all": "cmd_export_images_fetch_all",
        },
        command_paths=(
            ("export", "changes"),
            ("export", "image-fetch"),
            ("export", "geojson-fetch"),
            ("export", "images-fetch-all"),
        ),
        uses_http_defaults=True,
        passes_register_defaults=True,
    ),
)


def build_handler_lookup(namespace: dict[str, Callable]) -> dict[str, Callable]:
    """Resolve wrapper function names from the CLI module namespace."""

    handler_names = {
        handler_name
        for spec in COMMAND_GROUP_SPECS
        for handler_name in spec.handler_bindings.values()
    }
    return {name: namespace[name] for name in handler_names}


def command_requires_http_defaults(tokens: list[str]) -> bool:
    """Return whether the parsed command path should inherit remote HTTP defaults."""

    if len(tokens) < 2:
        return False
    command_path = (tokens[0], tokens[1])
    return any(
        command_path in spec.command_paths
        for spec in COMMAND_GROUP_SPECS
        if spec.uses_http_defaults
    )


def register_command_groups(
    subparsers,
    handler_lookup: dict[str, Callable],
    *,
    default_host: str | None,
    default_api_key: str | None,
) -> None:
    """Register all command groups from the shared registry metadata."""

    for spec in COMMAND_GROUP_SPECS:
        handlers = {
            parser_key: handler_lookup[handler_name]
            for parser_key, handler_name in spec.handler_bindings.items()
        }
        kwargs = {}
        if spec.passes_register_defaults:
            kwargs["default_host"] = default_host
            kwargs["default_api_key"] = default_api_key
        spec.register_fn(subparsers, handlers, **kwargs)
