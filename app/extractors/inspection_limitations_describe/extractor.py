"""Typed extractor wrapper for ``inspection_limitations_describe``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``InspectionLimitationsDescribeExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import InspectionLimitationsDescribeExtraction


def run_inspection_limitations_describe_extraction(
    transcript: str,
) -> InspectionLimitationsDescribeExtraction:
    """Run extraction for the ``inspection_limitations_describe`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``InspectionLimitationsDescribeExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        InspectionLimitationsDescribeExtraction,
        run_extraction("inspection_limitations_describe", transcript),
    )
