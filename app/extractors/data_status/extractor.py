"""Typed extractor wrapper for ``data_status``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``DataStatusExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import DataStatusExtraction


def run_data_status_extraction(transcript: str) -> DataStatusExtraction:
    """Run extraction for the ``data_status`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``DataStatusExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        DataStatusExtraction,
        run_extraction("data_status", transcript),
    )
