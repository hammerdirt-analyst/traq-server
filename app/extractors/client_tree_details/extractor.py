"""Typed extractor wrapper for ``client_tree_details``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``ClientTreeDetailsExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from .models import ClientTreeDetailsExtraction
from ..registry import run_extraction


def run_client_tree_details_extraction(transcript: str) -> ClientTreeDetailsExtraction:
    """Run extraction for the ``client_tree_details`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``ClientTreeDetailsExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(ClientTreeDetailsExtraction, run_extraction("client_tree_details", transcript))
