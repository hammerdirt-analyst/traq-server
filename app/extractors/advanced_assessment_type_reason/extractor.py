"""Typed extractor wrapper for ``advanced_assessment_type_reason``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``AdvancedAssessmentTypeReasonExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import AdvancedAssessmentTypeReasonExtraction


def run_advanced_assessment_type_reason_extraction(
    transcript: str,
) -> AdvancedAssessmentTypeReasonExtraction:
    """Run extraction for the ``advanced_assessment_type_reason`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``AdvancedAssessmentTypeReasonExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        AdvancedAssessmentTypeReasonExtraction,
        run_extraction("advanced_assessment_type_reason", transcript),
    )
