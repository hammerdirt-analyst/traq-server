"""Typed extractor wrapper for ``advanced_assessment_needed``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``AdvancedAssessmentNeededExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import AdvancedAssessmentNeededExtraction


def run_advanced_assessment_needed_extraction(
    transcript: str,
) -> AdvancedAssessmentNeededExtraction:
    """Run extraction for advanced-assessment-needed intent.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``AdvancedAssessmentNeededExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """
    return cast(
        AdvancedAssessmentNeededExtraction,
        run_extraction("advanced_assessment_needed", transcript),
    )
