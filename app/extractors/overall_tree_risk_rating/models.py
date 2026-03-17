"""Structured schema for the ``overall_tree_risk_rating`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``overall_tree_risk_rating`` section.

Dependencies:
    - pydantic.Field (and constrained types where needed) for field
      metadata and schema generation
    - ``StrictBaseModel`` for strict validation and OpenAI schema
      compatibility rules

Notes:
    This model is consumed by ``app.extractors.registry.run_extraction``
    and merged into draft/final form payloads by server round/final flows.
"""
from typing import Literal, Optional

from pydantic import Field

from ..common import StrictBaseModel


class OverallTreeRiskRatingExtraction(StrictBaseModel):
    section_id: Literal["overall_tree_risk_rating"] = Field(
        "overall_tree_risk_rating",
        description="Section identifier for this extraction.",
    )
    rating: Optional[Literal["low", "moderate", "high", "extreme"]] = Field(
        None,
        description="Overall tree risk rating if stated.",
    )
