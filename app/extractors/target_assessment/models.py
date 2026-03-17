"""Structured schema for the ``target_assessment`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``target_assessment`` section.

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

from pydantic import Field, conint

from ..common import StrictBaseModel


class TargetEntry(StrictBaseModel):
    target_number: Optional[str] = Field(
        None,
        description="Target number/identifier as stated (e.g., 'Target 1'). Null if not stated.",
    )
    label: Optional[str] = Field(
        None,
        description=(
            "Single-word label derived from the target description/context. "
            "Null if not stated or cannot be inferred."
        ),
    )
    zone_within_drip_line: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates target is within drip line. "
            "False if explicitly stated not within drip line. Null if not stated."
        ),
    )
    zone_within_1x_height: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates target is within 1x tree height. "
            "False if explicitly stated not within 1x height. Null if not stated."
        ),
    )
    zone_within_1_5x_height: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates target is within 1.5x tree height. "
            "False if explicitly stated not within 1.5x height. Null if not stated."
        ),
    )
    occupancy_rate: Optional[conint(ge=1, le=4)] = Field(
        None,
        description=(
            "Occupancy rate 1-4 as stated (1 rare, 4 constant). Null if not stated."
        ),
    )
    practical_to_move: Optional[bool] = Field(
        None,
        description=(
            "True if practical to move target. False if explicitly not practical. "
            "Null if not stated."
        ),
    )
    restriction_practical: Optional[bool] = Field(
        None,
        description=(
            "True if restriction is practical. False if explicitly not practical. "
            "Null if not stated."
        ),
    )


class TargetAssessmentExtraction(StrictBaseModel):
    section_id: Literal["target_assessment"] = Field(
        "target_assessment",
        description="Section identifier for this extraction.",
    )
    targets: list[TargetEntry] = Field(
        default_factory=list,
        description=(
            "Ordered targets as stated in transcript. Preserve order of mention."
        ),
    )
