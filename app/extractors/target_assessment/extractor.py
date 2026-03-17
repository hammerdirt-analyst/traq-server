"""Typed extractor wrapper for ``target_assessment``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``TargetAssessmentExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import TargetAssessmentExtraction
from ..registry import run_extraction


def run_target_assessment_extraction(transcript: str) -> TargetAssessmentExtraction:
    """Run extraction for the ``target_assessment`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``TargetAssessmentExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(TargetAssessmentExtraction, run_extraction("target_assessment", transcript))
