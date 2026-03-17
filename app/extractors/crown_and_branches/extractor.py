"""Typed extractor wrapper for ``crown_and_branches``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``CrownAndBranchesExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import CrownAndBranchesExtraction
from ..registry import run_extraction


def run_crown_and_branches_extraction(transcript: str) -> CrownAndBranchesExtraction:
    """Run extraction for the ``crown_and_branches`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``CrownAndBranchesExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(CrownAndBranchesExtraction, run_extraction("crown_and_branches", transcript))
