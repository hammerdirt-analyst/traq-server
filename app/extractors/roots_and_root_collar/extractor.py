"""Typed extractor wrapper for ``roots_and_root_collar``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``RootsAndRootCollarExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import RootsAndRootCollarExtraction
from ..registry import run_extraction


def run_roots_and_root_collar_extraction(transcript: str) -> RootsAndRootCollarExtraction:
    """Run extraction for the ``roots_and_root_collar`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``RootsAndRootCollarExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(RootsAndRootCollarExtraction, run_extraction("roots_and_root_collar", transcript))
