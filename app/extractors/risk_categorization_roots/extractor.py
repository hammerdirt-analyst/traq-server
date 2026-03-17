"""Typed extractor wrapper for ``risk_categorization_roots``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``RiskCategorizationRootsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import RiskCategorizationRootsExtraction


def run_risk_categorization_roots_extraction(
    transcript: str,
) -> RiskCategorizationRootsExtraction:
    """Run extraction for the ``risk_categorization_roots`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``RiskCategorizationRootsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        RiskCategorizationRootsExtraction,
        run_extraction("risk_categorization_roots", transcript),
    )

