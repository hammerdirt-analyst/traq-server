"""Overlay-based TRAQ PDF rendering utilities.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Render TRAQ form values into the PDF template using visual overlay geometry
    (`traq_full_map.json`) rather than AcroForm field names.

Backstory / rationale:
    The available TRAQ template has incomplete/inconsistent AcroForm metadata.
    Runtime filling therefore uses explicit box coordinates from the overlay
    mapping pipeline (`app/traq_2_schema/*`) to ensure every visual
    field can be addressed deterministically.

Coordinate system contract:
    - Mapping stores template-space pixels: `bbox_px = [x0, y0, x1, y1]`
    - Origin is top-left of the rendered overlay template
    - This module scales/transforms those coordinates into PDF page points
      before drawing text/check marks.

References:
    - `app/traq_2_schema/traq_full_map.json`
    - `app/traq_2_schema/build_traq_full_map.py`
    - `references/overlay_readme.md`
"""
from __future__ import annotations

from pathlib import Path
import json
from io import BytesIO
from typing import Any

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas


TRAQ_FULL_MAP = Path(__file__).resolve().parent / "traq_2_schema" / "traq_full_map.json"
MULTILINE_TOP_NUDGE_PT = -6
SINGLELINE_BASELINE_PAD_PT = 2
LINE_CHAR_LIMITS: dict[str, list[int]] = {
    "notes_explanations_descriptions.notes": [30, 60, 60, 60, 60],
}


