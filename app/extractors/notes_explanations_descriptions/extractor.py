"""Typed extractor wrapper for ``notes_explanations_descriptions``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``NotesExplanationsDescriptionsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import NotesExplanationsDescriptionsExtraction
from ..registry import run_extraction


def run_notes_explanations_descriptions_extraction(
    transcript: str,
) -> NotesExplanationsDescriptionsExtraction:
    """Run extraction for the ``notes_explanations_descriptions`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``NotesExplanationsDescriptionsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        NotesExplanationsDescriptionsExtraction,
        run_extraction("notes_explanations_descriptions", transcript),
    )
