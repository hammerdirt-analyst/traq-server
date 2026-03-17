"""Customer and billing admin CLI command handlers."""

from __future__ import annotations

import argparse
from typing import Any, Callable


CustomerServiceFactory = Callable[[], Any]
JsonPrinter = Callable[[object], None]


def _parse_search(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _wrap(action: Callable[[], object], print_json: JsonPrinter) -> int:
    try:
        payload = action()
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print_json(payload)
    return 0


def cmd_customer_list(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().list_customers(search=_parse_search(args.search)), print_json)


def cmd_customer_duplicates(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().customer_duplicates(), print_json)


def cmd_customer_create(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().create_customer(
            name=args.name,
            phone=args.phone,
            address=args.address,
        ),
        print_json,
    )


def cmd_customer_update(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().update_customer(
            args.customer_id,
            name=args.name,
            phone=args.phone,
            address=args.address,
        ),
        print_json,
    )


def cmd_customer_usage(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().customer_usage(args.customer_id), print_json)


def cmd_customer_merge(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().merge_customer(
            args.customer_id,
            target_customer_id=args.into,
        ),
        print_json,
    )


def cmd_customer_delete(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().delete_customer(args.customer_id), print_json)


def cmd_billing_list(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().list_billing_profiles(search=_parse_search(args.search)), print_json)


def cmd_billing_duplicates(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().billing_duplicates(), print_json)


def cmd_billing_create(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().create_billing_profile(
            billing_name=args.billing_name,
            billing_contact_name=args.billing_contact_name,
            billing_address=args.billing_address,
            contact_preference=args.contact_preference,
        ),
        print_json,
    )


def cmd_billing_update(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().update_billing_profile(
            args.billing_profile_id,
            billing_name=args.billing_name,
            billing_contact_name=args.billing_contact_name,
            billing_address=args.billing_address,
            contact_preference=args.contact_preference,
        ),
        print_json,
    )


def cmd_billing_usage(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().billing_usage(args.billing_profile_id), print_json)


def cmd_billing_merge(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(
        lambda: service_factory().merge_billing_profile(
            args.billing_profile_id,
            target_billing_profile_id=args.into,
        ),
        print_json,
    )


def cmd_billing_delete(args: argparse.Namespace, *, service_factory: CustomerServiceFactory, print_json: JsonPrinter) -> int:
    return _wrap(lambda: service_factory().delete_billing_profile(args.billing_profile_id), print_json)


def register_customer_commands(subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]]) -> None:
    """Register customer and billing command groups."""
    customer = subparsers.add_parser("customer", help="Customer and billing operations")
    customer_sub = customer.add_subparsers(dest="customer_cmd", required=True)

    list_cmd = customer_sub.add_parser("list", help="List reusable customers")
    list_cmd.add_argument("--search")
    list_cmd.set_defaults(func=handlers["customer_list"])

    dup_cmd = customer_sub.add_parser("duplicates", help="List duplicate customer-name candidates")
    dup_cmd.set_defaults(func=handlers["customer_duplicates"])

    create_cmd = customer_sub.add_parser("create", help="Create a reusable customer")
    create_cmd.add_argument("--name", required=True)
    create_cmd.add_argument("--phone")
    create_cmd.add_argument("--address")
    create_cmd.set_defaults(func=handlers["customer_create"])

    update_cmd = customer_sub.add_parser("update", help="Update a reusable customer")
    update_cmd.add_argument("customer_id")
    update_cmd.add_argument("--name")
    update_cmd.add_argument("--phone")
    update_cmd.add_argument("--address")
    update_cmd.set_defaults(func=handlers["customer_update"])

    usage_cmd = customer_sub.add_parser("usage", help="Show jobs and trees linked to a customer")
    usage_cmd.add_argument("customer_id")
    usage_cmd.set_defaults(func=handlers["customer_usage"])

    merge_cmd = customer_sub.add_parser("merge", help="Merge one customer into another")
    merge_cmd.add_argument("customer_id", help="source customer_id")
    merge_cmd.add_argument("--into", required=True, help="target customer_id")
    merge_cmd.set_defaults(func=handlers["customer_merge"])

    delete_cmd = customer_sub.add_parser("delete", help="Delete an unused customer")
    delete_cmd.add_argument("customer_id", help="customer_id or customer_code")
    delete_cmd.set_defaults(func=handlers["customer_delete"])

    billing_cmd = customer_sub.add_parser("billing", help="Billing profile operations")
    billing_sub = billing_cmd.add_subparsers(dest="billing_cmd", required=True)

    billing_list_cmd = billing_sub.add_parser("list", help="List billing profiles")
    billing_list_cmd.add_argument("--search")
    billing_list_cmd.set_defaults(func=handlers["billing_list"])

    billing_dup_cmd = billing_sub.add_parser("duplicates", help="List duplicate billing-name candidates")
    billing_dup_cmd.set_defaults(func=handlers["billing_duplicates"])

    billing_create_cmd = billing_sub.add_parser("create", help="Create a billing profile")
    billing_create_cmd.add_argument("--billing-name")
    billing_create_cmd.add_argument("--billing-contact-name")
    billing_create_cmd.add_argument("--billing-address")
    billing_create_cmd.add_argument("--contact-preference")
    billing_create_cmd.set_defaults(func=handlers["billing_create"])

    billing_update_cmd = billing_sub.add_parser("update", help="Update a billing profile")
    billing_update_cmd.add_argument("billing_profile_id")
    billing_update_cmd.add_argument("--billing-name")
    billing_update_cmd.add_argument("--billing-contact-name")
    billing_update_cmd.add_argument("--billing-address")
    billing_update_cmd.add_argument("--contact-preference")
    billing_update_cmd.set_defaults(func=handlers["billing_update"])

    billing_usage_cmd = billing_sub.add_parser("usage", help="Show jobs linked to a billing profile")
    billing_usage_cmd.add_argument("billing_profile_id")
    billing_usage_cmd.set_defaults(func=handlers["billing_usage"])

    billing_merge_cmd = billing_sub.add_parser("merge", help="Merge one billing profile into another")
    billing_merge_cmd.add_argument("billing_profile_id", help="source billing_profile_id")
    billing_merge_cmd.add_argument("--into", required=True, help="target billing_profile_id")
    billing_merge_cmd.set_defaults(func=handlers["billing_merge"])

    billing_delete_cmd = billing_sub.add_parser("delete", help="Delete an unused billing profile")
    billing_delete_cmd.add_argument("billing_profile_id", help="billing_profile_id or billing_code")
    billing_delete_cmd.set_defaults(func=handlers["billing_delete"])
