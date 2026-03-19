"""Request and response models used by the FastAPI surface.

This module centralizes the Pydantic models previously declared inline in
`app.main` so the application entrypoint can focus on app composition and route
wiring.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AssignedJob(BaseModel):
    """Assigned-job payload returned to device clients."""

    job_id: str
    job_number: str
    status: str
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    customer_name: str
    tree_number: int | None = None
    address: str
    tree_species: str
    reason: str | None = None
    job_name: str
    job_address: str
    job_phone: str
    contact_preference: str
    billing_name: str
    billing_address: str
    billing_contact_name: str | None = None
    location_notes: str | None = None
    server_revision_id: str | None = None
    review_payload: dict[str, Any] | None = None


class CustomerLookupRow(BaseModel):
    """Customer lookup row used to prefill new jobs on the client."""

    customer_id: str
    customer_code: str
    customer_name: str
    job_name: str
    job_address: str | None = None
    job_phone: str | None = None


class BillingProfileLookupRow(BaseModel):
    """Billing-profile lookup row used to prefill billing fields."""

    billing_profile_id: str
    billing_code: str
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    contact_preference: str | None = None


class CreateJobResponse(BaseModel):
    """Canonical job metadata returned after job creation or mutation."""

    job_id: str
    job_number: str
    status: str
    customer_name: str | None = None
    tree_number: int | None = None
    address: str | None = None
    tree_species: str | None = None
    reason: str | None = None
    job_name: str | None = None
    job_address: str | None = None
    job_phone: str | None = None
    contact_preference: str | None = None
    billing_name: str | None = None
    billing_address: str | None = None
    billing_contact_name: str | None = None
    location_notes: str | None = None


class CreateRoundResponse(BaseModel):
    """Response returned when a new round is created."""

    round_id: str
    status: str


class CreateJobRequest(BaseModel):
    """Job-creation payload accepted from the mobile client."""

    customer_name: str | None = Field(default=None, description="Customer/client name.")
    job_name: str = Field(..., description="Client/job name.")
    job_address: str = Field(..., description="Job site address.")
    job_phone: str = Field(..., description="Primary contact phone.")
    contact_preference: str = Field(..., description="Contact preference (text/phone call).")
    billing_name: str = Field(..., description="Billing name.")
    billing_address: str = Field(..., description="Billing address.")
    billing_contact_name: str | None = Field(
        default=None,
        description="Billing contact name (person).",
    )
    tree_number: int | None = Field(
        default=None,
        description="Optional customer-scoped tree number. Server validates or allocates the authoritative value.",
    )
    location_notes: str | None = Field(
        default=None,
        description="Free text notes describing the tree location on the property.",
    )


class ProfilePayload(BaseModel):
    """Persisted profile payload scoped to one authenticated identity."""

    name: str | None = None
    phone: str | None = None
    isa_number: str | None = None
    correspondence_street: str | None = None
    correspondence_city: str | None = None
    correspondence_state: str | None = None
    correspondence_zip: str | None = None
    correspondence_email: str | None = None


class StatusResponse(BaseModel):
    """Job status response returned by `GET /v1/jobs/{job_id}`."""

    status: str
    latest_round_id: str | None = None
    latest_round_status: str | None = None
    tree_number: int | None = None
    review_ready: bool = False
    server_revision_id: str | None = None


class ManifestItem(BaseModel):
    """One manifest row describing a recording or image artifact."""

    artifact_id: str
    section_id: str
    client_order: int = Field(default=0)
    kind: str = Field(default="recording")
    issue_id: str | None = None
    recorded_at: str | None = None


class FinalSubmitRequest(BaseModel):
    """Device payload used to finalize a completed review round."""

    round_id: str
    server_revision_id: str
    client_revision_id: str
    form: dict[str, Any]
    narrative: dict[str, Any]
    profile: ProfilePayload | None = None


class SubmitRoundRequest(BaseModel):
    """Submission payload for sending a round to review processing."""

    server_revision_id: str | None = None
    client_revision_id: str | None = None
    form: dict[str, Any] | None = None
    narrative: dict[str, Any] | None = None


class RegisterDeviceRequest(BaseModel):
    """Initial device registration payload used during bootstrap."""

    device_id: str
    device_name: str | None = None
    app_version: str | None = None
    profile_summary: dict[str, Any] | None = None


class IssueTokenRequest(BaseModel):
    """Token-issuance request for an approved device."""

    device_id: str
    ttl_seconds: int | None = 604800


class AssignJobRequest(BaseModel):
    """Admin payload used to assign a job to one device."""

    device_id: str


class AdminJobStatusRequest(BaseModel):
    """Admin payload used to set top-level and round status values."""

    status: str
    round_id: str | None = None
    round_status: str | None = None


class AdminJobUnlockRequest(BaseModel):
    """Admin payload used to reopen a finalized job for one device."""

    round_id: str | None = None
    device_id: str | None = None


class SiteFactorsRequest(BaseModel):
    """Transcript payload for the site-factors extractor."""

    transcript: str = Field(..., description="Full transcript for site factors section.")


class ClientTreeDetailsRequest(BaseModel):
    """Transcript payload for the client/tree-details extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for client & tree details section.",
    )


class LoadFactorsRequest(BaseModel):
    """Transcript payload for the load-factors extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for load factors section.",
    )


class CrownAndBranchesRequest(BaseModel):
    """Transcript payload for the crown-and-branches extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for crown and branches section.",
    )


class TrunkRequest(BaseModel):
    """Transcript payload for the trunk extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for trunk section.",
    )


class RootsAndRootCollarRequest(BaseModel):
    """Transcript payload for the roots/root-collar extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for roots and root collar section.",
    )


class TargetAssessmentRequest(BaseModel):
    """Transcript payload for the target-assessment extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for target assessment section.",
    )


class SummaryRequest(BaseModel):
    """Combined form/transcript payload for narrative generation."""

    form: dict[str, Any] = Field(
        ...,
        description="Draft form payload with extracted section data.",
    )
    transcript: str = Field(
        ...,
        description="Combined transcript text for the job/round.",
    )


class TreeHealthAndSpeciesRequest(BaseModel):
    """Transcript payload for the tree-health-and-species extractor."""

    transcript: str = Field(
        ...,
        description="Full transcript for tree health and species section.",
    )
