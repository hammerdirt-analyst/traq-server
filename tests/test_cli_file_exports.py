"""Focused coverage for shared CLI export file output helpers."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.cli.file_exports import filename_from_headers, save_bytes_output, save_json_output


class CliFileExportsTests(unittest.TestCase):
    def test_filename_from_headers_uses_content_disposition_when_present(self) -> None:
        self.assertEqual(
            filename_from_headers(
                {"Content-Disposition": 'attachment; filename="report.jpg"'},
                fallback="fallback.bin",
            ),
            "report.jpg",
        )

    def test_filename_from_headers_uses_fallback_when_missing(self) -> None:
        self.assertEqual(filename_from_headers({}, fallback="fallback.bin"), "fallback.bin")

    def test_save_bytes_output_writes_default_path(self) -> None:
        with TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "exports" / "img.jpg"
            saved = save_bytes_output(payload=b"abc", output_path=None, default_path=target)
            self.assertEqual(saved, target)
            self.assertEqual(target.read_bytes(), b"abc")

    def test_save_json_output_writes_requested_output_path(self) -> None:
        with TemporaryDirectory() as tempdir:
            requested = Path(tempdir) / "custom" / "payload.json"
            saved = save_json_output(
                payload={"ok": True, "count": 2},
                output_path=str(requested),
                default_path=Path(tempdir) / "ignored.json",
            )
            self.assertEqual(saved, requested)
            self.assertEqual(json.loads(requested.read_text(encoding="utf-8")), {"ok": True, "count": 2})
