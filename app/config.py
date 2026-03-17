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


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the server process.

    `database_url` is the persistence boundary for the SQL-backed server.
    PostgreSQL is now the required runtime target. The process fails fast when
    `TRAQ_DATABASE_URL` is not configured.
    """

    api_key: str
    storage_root: Path
    database_url: str
    admin_base_url: str
    discovery_port: int
    discovery_name: str


def load_settings() -> Settings:
    """Load environment-backed server settings.

    Important variables:
    - `TRAQ_API_KEY`: admin API key for privileged endpoints
    - `TRAQ_STORAGE_ROOT`: on-disk artifact root for media and final exports
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
            str(Path(__file__).resolve().parents[2] / "server_data"),
        )
    )
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
        database_url=database_url,
        admin_base_url=admin_base_url,
        discovery_port=discovery_port,
        discovery_name=discovery_name,
    )
