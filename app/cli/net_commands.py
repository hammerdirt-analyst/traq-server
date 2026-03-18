"""Network utility command handlers for the admin CLI."""

from __future__ import annotations

import argparse
import re
import subprocess
from ipaddress import ip_address
from typing import Callable


JsonPrinter = Callable[[object], None]


def _collect_ipv4_candidates() -> list[dict[str, str]]:
    """Collect likely non-loopback IPv4 addresses from the local host."""
    candidates: list[dict[str, str]] = []
    try:
        output = subprocess.check_output(["ip", "-4", "addr", "show"], text=True)
    except Exception:
        return candidates
    iface = ""
    for line in output.splitlines():
        header = re.match(r"^\d+:\s+([^:]+):", line)
        if header:
            iface = header.group(1).strip()
            continue
        inet = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)\b", line)
        if not inet:
            continue
        addr = inet.group(1)
        if addr.startswith("127."):
            continue
        scope = "global" if "scope global" in line else "other"
        dynamic = "yes" if "dynamic" in line else "no"
        rank = 0
        try:
            parsed = ip_address(addr)
            if parsed.is_private:
                rank += 10
            if not parsed.is_loopback:
                rank += 2
        except ValueError:
            pass
        if scope == "global":
            rank += 5
        if dynamic == "yes":
            rank += 1
        candidates.append(
            {
                "interface": iface,
                "ipv4": addr,
                "prefix": inet.group(2),
                "scope": scope,
                "dynamic": dynamic,
                "rank": str(rank),
            }
        )
    candidates.sort(key=lambda r: int(r["rank"]), reverse=True)
    return candidates


def _collect_ipv6_candidates() -> list[dict[str, str]]:
    """Collect likely global IPv6 addresses from the local host."""
    candidates: list[dict[str, str]] = []
    try:
        output = subprocess.check_output(["ip", "-6", "addr", "show"], text=True)
    except Exception:
        return candidates
    iface = ""
    for line in output.splitlines():
        header = re.match(r"^\d+:\s+([^:]+):", line)
        if header:
            iface = header.group(1).strip()
            continue
        inet6 = re.search(r"\binet6\s+([0-9a-fA-F:]+)/(\d+)\b", line)
        if not inet6:
            continue
        addr = inet6.group(1).lower()
        if addr == "::1" or addr.startswith("fe80:"):
            continue
        scope = "global" if "scope global" in line else "other"
        temporary = "yes" if "temporary" in line else "no"
        dynamic = "yes" if "dynamic" in line else "no"
        rank = 0
        if scope == "global":
            rank += 10
        if temporary == "yes":
            rank += 2
        if dynamic == "yes":
            rank += 1
        candidates.append(
            {
                "interface": iface,
                "ipv6": addr,
                "prefix": inet6.group(2),
                "scope": scope,
                "temporary": temporary,
                "dynamic": dynamic,
                "rank": str(rank),
            }
        )
    candidates.sort(key=lambda r: int(r["rank"]), reverse=True)
    return candidates


def cmd_net_ipv4(args: argparse.Namespace, *, print_json: JsonPrinter) -> int:
    """Show likely IPv4 addresses for configuring mobile clients."""
    rows = _collect_ipv4_candidates()
    try:
        concise = subprocess.check_output(["hostname", "-I"], text=True).strip()
    except Exception:
        concise = ""
    payload = {
        "ok": True,
        "note": "Use the top non-loopback IPv4 as Device Host IP in the mobile app.",
        "ipv4_candidates": rows,
        "hostname_I": concise,
    }
    if args.json:
        print_json(payload)
        return 0
    print("Likely IPv4 addresses (best first):")
    if not rows:
        print("  none found")
    for idx, row in enumerate(rows, start=1):
        print(
            f" {idx}. {row['ipv4']}/{row['prefix']} "
            f"iface={row['interface']} scope={row['scope']} dynamic={row['dynamic']}"
        )
    if concise:
        print(f"hostname -I: {concise}")
    return 0


def cmd_net_ipv6(args: argparse.Namespace, *, print_json: JsonPrinter) -> int:
    """Show likely IPv6 addresses for configuring mobile clients."""
    rows = _collect_ipv6_candidates()
    payload = {
        "ok": True,
        "note": "Use the top global IPv6 as Device Host IP. In URLs use brackets: http://[IPv6]:8000",
        "ipv6_candidates": rows,
    }
    if args.json:
        print_json(payload)
        return 0
    print("Likely IPv6 addresses (best first):")
    if not rows:
        print("  none found")
    for idx, row in enumerate(rows, start=1):
        print(
            f" {idx}. {row['ipv6']}/{row['prefix']} "
            f"iface={row['interface']} scope={row['scope']} temporary={row['temporary']} dynamic={row['dynamic']}"
        )
    print("URL form: http://[IPv6]:8000")
    return 0


def register_net_commands(subparsers, handlers: dict[str, Callable[[argparse.Namespace], int]]) -> None:
    """Register network utility commands."""
    net_cmd = subparsers.add_parser("net", help="Network utilities")
    net_sub = net_cmd.add_subparsers(dest="net_cmd", required=True)

    ipv4_cmd = net_sub.add_parser("ipv4", help="Show likely server IPv4 addresses for client settings")
    ipv4_cmd.add_argument("--json", action="store_true")
    ipv4_cmd.set_defaults(func=handlers["ipv4"])

    ipv6_cmd = net_sub.add_parser("ipv6", help="Show likely server IPv6 addresses for client settings")
    ipv6_cmd.add_argument("--json", action="store_true")
    ipv6_cmd.set_defaults(func=handlers["ipv6"])
