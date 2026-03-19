"""Form normalization and section-merge helpers for round review assembly."""

from __future__ import annotations

from typing import Any


class ReviewFormService:
    """Own normalization and merge rules for review form payloads."""

    @staticmethod
    def _merge_optional_str(
        existing: str | None,
        incoming: str | None,
        *,
        append: bool = False,
    ) -> str | None:
        """Merge scalar text values with preserve/append behavior."""
        if incoming is None or incoming == "":
            return existing
        if existing is None or existing == "":
            return incoming
        if append and incoming not in existing:
            return f"{existing} {incoming}".strip()
        return existing

    @staticmethod
    def _merge_optional_notes(
        existing: str | None,
        incoming: str | None,
    ) -> str | None:
        """Merge freeform notes preserving prior content."""
        if incoming is None or incoming == "":
            return existing
        if existing is None or existing == "":
            return incoming
        if incoming in existing:
            return existing
        return f"{existing}\n\n{incoming}".strip()

    @staticmethod
    def _cap_text(value: str | None, limit: int) -> str | None:
        """Cap text length at word boundary for field constraints."""
        if value is None:
            return None
        text = " ".join(str(value).split())
        if len(text) <= limit:
            return text
        clipped = text[:limit].rstrip()
        if " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        return clipped

    def merge_flat_section(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge flat section payloads while preserving non-empty existing values."""
        merged = dict(existing)
        if "section_id" in incoming:
            merged["section_id"] = incoming.get("section_id")
        for key, value in incoming.items():
            if key == "section_id":
                continue
            if key not in merged:
                merged[key] = value
                continue
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    def merge_notes_explanations_descriptions(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge notes section with append/cap rules."""
        merged = dict(existing)
        merged["section_id"] = incoming.get(
            "section_id",
            "notes_explanations_descriptions",
        )
        merged_notes = self._merge_optional_notes(
            merged.get("notes"),
            incoming.get("notes"),
        )
        merged["notes"] = self._cap_text(merged_notes, 230)
        return merged

    def merge_mitigation_options(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge mitigation option rows without duplication."""
        merged = dict(existing)
        merged["section_id"] = incoming.get("section_id", "mitigation_options")
        existing_rows = merged.get("options")
        if not isinstance(existing_rows, list):
            existing_rows = []
        existing_rows = [dict(row) for row in existing_rows if isinstance(row, dict)]

        incoming_rows = incoming.get("options")
        if not isinstance(incoming_rows, list):
            incoming_rows = []
        incoming_rows = [dict(row) for row in incoming_rows if isinstance(row, dict)]

        def _row_has_values(row: dict[str, Any]) -> bool:
            return any(value not in (None, "") for value in row.values())

        def _row_key(row: dict[str, Any]) -> tuple[str | None, str | None]:
            return (
                (row.get("option") or "").strip() or None,
                (row.get("residual_risk") or "").strip() or None,
            )

        existing_keys = {_row_key(row) for row in existing_rows if _row_has_values(row)}
        for incoming_row in incoming_rows:
            if not _row_has_values(incoming_row):
                continue
            key = _row_key(incoming_row)
            if key in existing_keys:
                continue
            existing_rows.append(incoming_row)
            existing_keys.add(key)
            if len(existing_rows) >= 4:
                break

        merged["options"] = existing_rows
        return merged

    def apply_form_patch(
        self,
        base_form: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        """Recursively apply one client patch onto a draft form payload."""
        merged: dict[str, Any] = dict(base_form or {})
        for key, value in patch.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self.apply_form_patch(
                    dict(merged.get(key) or {}),
                    dict(value),
                )
            else:
                merged[key] = value
        return merged

    def normalize_form_schema(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize form payload to the expected canonical schema."""
        normalized = dict(data or {})

        site = normalized.get("site_factors")
        if isinstance(site, dict):
            site_obj = dict(site)
            site_changes = site_obj.get("site_changes")
            site_changes_obj = dict(site_changes) if isinstance(site_changes, dict) else {}
            legacy_landscape = site_obj.pop("landscape_environment", None)
            if (
                site_changes_obj.get("landscape_environment") in (None, "")
                and legacy_landscape not in (None, "")
            ):
                site_changes_obj["landscape_environment"] = legacy_landscape
            site_changes_obj.pop("describe", None)
            site_changes_obj.setdefault("landscape_environment", None)
            site_obj["site_changes"] = site_changes_obj
            normalized["site_factors"] = site_obj

        recommended = normalized.get("recommended_inspection_interval")
        if isinstance(recommended, dict):
            rec_obj = dict(recommended)
            if rec_obj.get("text") in (None, "") and rec_obj.get("interval") not in (None, ""):
                rec_obj["text"] = rec_obj.get("interval")
            rec_obj.pop("interval", None)
            rec_obj.setdefault("text", None)
            normalized["recommended_inspection_interval"] = rec_obj

        crown = normalized.get("crown_and_branches")
        if isinstance(crown, dict):
            crown_obj = dict(crown)
            crown_obj.setdefault("cracks_notes", None)
            normalized["crown_and_branches"] = crown_obj

        return normalized

    def merge_site_factors(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Merge site-factors payloads while preserving non-empty existing values."""
        merged = dict(existing)
        for key in ("history_of_failures", "prevailing_wind_direction", "notes"):
            if key not in merged:
                merged[key] = incoming.get(key)
                continue
            merged[key] = self._merge_optional_str(
                merged.get(key),
                incoming.get(key),
                append=key == "notes",
            )
        for group_key, describe_key in (
            ("site_changes", None),
            ("soil_conditions", "describe"),
            ("common_weather", "describe"),
        ):
            base_group = dict(merged.get(group_key) or {})
            incoming_group = incoming.get(group_key) or {}
            if (
                group_key == "site_changes"
                and "landscape_environment" not in incoming_group
                and incoming.get("landscape_environment") not in (None, "")
            ):
                incoming_group = dict(incoming_group)
                incoming_group["landscape_environment"] = incoming.get("landscape_environment")
            if group_key == "site_changes":
                base_group.pop("describe", None)
                if isinstance(incoming_group, dict):
                    incoming_group = dict(incoming_group)
                    incoming_group.pop("describe", None)
            for key, value in incoming_group.items():
                if key not in base_group:
                    base_group[key] = value
                    continue
                if describe_key is not None and key == describe_key:
                    base_group[key] = self._merge_optional_str(
                        base_group.get(key),
                        value,
                        append=True,
                    )
                elif base_group.get(key) is None and value is not None:
                    base_group[key] = value
            merged[group_key] = base_group

        topography = dict(merged.get("topography") or {})
        incoming_topo = incoming.get("topography") or {}
        for key, value in incoming_topo.items():
            if key not in topography:
                topography[key] = value
                continue
            if topography.get(key) is None and value is not None:
                topography[key] = value
        merged["topography"] = topography
        return merged

    def merge_client_tree_details(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge client/tree details while preserving non-empty values."""
        return self.merge_flat_section(existing, incoming)

    def merge_target_assessment(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge target assessment rows while preserving prior values."""
        merged = dict(existing)
        merged["section_id"] = incoming.get("section_id", "target_assessment")

        existing_targets = merged.get("targets")
        if not isinstance(existing_targets, list):
            existing_targets = []
        existing_targets = [dict(item) for item in existing_targets if isinstance(item, dict)]

        incoming_targets = incoming.get("targets")
        if not isinstance(incoming_targets, list):
            incoming_targets = []
        incoming_targets = [dict(item) for item in incoming_targets if isinstance(item, dict)]

        for idx, incoming_target in enumerate(incoming_targets):
            if idx < len(existing_targets):
                base = dict(existing_targets[idx])
                for key, value in incoming_target.items():
                    if base.get(key) not in (None, ""):
                        continue
                    if value not in (None, ""):
                        base[key] = value
                existing_targets[idx] = base
            else:
                existing_targets.append(incoming_target)

        merged["targets"] = existing_targets
        return merged

    def merge_tree_health_and_species(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge tree health/species payloads."""
        return self._merge_nested_section(existing, incoming)

    def merge_load_factors(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge load-factor payloads."""
        return self.merge_flat_section(existing, incoming)

    def merge_crown_and_branches(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge crown-and-branches payloads."""
        return self._merge_nested_section(existing, incoming)

    def merge_trunk(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Merge trunk findings."""
        return self.merge_flat_section(existing, incoming)

    def merge_roots_and_root_collar(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge roots/root-collar findings."""
        return self.merge_flat_section(existing, incoming)

    def _merge_nested_section(
        self,
        existing: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        """Merge one section that contains nested groups."""
        merged = dict(existing)
        for key, value in incoming.items():
            if key == "section_id":
                merged[key] = value
                continue
            if isinstance(value, dict):
                base_group = dict(merged.get(key) or {})
                for subkey, subval in value.items():
                    if subkey not in base_group:
                        base_group[subkey] = subval
                    elif base_group.get(subkey) in (None, "") and subval not in (None, ""):
                        base_group[subkey] = subval
                merged[key] = base_group
                continue
            if key not in merged:
                merged[key] = value
            elif merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged
