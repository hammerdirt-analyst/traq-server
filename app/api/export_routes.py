"""Incremental export routes for downstream reporting clients."""

from __future__ import annotations

import mimetypes
from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse


def build_export_router(
    *,
    require_api_key: Callable[[str | None], Any],
    export_sync_service: Any,
    logger: Any,
) -> APIRouter:
    """Build export endpoints for downstream reporting clients."""

    router = APIRouter()

    @router.get("/v1/export/changes")
    def get_export_changes(
        cursor: str | None = Query(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return export-visible job changes since the provided cursor."""
        require_api_key(x_api_key, required_role="admin")
        try:
            payload = export_sync_service.build_changes(
                cursor=cursor,
                build_image_url=lambda job_id, image_ref: f"/v1/export/jobs/{job_id}/images/{image_ref}",
                build_geojson_url=lambda job_id: f"/v1/export/jobs/{job_id}/geojson",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        logger.info(
            "GET /v1/export/changes cursor=%s in_process=%s completed=%s transitioned=%s",
            cursor,
            len(payload.get("in_process") or []),
            len(payload.get("completed") or []),
            len(payload.get("transitioned_to_completed") or []),
        )
        return payload

    @router.get("/v1/export/jobs/{job_id}/images/{image_ref}")
    def get_export_image(
        job_id: str,
        image_ref: str,
        variant: str = Query(default="auto"),
        x_api_key: str | None = Header(default=None),
    ) -> FileResponse:
        """Download one export-visible image artifact."""
        require_api_key(x_api_key, required_role="admin")
        try:
            image_path = export_sync_service.resolve_image_path(
                job_id=job_id,
                image_ref=image_ref,
                variant=variant,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        media_type, _ = mimetypes.guess_type(str(image_path))
        logger.info("GET /v1/export/jobs/%s/images/%s variant=%s", job_id, image_ref, variant)
        return FileResponse(
            path=str(image_path),
            media_type=media_type or "application/octet-stream",
            filename=image_path.name,
        )

    @router.get("/v1/export/jobs/{job_id}/geojson")
    def get_export_geojson(
        job_id: str,
        x_api_key: str | None = Header(default=None),
    ) -> JSONResponse:
        """Return archived GeoJSON payload for one completed job."""
        require_api_key(x_api_key, required_role="admin")
        try:
            payload = export_sync_service.resolve_geojson_payload(job_id=job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        logger.info("GET /v1/export/jobs/%s/geojson", job_id)
        return JSONResponse(content=payload)

    return router
