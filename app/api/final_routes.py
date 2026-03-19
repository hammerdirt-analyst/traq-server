"""Finalization routes extracted from the app root."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse


def build_final_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_job_record: Callable[[str], Any],
    job_record_factory: Callable[..., Any],
    jobs: dict[str, Any],
    db_store: Any,
    is_correction_mode: Callable[[str, Any], bool],
    logger: Any,
    finalization_service: Any,
    artifact_store: Any,
    job_artifact_key: Callable[..., str],
    requested_tree_number_from_form: Callable[[dict[str, Any]], int | None],
    resolve_server_tree_number: Callable[[Any, int | None], int | None],
    normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
    apply_tree_number_to_form: Callable[[dict[str, Any], int | None], dict[str, Any]],
    save_job_record: Callable[[Any], None],
    identity_key: Callable[[Any, str | None], str],
    load_runtime_profile: Callable[[str], dict[str, Any] | None],
    media_runtime_service: Any,
    generate_traq_pdf: Callable[..., None],
    write_json: Callable[[Any, dict[str, Any]], None],
    read_json: Callable[[Any], Any],
    final_mutation_service: Any,
    unassign_job_record: Callable[[str], Any],
    materialize_artifact_path: Callable[[str], Any],
) -> APIRouter:
    """Build final submission and final report download routes."""

    router = APIRouter()

    @router.post("/v1/jobs/{job_id}/final")
    def submit_final(
        job_id: str,
        payload: Any,
        x_api_key: str | None = Header(default=None),
    ) -> FileResponse:
        """Finalize a job and generate final artifacts."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if not record:
            persisted_round = db_store.get_job_round(job_id, payload.round_id)
            if isinstance((persisted_round or {}).get("review_payload"), dict):
                record = job_record_factory(
                    job_id=job_id,
                    job_number=job_id,
                    status="DRAFT",
                )
                jobs[job_id] = record
            else:
                raise HTTPException(status_code=404, detail="Job not found")
        correction_mode = is_correction_mode(job_id, record)
        logger.info("POST /v1/jobs/%s/final correction_mode=%s", job_id, correction_mode)
        persisted_round = db_store.get_job_round(job_id, payload.round_id)
        review_payload = (persisted_round or {}).get("review_payload")
        transcript = finalization_service.transcript_from_review_payload(review_payload)
        artifact_names = finalization_service.artifact_names(correction_mode)
        pdf_key = job_artifact_key(job_id, artifact_names.pdf_name)
        pdf_path = artifact_store.stage_output(pdf_key)
        requested_tree_number = requested_tree_number_from_form(payload.form)
        record.tree_number = resolve_server_tree_number(
            record,
            requested_tree_number=requested_tree_number,
        )
        payload.form = finalization_service.ensure_risk_defaults(
            payload.form,
            normalize_form_schema=normalize_form_schema,
        )
        payload.form = apply_tree_number_to_form(payload.form, record.tree_number)
        save_job_record(record)
        try:
            from .. import report_letter

            job_info = finalization_service.build_job_info(record)
            narrative_text = ""
            if isinstance(payload.narrative, dict):
                narrative_text = payload.narrative.get("text") or ""
            else:
                narrative_text = str(payload.narrative or "")
            profile_payload = payload.profile.model_dump() if payload.profile else None
            profile_payload = finalization_service.resolve_profile_payload(
                profile_payload,
                fallback_loader=lambda: load_runtime_profile(identity_key(auth, x_api_key)),
            )
            polished_summary = report_letter.polish_summary(
                narrative_text,
                form_data=payload.form,
                transcript=transcript,
            )
            letter_text = report_letter.build_report_letter(
                profile=profile_payload,
                job=job_info,
                summary=polished_summary,
                form_data=payload.form,
            )
            report_key = job_artifact_key(job_id, artifact_names.report_name)
            report_docx_key = job_artifact_key(job_id, artifact_names.report_docx_name)
            report_path = artifact_store.stage_output(report_key)
            report_docx_path = artifact_store.stage_output(report_docx_key)
            sender_name = ""
            if isinstance(profile_payload, dict):
                sender_name = str(profile_payload.get("name") or "").strip()
            customer_name = str(record.billing_name or record.customer_name or "").strip()
            signature_isa = (
                f"ISA - {str(profile_payload.get('isa_number') or '').strip()}"
                if isinstance(profile_payload, dict)
                and str(profile_payload.get("isa_number") or "").strip()
                else None
            )
            report_images = media_runtime_service.load_job_report_images(
                job_id=job_id,
                round_id=record.latest_round_id or "",
            )
            report_letter.generate_report_letter_pdf(
                letter_text,
                str(report_path),
                sender_name=sender_name or None,
                customer_name=customer_name or None,
                signature_name=sender_name or None,
                signature_isa=signature_isa,
                job_number=record.job_number,
                report_images=report_images,
            )
            report_letter.generate_report_letter_docx(
                letter_text,
                str(report_docx_path),
            )
        except Exception as exc:
            logger.exception("Failed to generate report letter artifacts")
            raise HTTPException(
                status_code=500,
                detail="Report letter generation failed",
            ) from exc
        record.status = "ARCHIVED"
        record.latest_round_status = "REVIEW_RETURNED"
        save_job_record(record)
        archived_at = datetime.utcnow().isoformat() + "Z"
        user_name = (
            str(profile_payload.get("name") or "").strip()
            if isinstance(profile_payload, dict)
            else None
        ) or None
        final_payload = finalization_service.build_final_payload(
            job_id=job_id,
            round_id=payload.round_id,
            server_revision_id=payload.server_revision_id,
            client_revision_id=payload.client_revision_id,
            archived_at=archived_at,
            transcript=transcript,
            form=payload.form,
            narrative=payload.narrative,
            user_name=user_name,
            report_images=report_images,
        )
        final_json_key = job_artifact_key(job_id, artifact_names.final_json_name)
        final_json_path = artifact_store.stage_output(final_json_key)
        write_json(final_json_path, final_payload)
        generate_traq_pdf(form_data=final_payload["form"], output_path=pdf_path)
        try:
            from .. import geojson_export

            form_data = payload.form.get("data") if isinstance(payload.form.get("data"), dict) else payload.form
            if not isinstance(form_data, dict):
                form_data = {}
            geojson_key = job_artifact_key(job_id, artifact_names.geojson_name)
            geojson_path = artifact_store.stage_output(geojson_key)
            geojson_export.write_final_geojson(
                output_path=geojson_path,
                job_number=record.job_number,
                user_name=user_name,
                form_data=form_data,
                report_images=report_images,
            )
        except Exception as exc:
            logger.exception("Failed to generate final.geojson")
            raise HTTPException(
                status_code=500,
                detail="Final GeoJSON generation failed",
            ) from exc
        try:
            geojson_payload = read_json(geojson_path)
            if correction_mode:
                final_mutation_service.set_correction(
                    job_id,
                    payload=final_payload,
                    geojson_payload=geojson_payload if isinstance(geojson_payload, dict) else None,
                )
            else:
                final_mutation_service.set_final(
                    job_id,
                    payload=final_payload,
                    geojson_payload=geojson_payload if isinstance(geojson_payload, dict) else None,
                )
            pdf_path = artifact_store.commit_output(pdf_key, pdf_path)
            artifact_store.commit_output(report_key, report_path)
            artifact_store.commit_output(report_docx_key, report_docx_path)
            artifact_store.commit_output(final_json_key, final_json_path)
            artifact_store.commit_output(geojson_key, geojson_path)
            unassign_job_record(job_id)
        except KeyError:
            logger.info("Finalized job %s had no assignment to remove", job_id)
        except Exception:
            logger.exception("Failed to unassign finalized job %s", job_id)
            raise HTTPException(
                status_code=500,
                detail="Finalization cleanup failed",
            )
        return FileResponse(
            path=str(pdf_path),
            media_type="application/pdf",
            filename="traq_page1.pdf",
        )

    @router.get("/v1/jobs/{job_id}/final/report")
    def get_final_report_letter(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> FileResponse:
        """Download the generated report letter PDF for a job."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        correction_path = materialize_artifact_path(
            job_artifact_key(job_id, "final_report_letter_correction.pdf")
        )
        report_path = (
            correction_path
            if correction_path.exists()
            else materialize_artifact_path(job_artifact_key(job_id, "final_report_letter.pdf"))
        )
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report letter not found")
        return FileResponse(
            path=str(report_path),
            media_type="application/pdf",
            filename="report_letter.pdf",
        )

    return router
