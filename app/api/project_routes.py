"""Project registry routes for authenticated clients and admins."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header, HTTPException


def build_project_router(
    *,
    require_api_key: Callable[[str | None], Any],
    project_service: Any | None = None,
) -> APIRouter:
    """Build read-only project list routes for authenticated clients."""

    router = APIRouter()

    @router.get("/v1/projects")
    def list_projects(
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return the current server-managed project choices."""
        require_api_key(x_api_key)
        if project_service is None:
            raise HTTPException(status_code=501, detail="Project service not configured")
        return {"ok": True, "projects": project_service.list_projects()}

    return router
