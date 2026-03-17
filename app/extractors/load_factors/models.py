"""Structured schema for the ``load_factors`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``load_factors`` section.

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

from pydantic import Field, constr

from ..common import StrictBaseModel


class LoadFactorsExtraction(StrictBaseModel):
    section_id: Literal["load_factors"] = Field(
        "load_factors",
        description="Section identifier for this extraction.",
    )
    wind_exposure: Optional[Literal["protected", "partial", "full"]] = Field(
        None,
        description=(
            "Wind exposure if stated: protected, partial, or full. Null if not stated."
        ),
    )
    wind_funneling: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates wind funneling. False if explicitly negated. "
            "Null if not mentioned."
        ),
    )
    wind_funneling_notes: Optional[constr(max_length=40)] = Field(
        None,
        description=(
            "Concise cause/source note for wind funneling (<=40 chars), e.g., "
            "'between buildings', 'street canyon effect'. Null if not stated."
        ),
    )
    relative_crown_size: Optional[Literal["small", "medium", "large"]] = Field(
        None,
        description=(
            "Relative crown size if stated: small, medium, or large. Null if not stated."
        ),
    )
    crown_density: Optional[Literal["sparse", "normal", "dense"]] = Field(
        None,
        description=(
            "Crown density if stated: sparse, normal, or dense. Null if not stated."
        ),
    )
    interior_branches_density: Optional[Literal["few", "normal", "dense"]] = Field(
        None,
        description=(
            "Interior branches density if stated: few, normal, or dense. Null if not stated."
        ),
    )
    vines_mistletoe_moss_present: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates vines, mistletoe, or moss are present. "
            "False if explicitly stated none observed. Null if not mentioned."
        ),
    )
    vines_mistletoe_moss_notes: Optional[constr(max_length=50)] = Field(
        None,
        description=(
            "Concise vines/mistletoe/moss note (<=50 chars). "
            "If explicitly none, use phrase like 'No vines/mistletoe/moss observed'. "
            "Null if not stated."
        ),
    )
    recent_change_in_load_factors: Optional[constr(max_length=70)] = Field(
        None,
        description=(
            "Concise note (<=70 chars) for recent/planned interventions or changes that may "
            "increase branch loading. If explicitly none/planned none, use a concise none-noted "
            "phrase. Null if not stated."
        ),
    )
