"""Structured schema for the ``site_factors`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``site_factors`` section.

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

from pydantic import Field, conint, constr, field_validator

from ..common import StrictBaseModel


class Topography(StrictBaseModel):
    flat: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates level/flat ground (e.g., 'flat', 'level lot', "
            "'no slope'). False if slope/grade is mentioned. Null if not mentioned."
        ),
    )
    slope: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates slope/grade/incline/hillside or gives a % grade. "
            "False if transcript indicates flat/level. Null if not mentioned."
        ),
    )
    slope_percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description=(
            "Numeric slope percent if explicitly stated (e.g., '15 percent grade'). "
            "Null if not stated."
        ),
    )
    aspect: Optional[str] = Field(
        None,
        description=(
            "Aspect or facing direction if stated (e.g., north, northeast). Null if not stated."
        ),
    )


class SiteChanges(StrictBaseModel):
    none: Optional[bool] = Field(
        None,
        description=(
            "True only if transcript explicitly says no site changes. "
            "False if any site change is mentioned. Null if not mentioned."
        ),
    )
    grade_change: Optional[bool] = Field(
        None,
        description=(
            "True if transcript mentions regrading, grade changes, leveling, fill, or cut. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    site_clearing: Optional[bool] = Field(
        None,
        description=(
            "True if transcript mentions clearing/removing vegetation/trees or site clearing. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    changed_soil_hydrology: Optional[bool] = Field(
        None,
        description=(
            "True if transcript mentions changes to drainage, irrigation, water flow, "
            "or altered hydrology (e.g., pooling water after changes). "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    root_cuts: Optional[bool] = Field(
        None,
        description=(
            "True if transcript mentions root cuts, trenching, utilities, or construction "
            "cutting roots. False if explicitly denied. Null if not mentioned."
        ),
    )
    landscape_environment: Optional[constr(max_length=30)] = Field(
        None,
        description=(
            "Compressed surrounding environment phrase (<=30 chars) that preserves key context, "
            "and can combine cues (e.g., 'Rural elementary school', 'Urban residential parkway'). "
            "Prefer concise phrase, not a full sentence. Null if not mentioned."
        ),
    )


class SoilConditions(StrictBaseModel):
    limited_volume: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates restricted soil volume or limited rooting space "
            "(e.g., 'limited volume', 'confined soil', 'small planting area'). "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    saturated: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates saturated or waterlogged soil, poor drainage, "
            "standing water, or soggy soil. False if explicitly denied. Null if not mentioned."
        ),
    )
    shallow: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates shallow soil, thin soil, or bedrock near surface. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    compacted: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates compacted or hardened soil, heavy foot/vehicle traffic. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    pavement_over_roots: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates pavement, concrete, driveway, sidewalk, or hardscape "
            "over roots or root zone. Example: 'driveway over roots' => true. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    percent: Optional[conint(ge=0, le=100)] = Field(
        None,
        description=(
            "Percent value if explicitly given (e.g., '30 percent'). Null if not stated."
        ),
    )
    describe: Optional[constr(max_length=30)] = Field(
        None,
        description=(
            "Compressed soil/rooting phrase (<=30 chars) preserving key context (e.g., "
            "'Compacted, 30% paved roots', 'Shallow, limited volume'). "
            "Prefer concise phrase, not a full sentence. Null if not stated."
        ),
    )


class CommonWeather(StrictBaseModel):
    strong_winds: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates strong winds are common/typical. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    ice: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates ice events are common/typical. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    snow: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates snow is common/typical. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    heavy_rain: Optional[bool] = Field(
        None,
        description=(
            "True if transcript indicates heavy rain is common/typical. "
            "False if explicitly denied. Null if not mentioned."
        ),
    )
    describe: Optional[constr(max_length=30)] = Field(
        None,
        description=(
            "Compressed weather exposure phrase (<=30 chars) preserving key context (e.g., "
            "'Strong winter winds, rain', 'Heavy rain + SW winds'). "
            "Prefer concise phrase, not a full sentence. Null if not stated."
        ),
    )


class SiteFactorsExtraction(StrictBaseModel):
    section_id: Literal["site_factors"] = Field(
        "site_factors",
        description="Section identifier for this extraction.",
    )
    history_of_failures: Optional[str] = Field(
        None,
        description=(
            "History of failures if stated (e.g., prior branch/root failure). "
            "Null if not mentioned."
        ),
    )
    topography: Topography = Field(
        ..., 
        description="Topography inferences based on transcript.",
    )
    site_changes: SiteChanges = Field(
        ..., 
        description="Site change inferences based on transcript.",
    )
    soil_conditions: SoilConditions = Field(
        ..., 
        description="Soil condition inferences based on transcript.",
    )
    prevailing_wind_direction: Optional[str] = Field(
        None,
        description=(
            "Prevailing wind direction as abbreviation only (e.g., N, S, E, W, NE, NW, SE, SW). "
            "Null if not mentioned."
        ),
    )
    common_weather: CommonWeather = Field(
        ..., 
        description="Common weather inferences based on transcript.",
    )

    @field_validator("prevailing_wind_direction", mode="before")
    @classmethod
    def _normalize_prevailing_wind_direction(cls, value: object) -> Optional[str]:
        if value in (None, ""):
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        text = text.replace("-", " ")
        compact = "".join(ch for ch in text if ch.isalpha())

        direct = {
            "n", "s", "e", "w", "ne", "nw", "se", "sw",
            "nne", "ene", "ese", "sse", "ssw", "wsw", "wnw", "nnw",
        }
        if compact in direct:
            return compact.upper()

        mapping = {
            "north": "N",
            "south": "S",
            "east": "E",
            "west": "W",
            "northeast": "NE",
            "northwest": "NW",
            "southeast": "SE",
            "southwest": "SW",
            "northnortheast": "NNE",
            "eastnortheast": "ENE",
            "eastsoutheast": "ESE",
            "southsoutheast": "SSE",
            "southsouthwest": "SSW",
            "westsouthwest": "WSW",
            "westnorthwest": "WNW",
            "northnorthwest": "NNW",
        }
        if compact in mapping:
            return mapping[compact]

        parts = [p for p in text.split() if p]
        if len(parts) == 2 and set(parts).issubset({"north", "south", "east", "west"}):
            first = parts[0][0].upper()
            second = parts[1][0].upper()
            if first in {"E", "W"} and second in {"N", "S"}:
                return f"{second}{first}"
            return f"{first}{second}"

        return str(value).strip().upper()
