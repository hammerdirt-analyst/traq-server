"""Server-side customer and tree number allocation and lookup.

Authors: Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

This module manages the customer-scoped tree identifier used operationally by
jobs. It intentionally avoids any GPS or fuzzy matching. The rule is explicit:

- if a customer-scoped tree number is provided, reuse or create that tree
- otherwise allocate the next available tree number for that customer
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db_models import Customer, Tree

_CODE_PREFIX = "C"

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_tree_number(value: Any) -> int | None:
    """Normalize a tree number from imported/final payloads.

    Accepts integers, digit strings, and a small set of spelled-out legacy
    values so existing imported finals can seed the `trees` table.
    """

    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return None
        if text.isdigit():
            parsed = int(text)
            return parsed if parsed > 0 else None
        return _WORD_NUMBERS.get(text)
    return None


def next_tree_number(session: Session, customer: Customer) -> int:
    """Return the next available tree number for a customer."""

    current = session.scalar(
        select(func.max(Tree.tree_number)).where(Tree.customer_id == customer.id)
    )
    return int(current or 0) + 1


def _next_customer_code(session: Session) -> str:
    codes = session.scalars(select(Customer.customer_code)).all()
    max_number = 0
    for code in codes:
        if not code or not str(code).startswith(_CODE_PREFIX):
            continue
        suffix = str(code)[1:]
        if suffix.isdigit():
            max_number = max(max_number, int(suffix))
    return f"{_CODE_PREFIX}{max_number + 1:04d}"


def get_or_create_customer(
    session: Session,
    *,
    name: str,
    phone: str | None = None,
    address: str | None = None,
) -> Customer:
    """Return the reusable customer row for the provided operational identity."""

    row = session.scalar(
        select(Customer).where(
            Customer.name == name,
            Customer.phone.is_(phone) if phone is None else Customer.phone == phone,
            Customer.address.is_(address) if address is None else Customer.address == address,
        )
    )
    if row is None:
        row = Customer(
            customer_code=_next_customer_code(session),
            name=name,
            phone=phone,
            address=address,
        )
        session.add(row)
        session.flush()
    return row


def resolve_tree(session: Session, *, customer: Customer, requested_tree_number: int | None) -> Tree:
    """Return the resolved tree identity for a job.

    If `requested_tree_number` is provided, reuse the matching customer tree if
    present; otherwise create it. If no tree number is provided, allocate the
    next available one.
    """

    tree_number = requested_tree_number or next_tree_number(session, customer)
    row = session.scalar(
        select(Tree).where(Tree.customer_id == customer.id, Tree.tree_number == tree_number)
    )
    if row is None:
        row = Tree(customer=customer, tree_number=tree_number)
        session.add(row)
        session.flush()
    return row


def requested_tree_number_from_form(form_payload: dict[str, Any] | None) -> int | None:
    """Extract a provisional tree number from submitted form payload."""

    if not isinstance(form_payload, dict):
        return None
    data = form_payload.get("data")
    if not isinstance(data, dict):
        return None
    client_tree = data.get("client_tree_details")
    if not isinstance(client_tree, dict):
        return None
    return parse_tree_number(client_tree.get("tree_number"))


def apply_tree_number_to_form(
    form_payload: dict[str, Any] | None,
    tree_number: int | None,
) -> dict[str, Any] | None:
    """Write the authoritative tree number back into form payload data."""

    if not isinstance(form_payload, dict) or tree_number is None:
        return form_payload
    form_copy = dict(form_payload)
    data = dict(form_copy.get("data") or {})
    client_tree = dict(data.get("client_tree_details") or {})
    client_tree["tree_number"] = str(tree_number)
    data["client_tree_details"] = client_tree
    form_copy["data"] = data
    return form_copy
