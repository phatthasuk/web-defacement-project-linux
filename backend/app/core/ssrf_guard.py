"""
SSRF protection module.

Validates URLs against permitted schemes and rejects non-public, loopback,
link-local, multicast, RFC 6598 CGNAT / cloud overlay, and RFC 2544 benchmark addresses.
Connection-time DNS rebinding protection is enforced at the socket level by SsrfProxy.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import DnsResolutionError, SsrfBlockedError

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

BLOCKED_SPECIAL_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),  # RFC 6598 Shared Address Space / CGNAT / Cloud Overlays
    ipaddress.ip_network("198.18.0.0/15"),  # RFC 2544 Network Interconnect Device Benchmark
)


def validate_url(url: str, settings: Settings) -> None:
    parsed = validate_scheme(url, settings)
    if parsed.hostname is None:
        raise SsrfBlockedError(f"Blocked by SSRF guard: URL has no hostname: {url}")

    ips = resolve_host_ips(parsed.hostname)
    for ip in ips:
        if is_blocked_address(ip):
            raise SsrfBlockedError(
                f"Blocked by SSRF guard: {parsed.hostname} resolved to blocked address {ip}"
            )


def validate_scheme(url: str, settings: Settings):
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    allowed_schemes = {allowed.lower() for allowed in settings.allowed_schemes_list}
    if scheme not in allowed_schemes:
        raise SsrfBlockedError(f"Blocked by SSRF guard: URL scheme is not allowed: {scheme}")
    return parsed


def resolve_host_ips(hostname: str) -> list[IPAddress]:
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise DnsResolutionError(f"DNS resolution failed for host {hostname}") from exc

    ips: list[IPAddress] = []
    seen: set[IPAddress] = set()
    for addrinfo in addrinfos:
        raw_address = addrinfo[4][0]
        try:
            ip = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise SsrfBlockedError(
                f"Blocked by SSRF guard: resolver returned invalid address {raw_address}"
            ) from exc
        if ip not in seen:
            seen.add(ip)
            ips.append(ip)

    if not ips:
        raise DnsResolutionError(f"Host resolved to no addresses: {hostname}")
    return ips


def is_blocked_address(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True

    return any(ip in net for net in BLOCKED_SPECIAL_NETWORKS)
