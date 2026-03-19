"""Extraction and summary routes extracted from the app root."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header

from .models import (
    ClientTreeDetailsRequest,
    CrownAndBranchesRequest,
    LoadFactorsRequest,
    RootsAndRootCollarRequest,
    SiteFactorsRequest,
    SummaryRequest,
    TargetAssessmentRequest,
    TreeHealthAndSpeciesRequest,
    TrunkRequest,
)


def build_extraction_router(
    *,
    require_api_key: Callable[[str | None], Any],
    run_extraction_logged: Callable[[str, str], Any],
    generate_summary: Callable[..., str],
) -> APIRouter:
    """Build direct extraction and summary routes."""

    router = APIRouter()

    @router.post("/v1/extract/site_factors")
    def extract_site_factors(
        payload: SiteFactorsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for site_factors section transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("site_factors", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/client_tree_details")
    def extract_client_tree_details(
        payload: ClientTreeDetailsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for client_tree_details transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("client_tree_details", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/load_factors")
    def extract_load_factors(
        payload: LoadFactorsRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for load_factors transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("load_factors", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/crown_and_branches")
    def extract_crown_and_branches(
        payload: CrownAndBranchesRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for crown_and_branches transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("crown_and_branches", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/trunk")
    def extract_trunk(
        payload: TrunkRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for trunk transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("trunk", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/roots_and_root_collar")
    def extract_roots_and_root_collar(
        payload: RootsAndRootCollarRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for roots_and_root_collar transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("roots_and_root_collar", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/tree_health_and_species")
    def extract_tree_health_and_species(
        payload: TreeHealthAndSpeciesRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for tree_health_and_species transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("tree_health_and_species", payload.transcript)
        return result.model_dump()

    @router.post("/v1/extract/target_assessment")
    def extract_target_assessment(
        payload: TargetAssessmentRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Direct extraction endpoint for target_assessment transcript."""
        require_api_key(x_api_key)
        result = run_extraction_logged("target_assessment", payload.transcript)
        return result.model_dump()

    @router.post("/v1/summary")
    def generate_summary_endpoint(
        payload: SummaryRequest,
        x_api_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Generate narrative summary from supplied form/transcript payload."""
        require_api_key(x_api_key)
        summary = generate_summary(
            form_data=payload.form,
            transcript=payload.transcript,
        )
        return {"summary": summary}

    return router
