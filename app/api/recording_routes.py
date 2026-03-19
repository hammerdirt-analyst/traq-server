"""Recording upload route extracted from the app root."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Request


def build_recording_router(
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
) -> APIRouter:
    """Build the recording upload route."""

    router = APIRouter()

    @router.put("/v1/jobs/{job_id}/sections/{section_id}/recordings/{recording_id}")
    async def upload_recording(
        job_id: str,
        section_id: str,
        recording_id: str,
        request: Request,
        content_type: str | None = Header(default=None, alias="Content-Type"),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Store an uploaded section recording and persist metadata."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record = ensure_job_record(job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        assert_job_editable(record, auth, allow_correction=True)
        payload = await request.body()
        if not payload:
            raise HTTPException(status_code=400, detail="Empty recording payload")
        ext = media_runtime_service.guess_extension(content_type, ".m4a")
        artifact_key = job_artifact_key(
            job_id,
            "sections",
            section_id,
            "recordings",
            f"{recording_id}{ext}",
        )
        file_path = artifact_store.write_bytes(artifact_key, payload)
        audio_probe = media_runtime_service.probe_audio_metadata(file_path)
        meta = {
            "recording_id": recording_id,
            "section_id": section_id,
            "content_type": content_type,
            "bytes": len(payload),
            "stored_path": artifact_key,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
            "audio_probe": audio_probe,
        }
        round_id = record.latest_round_id
        if not round_id:
            raise HTTPException(status_code=400, detail="No active round for recording upload")
        db_store.upsert_round_recording(
            job_id=job_id,
            round_id=round_id,
            section_id=section_id,
            recording_id=recording_id,
            upload_status="uploaded",
            content_type=content_type,
            duration_ms=audio_probe.get("duration_ms"),
            artifact_path=artifact_key,
            metadata_json=meta,
        )
        write_json(section_dir(job_id, section_id) / "recordings" / f"{recording_id}.meta.json", meta)
        log_event(
            "RECORDING",
            (
                "PUT /v1/jobs/%s/sections/%s/recordings/%s "
                "content_type=%s bytes=%s codec=%s sr=%s ch=%s "
                "duration=%s format=%s ffprobe_error=%s"
            ),
            job_id,
            section_id,
            recording_id,
            content_type,
            len(payload),
            audio_probe.get("codec_name"),
            audio_probe.get("sample_rate"),
            audio_probe.get("channels"),
            audio_probe.get("duration"),
            audio_probe.get("format_name"),
            audio_probe.get("ffprobe_error"),
        )
        return {
            "ok": True,
            "job_id": job_id,
            "section_id": section_id,
            "recording_id": recording_id,
            "bytes": len(payload),
        }

    return router
