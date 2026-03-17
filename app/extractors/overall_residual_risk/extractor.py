"""Typed extractor wrapper for ``overall_residual_risk``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``OverallResidualRiskExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import OverallResidualRiskExtraction


def run_overall_residual_risk_extraction(
    transcript: str,
) -> OverallResidualRiskExtraction:
    """Run extraction for the ``overall_residual_risk`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``OverallResidualRiskExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        OverallResidualRiskExtraction,
        run_extraction("overall_residual_risk", transcript),
    )