def _get_json_path(data: dict[str, Any], path: str) -> Any:
    """Resolve dotted/list-indexed JSON paths from nested form payloads.

    Supports path segments like `targets[0].label`.
    Returns `None` for missing keys, invalid indices, or non-matching types.
    """
    if not path:
        return None
    current: Any = data
    for part in path.split("."):
        if not part:
            continue
        if "[" in part and part.endswith("]"):
            key, index_str = part[:-1].split("[", 1)
            try:
                index = int(index_str)
            except ValueError:
                return None
            if key:
                if not isinstance(current, dict):
                    return None
                current = current.get(key)
            if not isinstance(current, list):
                return None
            if index < 0 or index >= len(current):
                return None
            current = current[index]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _coerce_bool(value: Any) -> bool:
    """Normalize mixed boolean-like values into strict bool."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "on"}
    return bool(value)


def _format_value_for_path(json_path: str, value: Any) -> Any:
    """Apply path-specific output formatting before drawing.

    Adds quote markers for inch/foot fields where required by form convention.
    """
    if value is None:
        return None
    path = (json_path or "").strip()
    if path == "client_tree_details.dbh":
        text = str(value).strip()
        if not text:
            return None
        return text if '"' in text else f'{text}"'
    if path in {"client_tree_details.height", "client_tree_details.crown_spread_dia"}:
        text = str(value).strip()
        if not text:
            return None
        return text if "'" in text else f"{text}'"
    if path == "roots_and_root_collar.distance_from_trunk":
        text = str(value).strip()
        if not text:
            return None
        return text if "'" in text else f"{text}'"
    if path in {
        "crown_and_branches.dead_twigs_max_dia",
        "crown_and_branches.broken_hangers_max_dia",
        "trunk.cavity_nest_hole_depth",
        "roots_and_root_collar.collar_depth",
    }:
        text = str(value).strip()
        if not text:
            return None
        return text if '"' in text else f'{text}"'
    return value


def _parse_line_field_type(field_type: str) -> tuple[int, int] | None:
    """Parse multiline field markers.

    Accepted formats:
        - `line:<idx>`
        - `line:<idx>/<count>`
    """
    if not field_type.startswith("line:"):
        return None
    line_spec = field_type.split(":", 1)[1]
    try:
        if "/" in line_spec:
            idx_str, count_str = line_spec.split("/", 1)
            idx = int(idx_str)
            count = int(count_str)
        else:
            idx = int(line_spec)
            count = max(2, idx)
    except ValueError:
        return None
    if idx < 1 or count < 1:
        return None
    return idx, count


def _split_text_to_line_widths(
    c,
    text: str,
    line_widths: list[float],
    font_size: int,
) -> list[str]:
    """Split text across multiple visual lines by measured width.

    Notes:
        - Uses ReportLab string width measurement at the provided font size.
        - Last line carries remaining text; no truncation is performed here.
    """
    words = text.split()
    if not words or not line_widths:
        return ["" for _ in line_widths]

    lines: list[str] = []
    remaining = words[:]

    for i, width in enumerate(line_widths):
        if width <= 0:
            lines.append("")
            continue
        if not remaining:
            lines.append("")
            continue

        # Last line keeps remaining text (no truncation in pdf_fill).
        if i == len(line_widths) - 1:
            lines.append(" ".join(remaining))
            remaining = []
            continue

        current = remaining[0]
        consume = 1
        while consume < len(remaining):
            candidate = f"{current} {remaining[consume]}"
            if c.stringWidth(candidate, "Helvetica", font_size) <= width:
                current = candidate
                consume += 1
            else:
                break

        lines.append(current)
        remaining = remaining[consume:]

    return lines


def _split_text_to_char_limits(text: str, char_limits: list[int]) -> list[str]:
    """Split text by per-line character budget for designated fields.

    Used for fields where line budgets are contractual in the form layout
    (e.g., notes block first line shorter than subsequent lines).
    """
    words = text.split()
    if not words:
        return ["" for _ in char_limits]

    lines: list[str] = []
    remaining = words[:]
    for i, limit in enumerate(char_limits):
        if not remaining or limit <= 0:
            lines.append("")
            continue
        if i == len(char_limits) - 1:
            # Keep all remaining text on final line (no truncation in pdf_fill).
            candidate = " ".join(remaining)
            lines.append(candidate)
            remaining = []
            continue

        current = remaining[0]
        consume = 1
        while consume < len(remaining):
            candidate = f"{current} {remaining[consume]}"
            if len(candidate) <= limit:
                current = candidate
                consume += 1
            else:
                break
        lines.append(current[:limit].rstrip())
        remaining = remaining[consume:]
    return lines


def _draw_overlay(
    c: canvas.Canvas,
    page_width: float,
    page_height: float,
    render_size: list[int],
    fields: list[dict[str, Any]],
    form_data: dict[str, Any],
) -> None:
    """Render mapped values for a single PDF page overlay.

    Args:
        c: ReportLab canvas bound to the temporary overlay PDF stream.
        page_width: Target page width in PDF points.
        page_height: Target page height in PDF points.
        render_size: Source overlay render size `[width_px, height_px]`.
        fields: Mapping rows for the current page from `traq_full_map.json`.
        form_data: Form payload data (normalized shape).

    Behavior:
        - Checkbox fields draw `X` when value evaluates true/matches enum.
        - `line:x/y` fields use coordinated multiline splitting.
        - Other fields are treated as single-line and fit by shrinking font.
    """
    render_w, render_h = render_size
    scale_x = page_width / render_w
    scale_y = page_height / render_h

    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0, 0, 1)
    line_field_cache: dict[str, list[str]] = {}

    for entry in fields:
        bbox = entry.get("bbox_px")
        if not bbox:
            continue
        x0, y0, x1, y1 = bbox
        pdf_x0 = x0 * scale_x
        pdf_y1 = (render_h - y0) * scale_y
        pdf_x1 = x1 * scale_x
        pdf_y0 = (render_h - y1) * scale_y

        json_path = entry.get("json_path") or ""
        if not json_path:
            continue
        value = _get_json_path(form_data, json_path)
        value = _format_value_for_path(json_path, value)

        field_type = entry.get("type") or "text"
        parsed = _parse_line_field_type(field_type)
        if parsed is not None:
            idx, count = parsed
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            peer_entries: list[tuple[int, float]] = []
            for peer in fields:
                if peer.get("json_path") != json_path:
                    continue
                peer_type = str(peer.get("type") or "")
                peer_parsed = _parse_line_field_type(peer_type)
                if peer_parsed is None:
                    continue
                peer_idx, peer_count = peer_parsed
                if peer_count != count:
                    continue
                pb = peer.get("bbox_px")
                if not pb:
                    continue
                pw = max(0.0, (pb[2] - pb[0]) * scale_x - 4.0)
                peer_entries.append((peer_idx, pw))
            if not peer_entries:
                continue
            peer_entries.sort(key=lambda t: t[0])
            widths = [w for _, w in peer_entries]
            cache_key = f"{json_path}|{count}|{','.join(f'{w:.2f}' for w in widths)}|{text}"
            if cache_key not in line_field_cache:
                char_limits = LINE_CHAR_LIMITS.get(json_path)
                if char_limits and len(char_limits) == count:
                    line_field_cache[cache_key] = _split_text_to_char_limits(text, char_limits)
                else:
                    font_size = 10
                    c.setFont("Helvetica", font_size)
                    line_field_cache[cache_key] = _split_text_to_line_widths(c, text, widths, font_size)
            lines = line_field_cache[cache_key]
            if 1 <= idx <= len(lines):
                line_text = lines[idx - 1].strip()
                if line_text:
                    c.setFont("Helvetica", 10)
                    c.drawString(pdf_x0 + 2, pdf_y1 + MULTILINE_TOP_NUDGE_PT, line_text)
            continue
        if field_type == "checkbox":
            compare_value = entry.get("compare_value")
            is_checked = False
            if compare_value is not None:
                if isinstance(value, str):
                    is_checked = value.strip().lower() == str(compare_value).strip().lower()
            else:
                is_checked = _coerce_bool(value)
            if is_checked:
                cx = (pdf_x0 + pdf_x1) / 2.0
                cy = (pdf_y0 + pdf_y1) / 2.0
                c.drawString(cx - 3, cy - 3, "X")
            continue

        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        max_width = max(0, pdf_x1 - pdf_x0 - 4)
        # Non-line mapped fields are single-line by contract. Fit by shrinking font only.
        draw_size = 10
        for fs in (10, 9, 8, 7, 6, 5, 4):
            c.setFont("Helvetica", fs)
            if c.stringWidth(text, "Helvetica", fs) <= max_width:
                draw_size = fs
                break
        c.setFont("Helvetica", draw_size)
        c.drawString(pdf_x0 + 2, pdf_y0 + SINGLELINE_BASELINE_PAD_PT, text)


def generate_traq_pdf(
    *,
    form_data: dict[str, Any],
    output_path: Path,
    template_path: Path | None = None,
    flatten: bool = False,
) -> None:
    """Generate filled TRAQ PDF using overlay mapping for all pages.

    Args:
        form_data: Final/draft form payload. Supports top-level data or
            wrapped `{\"data\": ...}` payload shape.
        output_path: Output PDF path.
        template_path: Optional TRAQ template path override.
        flatten: Reserved compatibility parameter (current path is overlay-only).
    """
    template = template_path or (Path(__file__).resolve().parents[2] / "references" / "basic_traq_example.pdf")
    if not template.exists():
        raise RuntimeError(f"TRAQ template not found at {template}")
    reader = PdfReader(str(template))
    writer = PdfWriter()
    data = form_data.get("data") if isinstance(form_data.get("data"), dict) else form_data

    if not TRAQ_FULL_MAP.exists():
        raise RuntimeError(f"TRAQ full map not found at {TRAQ_FULL_MAP}")
    combined = json.loads(TRAQ_FULL_MAP.read_text(encoding="utf-8"))
    fields = combined.get("fields", [])
    render_sizes = {
        "1": combined.get("pages", {}).get("1", {}).get("render_size_px") or [1, 1],
        "2": combined.get("pages", {}).get("2", {}).get("render_size_px") or [1, 1],
    }

    for index, page in enumerate(reader.pages, start=1):
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)
        render_size = render_sizes.get(str(index), [1, 1])
        page_fields = [f for f in fields if f.get("page") == index]

        overlay_stream = BytesIO()
        c = canvas.Canvas(overlay_stream, pagesize=(page_width, page_height))
        _draw_overlay(
            c,
            page_width,
            page_height,
            render_size,
            page_fields,
            data,
        )
        c.save()
        overlay_stream.seek(0)
        overlay_reader = PdfReader(overlay_stream)
        page.merge_page(overlay_reader.pages[0])
        writer.add_page(page)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as f:
        writer.write(f)


def extract_pdf_field_values(pdf_path: Path) -> dict[str, str]:
    """Extract AcroForm values from a PDF for diagnostics/testing.

    This is a helper for inspection only. Runtime filling is overlay-based.
    """
    reader = PdfReader(str(pdf_path))
    try:
        fields = reader.get_fields() or {}
    except Exception:
        fields = {}
    values: dict[str, str] = {}
    if fields:
        for name, info in fields.items():
            val = info.get("/V")
            if val is None:
                continue
            values[name] = str(val)
        return values

    # Fallback: walk annotations to extract /T and /V directly.
    for page in reader.pages:
        annots = page.get("/Annots") or []
        if hasattr(annots, "get_object"):
            annots = annots.get_object()
        if not isinstance(annots, list):
            continue
        for annot_ref in annots:
            annot = annot_ref.get_object()
            name = annot.get("/T")
            val = annot.get("/V")
            if name is None or val is None:
                continue
            values[str(name)] = str(val)
    return values
