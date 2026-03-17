"""Typed extractor wrapper for ``risk_categorization_crown``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``RiskCategorizationCrownExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import RiskCategorizationCrownExtraction


def run_risk_categorization_crown_extraction(
    transcript: str,
) -> RiskCategorizationCrownExtraction:
    """Run extraction for the ``risk_categorization_crown`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``RiskCategorizationCrownExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        RiskCategorizationCrownExtraction,
        run_extraction("risk_categorization_crown", transcript),
    )

