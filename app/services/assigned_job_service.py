"""Assigned-job projection helpers for API read models."""

from __future__ import annotations

from typing import Any, Callable


class AssignedJobService:
    """Project authoritative job records into API-facing assigned-job payloads."""

    def __init__(
        self,
        *,
        db_store: Any,
        review_payload_service: Any,
        normalize_form_schema: Callable[[dict[str, Any]], dict[str, Any]],
        assigned_job_factory: Callable[..., Any],
    ) -> None:
        """Bind DB lookups and payload-normalization dependencies."""
        self._db_store = db_store
        self._review_payload_service = review_payload_service
        self._normalize_form_schema = normalize_form_schema
        self._assigned_job_factory = assigned_job_factory

    def to_assigned_job(self, record: Any) -> Any:
        """Convert one runtime job record into the assigned-job API model."""
        server_revision_id = None
        review_payload: dict[str, Any] | None = None
        latest_round_id = getattr(record, "latest_round_id", None)
        if latest_round_id:
            round_record = getattr(record, "rounds", {}).get(latest_round_id)
            if round_record is not None:
                server_revision_id = getattr(round_record, "server_revision_id", None)
            review_row = self._db_store.get_job_round(record.job_id, latest_round_id) or {}
            review_data = review_row.get("review_payload")
            if isinstance(review_data, dict):
                review_payload = self._review_payload_service.normalize_payload(
                    review_data,
                    tree_number=getattr(record, "tree_number", None),
                    normalize_form_schema=self._normalize_form_schema,
                    hydrated_images=self._review_payload_service.build_round_images(
                        self._db_store.list_round_images(record.job_id, latest_round_id)
                    ),
                )
                if server_revision_id is None:
                    server_revision_id = review_data.get("server_revision_id")
        return self._assigned_job_factory(
            job_id=record.job_id,
            job_number=record.job_number,
            status=record.status or "NOT_STARTED",
            latest_round_id=record.latest_round_id,
            latest_round_status=record.latest_round_status,
            customer_name=record.customer_name or "",
            project_id=getattr(record, "project_id", None),
            project=getattr(record, "project", None),
            project_slug=getattr(record, "project_slug", None),
            tree_number=record.tree_number,
            address=record.address or "",
            tree_species=record.tree_species or "",
            reason=record.reason,
            job_name=record.job_name or "",
            job_address=record.job_address or "",
            job_phone=record.job_phone or "",
            contact_preference=record.contact_preference or "",
            billing_name=record.billing_name or "",
            billing_address=record.billing_address or "",
            billing_contact_name=record.billing_contact_name,
            location_notes=record.location_notes,
            server_revision_id=server_revision_id,
            review_payload=review_payload,
        )

    def resolve_assigned_job(
        self,
        job_id: str,
        *,
        refresh_job_record_from_store: Callable[[str], Any | None],
        jobs_cache: dict[str, Any],
    ) -> Any | None:
        """Resolve one assigned job from persisted state, falling back to memory."""
        persisted = refresh_job_record_from_store(job_id)
        if persisted is not None:
            return self.to_assigned_job(persisted)
        record = jobs_cache.get(job_id)
        if record is not None:
            return self.to_assigned_job(record)
        return None
