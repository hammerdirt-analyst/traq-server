"""Structured schema for the ``notes_explanations_descriptions`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``notes_explanations_descriptions`` section.

Dependencies:
    - pydantic.Field (and constrained types where needed) for field
      metadata and schema generation
    - ``StrictBaseModel`` for strict validation and OpenAI schema
      compatibility rules

Notes:
    This model is consumed by ``app.extractors.registry.run_extraction``
    and merged into draft/final form payloads by server round/final flows.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field, constr

from ..common import StrictBaseModel


class NotesExplanationsDescriptionsExtraction(StrictBaseModel):
    section_id: Literal["notes_explanations_descriptions"] = Field(
        "notes_explanations_descriptions",
        description="Section identifier for this extraction.",
    )
    notes: constr(max_length=230) | None = Field(
        default=None,
        description=(
            "Summarize notes/explanations/descriptions from the transcript. "
            "Do not invent details. Keep total length <=230 characters."
        ),
    )
