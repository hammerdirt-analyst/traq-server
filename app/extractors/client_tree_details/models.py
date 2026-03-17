"""Structured schema for the ``client_tree_details`` extractor.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Defines the validated response contract used by the extractor
    registry for the ``client_tree_details`` section.

Dependencies:
    - pydantic.Field (and constrained types where needed) for field
      metadata and schema generation
    - ``StrictBaseModel`` for strict validation and OpenAI schema
      compatibility rules

Notes:
    This model is consumed by ``app.extractors.registry.run_extraction``
    and merged into draft/final form payloads by server round/final flows.
"""
import re
from typing import Literal, Optional

from pydantic import Field, field_validator

from ..common import StrictBaseModel


class ClientTreeDetailsExtraction(StrictBaseModel):
    section_id: Literal["client_tree_details"] = Field(
        "client_tree_details",
        description="Section identifier for this extraction.",
    )
    client: Optional[str] = Field(
        None,
        description="Client/customer name as stated. Null if not stated.",
    )
    date: Optional[str] = Field(
        None,
        description="Assessment date as stated (verbatim). Null if not stated.",
    )
    time: Optional[str] = Field(
        None,
        description="Assessment time as stated (verbatim). Null if not stated.",
    )
    address_tree_location: Optional[str] = Field(
        None,
        description="Address or tree location details as stated. Null if not stated.",
    )
    tree_number: Optional[int] = Field(
        None,
        description="Tree number as digits only (e.g., 1, 27). Null if not stated.",
    )
    sheet: Optional[int] = Field(
        None,
        description="Sheet number as digits only (e.g., 1, 2). Null if not stated.",
    )
    of: Optional[int] = Field(
        None,
        description="Total sheet count in 'sheet X of Y', digits only (e.g., 3). Null if not stated.",
    )
    tree_species: Optional[str] = Field(
        None,
        description="Tree species as stated. Null if not stated.",
    )
    dbh: Optional[int] = Field(
        None,
        description="DBH in inches as digits only (e.g., 52). Null if not stated.",
    )
    height: Optional[int] = Field(
        None,
        description="Height in feet as digits only (e.g., 38). Null if not stated.",
    )
    crown_spread_dia: Optional[int] = Field(
        None,
        description="Crown spread diameter in feet as digits only (e.g., 42). Null if not stated.",
    )
    assessors: Optional[str] = Field(
        None,
        description="Assessor(s) names as stated. Null if not stated.",
    )
    time_frame: Optional[str] = Field(
        None,
        description="Time frame or inspection window as stated. Null if not stated.",
    )
    tools_used: Optional[str] = Field(
        None,
        description="Tools used as stated. Null if not stated.",
    )

    @staticmethod
    def _word_to_int(text: str) -> Optional[int]:
        ones = {
            "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
            "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
            "nineteen": 19,
        }
        tens = {
            "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
            "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
        }
        scales = {"hundred": 100, "thousand": 1000}

        tokens = [t for t in re.split(r"[\s-]+", text.lower().strip()) if t and t != "and"]
        if not tokens:
            return None

        total = 0
        current = 0
        used = False
        for token in tokens:
            if token in ones:
                current += ones[token]
                used = True
            elif token in tens:
                current += tens[token]
                used = True
            elif token in scales:
                if current == 0:
                    current = 1
                current *= scales[token]
                if token == "thousand":
                    total += current
                    current = 0
                used = True
            else:
                return None
        if not used:
            return None
        return total + current

    @classmethod
    def _coerce_int_field(cls, value: object) -> Optional[int]:
        if value in (None, ""):
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        match = re.search(r"\d+", text)
        if match:
            return int(match.group(0))
        cleaned = re.sub(
            r"\b(tree|number|no|num|sheet|of)\b|[^\w\s-]",
            " ",
            text.lower(),
        )
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cls._word_to_int(cleaned)

    @field_validator("tree_number", "sheet", "of", "dbh", "height", "crown_spread_dia", mode="before")
    @classmethod
    def _normalize_int_fields(cls, value: object) -> Optional[int]:
        return cls._coerce_int_field(value)
