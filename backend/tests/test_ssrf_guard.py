import socket
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import patch

from app.core.config import Settings
from app.core.errors import SsrfBlockedError
from app.core.ssrf_guard import validate_url


def test_validate_url_rejects_disallowed_schemes_without_dns():
    settings = Settings()

    with patch("app.core.ssrf_guard.socket.getaddrinfo") as getaddrinfo:
        for url in ("file:///tmp/page.html", "ftp://example.com", "javascript:alert(1)"):
            try:
                validate_url(url, settings)
            except SsrfBlockedError:
                pass
            else:
                raise AssertionError(f"Expected {url} to be blocked")

    getaddrinfo.assert_not_called()


def test_validate_url_blocks_private_and_non_public_ranges():
    settings = Settings()
    blocked_addresses = [
        "127.0.0.1",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
    ]

    for address in blocked_addresses:
        with mocked_resolution([address]):
            try:
                validate_url("https://example.com", settings)
            except SsrfBlockedError as exc:
                assert "blocked address" in str(exc)
            else:
                raise AssertionError(f"Expected {address} to be blocked")


def test_validate_url_allows_public_address():
    with mocked_resolution(["93.184.216.34"]):
        validate_url("https://example.com", Settings())


def test_validate_url_blocks_obfuscated_addresses_after_resolution():
    settings = Settings()
    obfuscated_resolution_results = [
        "127.0.0.1",
        "127.0.0.1",
        "127.0.0.1",
        "::ffff:127.0.0.1",
    ]

    for resolved_address in obfuscated_resolution_results:
        with mocked_resolution([resolved_address]):
            try:
                validate_url("http://obfuscated.example", settings)
            except SsrfBlockedError:
                pass
            else:
                raise AssertionError(f"Expected {resolved_address} to be blocked")


def test_validate_url_checks_every_resolved_address():
    with mocked_resolution(["93.184.216.34", "10.0.0.5"]):
        try:
            validate_url("https://example.com", Settings())
        except SsrfBlockedError as exc:
            assert "10.0.0.5" in str(exc)
        else:
            raise AssertionError("Expected mixed public/private DNS results to be blocked")


def test_validate_url_fails_closed_on_dns_error():
    with patch(
        "app.core.ssrf_guard.socket.getaddrinfo",
        side_effect=socket.gaierror("not found"),
    ):
        try:
            validate_url("https://missing.example", Settings())
        except SsrfBlockedError as exc:
            assert "failed to resolve" in str(exc)
        else:
            raise AssertionError("Expected DNS failure to be blocked")


def test_validate_url_catches_dns_rebinding_on_second_resolution():
    with patch(
        "app.core.ssrf_guard.socket.getaddrinfo",
        side_effect=[
            make_addrinfos(["93.184.216.34"]),
            make_addrinfos(["10.0.0.5"]),
        ],
    ):
        validate_url("https://example.com", Settings())
        try:
            validate_url("https://example.com/redirected", Settings())
        except SsrfBlockedError as exc:
            assert "10.0.0.5" in str(exc)
        else:
            raise AssertionError("Expected rebound private address to be blocked")


@contextmanager
def mocked_resolution(addresses: list[str]) -> Iterator[None]:
    with patch("app.core.ssrf_guard.socket.getaddrinfo", return_value=make_addrinfos(addresses)):
        yield


def make_addrinfos(addresses: list[str]):
    return [
        (
            socket.AF_INET6 if ":" in address else socket.AF_INET,
            socket.SOCK_STREAM,
            0,
            "",
            (address, 0),
        )
        for address in addresses
    ]
