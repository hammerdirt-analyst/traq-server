from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.config import load_settings


class ConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.old_env = {key: os.environ.get(key) for key in self._env_keys()}
        self.addCleanup(self._restore_env)
        os.environ["TRAQ_DATABASE_URL"] = "sqlite:///test.db"
        os.environ["TRAQ_STORAGE_ROOT"] = str(Path(self.tempdir.name) / "storage")
        os.environ["TRAQ_ARTIFACT_BACKEND"] = "local"
        os.environ["TRAQ_ENABLE_DISCOVERY"] = "true"
        os.environ.pop("TRAQ_GCS_BUCKET", None)
        os.environ.pop("TRAQ_GCS_PREFIX", None)

    @staticmethod
    def _env_keys() -> tuple[str, ...]:
        return (
            "TRAQ_DATABASE_URL",
            "TRAQ_STORAGE_ROOT",
            "TRAQ_ARTIFACT_BACKEND",
            "TRAQ_GCS_BUCKET",
            "TRAQ_GCS_PREFIX",
            "TRAQ_ENABLE_DISCOVERY",
        )

    def _restore_env(self) -> None:
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_local_artifact_backend_is_default(self) -> None:
        settings = load_settings()
        self.assertEqual(settings.artifact_backend, "local")
        self.assertIsNone(settings.artifact_gcs_bucket)

    def test_gcs_artifact_backend_requires_bucket(self) -> None:
        os.environ["TRAQ_ARTIFACT_BACKEND"] = "gcs"
        with self.assertRaises(RuntimeError):
            load_settings()

    def test_gcs_artifact_backend_loads_bucket_and_prefix(self) -> None:
        os.environ["TRAQ_ARTIFACT_BACKEND"] = "gcs"
        os.environ["TRAQ_GCS_BUCKET"] = "traq-artifacts"
        os.environ["TRAQ_GCS_PREFIX"] = "prod"
        settings = load_settings()
        self.assertEqual(settings.artifact_backend, "gcs")
        self.assertEqual(settings.artifact_gcs_bucket, "traq-artifacts")
        self.assertEqual(settings.artifact_gcs_prefix, "prod")

    def test_discovery_flag_can_be_disabled(self) -> None:
        os.environ["TRAQ_ENABLE_DISCOVERY"] = "false"
        settings = load_settings()
        self.assertFalse(settings.enable_discovery)


if __name__ == "__main__":
    unittest.main()
