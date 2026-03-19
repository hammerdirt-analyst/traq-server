"""Round processing orchestration for review payload generation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable


class RoundProcessingService:
    """Own round transcript/extraction/review assembly behavior."""

    def __init__(
        self,
        *,
        db_store: Any,
        review_form_service: Any,
        review_payload_service: Any,
        build_section_transcript: Callable[..., tuple[str, list[str], list[dict[str, Any]]]],
        load_latest_review: Callable[[str, str | None], dict[str, Any]],
        run_extraction_logged: Callable[[str, str], Any],
        generate_summary: Callable[..., str],
        save_round_record: Callable[..., None],
        logger: Any,
        narrative_paragraphs_supplier: Callable[[], list[str]] | None = None,
    ) -> None:
        """Bind runtime collaborators for one app instance."""
        self._db_store = db_store
        self._review_form_service = review_form_service
        self._review_payload_service = review_payload_service
        self._build_section_transcript = build_section_transcript
        self._load_latest_review = load_latest_review
        self._run_extraction_logged = run_extraction_logged
        self._generate_summary = generate_summary
        self._save_round_record = save_round_record
        self._logger = logger
        self._narrative_paragraphs_supplier = narrative_paragraphs_supplier or (lambda: [])

    def process_round(
        self,
        job_id: str,
        round_id: str,
        record: Any,
        base_review_override: dict[str, Any] | None = None,
        manifest_override: list[dict[str, Any]] | None = None,
        force_reprocess: bool = False,
        force_transcribe: bool = False,
    ) -> dict[str, Any]:
        """Process one round into the canonical review payload."""
        round_record = record.rounds[round_id]
        manifest = manifest_override if manifest_override is not None else round_record.manifest
        section_ids = sorted({item.get("section_id") for item in manifest if item.get("section_id")})
        issue_ids_by_section: dict[str, set[str]] = {}
        for item in manifest:
            section_id = item.get("section_id")
            issue_id = item.get("issue_id")
            if section_id and issue_id:
                issue_ids_by_section.setdefault(str(section_id), set()).add(str(issue_id))

        base_review = (
            base_review_override
            if base_review_override is not None
            else self._load_latest_review(job_id, exclude_round_id=round_id)
        )
        section_recordings: dict[str, list[str]] = dict(base_review.get("section_recordings") or {})
        delta_transcripts: dict[str, str] = {}
        transcription_failures: list[dict[str, Any]] = []

        for section_id in section_ids:
            seen = set(section_recordings.get(section_id) or [])
            transcript, used, failures = self._build_section_transcript(
                job_id,
                round_id,
                section_id,
                manifest,
                seen_recordings=seen,
                force_reprocess=force_reprocess,
                force_transcribe=force_transcribe,
            )
            delta_transcripts[section_id] = transcript
            if failures:
                transcription_failures.extend(failures)
            if used:
                section_recordings[section_id] = list(seen.union(used))

        earliest_recorded_at = self._earliest_recorded_at(manifest)
        base_form = base_review.get("draft_form") or {}
        draft_form: dict[str, Any] = {
            "schema_name": base_form.get("schema_name", "demo"),
            "schema_version": base_form.get("schema_version", "0.0"),
            "data": self._review_form_service.normalize_form_schema(dict(base_form.get("data") or {})),
        }
        section_transcripts: dict[str, str] = dict(base_review.get("section_transcripts") or {})
        issue_transcripts: dict[str, dict[str, str]] = dict(base_review.get("issue_transcripts") or {})
        issue_recordings: dict[str, dict[str, list[str]]] = dict(base_review.get("issue_recordings") or {})

        self._merge_section_extractions(
            draft_form=draft_form,
            delta_transcripts=delta_transcripts,
            earliest_recorded_at=earliest_recorded_at,
        )
        self._merge_section_transcripts(section_transcripts, delta_transcripts)
        self._merge_issue_transcripts(
            job_id=job_id,
            round_id=round_id,
            section_ids=section_ids,
            issue_ids_by_section=issue_ids_by_section,
            manifest=manifest,
            issue_recordings=issue_recordings,
            issue_transcripts=issue_transcripts,
            transcription_failures=transcription_failures,
            force_reprocess=force_reprocess,
            force_transcribe=force_transcribe,
        )
        self._merge_risk_categorization(
            draft_form=draft_form,
            delta_transcripts=delta_transcripts,
            issue_transcripts=issue_transcripts,
        )

        combined_transcript = self._combined_transcript(section_transcripts)
        try:
            narrative = self._generate_summary(
                form_data=draft_form.get("data", {}),
                transcript=combined_transcript,
            )
        except Exception:
            self._logger.exception("Failed to generate summary narrative")
            narrative = "\n\n".join(self._narrative_paragraphs_supplier())

        normalized_data = self._review_form_service.normalize_form_schema(draft_form.get("data") or {})
        client_tree_details = dict(normalized_data.get("client_tree_details") or {})
        if record.tree_number is not None:
            client_tree_details["tree_number"] = str(record.tree_number)
            normalized_data["client_tree_details"] = client_tree_details
        draft_form["data"] = normalized_data
        review_payload = {
            "round_id": round_id,
            "server_revision_id": round_record.server_revision_id,
            "transcript": combined_transcript,
            "section_recordings": section_recordings,
            "section_transcripts": section_transcripts,
            "issue_recordings": issue_recordings,
            "issue_transcripts": issue_transcripts,
            "draft_form": draft_form,
            "draft_narrative": narrative,
            "form": normalized_data,
            "narrative": narrative,
            "tree_number": record.tree_number,
            "images": self._review_payload_service.build_round_images(
                self._db_store.list_round_images(job_id, round_id)
            ),
            "transcription_failures": transcription_failures,
        }
        self._logger.info(
            "[ROUND] job=%s round=%s sections=%s transcript_sections=%s failures=%s",
            job_id,
            round_id,
            len(section_ids),
            len([section for section, text in section_transcripts.items() if text]),
            len(transcription_failures),
        )
        self._save_round_record(job_id, round_record, review_payload=review_payload)
        return review_payload

    @staticmethod
    def _earliest_recorded_at(manifest: list[dict[str, Any]]) -> datetime | None:
        earliest_recorded_at: datetime | None = None
        for item in manifest:
            if item.get("kind") != "recording":
                continue
            recorded_raw = item.get("recorded_at")
            if not recorded_raw:
                continue
            try:
                recorded_dt = datetime.fromisoformat(recorded_raw)
            except ValueError:
                continue
            if earliest_recorded_at is None or recorded_dt < earliest_recorded_at:
                earliest_recorded_at = recorded_dt
        return earliest_recorded_at

    def _merge_section_extractions(
        self,
        *,
        draft_form: dict[str, Any],
        delta_transcripts: dict[str, str],
        earliest_recorded_at: datetime | None,
    ) -> None:
        merge_map = {
            "site_factors": self._review_form_service.merge_site_factors,
            "tree_health_and_species": self._review_form_service.merge_tree_health_and_species,
            "load_factors": self._review_form_service.merge_load_factors,
            "crown_and_branches": self._review_form_service.merge_crown_and_branches,
            "trunk": self._review_form_service.merge_trunk,
            "roots_and_root_collar": self._review_form_service.merge_roots_and_root_collar,
            "target_assessment": self._review_form_service.merge_target_assessment,
            "notes_explanations_descriptions": self._review_form_service.merge_notes_explanations_descriptions,
            "mitigation_options": self._review_form_service.merge_mitigation_options,
            "overall_tree_risk_rating": self._review_form_service.merge_flat_section,
            "work_priority": self._review_form_service.merge_flat_section,
            "overall_residual_risk": self._review_form_service.merge_flat_section,
            "recommended_inspection_interval": self._review_form_service.merge_flat_section,
            "data_status": self._review_form_service.merge_flat_section,
            "advanced_assessment_needed": self._review_form_service.merge_flat_section,
            "advanced_assessment_type_reason": self._review_form_service.merge_flat_section,
            "inspection_limitations": self._review_form_service.merge_flat_section,
            "inspection_limitations_describe": self._review_form_service.merge_flat_section,
        }
        for section_id, merger in merge_map.items():
            transcript = delta_transcripts.get(section_id)
            if not isinstance(transcript, str) or not transcript.strip():
                continue
            extraction = self._run_extraction_logged(section_id, transcript)
            prior = draft_form["data"].get(section_id) or {}
            draft_form["data"][section_id] = merger(prior, extraction.model_dump())

        transcript = delta_transcripts.get("client_tree_details")
        if isinstance(transcript, str) and transcript.strip():
            extraction = self._run_extraction_logged("client_tree_details", transcript)
            details = extraction.model_dump()
            if earliest_recorded_at is not None:
                details.setdefault("date", earliest_recorded_at.strftime("%Y-%m-%d"))
                details.setdefault("time", earliest_recorded_at.strftime("%H:%M"))
            prior = draft_form["data"].get("client_tree_details") or {}
            draft_form["data"]["client_tree_details"] = self._review_form_service.merge_client_tree_details(prior, details)

    @staticmethod
    def _merge_section_transcripts(
        section_transcripts: dict[str, str],
        delta_transcripts: dict[str, str],
    ) -> None:
        for section_id, delta_text in delta_transcripts.items():
            if not delta_text:
                continue
            existing_text = section_transcripts.get(section_id, "")
            if existing_text:
                if delta_text in existing_text:
                    continue
                section_transcripts[section_id] = f"{existing_text}\n\n{delta_text}"
            else:
                section_transcripts[section_id] = delta_text

    def _merge_issue_transcripts(
        self,
        *,
        job_id: str,
        round_id: str,
        section_ids: list[str],
        issue_ids_by_section: dict[str, set[str]],
        manifest: list[dict[str, Any]],
        issue_recordings: dict[str, dict[str, list[str]]],
        issue_transcripts: dict[str, dict[str, str]],
        transcription_failures: list[dict[str, Any]],
        force_reprocess: bool,
        force_transcribe: bool,
    ) -> None:
        for section_id in section_ids:
            issue_ids = issue_ids_by_section.get(section_id) or set()
            if not issue_ids:
                continue
            for issue_id in sorted(issue_ids):
                transcript, used, failures = self._build_section_transcript(
                    job_id,
                    round_id,
                    section_id,
                    manifest,
                    issue_id=issue_id,
                    seen_recordings=set((issue_recordings.get(section_id) or {}).get(issue_id, []) or []),
                    force_reprocess=force_reprocess,
                    force_transcribe=force_transcribe,
                )
                if failures:
                    transcription_failures.extend(failures)
                if not transcript:
                    continue
                issue_transcripts.setdefault(section_id, {})
                issue_recordings.setdefault(section_id, {})
                existing = issue_transcripts[section_id].get(issue_id, "")
                if not existing:
                    issue_transcripts[section_id][issue_id] = transcript
                elif transcript not in existing:
                    issue_transcripts[section_id][issue_id] = f"{existing}\n\n{transcript}"
                if used:
                    existing_used = issue_recordings[section_id].get(issue_id, [])
                    issue_recordings[section_id][issue_id] = list(sorted(set(existing_used).union(set(used))))

    def _merge_risk_categorization(
        self,
        *,
        draft_form: dict[str, Any],
        delta_transcripts: dict[str, str],
        issue_transcripts: dict[str, dict[str, str]],
    ) -> None:
        existing_rows = list(draft_form["data"].get("risk_categorization") or [])
        issue_map = issue_transcripts.get("risk_categorization")
        issue_text = ""
        if isinstance(issue_map, dict) and issue_map:
            issue_text = "\n\n".join(
                text for text in issue_map.values() if isinstance(text, str) and text.strip()
            )
        delta_text = delta_transcripts.get("risk_categorization") or ""
        combined_text = "\n\n".join(
            part for part in [issue_text, delta_text] if isinstance(part, str) and part.strip()
        )
        incoming_rows = self._extract_risk_rows(combined_text)
        merged_rows: list[dict[str, Any]] = []
        for idx, incoming in enumerate(incoming_rows):
            if idx < len(existing_rows):
                merged_rows.append(self._merge_risk_row(existing_rows[idx], incoming))
            else:
                merged_rows.append(incoming)
        if len(existing_rows) > len(merged_rows):
            merged_rows.extend(existing_rows[len(merged_rows):])
        draft_form["data"]["risk_categorization"] = merged_rows

    def _extract_risk_rows(self, text: str) -> list[dict[str, Any]]:
        if not isinstance(text, str) or not text.strip():
            return []
        try:
            extraction = self._run_extraction_logged("risk_categorization", text)
        except Exception:
            self._logger.exception("Risk categorization extraction failed", extra={"section_id": "risk_categorization"})
            return []
        extracted = extraction.model_dump()
        rows = extracted.get("rows") or []
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "condition_number": row.get("condition_number"),
                    "tree_part": row.get("tree_part"),
                    "condition": row.get("condition"),
                    "part_size": row.get("part_size"),
                    "fall_distance": row.get("fall_distance"),
                    "target_number": row.get("target_number"),
                    "target_protection": row.get("target_protection"),
                    "failure_likelihood": row.get("failure_likelihood"),
                    "impact_likelihood": row.get("impact_likelihood"),
                    "failure_and_impact": row.get("failure_and_impact"),
                    "consequences": row.get("consequences"),
                    "risk_rating": row.get("risk_rating"),
                }
            )
        return normalized

    @staticmethod
    def _merge_risk_row(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = dict(existing)
        for key, value in incoming.items():
            if merged.get(key) in (None, "") and value not in (None, ""):
                merged[key] = value
        return merged

    @staticmethod
    def _combined_transcript(section_transcripts: dict[str, str]) -> str:
        return "\n\n".join(
            f"[{section_id}]\n{text}".strip()
            for section_id, text in section_transcripts.items()
            if text
        )
