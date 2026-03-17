"""Structured schema for the ``tree_health_and_species`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``tree_health_and_species`` section.

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

from pydantic import Field, conint, constr

from ..common import StrictBaseModel


class FoliageProfile(StrictBaseModel):
    none_seasonal: Optional[bool] = Field(
        None,
        description=(
            "True if transcript states no foliage due to season. "
            "False if explicitly negated. Null if not mentioned."
        ),
    )
    none_dead: Optional[bool] = Field(
        None,
        description=(
            "True if transcript states no foliage because tree is dead. "
            "False if explicitly negated. Null if not mentioned."
        ),
    )
    normal_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description=(
            "Percent of normal foliage if stated (0-100). Null if not stated."
        ),
    )
    chlorotic_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description=(
            "Percent chlorotic foliage if stated (0-100). Null if not stated."
        ),
    )
    necrotic_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description=(
            "Percent necrotic foliage if stated (0-100). Null if not stated."
        ),
    )


class SpeciesFailureProfile(StrictBaseModel):
    branches: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates branch failures are a concern. "
            "False if explicitly negated. Null if not mentioned."
        ),
    )
    trunk: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates trunk failures are a concern. "
            "False if explicitly negated. Null if not mentioned."
        ),
    )
    roots: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates root failures are a concern. "
            "False if explicitly negated. Null if not mentioned."
        ),
    )
    describe: Optional[constr(max_length=100)] = Field(
        None,
        description=(
            "Concise description of potential weak points/defects (<=100 chars), "
            "e.g., codominant unions, included bark, decay-prone zones. Null if not stated."
        ),
    )


class TreeHealthAndSpeciesExtraction(StrictBaseModel):
    section_id: Literal["tree_health_and_species"] = Field(
        "tree_health_and_species",
        description="Section identifier for this extraction.",
    )
    vigor: Optional[Literal["low", "normal", "high"]] = Field(
        None,
        description="Tree vigor if stated: low, normal, or high. Null if not stated.",
    )
    foliage: FoliageProfile = Field(
        ...,
        description="Foliage condition and percent breakdown.",
    )
    pests: Optional[constr(max_length=70)] = Field(
        None,
        description=(
            "Compressed pests note (<=70 chars). "
            "If explicitly none, use phrase like 'No pests observed'. Null if not stated."
        ),
    )
    abiotic: Optional[constr(max_length=70)] = Field(
        None,
        description=(
            "Compressed abiotic-stressor note (<=70 chars). "
            "If explicitly none, use phrase like 'No abiotic stress observed'. Null if not stated."
        ),
    )
    species_failure_profile: SpeciesFailureProfile = Field(
        ...,
        description="Species-level failure profile.",
    )
