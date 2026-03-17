"""Structured schema for the ``inspection_limitations`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``inspection_limitations`` section.

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


class InspectionLimitationsExtraction(StrictBaseModel):
    section_id: Literal["inspection_limitations"] = Field(
        "inspection_limitations",
        description="Section identifier for this extraction.",
    )
    none: Optional[bool] = Field(
        None,
        description="True if no inspection limitations are stated. False if limitations are stated.",
    )
    visibility: Optional[bool] = Field(
        None,
        description="True if visibility limitations are stated. False if explicitly negated.",
    )
    access: Optional[bool] = Field(
        None,
        description="True if access limitations are stated. False if explicitly negated.",
    )
    vines: Optional[bool] = Field(
        None,
        description="True if vines are stated as a limitation. False if explicitly negated.",
    )
    root_collar_buried: Optional[bool] = Field(
        None,
        description="True if root collar buried is stated as a limitation. False if explicitly negated.",
    )
