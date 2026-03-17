"""Structured schema for the ``data_status`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``data_status`` section.

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


class DataStatusExtraction(StrictBaseModel):
    section_id: Literal["data_status"] = Field(
        "data_status",
        description="Section identifier for this extraction.",
    )
    status: Optional[Literal["final", "preliminary"]] = Field(
        None,
        description="Data status if stated: final or preliminary.",
    )
