"""Shared extractor runtime primitives (schema + Outlines/OpenAI execution).

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Provide common extraction utilities used by all section extractors:
    - strict model base config (`StrictBaseModel`)
    - OpenAI schema normalization helper for Outlines compatibility
    - prompt assembly + model execution via Outlines/OpenAI

Dependencies:
    - `outlines` for structured generation wrapper
    - `openai` SDK for model invocation
    - `pydantic` for response-model validation
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Type, TypeVar

import outlines
from openai import OpenAI
from pydantic import BaseModel
from pydantic.config import ConfigDict


T = TypeVar("T", bound=BaseModel)


def _enforce_openai_schema(schema: dict[str, Any]) -> None:
    """Mutate JSON schema into OpenAI-compatible required-property form.

    OpenAI `response_format` requires every declared property key to appear in
    `required`. This helper recursively enforces that constraint for object
    schemas while preserving `$ref` nodes.
    """
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        ref = schema.get("$ref")
        schema.clear()
        schema["$ref"] = ref
        return
    if "properties" in schema and isinstance(schema["properties"], dict):
        schema["required"] = list(schema["properties"].keys())
        for value in schema["properties"].values():
            _enforce_openai_schema(value)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema and isinstance(schema[key], list):
            for subschema in schema[key]:
                _enforce_openai_schema(subschema)
    if "items" in schema:
        _enforce_openai_schema(schema["items"])
    if "$defs" in schema and isinstance(schema["$defs"], dict):
        for subschema in schema["$defs"].values():
            _enforce_openai_schema(subschema)
    if "definitions" in schema and isinstance(schema["definitions"], dict):
        for subschema in schema["definitions"].values():
            _enforce_openai_schema(subschema)


class StrictBaseModel(BaseModel):
    """Base model for all extractors with strict schema behavior.

    - Rejects unknown keys (`extra="forbid"`).
    - Applies `_enforce_openai_schema` before schema export.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_enforce_openai_schema,
    )


def _read_text(path: Path) -> str:
    """Read UTF-8 prompt file text and strip leading/trailing whitespace."""
    return path.read_text(encoding="utf-8").strip()


def run_outlines_extraction(
    *,
    transcript: str,
    model_cls: Type[T],
    system_path: Path,
    section_path: Path,
    logger,
    model_env: str = "TRAQ_OPENAI_MODEL",
    default_model: str = "gpt-4o-mini",
) -> T:
    """Run structured extraction for one section transcript.

    Args:
        transcript: Section transcript content (must be non-empty).
        model_cls: Pydantic model class for structured output.
        system_path: Path to system prompt text.
        section_path: Path to section prompt text.
        logger: Logger used for extraction diagnostics.
        model_env: Environment variable name containing model id.
        default_model: Fallback model id when `model_env` is unset.

    Returns:
        Parsed and validated `model_cls` instance.

    Raises:
        ValueError: Transcript is empty.
        RuntimeError: `OPENAI_API_KEY` is missing.
        Exception: Propagates model/parse errors after logging.
    """
    if not transcript.strip():
        raise ValueError("Transcript is empty")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    model = os.environ.get(model_env, default_model)

    system_prompt = _read_text(system_path)
    section_prompt = _read_text(section_path)

    prompt = (
        f"{system_prompt}\n\n"
        f"Section instructions:\n{section_prompt}\n\n"
        f"Transcript:\n{transcript}\n"
    )

    client = OpenAI(api_key=api_key)
    fn = outlines.from_openai(client, model)
    response = fn(prompt, model_cls)

    if isinstance(response, model_cls):
        logger.info("Outlines parsed response.")
        return response

    raw_text = response if isinstance(response, str) else json.dumps(response)
    logger.info("Outlines raw response: %s", raw_text)
    try:
        return model_cls.model_validate_json(raw_text)
    except Exception:
        logger.exception("Failed to parse Outlines response JSON")
        logger.info("Raw response JSON: %s", raw_text)
        raise
