"""
SSRF protection module.

Known limitations:
SSRF protection validates DNS at request time; hosts other than the primary target can
theoretically rebind between validation and connection. Production deployments should
run capture workers in an egress-restricted network segment.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import Settings
from app.core.errors import SsrfBlockedError

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


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
        raise SsrfBlockedError(f"Blocked by SSRF guard: failed to resolve host {hostname}") from exc

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
        raise SsrfBlockedError(f"Blocked by SSRF guard: host resolved to no addresses {hostname}")
    return ips


def is_blocked_address(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )
