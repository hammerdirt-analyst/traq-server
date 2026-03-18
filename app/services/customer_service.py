"""Customer and billing profile service for operational server workflows.

This service owns reusable customer-facing identities that should not be copied
into every job row. Jobs reference these records; final artifacts remain a
separate reporting concern.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select

from ..db import session_scope
from ..db_models import BillingProfile, Customer, Tree


class CustomerService:
    """CRUD-style service for reusable customer and billing identities."""

    _CODE_RE = re.compile(r"^(?P<prefix>[A-Z])(?P<number>\d+)$")

    @staticmethod
    def _clean(value: str | None) -> str | None:
        """Trim user-provided text and collapse blanks to ``None``."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _customer_to_dict(row: Customer) -> dict[str, Any]:
        """Serialize a customer row for CLI and API responses."""
        return {
            "customer_id": str(row.id),
            "customer_code": row.customer_code,
            "name": row.name,
            "phone": row.phone,
            "address": row.address,
        }

    @staticmethod
    def _billing_to_dict(row: BillingProfile) -> dict[str, Any]:
        """Serialize a billing profile row for CLI and API responses."""
        return {
            "billing_profile_id": str(row.id),
            "billing_code": row.billing_code,
            "billing_name": row.billing_name,
            "billing_contact_name": row.billing_contact_name,
            "billing_address": row.billing_address,
            "contact_preference": row.contact_preference,
        }

    @staticmethod
    def _parse_uuid(value: str, label: str) -> UUID:
        """Parse a UUID-like reference or raise a keyed lookup error."""
        try:
            return UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise KeyError(f"{label} not found: {value}") from exc

    @classmethod
    def _next_code(cls, session, model, field_name: str, prefix: str) -> str:
        """Allocate the next short code for a reusable identity table."""
        codes = session.scalars(select(getattr(model, field_name))).all()
        max_number = 0
        for code in codes:
            if not code:
                continue
            match = cls._CODE_RE.match(str(code))
            if not match or match.group("prefix") != prefix:
                continue
            max_number = max(max_number, int(match.group("number")))
        return f"{prefix}{max_number + 1:04d}"

    def _resolve_customer(self, session, customer_ref: str) -> Customer:
        """Resolve a customer row from UUID or short code."""
        try:
            row = session.get(Customer, self._parse_uuid(customer_ref, "Customer"))
        except KeyError:
            row = session.scalar(select(Customer).where(Customer.customer_code == customer_ref.strip().upper()))
        if row is None:
            raise KeyError(f"Customer not found: {customer_ref}")
        return row

    def _resolve_billing(self, session, billing_ref: str) -> BillingProfile:
        """Resolve a billing profile row from UUID or short code."""
        try:
            row = session.get(BillingProfile, self._parse_uuid(billing_ref, "Billing profile"))
        except KeyError:
            row = session.scalar(select(BillingProfile).where(BillingProfile.billing_code == billing_ref.strip().upper()))
        if row is None:
            raise KeyError(f"Billing profile not found: {billing_ref}")
        return row

    def list_customers(self, search: str | None = None) -> list[dict[str, Any]]:
        """Return reusable customer rows, optionally filtered by search text."""
        with session_scope() as session:
            stmt = select(Customer).order_by(Customer.customer_code, Customer.created_at)
            term = self._clean(search)
            if term:
                like = f"%{term}%"
                stmt = stmt.where(
                    or_(
                        Customer.customer_code.ilike(like),
                        Customer.name.ilike(like),
                        Customer.phone.ilike(like),
                        Customer.address.ilike(like),
                    )
                )
            rows = session.scalars(stmt).all()
            return [self._customer_to_dict(row) for row in rows]

    def customer_duplicates(self) -> list[dict[str, Any]]:
        """Return duplicate-candidate groups based on normalized customer names."""
        with session_scope() as session:
            rows = session.scalars(select(Customer).order_by(Customer.customer_code)).all()
            grouped: dict[str, list[Customer]] = defaultdict(list)
            for row in rows:
                normalized = (row.name or "").strip().lower()
                if normalized:
                    grouped[normalized].append(row)
            return [
                {
                    "match_type": "customer_name",
                    "normalized_name": normalized,
                    "count": len(matches),
                    "records": [self._customer_to_dict(row) for row in matches],
                }
                for normalized, matches in grouped.items()
                if len(matches) > 1
            ]

    def get_customer(self, customer_ref: str) -> dict[str, Any] | None:
        """Return one customer by UUID or short code."""
        with session_scope() as session:
            try:
                row = self._resolve_customer(session, customer_ref)
            except KeyError:
                return None
            return self._customer_to_dict(row)

    def create_customer(
        self,
        *,
        name: str,
        phone: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Create one reusable customer identity."""
        cleaned_name = self._clean(name)
        if not cleaned_name:
            raise ValueError("Customer name is required")
        with session_scope() as session:
            row = Customer(
                customer_code=self._next_code(session, Customer, "customer_code", "C"),
                name=cleaned_name,
                phone=self._clean(phone),
                address=self._clean(address),
            )
            session.add(row)
            session.flush()
            return self._customer_to_dict(row)

    def get_or_create_customer(
        self,
        *,
        name: str,
        phone: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Reuse an exact customer identity match or create a new one."""
        cleaned_name = self._clean(name)
        if not cleaned_name:
            raise ValueError("Customer name is required")
        cleaned_phone = self._clean(phone)
        cleaned_address = self._clean(address)
        with session_scope() as session:
            row = session.scalar(
                select(Customer).where(
                    Customer.name == cleaned_name,
                    Customer.phone.is_(cleaned_phone)
                    if cleaned_phone is None
                    else Customer.phone == cleaned_phone,
                    Customer.address.is_(cleaned_address)
                    if cleaned_address is None
                    else Customer.address == cleaned_address,
                )
            )
            if row is None:
                row = Customer(
                    customer_code=self._next_code(session, Customer, "customer_code", "C"),
                    name=cleaned_name,
                    phone=cleaned_phone,
                    address=cleaned_address,
                )
                session.add(row)
                session.flush()
            return self._customer_to_dict(row)

    def update_customer(
        self,
        customer_id: str,
        *,
        name: str | None = None,
        phone: str | None = None,
        address: str | None = None,
    ) -> dict[str, Any]:
        """Update editable fields for one reusable customer."""
        with session_scope() as session:
            row = self._resolve_customer(session, customer_id)
            cleaned_name = self._clean(name)
            if name is not None:
                if not cleaned_name:
                    raise ValueError("Customer name cannot be blank")
                row.name = cleaned_name
            if phone is not None:
                row.phone = self._clean(phone)
            if address is not None:
                row.address = self._clean(address)
            session.flush()
            return self._customer_to_dict(row)

    def merge_customer(
        self,
        source_customer_id: str,
        *,
        target_customer_id: str,
    ) -> dict[str, Any]:
        """Merge one customer into another and re-home dependent jobs/trees."""
        with session_scope() as session:
            source = self._resolve_customer(session, source_customer_id)
            target = self._resolve_customer(session, target_customer_id)
            if source.id == target.id:
                raise ValueError("Source and target customer must be different")

            moved_job_count = len(source.jobs)
            moved_tree_count = 0
            merged_tree_count = 0

            target_tree_by_number = {tree.tree_number: tree for tree in target.trees}
            for tree in list(source.trees):
                existing = target_tree_by_number.get(tree.tree_number)
                if existing is None:
                    tree.customer = target
                    target_tree_by_number[tree.tree_number] = tree
                    moved_tree_count += 1
                    continue
                for job in list(tree.jobs):
                    job.tree = existing
                    job.customer = target
                    job.tree_number = existing.tree_number
                session.delete(tree)
                merged_tree_count += 1

            for job in list(source.jobs):
                job.customer = target
                if job.tree is None and job.tree_number is not None:
                    existing = target_tree_by_number.get(job.tree_number)
                    if existing is None:
                        existing = Tree(customer=target, tree_number=job.tree_number)
                        session.add(existing)
                        session.flush()
                        target_tree_by_number[job.tree_number] = existing
                        moved_tree_count += 1
                    job.tree = existing

            source_payload = self._customer_to_dict(source)
            session.delete(source)
            session.flush()
            return {
                "source_customer": source_payload,
                "target_customer": self._customer_to_dict(target),
                "moved_job_count": moved_job_count,
                "moved_tree_count": moved_tree_count,
                "merged_tree_count": merged_tree_count,
            }

    def delete_customer(self, customer_ref: str) -> dict[str, Any]:
        """Delete an unused customer record."""
        with session_scope() as session:
            row = self._resolve_customer(session, customer_ref)
            if row.jobs:
                raise ValueError(
                    f"Customer {row.customer_code} is still in use by {len(row.jobs)} job(s)"
                )
            if row.trees:
                raise ValueError(
                    f"Customer {row.customer_code} still has {len(row.trees)} tree record(s)"
                )
            payload = self._customer_to_dict(row)
            session.delete(row)
            session.flush()
            return {"deleted": True, "customer": payload}

    def customer_usage(self, customer_id: str) -> dict[str, Any]:
        """Summarize jobs and trees linked to one customer."""
        with session_scope() as session:
            row = self._resolve_customer(session, customer_id)
            jobs = sorted(row.jobs, key=lambda job: job.job_number)
            return {
                "customer": self._customer_to_dict(row),
                "job_count": len(jobs),
                "tree_count": len(row.trees),
                "job_numbers": [job.job_number for job in jobs],
                "jobs": [
                    {
                        "job_number": job.job_number,
                        "job_id": job.job_id,
                        "billing_code": job.billing_profile.billing_code if job.billing_profile else None,
                        "billing_name": job.billing_profile.billing_name if job.billing_profile else None,
                        "tree_number": job.tree_number,
                        "status": job.status.value,
                    }
                    for job in jobs
                ],
            }

    def list_billing_profiles(self, search: str | None = None) -> list[dict[str, Any]]:
        """Return reusable billing profiles, optionally filtered by search text."""
        with session_scope() as session:
            stmt = select(BillingProfile).order_by(BillingProfile.billing_code, BillingProfile.created_at)
            term = self._clean(search)
            if term:
                like = f"%{term}%"
                stmt = stmt.where(
                    or_(
                        BillingProfile.billing_code.ilike(like),
                        BillingProfile.billing_name.ilike(like),
                        BillingProfile.billing_contact_name.ilike(like),
                        BillingProfile.billing_address.ilike(like),
                    )
                )
            rows = session.scalars(stmt).all()
            return [self._billing_to_dict(row) for row in rows]

    def billing_duplicates(self) -> list[dict[str, Any]]:
        """Return duplicate-candidate groups based on normalized billing names."""
        with session_scope() as session:
            rows = session.scalars(select(BillingProfile).order_by(BillingProfile.billing_code)).all()
            grouped: dict[str, list[BillingProfile]] = defaultdict(list)
            for row in rows:
                normalized = (row.billing_name or "").strip().lower()
                if normalized:
                    grouped[normalized].append(row)
            return [
                {
                    "match_type": "billing_name",
                    "normalized_billing_name": normalized,
                    "count": len(matches),
                    "records": [self._billing_to_dict(row) for row in matches],
                }
                for normalized, matches in grouped.items()
                if len(matches) > 1
            ]

    def get_billing_profile(self, billing_profile_id: str) -> dict[str, Any] | None:
        """Return one billing profile by UUID or short code."""
        with session_scope() as session:
            try:
                row = self._resolve_billing(session, billing_profile_id)
            except KeyError:
                return None
            return self._billing_to_dict(row)

    def create_billing_profile(
        self,
        *,
        billing_name: str | None = None,
        billing_contact_name: str | None = None,
        billing_address: str | None = None,
        contact_preference: str | None = None,
    ) -> dict[str, Any]:
        """Create one reusable billing profile."""
        with session_scope() as session:
            row = BillingProfile(
                billing_code=self._next_code(session, BillingProfile, "billing_code", "B"),
                billing_name=self._clean(billing_name),
                billing_contact_name=self._clean(billing_contact_name),
                billing_address=self._clean(billing_address),
                contact_preference=self._clean(contact_preference),
            )
            session.add(row)
            session.flush()
            return self._billing_to_dict(row)

    def get_or_create_billing_profile(
        self,
        *,
        billing_name: str | None = None,
        billing_contact_name: str | None = None,
        billing_address: str | None = None,
        contact_preference: str | None = None,
    ) -> dict[str, Any] | None:
        """Reuse an exact billing profile match or create a new one."""
        cleaned_name = self._clean(billing_name)
        cleaned_contact = self._clean(billing_contact_name)
        cleaned_address = self._clean(billing_address)
        cleaned_preference = self._clean(contact_preference)
        if not any([cleaned_name, cleaned_contact, cleaned_address, cleaned_preference]):
            return None
        with session_scope() as session:
            row = session.scalar(
                select(BillingProfile).where(
                    BillingProfile.billing_name.is_(cleaned_name)
                    if cleaned_name is None
                    else BillingProfile.billing_name == cleaned_name,
                    BillingProfile.billing_contact_name.is_(cleaned_contact)
                    if cleaned_contact is None
                    else BillingProfile.billing_contact_name == cleaned_contact,
                    BillingProfile.billing_address.is_(cleaned_address)
                    if cleaned_address is None
                    else BillingProfile.billing_address == cleaned_address,
                    BillingProfile.contact_preference.is_(cleaned_preference)
                    if cleaned_preference is None
                    else BillingProfile.contact_preference == cleaned_preference,
                )
            )
            if row is None:
                row = BillingProfile(
                    billing_code=self._next_code(session, BillingProfile, "billing_code", "B"),
                    billing_name=cleaned_name,
                    billing_contact_name=cleaned_contact,
                    billing_address=cleaned_address,
                    contact_preference=cleaned_preference,
                )
                session.add(row)
                session.flush()
            return self._billing_to_dict(row)

    def update_billing_profile(
        self,
        billing_profile_id: str,
        *,
        billing_name: str | None = None,
        billing_contact_name: str | None = None,
        billing_address: str | None = None,
        contact_preference: str | None = None,
    ) -> dict[str, Any]:
        """Update editable fields for one reusable billing profile."""
        with session_scope() as session:
            row = self._resolve_billing(session, billing_profile_id)
            if billing_name is not None:
                row.billing_name = self._clean(billing_name)
            if billing_contact_name is not None:
                row.billing_contact_name = self._clean(billing_contact_name)
            if billing_address is not None:
                row.billing_address = self._clean(billing_address)
            if contact_preference is not None:
                row.contact_preference = self._clean(contact_preference)
            session.flush()
            return self._billing_to_dict(row)

    def merge_billing_profile(
        self,
        source_billing_profile_id: str,
        *,
        target_billing_profile_id: str,
    ) -> dict[str, Any]:
        """Merge one billing profile into another and re-home dependent jobs."""
        with session_scope() as session:
            source = self._resolve_billing(session, source_billing_profile_id)
            target = self._resolve_billing(session, target_billing_profile_id)
            if source.id == target.id:
                raise ValueError("Source and target billing profiles must be different")
            moved_job_count = len(source.jobs)
            for job in list(source.jobs):
                job.billing_profile = target
            source_payload = self._billing_to_dict(source)
            session.delete(source)
            session.flush()
            return {
                "source_billing_profile": source_payload,
                "target_billing_profile": self._billing_to_dict(target),
                "moved_job_count": moved_job_count,
            }

    def delete_billing_profile(self, billing_ref: str) -> dict[str, Any]:
        """Delete an unused billing profile."""
        with session_scope() as session:
            row = self._resolve_billing(session, billing_ref)
            if row.jobs:
                raise ValueError(
                    f"Billing profile {row.billing_code} is still in use by {len(row.jobs)} job(s)"
                )
            payload = self._billing_to_dict(row)
            session.delete(row)
            session.flush()
            return {"deleted": True, "billing_profile": payload}

    def billing_usage(self, billing_profile_id: str) -> dict[str, Any]:
        """Summarize jobs linked to one billing profile."""
        with session_scope() as session:
            row = self._resolve_billing(session, billing_profile_id)
            jobs = sorted(row.jobs, key=lambda job: job.job_number)
            return {
                "billing_profile": self._billing_to_dict(row),
                "job_count": len(jobs),
                "job_numbers": [job.job_number for job in jobs],
                "jobs": [
                    {
                        "job_number": job.job_number,
                        "job_id": job.job_id,
                        "customer_code": job.customer.customer_code if job.customer else None,
                        "customer_name": job.customer.name if job.customer else None,
                        "tree_number": job.tree_number,
                        "status": job.status.value,
                    }
                    for job in jobs
                ],
            }
