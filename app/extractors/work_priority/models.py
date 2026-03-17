"""Structured schema for the ``work_priority`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``work_priority`` section.

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


class WorkPriorityExtraction(StrictBaseModel):
    section_id: Literal["work_priority"] = Field(
        "work_priority",
        description="Section identifier for this extraction.",
    )
    priority: Optional[Literal["1", "2", "3", "4"]] = Field(
        None,
        description="Work priority if stated (1-4).",
    )
