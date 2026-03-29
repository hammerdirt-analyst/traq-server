"""Shared test support for admin CLI command coverage."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from app import db as db_module
from app.config import load_settings
from app.db import create_schema, init_database
from app.db_store import DatabaseStore
from app.services.inspection_service import InspectionService

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import admin_cli  # type: ignore  # noqa: E402

try:
    import app.db as cli_db_module  # type: ignore
except Exception:  # pragma: no cover - only relevant in CLI import mode
    cli_db_module = None


class AdminCliTestCase(unittest.TestCase):
    """Shared CLI test fixture with isolated storage and database state."""

    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage_root = Path(self.tempdir.name) / "storage"
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.old_env = {key: os.environ.get(key) for key in self._env_keys()}
        os.environ["TRAQ_STORAGE_ROOT"] = str(self.storage_root)
        os.environ["TRAQ_DATABASE_URL"] = f"sqlite:///{self.storage_root / 'test.db'}"
        self.addCleanup(self._restore_env)

        db_module._engine = None
        db_module._SessionLocal = None
        if cli_db_module is not None:
            cli_db_module._engine = None
            cli_db_module._SessionLocal = None
        init_database(load_settings())
        create_schema()
        self.store = DatabaseStore()
        self.inspection_service = InspectionService(settings=load_settings(), db_store=self.store)

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return (
            "TRAQ_STORAGE_ROOT",
            "TRAQ_DATABASE_URL",
            "TRAQ_ADMIN_BASE_URL",
            "TRAQ_API_KEY",
            "TRAQ_CLOUD_ADMIN_BASE_URL",
            "TRAQ_CLOUD_API_KEY",
        )

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        db_module._engine = None
        db_module._SessionLocal = None
        if cli_db_module is not None:
            cli_db_module._engine = None
            cli_db_module._SessionLocal = None

    def _register_pending_device(self, device_id: str = "device-1") -> None:
        self.store.register_device(
            device_id=device_id,
            device_name="Pixel",
            app_version="0.1.0",
            profile_summary=None,
        )

    def _stdout_for(self, func, *args, **kwargs) -> tuple[int, str]:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = func(*args, **kwargs)
        return int(rc), stdout.getvalue()
