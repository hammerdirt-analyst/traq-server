"""Unit tests for shared runtime context construction."""

from __future__ import annotations

import logging
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.runtime_context import RuntimeContext


class RuntimeContextTests(unittest.TestCase):
    def _settings(self, *, artifact_backend: str = "local") -> SimpleNamespace:
        return SimpleNamespace(
            api_key="test-key",
            storage_root=__import__("pathlib").Path("/tmp/runtime-context-test"),
            artifact_backend=artifact_backend,
            artifact_gcs_bucket="bucket-name",
            artifact_gcs_prefix="prefix",
            discovery_port=8000,
            discovery_name="TRAQ Server",
        )

    def test_context_builds_local_artifact_store_and_services(self) -> None:
        context = RuntimeContext(
            settings=self._settings(),
            logger=logging.getLogger("runtime-context-test"),
        )

        self.assertEqual(context.access_control_service._api_key, "test-key")
        self.assertEqual(context.artifact_store.__class__.__name__, "LocalArtifactStore")
        self.assertIsNotNone(context.media_runtime_service)
        self.assertEqual(context.jobs, {})

    def test_context_uses_gcs_artifact_store_when_requested(self) -> None:
        fake_store = object()
        with patch("app.runtime_context.create_artifact_store", return_value=fake_store):
            context = RuntimeContext(
                settings=self._settings(artifact_backend="gcs"),
                logger=logging.getLogger("runtime-context-test"),
            )

        self.assertIs(context.artifact_store, fake_store)

    def test_bind_runtime_state_service_attaches_state_helper(self) -> None:
        context = RuntimeContext(
            settings=self._settings(),
            logger=logging.getLogger("runtime-context-test"),
        )

        context.bind_runtime_state_service(
            parse_tree_number=lambda value: int(value) if value else None,
            job_record_factory=lambda **kwargs: kwargs,
            round_record_factory=lambda **kwargs: kwargs,
            write_json=lambda path, payload: None,
        )

        self.assertIsNotNone(context.runtime_state_service)
        self.assertEqual(context.runtime_state_service._storage_root, context.settings.storage_root)


if __name__ == "__main__":
    unittest.main()
