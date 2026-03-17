"""Structured schema for the ``roots_and_root_collar`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``roots_and_root_collar`` section.

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


class RootsAndRootCollarExtraction(StrictBaseModel):
    section_id: Literal["roots_and_root_collar"] = Field(
        "roots_and_root_collar",
        description="Section identifier for this extraction.",
    )
    collar_buried_not_visible: Optional[bool] = Field(
        None,
        description="True if collar buried/not visible is stated. False if explicitly negated. Null if not mentioned.",
    )
    collar_depth: Optional[int] = Field(
        None,
        description="Collar depth in inches as digits only. Null if not stated.",
    )
    stem_girdling: Optional[bool] = Field(
        None,
        description="True if stem girdling is stated. False if explicitly negated. Null if not mentioned.",
    )
    dead: Optional[bool] = Field(
        None,
        description="True if dead is stated. False if explicitly negated. Null if not mentioned.",
    )
    decay: Optional[bool] = Field(
        None,
        description="True if decay is stated. False if explicitly negated. Null if not mentioned.",
    )
    conks_mushrooms: Optional[bool] = Field(
        None,
        description="True if conks/mushrooms are stated. False if explicitly negated. Null if not mentioned.",
    )
    ooze: Optional[bool] = Field(
        None,
        description="True if ooze is stated. False if explicitly negated. Null if not mentioned.",
    )
    cavity: Optional[bool] = Field(
        None,
        description="True if cavity is stated. False if explicitly negated. Null if not mentioned.",
    )
    cavity_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description="Cavity percent circumference if stated (0-100). Null if not stated.",
    )
    cracks: Optional[bool] = Field(
        None,
        description="True if cracks are stated. False if explicitly negated. Null if not mentioned.",
    )
    cut_damaged_roots: Optional[bool] = Field(
        None,
        description="True if cut/damaged roots are stated. False if explicitly negated. Null if not mentioned.",
    )
    distance_from_trunk: Optional[int] = Field(
        None,
        description="Distance from trunk in feet as digits only. Null if not stated.",
    )
    root_plate_lifting: Optional[bool] = Field(
        None,
        description="True if root plate lifting is stated. False if explicitly negated. Null if not mentioned.",
    )
    soil_weakness: Optional[bool] = Field(
        None,
        description="True if soil weakness is stated. False if explicitly negated. Null if not mentioned.",
    )
    response_growth: Optional[constr(max_length=40)] = Field(
        None,
        description="Concise response-growth note (<=40 chars). Null if not stated.",
    )
    main_concerns: Optional[constr(max_length=88)] = Field(
        None,
        description="Main concerns summary (<=88 chars). Null if not stated.",
    )
    load_on_defect: Optional[Literal["n/a", "minor", "moderate", "significant"]] = Field(
        None,
        description="Load on defect if stated: n/a, minor, moderate, significant. Null if not stated.",
    )
    likelihood_of_failure: Optional[Literal["improbable", "possible", "probable", "imminent"]] = Field(
        None,
        description="Likelihood of failure if stated: improbable, possible, probable, imminent. Null if not stated.",
    )
