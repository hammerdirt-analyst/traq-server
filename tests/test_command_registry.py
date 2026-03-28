"""Tests for CLI command registry metadata."""

from __future__ import annotations

import unittest

from app.cli.command_registry import COMMAND_GROUP_SPECS, command_requires_http_defaults


class CommandRegistryTests(unittest.TestCase):
    def test_http_default_paths_cover_expected_remote_commands(self) -> None:
        self.assertTrue(command_requires_http_defaults(["device", "pending"]))
        self.assertTrue(command_requires_http_defaults(["customer", "billing"]))
        self.assertTrue(command_requires_http_defaults(["job", "inspect"]))
        self.assertTrue(command_requires_http_defaults(["export", "images-fetch-all"]))
        self.assertFalse(command_requires_http_defaults(["final", "set-final"]))
        self.assertFalse(command_requires_http_defaults(["net", "ipv4"]))

    def test_registry_group_names_are_unique(self) -> None:
        names = [spec.name for spec in COMMAND_GROUP_SPECS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
