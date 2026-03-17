"""Typed extractor wrapper for ``risk_categorization_trunk``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``RiskCategorizationTrunkExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import RiskCategorizationTrunkExtraction


def run_risk_categorization_trunk_extraction(
    transcript: str,
) -> RiskCategorizationTrunkExtraction:
    """Run extraction for the ``risk_categorization_trunk`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``RiskCategorizationTrunkExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        RiskCategorizationTrunkExtraction,
        run_extraction("risk_categorization_trunk", transcript),
    )

