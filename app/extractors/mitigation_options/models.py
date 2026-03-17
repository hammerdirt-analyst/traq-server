"""Structured schema for the ``mitigation_options`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``mitigation_options`` section.

Dependencies:
    - pydantic.Field (and constrained types where needed) for field
      metadata and schema generation
    - ``StrictBaseModel`` for strict validation and OpenAI schema
      compatibility rules

Notes:
    This model is consumed by ``app.extractors.registry.run_extraction``
    and merged into draft/final form payloads by server round/final flows.
"""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..common import StrictBaseModel


ResidualRisk = Literal["low", "moderate", "high", "extreme"]


class MitigationOption(StrictBaseModel):
    option: str | None = Field(
        default=None,
        description="Mitigation option text (short line).",
    )
    residual_risk: ResidualRisk | None = Field(
        default=None,
        description="Residual risk for this option (low/moderate/high/extreme).",
    )


class MitigationOptionsExtraction(StrictBaseModel):
    section_id: Literal["mitigation_options"] = Field(
        "mitigation_options",
        description="Section identifier for this extraction.",
    )
    options: list[MitigationOption] = Field(
        default_factory=list,
        description=(
            "Ordered mitigation options. Each entry has an option string and "
            "optional residual risk. Keep to short lines. Do not invent."
        ),
    )
