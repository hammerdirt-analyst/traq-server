#!/usr/bin/env python3
"""Build the canonical TRAQ overlay mapping used at runtime.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Compiles the page-level visual overlay templates and the human-curated
    mapping specs (`mapone.md`, `maptwo.md`) into one canonical
    `traq_full_map.json` used by `server/app/pdf_fill.py`.

Backstory / design rationale:
    The TRAQ PDF copy used in this project has incomplete/inconsistent AcroForm
    fields. To avoid silent placement gaps, the runtime fill path is based on
    visual overlay boxes (pixel coordinates) rather than AcroForm names.
    This builder is the bridge from:
    - visual geometry (overlay JSONs with box IDs + bounding boxes), and
    - semantic mapping (markdown files mapping box IDs to JSON paths/types)
    into a single runtime map.

Coordinate system:
    - `bbox_px` values are template-render pixel coordinates from overlay JSON.
    - Origin is top-left of the rendered template page.
    - Values are stored as `[x0, y0, x1, y1]` in that same pixel space.
    - Downstream rendering (`pdf_fill.py`) scales these into PDF points per page.

References:
    - `references/overlay_readme.md`
    - `references/docs/IMPLEMENTATION_PLAN_2026-02-11.md`
    - `server/app/traq_2_schema/overlay_page1.json`
    - `server/app/traq_2_schema/overlay_page2.json`
    - `server/app/traq_2_schema/mapone.md`
    - `server/app/traq_2_schema/maptwo.md`
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIR = Path(__file__).resolve().parent


def _read_json(path: Path) -> dict:
    """Read and parse a UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_mapone(path: Path) -> list[dict]:
    """Parse page-1 semantic mapping (`mapone.md`) into normalized entries.

    Args:
        path: Path to `mapone.md`.

    Returns:
        List of mapping rows with keys:
        `box_id`, `json_path`, `type`, and optional `compare_value`.

    Notes:
        Handles special rules:
        - target index scoping for `target_assessment.targets[i]`
        - enum checkbox compare values for specific paths
        - multiline continuation fields (`main_concerns` line 1/2)
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    mappings = []
    section_id = None
    target_index = None
    prefix = ""

    number_line = re.compile(r'^(\d+)\.\s*"([^"]+)"\s*:\s*([^,]+)')
    quoted_value = re.compile(r'"([^"]+)"')

    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith('"section_id"'):
            match = quoted_value.search(raw)
            section_id = match.group(1) if match else None
            prefix = ""
            target_index = None
            continue
        if raw.startswith('"section id"'):
            match = quoted_value.search(raw)
            section_id = match.group(1) if match else None
            prefix = ""
            target_index = None
            continue
        if raw.startswith("section_id:"):
            section_id = raw.split("section_id:", 1)[1].strip() or None
            prefix = ""
            target_index = None
            continue
        if raw.startswith('"targets_number'):
            match = re.search(r"\[(\d+)\]", raw)
            target_index = int(match.group(1)) if match else 0
            prefix = "target_assessment.targets"
            continue
        if (
            raw.startswith('"site_factors.')
            or raw.startswith('"tree_health_and_species.')
            or raw.startswith('"load_factors.')
            or raw.startswith('"crown_and_branches.')
            or raw.startswith('"trunk.')
            or raw.startswith('"roots_and_root_collar.')
        ):
            match = quoted_value.search(raw)
            prefix = match.group(1) if match else raw.strip('":')
            continue
        if raw in {
            "site_factors",
            "tree_health_and_species",
            "load_factors",
            "crown_and_branches",
            "trunk",
            "roots_and_root_collar",
        }:
            prefix = raw
            continue

        match = number_line.match(raw)
        if not match or not section_id:
            continue
        box_id = int(match.group(1))
        field = match.group(2)
        raw_type = match.group(3).strip().lower() if match.group(3) else ""
        if raw_type == "tet":
            raw_type = "text"

        enum_paths = {
            "tree_health_and_species.vigor",
            "load_factors.wind_exposure",
            "load_factors.relative_crown_size",
            "load_factors.crown_density",
            "load_factors.interior_branches_density",
            "crown_and_branches.load_on_defect",
            "crown_and_branches.likelihood_of_failure",
            "trunk.load_on_defect",
            "trunk.likelihood_of_failure",
            "roots_and_root_collar.load_on_defect",
            "roots_and_root_collar.likelihood_of_failure",
        }

        if "." in field:
            json_path = field
        elif section_id == "client_tree_details":
            json_path = f"client_tree_details.{field}"
        elif section_id == "target_assessment":
            idx = target_index if target_index is not None else 0
            json_path = f"target_assessment.targets[{idx}].{field}"
        elif section_id == "site_factors":
            json_path = f"{prefix}.{field}" if prefix.startswith("site_factors.") else f"site_factors.{field}"
        elif section_id == "tree_health_and_species":
            if prefix.startswith("tree_health_and_species."):
                json_path = prefix if prefix in enum_paths else f"{prefix}.{field}"
            else:
                json_path = f"tree_health_and_species.{field}"
        elif section_id == "load_factors":
            if prefix.startswith("load_factors."):
                json_path = prefix if prefix in enum_paths else f"{prefix}.{field}"
            else:
                json_path = f"load_factors.{field}"
        elif section_id == "crown_and_branches":
            if prefix.startswith("crown_and_branches."):
                json_path = prefix if prefix in enum_paths else f"{prefix}.{field}"
            else:
                json_path = f"crown_and_branches.{field}"
        elif section_id == "trunk":
            if prefix.startswith("trunk."):
                json_path = prefix if prefix in enum_paths else f"{prefix}.{field}"
            else:
                json_path = f"trunk.{field}"
        elif section_id == "roots_and_root_collar":
            if prefix.startswith("roots_and_root_collar."):
                json_path = prefix if prefix in enum_paths else f"{prefix}.{field}"
            else:
                json_path = f"roots_and_root_collar.{field}"
        else:
            json_path = f"{section_id}.{field}"

        map_type = raw_type
        if section_id in {"crown_and_branches", "trunk", "roots_and_root_collar"}:
            if field == "main_concerns":
                map_type = "line:1"
            elif field in {"main_concerns_line_2", "main_concerns_2"}:
                json_path = f"{section_id}.main_concerns"
                map_type = "line:2"
        entry = {
            "box_id": box_id,
            "json_path": json_path,
            "type": map_type,
        }
        if raw_type == "checkbox" and prefix in enum_paths:
            entry["compare_value"] = field
        mappings.append(entry)
    return mappings


def _parse_maptwo(path: Path) -> list[dict]:
    """Parse page-2 semantic mapping (`maptwo.md`) into normalized entries.

    Args:
        path: Path to `maptwo.md`.

    Returns:
        List of mapping rows with keys:
        `box_id`, `json_path`, `type`, `section_id`, and optional
        `compare_value`.

    Notes:
        Handles special rules:
        - line-indexed notes field (`line:1/5`..`line:5/5`)
        - enum-to-checkbox expansion for single-select groups
        - risk-categorization matrix compare-value mapping
    """
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    mappings = []
    section_id = None
    block_prefix = None
    notes_line_index = 0
    enum_block_map = {
        "overall_tree_risk_rating": "overall_tree_risk_rating.rating",
        "overall_residual_risk": "overall_residual_risk.rating",
        "work_priority": "work_priority.priority",
        "data_status": "data_status.status",
        "advanced_assessment_needed": "advanced_assessment_needed.needed",
    }

    number_line = re.compile(r'^(\d+)\.\s*"([^"]+)"\s*:\s*([^,]+)')
    block_line = re.compile(r'^"([^"]+)"\s*:\s*$')

    for raw in lines:
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith("section_id:"):
            section_id = raw.split("section_id:", 1)[1].strip() or None
            continue
        block_match = block_line.match(raw)
        if block_match:
            block_prefix = block_match.group(1)
            if block_prefix == "notes_explanations_descriptions":
                notes_line_index = 0
            continue
        match = number_line.match(raw)
        if not match or not section_id:
            continue
        box_id = int(match.group(1))
        field = match.group(2)
        raw_type = match.group(3).strip().lower() if match.group(3) else ""
        if raw_type == "tet":
            raw_type = "text"
        if raw_type.startswith("enum["):
            raw_type = "enum"
        if block_prefix:
            if block_prefix.startswith("mitigation_options["):
                idx = block_prefix.split("[", 1)[1].split("]", 1)[0]
                json_path = f"mitigation_options.options[{idx}].{field}"
            else:
                json_path = f"{block_prefix}.{field}"
        else:
            json_path = field
        map_type = raw_type
        compare_value = None
        if block_prefix == "notes_explanations_descriptions" and field == "notes":
            notes_line_index += 1
            map_type = f"line:{notes_line_index}/5"
            json_path = "notes_explanations_descriptions.notes"
        if raw_type == "checkbox" and block_prefix in enum_block_map:
            json_path = enum_block_map[block_prefix]
            compare_value = field
        if raw_type == "checkbox" and block_prefix and block_prefix.startswith("risk_categorization[") and "." in field:
            head, tail = field.split(".", 1)
            json_path = f"{block_prefix}.{head}"
            compare_value = tail
        if raw_type == "enum":
            if block_prefix and block_prefix.startswith("mitigation_options[") and field == "residual_risk":
                map_type = "text"
            else:
                map_type = "checkbox"
                if block_prefix in enum_block_map:
                    json_path = enum_block_map[block_prefix]
                compare_value = field
        entry = {
            "box_id": box_id,
            "json_path": json_path,
            "type": map_type,
            "section_id": section_id,
        }
        if compare_value is not None:
            entry["compare_value"] = compare_value
        mappings.append(entry)
    return mappings


def _index_overlay(overlay: dict) -> dict[int, dict]:
    """Create a box-id index from an overlay JSON payload."""
    index = {}
    for el in overlay.get("elements", []):
        if "id" not in el:
            continue
        index[int(el["id"])] = el
    return index


def main() -> None:
    """Build and write the canonical merged TRAQ overlay map.

    Flow:
        1) Read page overlay geometry JSON files.
        2) Parse semantic mappings from `mapone.md` and `maptwo.md`.
        3) Join rows by `box_id` to attach `bbox_px`.
        4) Emit merged payload with page metadata and missing-ID diagnostics.
    """
    parser = argparse.ArgumentParser(description="Build combined TRAQ map with box coords and json paths.")
    parser.add_argument(
        "--page1-overlay",
        type=Path,
        default=SCHEMA_DIR / "overlay_page1.json",
        help="Page 1 overlay JSON",
    )
    parser.add_argument(
        "--page2-overlay",
        type=Path,
        default=SCHEMA_DIR / "overlay_page2.json",
        help="Page 2 overlay JSON",
    )
    parser.add_argument(
        "--mapone",
        type=Path,
        default=SCHEMA_DIR / "mapone.md",
        help="mapone.md",
    )
    parser.add_argument(
        "--maptwo",
        type=Path,
        default=SCHEMA_DIR / "maptwo.md",
        help="maptwo.md",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=SCHEMA_DIR / "traq_full_map.json",
        help="Output combined map JSON",
    )
    args = parser.parse_args()

    page1 = _read_json(args.page1_overlay)
    page2 = _read_json(args.page2_overlay)
    page1_index = _index_overlay(page1)
    page2_index = _index_overlay(page2)

    page1_fields = _parse_mapone(args.mapone)
    page2_fields = _parse_maptwo(args.maptwo)

    combined_fields = []
    missing = []

    for entry in page1_fields:
        box_id = entry["box_id"]
        el = page1_index.get(box_id)
        if not el:
            missing.append({"page": 1, **entry})
            continue
        combined_fields.append(
            {
                "page": 1,
                "box_id": box_id,
                "bbox_px": el.get("bbox_px"),
                "json_path": entry["json_path"],
                "type": entry["type"],
                "compare_value": entry.get("compare_value"),
            }
        )

    for entry in page2_fields:
        box_id = entry["box_id"]
        el = page2_index.get(box_id)
        if not el:
            missing.append({"page": 2, **entry})
            continue
        combined_fields.append(
            {
                "page": 2,
                "box_id": box_id,
                "bbox_px": el.get("bbox_px"),
                "json_path": entry["json_path"],
                "type": entry["type"],
                "section_id": entry.get("section_id"),
                "compare_value": entry.get("compare_value"),
            }
        )

    payload = {
        "pages": {
            "1": {"render_size_px": page1.get("render_size_px"), "source": str(args.page1_overlay)},
            "2": {"render_size_px": page2.get("render_size_px"), "source": str(args.page2_overlay)},
        },
        "fields": combined_fields,
        "missing": missing,
    }

    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote combined map: {args.out}")
    if missing:
        print(f"Missing {len(missing)} box ids (see 'missing' in output).")


if __name__ == "__main__":
    main()
