"""Structured schema for the ``advanced_assessment_type_reason`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``advanced_assessment_type_reason`` section.

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


class AdvancedAssessmentTypeReasonExtraction(StrictBaseModel):
    section_id: Literal["advanced_assessment_type_reason"] = Field(
        "advanced_assessment_type_reason",
        description="Section identifier for this extraction.",
    )
    text: constr(max_length=40) | None = Field(
        None,
        description=(
            "Advanced assessment type/reason as stated. Keep concise and <= 40 "
            "characters. Null if not stated."
        ),
    )
