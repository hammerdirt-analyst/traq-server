"""
Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex
"""
from typing import Optional

from pydantic import Field

from ..common import StrictBaseModel


class Matrix2Condition(StrictBaseModel):
    condition_number: Optional[str] = Field(
        None,
        description="Condition number/index if stated. Null if not stated.",
    )
    tree_part: Optional[str] = Field(
        None,
        description="Tree part as stated (e.g., Crown, Trunk, Roots). Null if not stated.",
    )
    condition: Optional[str] = Field(
        None,
        description="Single condition of concern (one row). Null if not stated.",
    )
    part_size: Optional[str] = Field(
        None,
        description="Part size as stated (e.g., 2\"). Null if not stated.",
    )
    fall_distance: Optional[str] = Field(
        None,
        description="Fall distance as stated. Null if not stated.",
    )
    target_number: Optional[str] = Field(
        None,
        description="Target number as stated (may refer to target assessment).",
    )
    target_protection: Optional[str] = Field(
        None,
        description="Target protection as stated. Null if not stated.",
    )
    failure_likelihood: Optional[str] = Field(
        None,
        description="Failure likelihood as stated. Null if not stated.",
    )
    impact_likelihood: Optional[str] = Field(
        None,
        description="Impact likelihood as stated. Null if not stated.",
    )
    failure_and_impact: Optional[str] = Field(
        None,
        description="Failure and impact likelihood as stated. Null if not stated.",
    )
    consequences: Optional[str] = Field(
        None,
        description="Consequences as stated. Null if not stated.",
    )
    risk_rating: Optional[str] = Field(
        None,
        description="Overall risk rating as stated. Null if not stated.",
    )
