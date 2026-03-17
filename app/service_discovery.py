"""Local service discovery advertisement for the TRAQ demo server.

Authors:
    Roger Erismann (https://hammerdirt.solutions), OpenAI Codex

Purpose:
    Advertises the running server on the local network via mDNS / DNS-SD so
    mobile clients can discover it without manually typing the laptop IP.

Notes:
    - Current implementation advertises non-loopback IPv4 addresses only.
    - Service type is `_traq._tcp.local.`
    - TXT metadata is intentionally small and non-sensitive.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import threading
from dataclasses import dataclass

try:
    from zeroconf import IPVersion, ServiceInfo, Zeroconf
except ImportError:  # pragma: no cover - optional runtime dependency guard
    IPVersion = None
    ServiceInfo = None
    Zeroconf = None


SERVICE_TYPE = "_traq._tcp.local."


@dataclass(frozen=True)
class DiscoveryConfig:
    port: int = 8000
    service_name: str = "TRAQ Server"
    instance_name: str = ""


def _ipv4_addresses() -> list[bytes]:
    """Return non-loopback IPv4 addresses encoded for zeroconf."""
    candidates: list[str] = []
    seen: set[str] = set()

    def add_ip(ip: str) -> None:
        if not ip or ip.startswith("127.") or ip in seen:
            return
        seen.add(ip)
        candidates.append(ip)

    hostname = socket.gethostname()
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        infos = []
    for info in infos:
        add_ip(info[4][0])

    try:
        _, _, host_ips = socket.gethostbyname_ex(hostname)
    except OSError:
        host_ips = []
    for ip in host_ips:
        add_ip(ip)

    # Linux fallback: hostname -I reliably reports current LAN IPv4 addresses.
    if not candidates:
        try:
            output = subprocess.run(
                ["hostname", "-I"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
        except Exception:
            output = ""
        for token in output.split():
            if "." in token:
                add_ip(token.strip())

    if not candidates:
        try:
            output = subprocess.run(
                ["ip", "-4", "addr", "show", "scope", "global"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
        except Exception:
            output = ""
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("inet "):
                continue
            ip = line.split()[1].split("/")[0].strip()
            add_ip(ip)

    return [socket.inet_aton(ip) for ip in candidates]


class ServiceDiscoveryAdvertiser:
    """Advertise the TRAQ service over mDNS for local client discovery."""

    def __init__(self, config: DiscoveryConfig, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start_in_background(self) -> None:
        """Start advertisement on a daemon thread so app startup never blocks."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._start_logged,
                name="traq-mdns-advertiser",
                daemon=True,
            )
            self._thread.start()

    def _start_logged(self) -> None:
        """Start advertisement and log failures without raising to callers."""
        try:
            self.start()
        except Exception:
            self._logger.exception("[DISCOVERY] background advertisement failed")

    def start(self) -> bool:
        """Start zeroconf advertisement if a usable LAN address exists."""
        if Zeroconf is None or ServiceInfo is None or IPVersion is None:
            self._logger.info("[DISCOVERY] zeroconf not installed; advertisement skipped")
            return False
        addresses = _ipv4_addresses()
        if not addresses:
            self._logger.info("[DISCOVERY] no non-loopback IPv4 address available; advertisement skipped")
            return False
        instance = self._config.instance_name.strip() or socket.gethostname()
        service_instance = f"{self._config.service_name} ({instance}).{SERVICE_TYPE}"
        properties = {
            b"name": self._config.service_name.encode("utf-8"),
            b"instance": instance.encode("utf-8"),
            b"api": b"v1",
        }
        self._zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self._info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=service_instance,
            addresses=addresses,
            port=self._config.port,
            properties=properties,
            server=f"{instance}.local.",
        )
        self._zeroconf.register_service(self._info)
        advertised = ", ".join(socket.inet_ntoa(addr) for addr in addresses)
        self._logger.info(
            "[DISCOVERY] advertised service=%s port=%s addresses=%s",
            service_instance,
            self._config.port,
            advertised,
        )
        return True

    def stop(self) -> None:
        """Stop zeroconf advertisement and release resources."""
        if self._zeroconf is None:
            return
        try:
            if self._info is not None:
                self._zeroconf.unregister_service(self._info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
            self._info = None
            self._logger.info("[DISCOVERY] advertisement stopped")
