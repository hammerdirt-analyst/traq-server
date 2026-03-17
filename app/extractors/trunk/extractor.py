"""Typed extractor wrapper for ``trunk``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``TrunkExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import TrunkExtraction
from ..registry import run_extraction


def run_trunk_extraction(transcript: str) -> TrunkExtraction:
    """Run extraction for the ``trunk`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``TrunkExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(TrunkExtraction, run_extraction("trunk", transcript))
