"""Typed extractor wrapper for ``inspection_limitations``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``InspectionLimitationsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import InspectionLimitationsExtraction


def run_inspection_limitations_extraction(
    transcript: str,
) -> InspectionLimitationsExtraction:
    """Run extraction for the ``inspection_limitations`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``InspectionLimitationsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        InspectionLimitationsExtraction,
        run_extraction("inspection_limitations", transcript),
    )
