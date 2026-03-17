"""Typed extractor wrapper for ``work_priority``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``WorkPriorityExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
from typing import cast

from ..registry import run_extraction
from .models import WorkPriorityExtraction


def run_work_priority_extraction(transcript: str) -> WorkPriorityExtraction:
    """Run extraction for the ``work_priority`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``WorkPriorityExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    return cast(
        WorkPriorityExtraction,
        run_extraction("work_priority", transcript),
    )
