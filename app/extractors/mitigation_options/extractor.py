"""Typed extractor wrapper for ``mitigation_options``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``MitigationOptionsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import MitigationOptionsExtraction
from ..registry import run_extraction


def run_mitigation_options_extraction(
    transcript: str,
) -> MitigationOptionsExtraction:
    """Run extraction for the ``mitigation_options`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``MitigationOptionsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        MitigationOptionsExtraction,
        run_extraction("mitigation_options", transcript),
    )
