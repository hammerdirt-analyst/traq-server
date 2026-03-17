"""Structured schema for the ``recommended_inspection_interval`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``recommended_inspection_interval`` section.

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


class RecommendedInspectionIntervalExtraction(StrictBaseModel):
    section_id: Literal["recommended_inspection_interval"] = Field(
        "recommended_inspection_interval",
        description="Section identifier for this extraction.",
    )
    text: constr(max_length=30) | None = Field(
        None,
        description=(
            "Recommended inspection interval in compact form, e.g. '18 months', "
            "'2 years', '18-24 months', '2-3 years'. Null if not stated."
        ),
    )
