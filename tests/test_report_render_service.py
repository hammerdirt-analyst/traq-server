"""Focused checks for summary and TRAQ PDF rendering helpers."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.services.report_render_service import ReportRenderService


class ReportRenderServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ReportRenderService()

    def test_generate_summary_delegates_to_report_letter(self) -> None:
        with patch("app.report_letter.generate_summary", return_value="summary") as mock_generate:
            result = self.service.generate_summary(form_data={"a": 1}, transcript="hello")

        self.assertEqual(result, "summary")
        mock_generate.assert_called_once_with(form_data={"a": 1}, transcript="hello")

    def test_generate_traq_pdf_delegates_to_pdf_fill(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "out.pdf"
            with patch("app.pdf_fill.generate_traq_pdf") as mock_generate:
                self.service.generate_traq_pdf(form_data={"a": 1}, output_path=output_path)

        mock_generate.assert_called_once_with(
            form_data={"a": 1},
            output_path=output_path,
            flatten=True,
        )


if __name__ == "__main__":
    unittest.main()
