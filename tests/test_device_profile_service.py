"""Focused regression checks for device auth/profile helper extraction."""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.device_profile_service import DeviceProfileService


class DeviceProfileServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.db_store = Mock()
        self.write_json = Mock()
        self.logger = logging.getLogger("device-profile-service-test")
        self.service = DeviceProfileService(
            storage_root=Path(self.tmpdir.name),
            db_store=self.db_store,
            write_json=self.write_json,
            logger=self.logger,
        )

    def test_register_device_record_wraps_failures_as_http_500(self) -> None:
        self.db_store.register_device.side_effect = RuntimeError("boom")

        with self.assertRaises(HTTPException) as ctx:
            self.service.register_device_record(
                device_id="device-1",
                device_name="Phone",
                app_version="1.0.0",
                profile_summary={},
            )

        self.assertEqual(ctx.exception.status_code, 500)
        self.assertEqual(ctx.exception.detail, "Device registration failed")

    def test_get_device_record_suppresses_lookup_errors(self) -> None:
        self.db_store.get_device.side_effect = RuntimeError("db down")

        self.assertIsNone(self.service.get_device_record("device-1"))

    def test_save_runtime_profile_exports_debug_copy(self) -> None:
        stored = {"name": "Roger"}
        self.db_store.upsert_runtime_profile.return_value = stored

        result = self.service.save_runtime_profile("identity-1", {"name": "Roger"})

        self.assertEqual(result, stored)
        self.write_json.assert_called_once()
        path_arg, payload_arg = self.write_json.call_args.args
        self.assertTrue(str(path_arg).startswith(str(Path(self.tmpdir.name) / "profiles")))
        self.assertEqual(payload_arg, stored)

    def test_load_runtime_profile_copies_db_payload(self) -> None:
        payload = {"name": "Roger"}
        self.db_store.get_runtime_profile.return_value = payload

        result = self.service.load_runtime_profile("identity-1")

        self.assertEqual(result, payload)
        self.assertIsNot(result, payload)


if __name__ == "__main__":
    unittest.main()
