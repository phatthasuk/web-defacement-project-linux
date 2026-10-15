"""A hostile page must be rejected on resource budgets, not after it has spent them."""

import asyncio
import ipaddress
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.errors import CaptureBudgetExceeded
from app.services.capture.capture import capture_snapshot

# Words, not one long token: an unbroken run would make the page absurdly wide.
_FILLER = (b"lorem ipsum dolor " * 4000)[:65536]
FAST = {"PAGE_STABILIZE_ENABLED": False, "PAGE_TIMEOUT_SECONDS": 5}


def _page(tmp_path: Path, body: str, name: str = "page.html") -> Path:
    page_file = tmp_path / name
    page_file.write_text(f"<!doctype html><body style='margin:0'>{body}", encoding="utf-8")
    return page_file


async def _capture(page_file: Path, tmp_path: Path, **overrides: object):
    settings = Settings(**FAST, **overrides)  # type: ignore[arg-type]
    with patch("app.services.capture.capture.validate_url"):
        return await capture_snapshot(page_file.as_uri(), settings, tmp_path / "out")


async def test_page_within_budget_is_captured(tmp_path: Path) -> None:
    result = await _capture(_page(tmp_path, "<p>Hello</p>"), tmp_path)

    assert result.title == ""
    assert Path(result.screenshot_path).exists()


async def test_page_taller_than_limit_is_rejected(tmp_path: Path) -> None:
    page = _page(tmp_path, "<div style='height:5000px'>tall</div>")

    with pytest.raises(CaptureBudgetExceeded, match="5000px tall"):
        await _capture(page, tmp_path, MAX_SCREENSHOT_HEIGHT_PX=2000)


async def test_screenshot_pixel_count_over_limit_is_rejected(tmp_path: Path) -> None:
    page = _page(tmp_path, "<div style='width:4000px;height:3000px'>big</div>")

    with pytest.raises(CaptureBudgetExceeded, match="pixels"):
        await _capture(page, tmp_path, MAX_SCREENSHOT_PIXELS=5_000_000)


async def test_dom_with_too_many_nodes_is_rejected(tmp_path: Path) -> None:
    page = _page(
        tmp_path,
        "<script>for (let i = 0; i < 5000; i++) document.body.append("
        "document.createElement('i'));</script>",
    )

    with pytest.raises(CaptureBudgetExceeded, match="nodes"):
        await _capture(page, tmp_path, MAX_DOM_NODES=1000)


async def test_page_cannot_hide_its_size_by_overriding_scroll_height(tmp_path: Path) -> None:
    """The measurement comes from the browser, not from script the page controls."""
    page = _page(
        tmp_path,
        "<script>for (const el of [document.documentElement, document.body])"
        " Object.defineProperty(el, 'scrollHeight', {get: () => 0});</script>"
        "<div style='height:5000px'>tall</div>",
    )

    with pytest.raises(CaptureBudgetExceeded, match="tall"):
        await _capture(page, tmp_path, MAX_SCREENSHOT_HEIGHT_PX=2000)


async def _serve(body_size: int) -> tuple[asyncio.Server, int]:
    """A close-delimited HTTP/1.1 response: no Content-Length for the proxy to trust."""

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n")
        writer.write(b"<html><body>")
        try:
            sent = 0
            while sent < body_size:
                writer.write(_FILLER)
                await writer.drain()
                sent += 65536
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


async def _capture_over_http(port: int, tmp_path: Path, **overrides: object):
    settings = Settings(**FAST, **overrides)  # type: ignore[arg-type]
    with (
        patch("app.services.capture.capture.validate_url"),
        patch(
            "app.services.capture.ssrf_proxy.resolve_host_ips",
            return_value=[ipaddress.ip_address("127.0.0.1")],
        ),
        patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False),
    ):
        return await asyncio.wait_for(
            capture_snapshot(f"http://allowed.test:{port}/", settings, tmp_path / "out"),
            timeout=30,
        )


async def test_response_over_transfer_budget_is_rejected_while_streaming(tmp_path: Path) -> None:
    server, port = await _serve(body_size=4 * 1024 * 1024)
    try:
        with pytest.raises(CaptureBudgetExceeded, match="transfer budget"):
            await _capture_over_http(port, tmp_path, MAX_CAPTURE_TRANSFER_MB=1)
    finally:
        server.close()
        await server.wait_closed()
    staging = tmp_path / "out" / "staging"
    assert not staging.exists() or not list(staging.iterdir())


async def test_response_under_transfer_budget_is_captured(tmp_path: Path) -> None:
    server, port = await _serve(body_size=256 * 1024)
    try:
        result = await _capture_over_http(port, tmp_path, MAX_CAPTURE_TRANSFER_MB=1)
    finally:
        server.close()
        await server.wait_closed()

    assert Path(result.html_path).exists()
