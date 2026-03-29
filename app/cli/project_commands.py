"""Project admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
    """Execute one project action with shared CLI error handling."""
    try:
        payload = action()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_project_list(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """List server-managed projects."""
    return _wrap(lambda: backend.project.list(), print_json)


def cmd_project_create(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Create one server-managed project."""
    return _wrap(
        lambda: backend.project.create(
            project=args.project,
            project_slug=args.project_slug,
        ),
        print_json,
    )


def cmd_project_update(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Update one server-managed project."""
    return _wrap(
        lambda: backend.project.update(
            args.project_ref,
            project=args.project,
            project_slug=args.project_slug,
        ),
        print_json,
    )


def register_project_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str,
    default_api_key: str,
) -> None:
    """Register the project command group."""
    project = subparsers.add_parser("project", help="Server-managed project registry operations")
    project_sub = project.add_subparsers(dest="project_cmd", required=True)

    list_cmd = project_sub.add_parser("list", help="List projects")
    list_cmd.add_argument("--host", default=default_host)
    list_cmd.add_argument("--api-key", default=default_api_key)
    list_cmd.set_defaults(func=handlers["list"])

    create_cmd = project_sub.add_parser("create", help="Create a project")
    create_cmd.add_argument("--project", required=True)
    create_cmd.add_argument("--project-slug")
    create_cmd.add_argument("--host", default=default_host)
    create_cmd.add_argument("--api-key", default=default_api_key)
    create_cmd.set_defaults(func=handlers["create"])

    update_cmd = project_sub.add_parser("update", help="Update a project")
    update_cmd.add_argument("--project-ref", required=True, help="project_id or project_slug")
    update_cmd.add_argument("--project")
    update_cmd.add_argument("--project-slug")
    update_cmd.add_argument("--host", default=default_host)
    update_cmd.add_argument("--api-key", default=default_api_key)
    update_cmd.set_defaults(func=handlers["update"])
