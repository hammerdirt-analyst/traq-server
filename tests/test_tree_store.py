"""Tests for server-side tree number allocation rules."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from server.app.services.tree_store import parse_tree_number


class TreeStoreParsingTests(unittest.TestCase):
    def test_parse_tree_number_accepts_ints_digits_and_legacy_words(self) -> None:
        self.assertEqual(parse_tree_number(1), 1)
        self.assertEqual(parse_tree_number("2"), 2)
        self.assertEqual(parse_tree_number(" one "), 1)
        self.assertEqual(parse_tree_number("ten"), 10)

    def test_parse_tree_number_rejects_empty_or_invalid_values(self) -> None:
        self.assertIsNone(parse_tree_number(None))
        self.assertIsNone(parse_tree_number(""))
        self.assertIsNone(parse_tree_number("oak"))
        self.assertIsNone(parse_tree_number(0))


if __name__ == "__main__":
    unittest.main()
