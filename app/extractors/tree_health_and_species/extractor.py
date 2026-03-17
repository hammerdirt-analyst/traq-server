"""Typed extractor wrapper for ``tree_health_and_species``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``TreeHealthAndSpeciesExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import TreeHealthAndSpeciesExtraction
from ..registry import run_extraction


def run_tree_health_and_species_extraction(transcript: str) -> TreeHealthAndSpeciesExtraction:
    """Run extraction for the ``tree_health_and_species`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``TreeHealthAndSpeciesExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(TreeHealthAndSpeciesExtraction, run_extraction("tree_health_and_species", transcript))
