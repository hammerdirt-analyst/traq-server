"""Project CLI coverage."""

from __future__ import annotations

import argparse
import json
from unittest.mock import patch

from tests.admin_cli_support import AdminCliTestCase, admin_cli


class AdminCliProjectTests(AdminCliTestCase):
    """Cover local and remote project command behavior."""

    def test_project_create_list_and_update_local(self) -> None:
        rc, output = self._stdout_for(
            admin_cli.cmd_project_create,
            argparse.Namespace(project="Briarwood", project_slug=None),
        )
        self.assertEqual(rc, 0)
        created = json.loads(output)
        self.assertTrue(created["project_id"].startswith("project_"))
        self.assertEqual(created["project_slug"], "briarwood")

        rc, output = self._stdout_for(admin_cli.cmd_project_list, argparse.Namespace())
        self.assertEqual(rc, 0)
        listed = json.loads(output)
        self.assertEqual(listed[0]["project"], "Briarwood")

        rc, output = self._stdout_for(
            admin_cli.cmd_project_update,
            argparse.Namespace(project_ref=created["project_id"], project="Briarwood West", project_slug=None),
        )
        self.assertEqual(rc, 0)
        updated = json.loads(output)
        self.assertEqual(updated["project"], "Briarwood West")
        self.assertEqual(updated["project_slug"], "briarwood-west")

    @patch("admin_cli._http")
    def test_project_commands_remote(self, http_mock) -> None:
        http_mock.side_effect = [
            (200, {"ok": True, "project": {"project_id": "project_1", "project": "Arboretum", "project_slug": "arboretum"}}),
            (200, {"ok": True, "projects": [{"project_id": "project_1", "project": "Arboretum", "project_slug": "arboretum"}]}),
            (200, {"ok": True, "project": {"project_id": "project_1", "project": "Arboretum West", "project_slug": "arboretum-west"}}),
        ]

        rc, output = self._stdout_for(
            admin_cli.cmd_project_create,
            argparse.Namespace(project="Arboretum", project_slug=None, host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"project_id": "project_1"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_project_list,
            argparse.Namespace(host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"project": "Arboretum"', output)

        rc, output = self._stdout_for(
            admin_cli.cmd_project_update,
            argparse.Namespace(project_ref="project_1", project="Arboretum West", project_slug=None, host="https://example.test", api_key="demo-key"),
        )
        self.assertEqual(rc, 0)
        self.assertIn('"project_slug": "arboretum-west"', output)


if __name__ == "__main__":
    import unittest

    unittest.main()
