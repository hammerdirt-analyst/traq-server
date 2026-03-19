"""Summary and PDF render helpers for final/report workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any


class ReportRenderService:
    """Wrap report-letter and TRAQ PDF rendering behind a stable boundary."""

    @staticmethod
    def generate_summary(*, form_data: dict[str, Any], transcript: str) -> str:
        """Generate the narrative summary from form data and transcript text."""
        from .. import report_letter

        return report_letter.generate_summary(
            form_data=form_data,
            transcript=transcript,
        )

    @staticmethod
    def generate_traq_pdf(*, form_data: dict[str, Any], output_path: Path) -> None:
        """Render the filled TRAQ PDF to the target output path."""
        from .. import pdf_fill

        pdf_fill.generate_traq_pdf(
            form_data=form_data,
            output_path=output_path,
            flatten=True,
        )
