"""Repo-local API server entrypoint.

This module gives the standalone repo a stable console script so operators do
not need to remember the `uvicorn app.main:app ...` invocation details.
"""
from __future__ import annotations

import argparse

import uvicorn

from .config import load_settings


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone API server parser."""

    settings = load_settings()
    parser = argparse.ArgumentParser(
        prog="traq-server",
        description="Run the TRAQ FastAPI server from the standalone repo.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host interface to bind. Defaults to 0.0.0.0.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.discovery_port,
        help="Port to bind. Defaults to TRAQ_DISCOVERY_PORT or 8000.",
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Uvicorn log level. Defaults to info.",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development.",
    )
    return parser


def main() -> int:
    """Run the standalone API server."""

    parser = build_parser()
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
