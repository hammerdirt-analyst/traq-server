"""Typed extractor wrapper for ``recommended_inspection_interval``.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provides a section-specific entry point that delegates extraction
    to the central registry while preserving concrete return typing
    for callers and documentation.

Dependencies:
    - ``app.extractors.registry.run_extraction`` for shared extraction flow
    - ``RecommendedInspectionIntervalExtraction`` for output validation and typing

Data flow:
    transcript (str) -> registry -> Outlines/OpenAI -> validated model object
"""
import re
from typing import cast

from ..registry import run_extraction
from .models import RecommendedInspectionIntervalExtraction


_WORD_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


def _normalize_recommended_interval(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    s = raw.lower().replace("–", "-").replace("—", "-")

    for word, num in _WORD_NUM.items():
        s = re.sub(rf"\b{word}\b", str(num), s)

    range_match = re.search(
        r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\s*(months?|years?)\b",
        s,
    )
    if range_match:
        start = int(range_match.group(1))
        end = int(range_match.group(2))
        unit = range_match.group(3)
        normalized_unit = "months" if unit.startswith("month") else "years"
        return f"{start}-{end} {normalized_unit}"

    single_match = re.search(r"\b(\d{1,2})\s*(months?|years?)\b", s)
    if single_match:
        value = int(single_match.group(1))
        unit = single_match.group(2)
        if unit.startswith("month"):
            normalized_unit = "month" if value == 1 else "months"
        else:
            normalized_unit = "year" if value == 1 else "years"
        return f"{value} {normalized_unit}"

    # Fallback: keep a short coherent phrase.
    compact = " ".join(raw.split())
    return compact[:30].rstrip()


def run_recommended_inspection_interval_extraction(
    transcript: str,
) -> RecommendedInspectionIntervalExtraction:
    """Run extraction for the ``recommended_inspection_interval`` section.

    Args:
        transcript: Section transcript text to parse.

    Returns:
        Parsed ``RecommendedInspectionIntervalExtraction`` payload.

    Raises:
        KeyError: If section id is not registered.
        ValueError: If transcript is empty.
        RuntimeError: If OpenAI configuration is missing.
    """

    result = cast(
        RecommendedInspectionIntervalExtraction,
        run_extraction("recommended_inspection_interval", transcript),
    )
    normalized = _normalize_recommended_interval(result.text)
    return result.model_copy(update={"text": normalized})
