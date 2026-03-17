"""Structured schema for the ``risk_categorization`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``risk_categorization`` section.

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

from pydantic import Field

from ..common import StrictBaseModel
from ..risk_categorization.common import Matrix2Condition


class RiskCategorizationExtraction(StrictBaseModel):
    section_id: Literal["risk_categorization"] = Field(
        "risk_categorization",
        description="Section identifier for this extraction.",
    )
    rows: list[Matrix2Condition] = Field(
        default_factory=list,
        description=(
            "Ordered risk categorization rows. Each row corresponds to a condition of concern "
            "and its ratings."
        ),
    )
