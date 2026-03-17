"""Typed extractor wrapper for ``site_factors``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``SiteFactorsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import SiteFactorsExtraction
from ..registry import run_extraction


def run_site_factors_extraction(transcript: str) -> SiteFactorsExtraction:
    """Run extraction for the ``site_factors`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``SiteFactorsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(SiteFactorsExtraction, run_extraction("site_factors", transcript))
