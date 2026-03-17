"""Structured schema for the ``advanced_assessment_needed`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``advanced_assessment_needed`` section.

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


class AdvancedAssessmentNeededExtraction(StrictBaseModel):
    """Structured extraction payload for advanced assessment requirement.

    Attributes:
        section_id: Fixed section key used by registry routing and downstream
            merge logic.
        needed: One of ``"yes"`` or ``"no"`` when stated in transcript;
            ``None`` when not stated.

    Validation:
        - Extra keys are rejected by ``StrictBaseModel``.
        - ``needed`` is constrained to the allowed literal values.
    """

    section_id: Literal["advanced_assessment_needed"] = Field(
        "advanced_assessment_needed",
        description="Section identifier for this extraction.",
    )
    needed: Optional[Literal["no", "yes"]] = Field(
        None,
        description="Advanced assessment needed if stated: yes or no.",
    )
