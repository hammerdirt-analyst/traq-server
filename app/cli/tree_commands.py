"""Standalone tree-identification admin CLI commands."""

from __future__ import annotations

import argparse
from typing import Callable

from .backends import CliBackendBundle

JsonPrinter = Callable[[object], None]


def cmd_tree_identify(
    args: argparse.Namespace,
    *,
    backend: CliBackendBundle,
    print_json: JsonPrinter,
) -> int:
    """Call the standalone tree-identification endpoint."""
    try:
        payload = backend.tree.identify(
            image_paths=list(args.image),
            organs=list(args.organ or []),
            project=args.project,
            include_related_images=args.include_related_images,
            no_reject=args.no_reject,
            nb_results=args.nb_results,
            lang=args.lang,
        )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def register_tree_commands(
    subparsers,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    *,
    default_host: str | None = None,
    default_api_key: str | None = None,
) -> None:
    """Register standalone tree-identification commands."""
    tree = subparsers.add_parser("tree", help="Standalone tree-identification utilities")
    tree_sub = tree.add_subparsers(dest="tree_cmd", required=True)

    identify_cmd = tree_sub.add_parser("identify", help="Identify a tree from up to five images")
    identify_cmd.add_argument("--image", action="append", required=True, help="Path to one image file; repeat up to 5 times")
    identify_cmd.add_argument("--organ", action="append", dest="organ", help="Optional organ hint; repeat to match image count")
    identify_cmd.add_argument("--project", default="all")
    identify_cmd.add_argument("--include-related-images", action="store_true")
    identify_cmd.add_argument("--no-reject", action="store_true")
    identify_cmd.add_argument("--nb-results", type=int, default=None)
    identify_cmd.add_argument("--lang", default=None)
    identify_cmd.add_argument("--host", default=default_host)
    identify_cmd.add_argument("--api-key", default=default_api_key)
    identify_cmd.set_defaults(func=handlers["identify"])
