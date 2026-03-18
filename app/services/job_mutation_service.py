"""Job mutation service for operational metadata updates.

This service handles the editable job metadata that sits between reusable
customer/billing identities and the round/final workflow. It preserves the
server-side tree identity rule: tree numbers are customer-scoped and resolved by
server logic, not by fuzzy matching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from ..config import load_settings
from ..db import session_scope
from ..db_models import BillingProfile, Customer, Job, JobStatus
from .tree_store import parse_tree_number, resolve_tree


class JobMutationService:
    """Create and update operational job records in the database."""

    @staticmethod
    def _clean(value: str | None) -> str | None:
        """Trim free-form operator input and normalize blanks to ``None``."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _parse_uuid(value: str | None, label: str) -> UUID | None:
        """Parse an optional UUID reference or raise a keyed lookup error."""
        if value is None:
            return None
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise KeyError(f"{label} not found: {value}") from exc

    @staticmethod
    def _customer_snapshot(customer: Customer | None) -> dict[str, Any]:
        """Build the customer-derived job shell fields for persistence."""
        if customer is None:
            return {
                "customer_id": None,
                "customer_code": None,
                "customer_name": None,
                "address": None,
                "job_phone": None,
            }
        return {
            "customer_id": str(customer.id),
            "customer_code": customer.customer_code,
            "customer_name": customer.name,
            "address": customer.address,
            "job_phone": customer.phone,
        }

    @staticmethod
    def _billing_snapshot(billing: BillingProfile | None) -> dict[str, Any]:
        """Build the billing-derived job shell fields for persistence."""
        if billing is None:
            return {
                "billing_profile_id": None,
                "billing_code": None,
                "billing_name": None,
                "billing_address": None,
                "billing_contact_name": None,
                "contact_preference": None,
            }
        return {
            "billing_profile_id": str(billing.id),
            "billing_code": billing.billing_code,
            "billing_name": billing.billing_name,
            "billing_address": billing.billing_address,
            "billing_contact_name": billing.billing_contact_name,
            "contact_preference": billing.contact_preference,
        }

    def _resolve_customer(self, session, customer_ref: str | None) -> Customer | None:
        """Resolve a customer from UUID or short code."""
        if customer_ref is None:
            return None
        try:
            customer_uuid = self._parse_uuid(customer_ref, "Customer")
        except KeyError:
            customer_uuid = None
        if customer_uuid is not None:
            row = session.get(Customer, customer_uuid)
            if row is not None:
                return row
        row = session.scalar(select(Customer).where(Customer.customer_code == customer_ref.strip().upper()))
        if row is None:
            raise KeyError(f"Customer not found: {customer_ref}")
        return row

    def _resolve_billing_profile(self, session, billing_ref: str | None) -> BillingProfile | None:
        """Resolve a billing profile from UUID or short code."""
        if billing_ref is None:
            return None
        try:
            billing_uuid = self._parse_uuid(billing_ref, "Billing profile")
        except KeyError:
            billing_uuid = None
        if billing_uuid is not None:
            row = session.get(BillingProfile, billing_uuid)
            if row is not None:
                return row
        row = session.scalar(
            select(BillingProfile).where(BillingProfile.billing_code == billing_ref.strip().upper())
        )
        if row is None:
            raise KeyError(f"Billing profile not found: {billing_ref}")
        return row

    @staticmethod
    def _job_to_dict(row: Job) -> dict[str, Any]:
        """Serialize a job row with its denormalized operational shell."""
        payload = dict(row.details_json or {})
        payload.update(
            {
                "job_id": row.job_id,
                "job_number": row.job_number,
                "status": row.status.value,
                "tree_number": row.tree_number,
                "job_name": row.job_name,
                "job_address": row.job_address,
                "reason": row.reason,
                "location_notes": row.location_notes,
                "tree_species": row.tree_species,
                "customer_id": str(row.customer_id) if row.customer_id else None,
                "billing_profile_id": str(row.billing_profile_id) if row.billing_profile_id else None,
                "tree_id": str(row.tree_id) if row.tree_id else None,
                "latest_round_id": row.latest_round_id,
                "latest_round_status": row.latest_round_status.value if row.latest_round_status else None,
            }
        )
        return payload

    def create_job(
        self,
        *,
        job_id: str,
        job_number: str,
        status: str = "DRAFT",
        customer_id: str | None = None,
        billing_profile_id: str | None = None,
        tree_number: int | str | None = None,
        job_name: str | None = None,
        job_address: str | None = None,
        reason: str | None = None,
        location_notes: str | None = None,
        tree_species: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new job and materialize its mirrored shell fields."""
        with session_scope() as session:
            existing = session.scalar(select(Job).where(Job.job_id == job_id))
            if existing is not None:
                raise ValueError(f"Job already exists: {job_id}")
            job = Job(
                job_id=job_id,
                job_number=job_number,
                status=JobStatus(status.strip().upper()),
            )
            session.add(job)
            self._apply_mutation(
                session,
                job,
                customer_id=customer_id,
                billing_profile_id=billing_profile_id,
                tree_number=tree_number,
                job_name=job_name,
                job_address=job_address,
                reason=reason,
                location_notes=location_notes,
                tree_species=tree_species,
                details=details,
            )
            session.flush()
            self._sync_job_record(job)
            return self._job_to_dict(job)

    def update_job(
        self,
        job_ref: str,
        *,
        customer_id: str | None = None,
        billing_profile_id: str | None = None,
        tree_number: int | str | None = None,
        job_name: str | None = None,
        job_address: str | None = None,
        reason: str | None = None,
        location_notes: str | None = None,
        tree_species: str | None = None,
        status: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing job and refresh its derived snapshots."""
        with session_scope() as session:
            job = self._find_job(session, job_ref)
            if job is None:
                raise KeyError(f"Job not found: {job_ref}")
            if status is not None:
                job.status = JobStatus(status.strip().upper())
            self._apply_mutation(
                session,
                job,
                customer_id=customer_id,
                billing_profile_id=billing_profile_id,
                tree_number=tree_number,
                job_name=job_name,
                job_address=job_address,
                reason=reason,
                location_notes=location_notes,
                tree_species=tree_species,
                details=details,
            )
            session.flush()
            self._sync_job_record(job)
            return self._job_to_dict(job)

    def _apply_mutation(
        self,
        session,
        job: Job,
        *,
        customer_id: str | None,
        billing_profile_id: str | None,
        tree_number: int | str | None,
        job_name: str | None,
        job_address: str | None,
        reason: str | None,
        location_notes: str | None,
        tree_species: str | None,
        details: dict[str, Any] | None,
    ) -> None:
        """Apply one mutation request to the job shell and tree linkage."""
        previous_customer_id = job.customer_id
        customer_relinked = False
        if customer_id is not None:
            customer = self._resolve_customer(session, customer_id)
            job.customer = customer
            customer_relinked = customer.id != previous_customer_id
        if billing_profile_id is not None:
            billing = self._resolve_billing_profile(session, billing_profile_id)
            job.billing_profile = billing

        if customer_relinked and job.customer is not None:
            if job_name is None:
                job.job_name = self._clean(job.customer.name)
            if job_address is None:
                job.job_address = self._clean(job.customer.address)
        if job_name is not None:
            job.job_name = self._clean(job_name)
        if job_address is not None:
            job.job_address = self._clean(job_address)
        if reason is not None:
            job.reason = self._clean(reason)
        if location_notes is not None:
            job.location_notes = self._clean(location_notes)
        if tree_species is not None:
            job.tree_species = self._clean(tree_species)

        requested_tree_number = parse_tree_number(tree_number)
        if job.customer is not None and (
            tree_number is not None or job.tree is None or customer_relinked
        ):
            # Tree numbers are customer-scoped. When a job moves to a different
            # customer, allocate a fresh tree number unless the operator
            # explicitly requests one.
            tree = resolve_tree(
                session,
                customer=job.customer,
                requested_tree_number=requested_tree_number if tree_number is not None else None,
            )
            job.tree = tree
            job.tree_number = tree.tree_number
        elif tree_number is not None and job.customer is None:
            raise ValueError("Customer is required before assigning a tree number")

        customer_snapshot = self._customer_snapshot(job.customer)
        billing_snapshot = self._billing_snapshot(job.billing_profile)
        merged_details = dict(job.details_json or {})
        if details:
            merged_details.update(details)
        merged_details.update(
            {
                "job_name": job.job_name,
                "job_address": job.job_address,
                "reason": job.reason,
                "location_notes": job.location_notes,
                "tree_species": job.tree_species,
                "tree_number": job.tree_number,
                **customer_snapshot,
                **billing_snapshot,
            }
        )
        job.details_json = merged_details

    @staticmethod
    def _find_job(session, job_ref: str) -> Job | None:
        """Look up a job by server id or operator-facing job number."""
        if job_ref.startswith("job_"):
            return session.scalar(select(Job).where(Job.job_id == job_ref))
        return session.scalar(select(Job).where(Job.job_number == job_ref))

    def _sync_job_record(self, job: Job) -> None:
        """Export the current job shell as a non-authoritative debug record."""
        settings = load_settings()
        job_path = settings.storage_root / "jobs" / job.job_id / "job_record.json"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        current: dict[str, Any] = {}
        if job_path.exists():
            try:
                loaded = json.loads(job_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current = loaded
            except json.JSONDecodeError:
                current = {}

        details = dict(job.details_json or {})
        customer_snapshot = self._customer_snapshot(job.customer)
        billing_snapshot = self._billing_snapshot(job.billing_profile)

        current.update(
            {
                "job_id": job.job_id,
                "job_number": job.job_number,
                "status": job.status.value,
                "tree_number": job.tree_number,
                "job_name": job.job_name,
                "job_address": job.job_address,
                "reason": job.reason,
                "location_notes": job.location_notes,
                "tree_species": job.tree_species,
                "latest_round_id": job.latest_round_id,
                "latest_round_status": job.latest_round_status.value if job.latest_round_status else None,
                "customer_name": customer_snapshot["customer_name"],
                "address": customer_snapshot["address"],
                "job_phone": customer_snapshot["job_phone"],
                "billing_name": billing_snapshot["billing_name"],
                "billing_address": billing_snapshot["billing_address"],
                "billing_contact_name": billing_snapshot["billing_contact_name"],
                "contact_preference": billing_snapshot["contact_preference"],
                "customer_id": customer_snapshot["customer_id"],
                "customer_code": customer_snapshot["customer_code"],
                "billing_profile_id": billing_snapshot["billing_profile_id"],
                "billing_code": billing_snapshot["billing_code"],
            }
        )
        job_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
