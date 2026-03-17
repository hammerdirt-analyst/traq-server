"""Structured schema for the ``crown_and_branches`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``crown_and_branches`` section.

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


class PruningHistory(StrictBaseModel):
    crown_cleaned: Optional[bool] = Field(
        None,
        description="True if crown cleaned is stated. False if explicitly negated. Null if not mentioned.",
    )
    reduced: Optional[bool] = Field(
        None,
        description="True if reduced is stated. False if explicitly negated. Null if not mentioned.",
    )
    topped: Optional[bool] = Field(
        None,
        description="True if topped is stated. False if explicitly negated. Null if not mentioned.",
    )
    flush_cuts: Optional[bool] = Field(
        None,
        description="True if flush cuts are stated. False if explicitly negated. Null if not mentioned.",
    )
    thinned: Optional[bool] = Field(
        None,
        description="True if thinned is stated. False if explicitly negated. Null if not mentioned.",
    )
    other: Optional[constr(max_length=30)] = Field(
        None,
        description="Concise other-pruning note (<=30 chars). Null if not mentioned.",
    )
    raised: Optional[bool] = Field(
        None,
        description="True if raised is stated. False if explicitly negated. Null if not mentioned.",
    )
    lion_tailed: Optional[bool] = Field(
        None,
        description="True if lion-tailed is stated. False if explicitly negated. Null if not mentioned.",
    )


class CrownAndBranchesExtraction(StrictBaseModel):
    section_id: Literal["crown_and_branches"] = Field(
        "crown_and_branches",
        description="Section identifier for this extraction.",
    )
    unbalanced_crown: Optional[bool] = Field(
        None,
        description="True if unbalanced crown is stated. False if explicitly negated. Null if not mentioned.",
    )
    lcr_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description="Live crown ratio percent if stated (0-100). Null if not stated.",
    )
    dead_twigs_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description="Dead twigs/branches percent overall if stated (0-100). Null if not stated.",
    )
    dead_twigs_max_dia: Optional[int] = Field(
        None,
        description="Dead twigs/branches max diameter in inches as digits only. Null if not stated.",
    )
    broken_hangers_number: Optional[int] = Field(
        None,
        description="Broken/hangers count if stated. Null if not stated.",
    )
    broken_hangers_max_dia: Optional[int] = Field(
        None,
        description="Broken/hangers max diameter in inches as digits only. Null if not stated.",
    )
    over_extended_branches: Optional[bool] = Field(
        None,
        description="True if over-extended branches are stated. False if explicitly negated. Null if not mentioned.",
    )
    pruning_history: PruningHistory = Field(
        ...,
        description="Pruning history indicators.",
    )
    cracks: Optional[bool] = Field(
        None,
        description="True if cracks are stated. False if explicitly negated. Null if not mentioned.",
    )
    cracks_notes: Optional[constr(max_length=50)] = Field(
        None,
        description=(
            "Concise crack-detail note (<=50 chars) describing nature of crack "
            "(e.g., length, position, depth, progression). Null if not stated."
        ),
    )
    lightning_damage: Optional[bool] = Field(
        None,
        description="True if lightning damage is stated. False if explicitly negated. Null if not mentioned.",
    )
    codominant: Optional[bool] = Field(
        None,
        description="True if codominant is stated. False if explicitly negated. Null if not mentioned.",
    )
    codominant_notes: Optional[constr(max_length=50)] = Field(
        None,
        description=(
            "Concise codominant-detail note (<=50 chars), e.g., included bark/union details. "
            "Null if not stated."
        ),
    )
    included_bark: Optional[bool] = Field(
        None,
        description="True if included bark is stated. False if explicitly negated. Null if not mentioned.",
    )
    weak_attachments: Optional[bool] = Field(
        None,
        description="True if weak attachments are stated. False if explicitly negated. Null if not mentioned.",
    )
    weak_attachments_notes: Optional[constr(max_length=40)] = Field(
        None,
        description=(
            "Concise weak-attachment note (<=40 chars). Null if not stated."
        ),
    )
    cavity_nest_hole_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description="Cavity/nest hole percent circumference if stated (0-100). Null if not stated.",
    )
    previous_branch_failures: Optional[bool] = Field(
        None,
        description="True if previous branch failures are stated. False if explicitly negated. Null if not mentioned.",
    )
    previous_branch_failures_notes: Optional[constr(max_length=30)] = Field(
        None,
        description="Concise previous-failure note (<=30 chars). Null if not stated.",
    )
    similar_branches_present: Optional[bool] = Field(
        None,
        description="True if similar branches present is stated. False if explicitly negated. Null if not mentioned.",
    )
    dead_missing_bark: Optional[bool] = Field(
        None,
        description="True if dead/missing bark is stated. False if explicitly negated. Null if not mentioned.",
    )
    cankers_galls_burls: Optional[bool] = Field(
        None,
        description="True if cankers/galls/burls are stated. False if explicitly negated. Null if not mentioned.",
    )
    sapwood_damage_decay: Optional[bool] = Field(
        None,
        description="True if sapwood damage/decay is stated. False if explicitly negated. Null if not mentioned.",
    )
    conks: Optional[bool] = Field(
        None,
        description="True if conks are stated. False if explicitly negated. Null if not mentioned.",
    )
    heartwood_decay: Optional[bool] = Field(
        None,
        description="True if heartwood decay is stated. False if explicitly negated. Null if not mentioned.",
    )
    heartwood_decay_notes: Optional[constr(max_length=40)] = Field(
        None,
        description=(
            "Concise heartwood-decay note (<=40 chars) describing extent/type of decay. "
            "Null if not stated."
        ),
    )
    response_growth: Optional[constr(max_length=70)] = Field(
        None,
        description=(
            "Concise response-growth note (<=70 chars) describing location/extent. "
            "Null if not stated."
        ),
    )
    main_concerns: Optional[constr(max_length=215)] = Field(
        None,
        description=(
            "Main concerns summary (<=215 chars). Null if not stated."
        ),
    )
    load_on_defect: Optional[Literal["n/a", "minor", "moderate", "significant"]] = Field(
        None,
        description="Load on defect if stated: n/a, minor, moderate, significant. Null if not stated.",
    )
    load_on_defect_notes: Optional[constr(max_length=70)] = Field(
        None,
        description="Concise load-on-defect note (<=70 chars). Null if not stated.",
    )
    likelihood_of_failure: Optional[Literal["improbable", "possible", "probable", "imminent"]] = Field(
        None,
        description="Likelihood of failure if stated: improbable, possible, probable, imminent. Null if not stated.",
    )
    likelihood_of_failure_notes: Optional[constr(max_length=70)] = Field(
        None,
        description="Concise likelihood-of-failure note (<=70 chars). Null if not stated.",
    )
    dead_twigs: Optional[bool] = Field(
        None,
        description="True if dead twigs/branches are stated. False if explicitly negated. Null if not mentioned.",
    )
