"""Release verification helpers for CI and operator deploy gates."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence
from urllib import error, request

PRE_DEPLOY_TEST_MODULES: tuple[str, ...] = (
    "tests.test_api_routers",
    "tests.test_admin_cli",
    "tests.test_command_registry",
    "tests.test_config",
    "tests.test_export_sync_service",
    "tests.test_media_runtime_service",
    "tests.test_staging_sync_service",
    "tests.test_tree_identification_service",
)


class VerificationError(RuntimeError):
    """Raised when a release verification gate fails."""


def pre_deploy_command() -> tuple[str, ...]:
    """Return the pre-deploy regression command."""

    return ("uv", "run", "python", "-m", "unittest", *PRE_DEPLOY_TEST_MODULES)


def default_pre_deploy_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return stable environment variables for CI-safe pre-deploy tests."""

    env = dict(base_env or os.environ)
    env.setdefault("TRAQ_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    env.setdefault("TRAQ_ENABLE_DISCOVERY", "false")
    env.setdefault("TRAQ_AUTO_CREATE_SCHEMA", "false")
    env.setdefault("TRAQ_ENABLE_FILE_LOGGING", "false")
    return env


def required_post_deploy_env(base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Validate and return the env required for live post-deploy smoke checks."""

    env = dict(base_env or os.environ)
    missing = [key for key in ("TRAQ_CLOUD_ADMIN_BASE_URL",) if not str(env.get(key) or "").strip()]
    if missing:
        raise VerificationError(f"Missing required environment variables: {', '.join(missing)}")
    return env


def run_pre_deploy(*, cwd: Path, base_env: Mapping[str, str] | None = None) -> None:
    """Execute the pre-deploy regression gate."""

    _run_command(
        pre_deploy_command(),
        cwd=cwd,
        env=default_pre_deploy_env(base_env),
        step_name="pre-deploy-regression",
    )


def run_post_deploy(*, cwd: Path, base_env: Mapping[str, str] | None = None) -> None:
    """Execute the live post-deploy health verification."""

    del cwd
    env = required_post_deploy_env(base_env)
    _health_check(str(env["TRAQ_CLOUD_ADMIN_BASE_URL"]).rstrip("/"))


def _health_check(base_url: str) -> None:
    url = f"{base_url}/health"
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except error.HTTPError as exc:  # pragma: no cover - exercised through failure path wrapper
        detail = exc.read().decode("utf-8", errors="replace")
        raise VerificationError(f"Health check failed: HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:  # pragma: no cover - exercised through failure path wrapper
        raise VerificationError(f"Health check failed: {exc}") from exc
    if int(getattr(resp, "status", 200)) != 200:
        raise VerificationError(f"Health check failed: HTTP {resp.status}")
    if not isinstance(payload, dict) or str(payload.get("status") or "").lower() != "ok":
        raise VerificationError(f"Unexpected health payload: {payload}")


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    step_name: str,
) -> None:
    completed = subprocess.run(list(command), cwd=str(cwd), env=dict(env), check=False)
    if completed.returncode != 0:
        raise VerificationError(f"Step failed [{step_name}]: {' '.join(command)}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for release verification modes."""

    args = list(argv or sys.argv[1:])
    if len(args) != 1 or args[0] not in {"pre-deploy", "post-deploy"}:
        print("Usage: python scripts/release_verify.py <pre-deploy|post-deploy>")
        return 2
    repo_root = Path(__file__).resolve().parent.parent
    try:
        if args[0] == "pre-deploy":
            run_pre_deploy(cwd=repo_root)
        else:
            run_post_deploy(cwd=repo_root)
    except VerificationError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"OK: {args[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
