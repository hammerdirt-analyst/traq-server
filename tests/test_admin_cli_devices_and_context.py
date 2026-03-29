"""Device, context, and low-level CLI plumbing coverage."""

from __future__ import annotations

import argparse
import io
import sys
from unittest.mock import patch

from tests.admin_cli_support import AdminCliTestCase, admin_cli


class AdminCliDevicesAndContextTests(AdminCliTestCase):
    def test_device_list_pending_validate_approve_revoke_and_issue_token(self) -> None:
        self._register_pending_device("device-1")
        self._register_pending_device("device-2")

        rc, output = self._stdout_for(
            admin_cli.cmd_device_list,
            argparse.Namespace(status="pending", json=False),
        )
        self.assertEqual(rc, 0)
        self.assertIn("device-1"[:8], output)
        self.assertIn("pending", output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_pending,
            argparse.Namespace(json=True),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"device_id": "device-1"', output)
        self.assertIn('"device_id": "device-2"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_validate,
            argparse.Namespace(index=2, role="admin"),
        )
        self.assertEqual(rc, 0)
        self.assertIn("Validated device", output)
        approved = self.store.get_device("device-2")
        self.assertIsNotNone(approved)
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["role"], "admin")

        rc, output = self._stdout_for(
            admin_cli.cmd_device_approve,
            argparse.Namespace(device_id="device-1", role="arborist"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "approved"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_issue_token,
            argparse.Namespace(device_id="device-1", ttl=3600),
        )
        self.assertEqual(rc, 0)
        self.assertIn("access_token", output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_revoke,
            argparse.Namespace(device_id="device-1"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "revoked"', output)

    @patch("admin_cli._pending_devices")
    def test_device_validate_handles_invalid_index(self, pending_mock) -> None:
        pending_mock.return_value = [{"device_id": "device-1"}]
        rc, output = self._stdout_for(
            admin_cli.cmd_device_validate,
            argparse.Namespace(index=5, role="arborist"),
        )
        self.assertEqual(rc, 1)
        self.assertIn("Invalid index", output)

    @patch("admin_cli._http")
    def test_remote_device_commands(self, http_mock) -> None:
        http_mock.side_effect = [
            (200, {"ok": True, "devices": [{"device_id": "device-1", "status": "pending", "role": "arborist"}]}),
            (200, {"ok": True, "devices": [{"device_id": "device-1", "status": "pending", "role": "arborist"}]}),
            (200, {"ok": True, "device": {"device_id": "device-1", "status": "approved", "role": "admin"}}),
            (200, {"ok": True, "device": {"device_id": "device-1", "status": "approved", "role": "admin"}}),
            (200, {"ok": True, "device": {"device_id": "device-1", "status": "revoked", "role": "admin"}}),
            (200, {"ok": True, "access_token": "token", "device_id": "device-1"}),
        ]

        rc, output = self._stdout_for(
            admin_cli.cmd_device_pending,
            argparse.Namespace(json=True, host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"device_id": "device-1"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_validate,
            argparse.Namespace(index=1, role="admin", host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn("Validated device", output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_approve,
            argparse.Namespace(device_id="device-1", role="admin", host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "approved"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_revoke,
            argparse.Namespace(device_id="device-1", host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"status": "revoked"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_device_issue_token,
            argparse.Namespace(device_id="device-1", ttl=600, host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"access_token": "token"', output)

    def test_context_defaults_select_local_and_cloud(self) -> None:
        import os
        os.environ["TRAQ_ADMIN_BASE_URL"] = "http://127.0.0.1:8000"
        os.environ["TRAQ_API_KEY"] = "demo-key"
        os.environ["TRAQ_CLOUD_ADMIN_BASE_URL"] = "https://cloud.example.run.app"
        os.environ["TRAQ_CLOUD_API_KEY"] = "cloud-key"
        self.assertEqual(admin_cli._context_defaults("local"), ("http://127.0.0.1:8000", "demo-key"))
        self.assertEqual(admin_cli._context_defaults("cloud"), ("https://cloud.example.run.app", "cloud-key"))

    def test_cloud_context_requires_explicit_settings(self) -> None:
        with patch("admin_cli._settings") as settings_mock:
            settings_mock.return_value = type("Settings", (), {"cloud_admin_base_url": None, "cloud_api_key": None})()
            with self.assertRaises(RuntimeError):
                admin_cli._context_defaults("cloud")

    def test_http_defaults_cover_device_commands(self) -> None:
        self.assertEqual(
            admin_cli._inject_http_defaults(["device", "pending"], host="https://cloud.example.run.app", api_key="cloud-key"),
            ["device", "pending", "--host", "https://cloud.example.run.app", "--api-key", "cloud-key"],
        )

    @patch("admin_cli._run_repl")
    def test_main_cloud_context_starts_repl_with_cloud_defaults(self, repl_mock) -> None:
        import os
        os.environ["TRAQ_CLOUD_ADMIN_BASE_URL"] = "https://cloud.example.run.app"
        os.environ["TRAQ_CLOUD_API_KEY"] = "cloud-key"
        repl_mock.return_value = 0
        with patch.object(sys, "argv", ["traq-admin", "cloud"]):
            rc = admin_cli.main()
        self.assertEqual(rc, 0)
        _, kwargs = repl_mock.call_args
        self.assertEqual(kwargs["context_name"], "cloud")

    @patch("admin_cli.cmd_device_pending")
    def test_main_cloud_context_injects_http_defaults_for_one_shot_commands(self, pending_mock) -> None:
        import os
        os.environ["TRAQ_CLOUD_ADMIN_BASE_URL"] = "https://cloud.example.run.app"
        os.environ["TRAQ_CLOUD_API_KEY"] = "cloud-key"
        pending_mock.return_value = 0
        with patch.object(sys, "argv", ["traq-admin", "cloud", "device", "pending"]):
            rc = admin_cli.main()
        self.assertEqual(rc, 0)
        args = pending_mock.call_args.args[0]
        self.assertEqual(args.host, "https://cloud.example.run.app")
        self.assertEqual(args.api_key, "cloud-key")

    def test_resolve_device_id_accepts_unique_prefix(self) -> None:
        self._register_pending_device("dc82323f-5424-49a2-9211-67b01f9f9ded")
        resolved = admin_cli._resolve_device_id("dc82323f")
        self.assertEqual(resolved, "dc82323f-5424-49a2-9211-67b01f9f9ded")

    @patch("app.cli.net_commands.subprocess.check_output")
    def test_net_ipv4_and_ipv6(self, check_output_mock) -> None:
        check_output_mock.side_effect = [
            "2: wlp0s20f3: <BROADCAST>\n    inet 192.168.12.231/24 scope global dynamic wlp0s20f3\n",
            "192.168.12.231 2601:204:f301:8de0::dcf0\n",
            "2: wlp0s20f3: <BROADCAST>\n    inet6 2601:204:f301:8de0::dcf0/128 scope global dynamic \n",
        ]

        rc, output = self._stdout_for(admin_cli.cmd_net_ipv4, argparse.Namespace(json=False))
        self.assertEqual(rc, 0)
        self.assertIn("192.168.12.231/24", output)

        rc, output = self._stdout_for(admin_cli.cmd_net_ipv6, argparse.Namespace(json=True))
        self.assertEqual(rc, 0)
        self.assertIn("2601:204:f301:8de0::dcf0", output)
