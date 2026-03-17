"""Structured schema for the ``inspection_limitations_describe`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``inspection_limitations_describe`` section.

Dependencies:
    - pydantic.Field (and constrained types where needed) for field
      metadata and schema generation
    - ``StrictBaseModel`` for strict validation and OpenAI schema
      compatibility rules

Notes:
    This model is consumed by ``app.extractors.registry.run_extraction``
    and merged into draft/final form payloads by server round/final flows.
"""
from typing import Literal

from pydantic import Field, constr

from ..common import StrictBaseModel


class InspectionLimitationsDescribeExtraction(StrictBaseModel):
    section_id: Literal["inspection_limitations_describe"] = Field(
        "inspection_limitations_describe",
        description="Section identifier for this extraction.",
    )
    text: constr(max_length=40) | None = Field(
        None,
        description=(
            "Inspection limitations description as stated. Keep concise and <= 40 "
            "characters. Null if not stated."
        ),
    )
