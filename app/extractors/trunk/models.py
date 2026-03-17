"""Structured schema for the ``trunk`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``trunk`` section.

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


class TrunkExtraction(StrictBaseModel):
    section_id: Literal["trunk"] = Field(
        "trunk",
        description="Section identifier for this extraction.",
    )
    dead_missing_bark: Optional[bool] = Field(
        None,
        description="True if dead/missing bark is stated. False if explicitly negated. Null if not mentioned.",
    )
    abnormal_bark_texture_color: Optional[bool] = Field(
        None,
        description="True if abnormal bark texture/color is stated. False if explicitly negated. Null if not mentioned.",
    )
    codominant_stems: Optional[bool] = Field(
        None,
        description="True if codominant stems are stated. False if explicitly negated. Null if not mentioned.",
    )
    included_bark: Optional[bool] = Field(
        None,
        description="True if included bark is stated. False if explicitly negated. Null if not mentioned.",
    )
    cracks: Optional[bool] = Field(
        None,
        description="True if cracks are stated. False if explicitly negated. Null if not mentioned.",
    )
    sapwood_damage_decay: Optional[bool] = Field(
        None,
        description="True if sapwood damage/decay is stated. False if explicitly negated. Null if not mentioned.",
    )
    cankers_galls_burls: Optional[bool] = Field(
        None,
        description="True if cankers/galls/burls are stated. False if explicitly negated. Null if not mentioned.",
    )
    sap_ooze: Optional[bool] = Field(
        None,
        description="True if sap ooze is stated. False if explicitly negated. Null if not mentioned.",
    )
    lightning_damage: Optional[bool] = Field(
        None,
        description="True if lightning damage is stated. False if explicitly negated. Null if not mentioned.",
    )
    heartwood_decay: Optional[bool] = Field(
        None,
        description="True if heartwood decay is stated. False if explicitly negated. Null if not mentioned.",
    )
    conks_mushrooms: Optional[bool] = Field(
        None,
        description="True if conks/mushrooms are stated. False if explicitly negated. Null if not mentioned.",
    )
    cavity_nest_hole_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description="Cavity/nest hole percent circumference if stated (0-100). Null if not stated.",
    )
    cavity_nest_hole_depth: Optional[int] = Field(
        None,
        description="Cavity/nest hole depth in inches as digits only. Null if not stated.",
    )
    poor_taper: Optional[bool] = Field(
        None,
        description="True if poor taper is stated. False if explicitly negated. Null if not mentioned.",
    )
    lean_degrees: Optional[int] = Field(
        None,
        description="Lean degrees if stated. Null if not stated.",
    )
    lean_corrected: Optional[constr(max_length=40)] = Field(
        None,
        description="Concise lean-correction note (<=40 chars). Null if not stated.",
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
