"""Round manifest route extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header

from .models import ManifestItem


def build_round_manifest_router(
    *,
    require_api_key: Callable[[str | None], Any],
    assert_job_assignment: Callable[[str, Any], None],
    ensure_round_record: Callable[[str, str], tuple[Any, Any]],
    assert_round_editable: Callable[[Any, str, Any], None],
    save_round_record: Callable[[str, Any], None],
    logger: Any,
) -> APIRouter:
    """Build the round manifest update route."""

    router = APIRouter()

    @router.put("/v1/jobs/{job_id}/rounds/{round_id}/manifest")
    def set_manifest(
        job_id: str,
        round_id: str,
        manifest: list[ManifestItem],
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Replace round manifest (recordings/images metadata list)."""
        auth = require_api_key(x_api_key)
        assert_job_assignment(job_id, auth)
        record, round_record = ensure_round_record(job_id, round_id)
        assert_round_editable(record, round_id, auth, allow_correction=True)
        round_record.manifest = [item.model_dump() for item in manifest]
        save_round_record(job_id, round_record)
        logger.info(
            "PUT /v1/jobs/%s/rounds/%s/manifest (%s items)",
            job_id,
            round_id,
            len(manifest),
        )
        return {"ok": True, "round_id": round_id, "manifest_count": len(manifest)}

    return router
