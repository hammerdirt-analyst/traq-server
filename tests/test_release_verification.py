"""Tests for release verification helpers."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

from app.release_verification import (
    PRE_DEPLOY_TEST_MODULES,
    VerificationError,
    _health_check,
    default_pre_deploy_env,
    pre_deploy_command,
    required_post_deploy_env,
    run_post_deploy,
    run_pre_deploy,
)


class ReleaseVerificationTests(unittest.TestCase):
    def test_pre_deploy_command_includes_expected_modules(self) -> None:
        command = pre_deploy_command()
        self.assertEqual(command[:4], ("uv", "run", "python", "-m"))
        self.assertIn("tests.test_admin_cli_devices_and_context", command)
        self.assertIn("tests.test_admin_cli_exports_stage_repl", command)
        self.assertIn("tests.test_admin_cli_jobs_rounds", command)
        self.assertIn("tests.test_admin_cli_customers_artifacts", command)
        self.assertEqual(command[-1], PRE_DEPLOY_TEST_MODULES[-1])

    def test_default_pre_deploy_env_sets_ci_safe_defaults(self) -> None:
        env = default_pre_deploy_env({})
        self.assertEqual(env["TRAQ_DATABASE_URL"], "sqlite+pysqlite:///:memory:")
        self.assertEqual(env["TRAQ_ENABLE_DISCOVERY"], "false")
        self.assertEqual(env["TRAQ_AUTO_CREATE_SCHEMA"], "false")
        self.assertEqual(env["TRAQ_ENABLE_FILE_LOGGING"], "false")

    def test_required_post_deploy_env_rejects_missing_values(self) -> None:
        with self.assertRaises(VerificationError):
            required_post_deploy_env({})

    def test_required_post_deploy_env_accepts_complete_values(self) -> None:
        env = required_post_deploy_env(
            {
                "TRAQ_CLOUD_ADMIN_BASE_URL": "https://example.test",
            }
        )
        self.assertEqual(env["TRAQ_CLOUD_ADMIN_BASE_URL"], "https://example.test")

    @patch("app.release_verification.subprocess.run")
    def test_run_pre_deploy_executes_single_regression_step(self, run_mock: Mock) -> None:
        run_mock.return_value = MagicMock(returncode=0)
        run_pre_deploy(cwd=Path("/tmp/repo"), base_env={})
        self.assertEqual(run_mock.call_count, 1)
        command = tuple(run_mock.call_args.kwargs["args"] if "args" in run_mock.call_args.kwargs else run_mock.call_args.args[0])
        self.assertEqual(command, pre_deploy_command())

    @patch("app.release_verification._health_check")
    def test_run_post_deploy_runs_health_check_only(self, health_mock: Mock) -> None:
        run_post_deploy(
            cwd=Path("/tmp/repo"),
            base_env={
                "TRAQ_CLOUD_ADMIN_BASE_URL": "https://example.test/",
            },
        )
        health_mock.assert_called_once_with("https://example.test")

    @patch("app.release_verification.request.urlopen")
    def test_health_check_accepts_ok_payload(self, urlopen_mock: Mock) -> None:
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"ok"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        urlopen_mock.return_value = response
        _health_check("https://example.test")

    @patch("app.release_verification.request.urlopen")
    def test_health_check_rejects_unexpected_payload(self, urlopen_mock: Mock) -> None:
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"status":"down"}'
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        urlopen_mock.return_value = response
        with self.assertRaises(VerificationError):
            _health_check("https://example.test")


if __name__ == "__main__":
    unittest.main()
