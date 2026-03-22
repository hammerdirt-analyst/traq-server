"""Image upload and patch routes extracted from the app root."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request


def build_image_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_job_record: Callable[[str], Any],
    assert_job_editable: Callable[[Any, Any], None],
    media_runtime_service: Any,
    job_artifact_key: Callable[..., str],
    artifact_store: Any,
    db_store: Any,
    write_json: Callable[[Any, dict[str, Any]], None],
    section_dir: Callable[[str, str], Any],
    log_event: Callable[..., None],
    job_photos_section_id: str,
) -> APIRouter:
    """Build image upload and metadata patch routes."""

    router = APIRouter()

    @router.put("/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}")
    async def upload_image(
        job_id: str,
        section_id: str,
        image_id: str,
        request: Request,
        content_type: str | None = Header(default=None, alias="Content-Type"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store an uploaded job photo and report-ready derivative."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        if section_id != job_photos_section_id:
            raise HTTPException(
                status_code=400,
                detail=f"Images must use section_id='{job_photos_section_id}'",
            )
        record = ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_job_editable(record, auth, allow_correction=True)
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Empty image payload")
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for image upload")
        existing_ids = {
            str(row.get("image_id") or "")
            for row in db_store.list_round_images(job_id, round_id)
            if str(row.get("section_id") or "") == section_id
        }
        if image_id not in existing_ids and len(existing_ids) >= 5:
            raise HTTPException(status_code=400, detail="Maximum 5 images per job")
        ext = media_runtime_service.guess_extension(content_type, ".jpg")
        artifact_key = job_artifact_key(
            job_id,
            "sections",
            section_id,
            "images",
            f"{image_id}{ext}",
        )
        file_path = artifact_store.write_bytes(artifact_key, payload)
        report_key = job_artifact_key(
            job_id,
            "sections",
            section_id,
            "images",
            f"{image_id}.report.jpg",
        )
        staged_report_path = artifact_store.stage_output(report_key)
        media_runtime_service.build_report_image_variant(
            file_path,
            staged_report_path,
        )
        committed_report_path = artifact_store.commit_output(report_key, staged_report_path)
        report_bytes = committed_report_path.stat().st_size
        meta = {
            "image_id": image_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": artifact_key,
            "report_image_path": report_key,
            "report_bytes": report_bytes,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
        }
        db_store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
            upload_status="uploaded",
            artifact_path=artifact_key,
            metadata_json=meta,
        )
        write_json(section_dir(job_id, section_id) / "images" / f"{image_id}.meta.json", meta)
        log_event(
            "IMAGE",
            "upload job=%s section=%s image=%s bytes=%s report_bytes=%s",
            job_id,
            section_id,
            image_id,
            len(payload),
            report_bytes,
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "image_id": image_id,
            "bytes": len(payload),
        }

    @router.patch("/v1/jobs/{job_id}/sections/{section_id}/images/{image_id}")
    def patch_image(
        job_id: str,
        section_id: str,
        image_id: str,
        payload: dict[str, Any],
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Update image metadata for a stored job photo."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        if section_id != job_photos_section_id:
            raise HTTPException(
                status_code=400,
                detail=f"Images must use section_id='{job_photos_section_id}'",
            )
        record = ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_job_editable(record, auth, allow_correction=True)
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for image patch")
        existing = db_store.get_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
        )
        if not isinstance(existing, dict):
            raise HTTPException(status_code=404, detail="Image not found")
        meta = dict(existing.get("metadata_json") or {})
        meta.update(payload)
        meta["updated_at"] = datetime.utcnow().isoformat() + "Z"
        db_store.upsert_round_image(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            image_id=image_id,
            upload_status=str(existing.get("upload_status") or "uploaded"),
            caption=str(payload.get("caption") or meta.get("caption") or "").strip() or None,
            latitude=str(
                (payload.get("gps") or {}).get("latitude")
                or payload.get("latitude")
                or meta.get("latitude")
                or ""
            ).strip()
            or None,
            longitude=str(
                (payload.get("gps") or {}).get("longitude")
                or payload.get("longitude")
                or meta.get("longitude")
                or ""
            ).strip()
            or None,
            artifact_path=str(existing.get("artifact_path") or meta.get("stored_path") or "").strip() or None,
            metadata_json=meta,
        )
        write_json(section_dir(job_id, section_id) / "images" / f"{image_id}.meta.json", meta)
        log_event(
            "IMAGE",
            "patch job=%s section=%s image=%s keys=%s",
            job_id,
            section_id,
            image_id,
            sorted(payload.keys()),
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "image_id": image_id,
            "payload": payload,
        }

    return router
