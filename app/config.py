"""
Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex
"""
from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv() -> None:
    """Populate environment variables from `server/.env` when present.

    This keeps local operator workflows simple without overriding variables that
    are already set in the shell or process environment.
    """

    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip().strip("'").strip('"')
        os.environ[key] = value


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean environment value: {value!r}")


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the server process.

    `database_url` is the persistence boundary for the SQL-backed server.
    PostgreSQL is now the required runtime target. The process fails fast when
    `TRAQ_DATABASE_URL` is not configured.
    """

    api_key: str
    storage_root: Path
    artifact_backend: str
    artifact_gcs_bucket: str | None
    artifact_gcs_prefix: str | None
    enable_discovery: bool
    auto_create_schema: bool
    enable_file_logging: bool
    database_url: str
    admin_base_url: str
    discovery_port: int
    discovery_name: str


def load_settings() -> Settings:
    """Load environment-backed server settings.

    Important variables:
    - `TRAQ_API_KEY`: admin API key for privileged endpoints
    - `TRAQ_STORAGE_ROOT`: on-disk artifact root for media and final exports;
      defaults to the repo-local `./local_data`
    - `TRAQ_ARTIFACT_BACKEND`: `local` or `gcs`; defaults to `local`
    - `TRAQ_GCS_BUCKET`: required when `TRAQ_ARTIFACT_BACKEND=gcs`
    - `TRAQ_GCS_PREFIX`: optional object prefix inside the bucket
    - `TRAQ_ENABLE_DISCOVERY`: enable local mDNS discovery; defaults to `true`
    - `TRAQ_AUTO_CREATE_SCHEMA`: local/dev schema bootstrap; defaults to `true`
    - `TRAQ_ENABLE_FILE_LOGGING`: write rotating local log files; defaults to `true`
    - `TRAQ_DATABASE_URL`: required SQLAlchemy connection string; PostgreSQL is
      the required deployment target
    - `TRAQ_ADMIN_BASE_URL`: default server base URL for admin CLI HTTP
      commands; defaults to `http://127.0.0.1:<TRAQ_DISCOVERY_PORT>`
    - `TRAQ_DISCOVERY_PORT` / `TRAQ_DISCOVERY_NAME`: mDNS advertisement config
    """

    _load_dotenv()
    api_key = os.environ.get("TRAQ_API_KEY", "demo-key")
    storage_root = Path(
        os.environ.get(
            "TRAQ_STORAGE_ROOT",
            str(Path(__file__).resolve().parents[1] / "local_data"),
        )
    )
    artifact_backend = (os.environ.get("TRAQ_ARTIFACT_BACKEND") or "local").strip().lower()
    if artifact_backend not in {"local", "gcs"}:
        raise RuntimeError("TRAQ_ARTIFACT_BACKEND must be 'local' or 'gcs'.")
    artifact_gcs_bucket = (os.environ.get("TRAQ_GCS_BUCKET") or "").strip() or None
    artifact_gcs_prefix = (os.environ.get("TRAQ_GCS_PREFIX") or "").strip() or None
    if artifact_backend == "gcs" and not artifact_gcs_bucket:
        raise RuntimeError("TRAQ_GCS_BUCKET is required when TRAQ_ARTIFACT_BACKEND=gcs.")
    enable_discovery = _parse_bool_env(os.environ.get("TRAQ_ENABLE_DISCOVERY"), default=True)
    auto_create_schema = _parse_bool_env(os.environ.get("TRAQ_AUTO_CREATE_SCHEMA"), default=True)
    enable_file_logging = _parse_bool_env(os.environ.get("TRAQ_ENABLE_FILE_LOGGING"), default=True)
    database_url = (os.environ.get("TRAQ_DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError(
            "TRAQ_DATABASE_URL is required. Set it to the PostgreSQL connection string "
            "for this server, for example "
            "'postgresql+psycopg://traq_app:<password>@127.0.0.1:5432/traq_demo'."
        )
    discovery_port = int(os.environ.get("TRAQ_DISCOVERY_PORT", "8000"))
    discovery_name = os.environ.get("TRAQ_DISCOVERY_NAME", "TRAQ Server")
    admin_base_url = os.environ.get(
        "TRAQ_ADMIN_BASE_URL",
        f"http://127.0.0.1:{discovery_port}",
    ).rstrip("/")
    storage_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        api_key=api_key,
        storage_root=storage_root,
        artifact_backend=artifact_backend,
        artifact_gcs_bucket=artifact_gcs_bucket,
        artifact_gcs_prefix=artifact_gcs_prefix,
        enable_discovery=enable_discovery,
        auto_create_schema=auto_create_schema,
        enable_file_logging=enable_file_logging,
        database_url=database_url,
        admin_base_url=admin_base_url,
        discovery_port=discovery_port,
        discovery_name=discovery_name,
    )
