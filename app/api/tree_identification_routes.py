"""Standalone tree-identification routes."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from ..services.tree_identification_service import (
    MAX_TREE_IDENTIFICATION_IMAGES,
    TreeIdentificationError,
    TreeIdentificationImage,
)


def build_tree_identification_router(
    *,
    require_api_key: Callable[[str | None], Any],
    tree_identification_service: Any,
    logger: Any,
) -> APIRouter:
    """Build standalone tree-identification endpoints."""

    router = APIRouter()

    @router.post("/v1/trees/identify")
    async def identify_trees(
        images: list[UploadFile] = File(...),
        organs: list[str] | None = Form(default=None),
        project: str | None = Form(default=None),
        include_related_images: bool = Form(default=False),
        no_reject: bool = Form(default=False),
        nb_results: int | None = Form(default=None),
        lang: str | None = Form(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Identify tree species from up to five uploaded images."""
        require_api_key(x_api_key)
        if len(images) > MAX_TREE_IDENTIFICATION_IMAGES:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_TREE_IDENTIFICATION_IMAGES} images are allowed",
            )
        normalized_images: list[TreeIdentificationImage] = []
        for image in images:
            normalized_images.append(
                TreeIdentificationImage(
                    filename=image.filename or "upload.jpg",
                    content_type=(image.content_type or "application/octet-stream").strip().lower(),
                    data=await image.read(),
                )
            )
        try:
            result = tree_identification_service.identify(
                images=normalized_images,
                organs=organs,
                project=project,
                include_related_images=include_related_images,
                no_reject=no_reject,
                nb_results=nb_results,
                lang=lang,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except TreeIdentificationError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        logger.info("POST /v1/trees/identify -> images=%s project=%s", len(images), project or "default")
        return result

    return router
