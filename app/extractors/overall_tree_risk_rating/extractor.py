"""Typed extractor wrapper for ``overall_tree_risk_rating``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``OverallTreeRiskRatingExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import OverallTreeRiskRatingExtraction


def run_overall_tree_risk_rating_extraction(
    transcript: str,
) -> OverallTreeRiskRatingExtraction:
    """Run extraction for the ``overall_tree_risk_rating`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``OverallTreeRiskRatingExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        OverallTreeRiskRatingExtraction,
        run_extraction("overall_tree_risk_rating", transcript),
    )
