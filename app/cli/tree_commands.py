"""Standalone tree-identification admin CLI commands."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable


HttpCaller = Callable[..., tuple[int, Any]]
JsonPrinter = Callable[[object], None]


def cmd_tree_identify(
    args: argparse.Namespace,
    *,
    http: HttpCaller,
    print_json: JsonPrinter,
) -> int:
    """Call the standalone tree-identification endpoint."""
    image_paths = [Path(item) for item in args.image]
    missing = [str(path) for path in image_paths if not path.exists()]
    if missing:
        print(f"ERROR: Missing image files: {', '.join(missing)}")
        return 1
    if len(image_paths) > 5:
        print("ERROR: Maximum 5 images are allowed")
        return 1
    payload = {
        "project": args.project,
        "include_related_images": args.include_related_images,
        "no_reject": args.no_reject,
        "nb_results": args.nb_results,
        "lang": args.lang,
    }
    files = []
    try:
        for path in image_paths:
            files.append(
                (
                    "images",
                    path.name,
                    path.read_bytes(),
                    "image/png" if path.suffix.lower() == ".png" else "image/jpeg",
                )
            )
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    for organ in args.organ or []:
        payload.setdefault("organs", []).append(organ)
    code, body = http(
        "POST",
        f"{args.host.rstrip('/')}/v1/trees/identify",
        api_key=args.api_key,
        payload=payload,
        files=files,
    )
    if code != 200:
        print(f"HTTP {code}: {body}")
        return 1
    print_json(body)
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
