import asyncio
import ipaddress
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from playwright.async_api import Error as PlaywrightError

from app.core.config import Settings
from app.services.capture.capture import capture_snapshot

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_page.html"


async def test_capture_snapshot(tmp_path: Path):
    settings = Settings()
    url = FIXTURE_PATH.as_uri()
    out_dir = tmp_path / f"capture-{uuid4()}"

    with patch("app.services.capture.capture.validate_url"):
        result = await capture_snapshot(
            url,
            settings,
            out_dir,
        )

    assert result.title == "Sample Fixture Page"
    assert result.redirect_count == 0

    screenshot_path = Path(result.screenshot_path)
    text_path = Path(result.text_path)
    html_path = Path(result.html_path)

    assert screenshot_path.exists()
    assert text_path.exists()
    assert html_path.exists()

    assert "Sample Fixture Page" in text_path.read_text(encoding="utf-8")
    assert "Sample Fixture Page" in html_path.read_text(encoding="utf-8")


async def test_capture_snapshot_blocks_private_subresource(tmp_path: Path):
    from app.core.errors import SsrfBlockedError
    from app.core.ssrf_guard import validate_url

    settings = Settings()
    out_dir = tmp_path / f"capture-{uuid4()}"

    original_validate_url = validate_url

    def mock_validate_url(test_url: str, settings: Settings):
        if "private-subresource" in test_url:
            raise SsrfBlockedError("Blocked by SSRF guard: private subresource")
        if test_url.startswith("file://"):
            return
        original_validate_url(test_url, settings)

    html_content = """
    <html>
    <body>
        <h1>Hello World</h1>
        <img src="http://private-subresource.example.com/image.png">
    </body>
    </html>
    """
    temp_html = tmp_path / "page_with_subresource.html"
    temp_html.write_text(html_content, encoding="utf-8")
    page_url = temp_html.as_uri()

    with patch("app.services.capture.capture.validate_url", side_effect=mock_validate_url):
        result = await capture_snapshot(
            page_url,
            settings,
            out_dir,
        )

    assert result.redirect_count == 0
    assert Path(result.screenshot_path).exists()


async def test_capture_snapshot_allows_iframes_without_consuming_redirect_limit(tmp_path: Path):
    settings = Settings()
    settings.REDIRECT_LIMIT = 1
    out_dir = tmp_path / f"capture-{uuid4()}"

    iframe_src = tmp_path / "iframe.html"
    iframe_src.write_text("<html><body>Iframe</body></html>", encoding="utf-8")

    main_content = f"""
    <html>
    <body>
        <iframe src="{iframe_src.as_uri()}"></iframe>
        <iframe src="{iframe_src.as_uri()}"></iframe>
    </body>
    </html>
    """
    main_page = tmp_path / "main.html"
    main_page.write_text(main_content, encoding="utf-8")

    def mock_validate_url(test_url: str, settings: Settings):
        return

    with patch("app.services.capture.capture.validate_url", side_effect=mock_validate_url):
        result = await capture_snapshot(
            main_page.as_uri(),
            settings,
            out_dir,
        )

    assert result.redirect_count == 0
    assert Path(result.screenshot_path).exists()


async def test_capture_snapshot_routes_all_requests_through_loopback_proxy(tmp_path: Path):
    settings = Settings()
    url = "http://example.com/page"
    out_dir = tmp_path / f"capture-{uuid4()}"

    # Page stabilisation drives a real browser; this test only asserts the
    # launch arguments, so keep the pipeline out of a fully mocked page.
    settings.PAGE_STABILIZE_ENABLED = False

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_response = AsyncMock()
    mock_page.goto.return_value = mock_response
    mock_page.content.return_value = "<html></html>"
    mock_page.inner_text.return_value = "text"
    mock_page.screenshot.return_value = b"screenshot"
    mock_page.title.return_value = "title"
    mock_page.url = "http://example.com/page"
    mock_response.status = 200
    mock_response.request = AsyncMock()
    mock_response.request.redirected_from = None
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_ap = MagicMock()
    mock_ap.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_ap.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap):
        await capture_snapshot(url, settings, out_dir)

    mock_playwright_instance.chromium.launch.assert_called_once()
    called_kwargs = mock_playwright_instance.chromium.launch.call_args[1]
    assert called_kwargs.get("chromium_sandbox") is True
    assert called_kwargs["proxy"]["server"].startswith("http://127.0.0.1:")


async def test_capture_snapshot_sandbox_configuration(tmp_path: Path):
    settings_enabled = Settings(BROWSER_DISABLE_SANDBOX=False, PAGE_STABILIZE_ENABLED=False)
    settings_disabled = Settings(BROWSER_DISABLE_SANDBOX=True, PAGE_STABILIZE_ENABLED=False)
    url = "http://example.com/page"
    out_dir = tmp_path / f"capture-{uuid4()}"

    def build_mock_ap():
        mock_browser = AsyncMock()
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_response = AsyncMock()
        mock_page.goto.return_value = mock_response
        mock_page.content.return_value = "<html></html>"
        mock_page.inner_text.return_value = "text"
        mock_page.screenshot.return_value = b"screenshot"
        mock_page.title.return_value = "title"
        mock_page.url = url
        mock_response.status = 200
        mock_response.request = AsyncMock()
        mock_response.request.redirected_from = None
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        mock_playwright_instance = MagicMock()
        mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)
        mock_ap = MagicMock()
        mock_ap.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
        mock_ap.__aexit__ = AsyncMock(return_value=None)
        return mock_ap, mock_playwright_instance

    # 1. BROWSER_DISABLE_SANDBOX = False -> chromium_sandbox=True, no --no-sandbox
    mock_ap_1, mock_launch_1 = build_mock_ap()
    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap_1):
        await capture_snapshot(url, settings_enabled, out_dir)

    kwargs_1 = mock_launch_1.chromium.launch.call_args[1]
    assert kwargs_1["chromium_sandbox"] is True
    assert "--no-sandbox" not in kwargs_1["args"]

    # 2. BROWSER_DISABLE_SANDBOX = True -> chromium_sandbox=False, has --no-sandbox
    mock_ap_2, mock_launch_2 = build_mock_ap()
    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap_2):
        await capture_snapshot(url, settings_disabled, out_dir)

    kwargs_2 = mock_launch_2.chromium.launch.call_args[1]
    assert kwargs_2["chromium_sandbox"] is False
    assert "--no-sandbox" in kwargs_2["args"]
    assert "--disable-setuid-sandbox" in kwargs_2["args"]



async def test_capture_does_not_hide_overlay_content(tmp_path: Path):
    """An overlay-shaped defacement must survive into the diffed artifacts.

    Capture used to inject `display: none` for `.modal`, `.modal-backdrop`,
    `[class*="preload"]` and friends. That removed the element from the
    screenshot *and* from inner_text("body"), so a defacement delivered as an
    overlay would have been reported as "no change". Nothing may be hidden.
    """
    settings = Settings()
    out_dir = tmp_path / f"capture-{uuid4()}"

    # Class names taken from the rules that used to hide content, plus a
    # dismiss control that deliberately does not work.
    html_content = """
    <html><body>
      <main><h1>Normal page content</h1></main>
      <div class="modal-backdrop"></div>
      <div class="modal show">
        <button class="btn-close" onclick="return false;">close</button>
        <p>DEFACED-BY-OVERLAY</p>
      </div>
      <div class="preloader"><p>DEFACED-IN-PRELOADER</p></div>
      <div class="loading-overlay"><p>DEFACED-IN-LOADER</p></div>
    </body></html>
    """
    page_file = tmp_path / "overlay_defacement.html"
    page_file.write_text(html_content, encoding="utf-8")

    with patch("app.services.capture.capture.validate_url"):
        result = await capture_snapshot(page_file.as_uri(), settings, out_dir)

    captured_text = Path(result.text_path).read_text(encoding="utf-8")
    assert "DEFACED-BY-OVERLAY" in captured_text
    assert "DEFACED-IN-PRELOADER" in captured_text
    assert "DEFACED-IN-LOADER" in captured_text
    assert "Normal page content" in captured_text


async def test_capture_snapshot_sandbox_failure_does_not_fallback(tmp_path: Path):
    settings = Settings(BROWSER_DISABLE_SANDBOX=False, PAGE_STABILIZE_ENABLED=False)
    url = "http://example.com/page"
    out_dir = tmp_path / f"capture-{uuid4()}"

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch = AsyncMock(
        side_effect=PlaywrightError("Target page, context or browser has been closed (sandboxing)")
    )
    mock_ap = MagicMock()
    mock_ap.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_ap.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap):
        try:
            await capture_snapshot(url, settings, out_dir)
        except PlaywrightError as exc:
            assert "sandboxing" in str(exc)
        else:
            raise AssertionError("Expected launch error to be raised without fallback")

    assert mock_playwright_instance.chromium.launch.call_count == 1


async def _start_http_fixture(handler):
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def test_capture_redirect_preserves_final_url_and_relative_resources(tmp_path: Path):
    requests: list[str] = []

    async def fixture(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                request = (await reader.readuntil(b"\r\n\r\n")).decode("iso-8859-1")
                path = request.split(" ", 2)[1]
                requests.append(path)
                if path == "/start":
                    response = (
                        b"HTTP/1.1 302 Found\r\nLocation: /folder/page\r\n"
                        b"Content-Length: 0\r\n\r\n"
                    )
                elif path == "/folder/image.png":
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: image/png\r\n"
                        b"Content-Length: 0\r\n\r\n"
                    )
                else:
                    body = b"<html><body>redirected<img src='image.png'></body></html>"
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        + f"Content-Length: {len(body)}\r\n\r\n".encode()
                        + body
                    )
                writer.write(response)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    server, port = await _start_http_fixture(fixture)
    try:
        with patch("app.services.capture.capture.validate_url"), \
             patch("app.services.capture.ssrf_proxy.resolve_host_ips", return_value=[
                 ipaddress.ip_address("127.0.0.1")
             ]), \
             patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False):
            result = await capture_snapshot(
                f"http://allowed.test:{port}/start",
                Settings(PAGE_STABILIZE_ENABLED=False),
                tmp_path,
            )
    finally:
        server.close()
        await server.wait_closed()

    assert result.final_url == f"http://allowed.test:{port}/folder/page"
    assert result.redirect_count == 1
    captured_text = Path(result.text_path).read_text(encoding="utf-8")
    assert "redirected" in captured_text
    assert "/folder/page" in requests
    assert "/folder/image.png" in requests


async def test_capture_blocks_redirect_before_destination_receives_request(tmp_path: Path):
    blocked_requests = 0

    async def blocked_fixture(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal blocked_requests
        blocked_requests += 1
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        writer.close()

    blocked_server, blocked_port = await _start_http_fixture(blocked_fixture)

    async def allowed_fixture(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        await reader.readuntil(b"\r\n\r\n")
        location = f"http://blocked.test:{blocked_port}/private"
        writer.write(
            b"HTTP/1.1 302 Found\r\n"
            + f"Location: {location}\r\n".encode()
            + b"Content-Length: 0\r\n\r\n"
        )
        await writer.drain()
        writer.close()

    allowed_server, allowed_port = await _start_http_fixture(allowed_fixture)

    def validate(test_url: str, _settings: Settings) -> None:
        from app.core.errors import SsrfBlockedError

        if "blocked.test" in test_url:
            raise SsrfBlockedError("Blocked by SSRF guard: blocked.test")

    try:
        with patch("app.services.capture.capture.validate_url", side_effect=validate), \
             patch("app.services.capture.ssrf_proxy.resolve_host_ips", return_value=[
                 ipaddress.ip_address("127.0.0.1")
             ]), \
             patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False):
            try:
                await capture_snapshot(
                    f"http://allowed.test:{allowed_port}/start",
                    Settings(PAGE_STABILIZE_ENABLED=False),
                    tmp_path,
                )
            except Exception as exc:
                from app.core.errors import SsrfBlockedError

                assert isinstance(exc, SsrfBlockedError)
            else:
                raise AssertionError("Expected redirect to a blocked destination to fail")
    finally:
        allowed_server.close()
        blocked_server.close()
        await allowed_server.wait_closed()
        await blocked_server.wait_closed()

    assert blocked_requests == 0


async def test_capture_blocks_redirect_hop_beyond_configured_limit(tmp_path: Path):
    requests: list[str] = []

    async def fixture(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            while True:
                request = (await reader.readuntil(b"\r\n\r\n")).decode("iso-8859-1")
                path = request.split(" ", 2)[1]
                requests.append(path)
                next_path = {"/start": "/hop-1", "/hop-1": "/hop-2"}.get(path)
                if next_path:
                    response = (
                        b"HTTP/1.1 302 Found\r\n"
                        + f"Location: {next_path}\r\n".encode()
                        + b"Content-Length: 0\r\n\r\n"
                    )
                else:
                    body = b"<html><body>too far</body></html>"
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        + f"Content-Length: {len(body)}\r\n\r\n".encode()
                        + body
                    )
                writer.write(response)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    server, port = await _start_http_fixture(fixture)
    try:
        with patch("app.services.capture.capture.validate_url"), \
             patch("app.services.capture.ssrf_proxy.resolve_host_ips", return_value=[
                 ipaddress.ip_address("127.0.0.1")
             ]), \
             patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False):
            try:
                await capture_snapshot(
                    f"http://allowed.test:{port}/start",
                    Settings(PAGE_STABILIZE_ENABLED=False, REDIRECT_LIMIT=1),
                    tmp_path,
                )
            except Exception as exc:
                from app.core.errors import SsrfBlockedError

                assert isinstance(exc, SsrfBlockedError)
                assert "redirect limit exceeded" in str(exc)
            else:
                raise AssertionError("Expected redirect limit to stop the second hop")
    finally:
        server.close()
        await server.wait_closed()

    assert "/start" in requests
    assert "/hop-1" in requests
    assert "/hop-2" not in requests


async def test_capture_guards_popup_first_request_and_redirect(tmp_path: Path):
    allowed_requests: list[str] = []
    blocked_requests = 0

    async def blocked_fixture(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal blocked_requests
        blocked_requests += 1
        await reader.readuntil(b"\r\n\r\n")
        writer.close()

    blocked_server, blocked_port = await _start_http_fixture(blocked_fixture)

    async def allowed_fixture(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                request = (await reader.readuntil(b"\r\n\r\n")).decode("iso-8859-1")
                path = request.split(" ", 2)[1]
                allowed_requests.append(path)
                if path == "/popup":
                    response = (
                        b"HTTP/1.1 302 Found\r\n"
                        + f"Location: http://blocked.test:{blocked_port}/private\r\n".encode()
                        + b"Content-Length: 0\r\n\r\n"
                    )
                else:
                    body = b"<html><body><script>window.open('/popup')</script>main</body></html>"
                    response = (
                        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                        + f"Content-Length: {len(body)}\r\n\r\n".encode()
                        + body
                    )
                writer.write(response)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    allowed_server, allowed_port = await _start_http_fixture(allowed_fixture)

    def validate(test_url: str, _settings: Settings) -> None:
        from app.core.errors import SsrfBlockedError

        if "blocked.test" in test_url:
            raise SsrfBlockedError("Blocked by SSRF guard: blocked.test")

    try:
        with patch("app.services.capture.capture.validate_url", side_effect=validate), \
             patch("app.services.capture.ssrf_proxy.resolve_host_ips", return_value=[
                 ipaddress.ip_address("127.0.0.1")
             ]), \
             patch("app.services.capture.ssrf_proxy.is_blocked_address", return_value=False):
            await capture_snapshot(
                f"http://allowed.test:{allowed_port}/",
                Settings(PAGE_STABILIZE_ENABLED=False, PAGE_EXTRA_WAIT_MS=100),
                tmp_path,
            )
            await asyncio.sleep(0.1)
    finally:
        allowed_server.close()
        blocked_server.close()
        await allowed_server.wait_closed()
        await blocked_server.wait_closed()

    assert "/popup" in allowed_requests
    assert blocked_requests == 0


async def test_capture_proxy_blocks_rebound_private_ip_at_connection_time(tmp_path: Path):
    destination_connections = 0

    async def destination(
        _reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal destination_connections
        destination_connections += 1
        writer.close()

    server, port = await _start_http_fixture(destination)
    try:
        # The route-level check represents an earlier public DNS answer. The
        # proxy resolves again immediately before connect and sees a private IP.
        with patch("app.services.capture.capture.validate_url"), \
             patch(
                 "app.services.capture.ssrf_proxy.resolve_host_ips",
                 return_value=[ipaddress.ip_address("127.0.0.1")],
             ):
            try:
                await capture_snapshot(
                    f"http://rebound.test:{port}/",
                    Settings(PAGE_STABILIZE_ENABLED=False),
                    tmp_path,
                )
            except Exception as exc:
                from app.core.errors import SsrfBlockedError

                assert isinstance(exc, SsrfBlockedError)
                assert "blocked address" in str(exc)
            else:
                raise AssertionError("Expected the connection-time IP check to block the request")
    finally:
        server.close()
        await server.wait_closed()

    assert destination_connections == 0


async def test_capture_snapshot_cleans_staging_on_failure_during_write(tmp_path: Path):
    settings = Settings()
    url = FIXTURE_PATH.as_uri()
    out_dir = tmp_path / f"capture-fail-{uuid4()}"

    created_staging_dirs: list[Path] = []
    original_mkdir = Path.mkdir

    def track_mkdir(self, *args, **kwargs):
        original_mkdir(self, *args, **kwargs)
        if "staging" in self.parts and len(self.parts) > 1:
            created_staging_dirs.append(self)

    with patch("app.services.capture.capture.validate_url"), \
         patch.object(Path, "write_text", side_effect=OSError("Simulated disk error")), \
         patch.object(Path, "mkdir", track_mkdir):
        try:
            await capture_snapshot(url, settings, out_dir)
        except OSError:
            pass
        else:
            raise AssertionError("Expected OSError")

    # Staging snapshot directory should be cleaned up (no lingering files or subdirectories)
    staging_parent = out_dir / "staging"
    if staging_parent.exists():
        assert list(staging_parent.iterdir()) == []


async def test_capture_snapshot_cleans_staging_when_browser_close_is_cancelled(tmp_path: Path):
    settings = Settings()
    url = FIXTURE_PATH.as_uri()
    out_dir = tmp_path / f"capture-close-cancel-{uuid4()}"

    async def cancel_close(*args, **kwargs):
        raise asyncio.CancelledError("cancelled while closing browser")

    with patch("app.services.capture.capture.validate_url"), \
         patch("playwright.async_api.Browser.close", new=cancel_close):
        with pytest.raises(asyncio.CancelledError):
            await capture_snapshot(url, settings, out_dir)

    staging_parent = out_dir / "staging"
    if staging_parent.exists():
        assert list(staging_parent.iterdir()) == []


async def test_capture_snapshot_cleans_staging_when_proxy_exit_is_cancelled(tmp_path: Path):
    settings = Settings()
    url = FIXTURE_PATH.as_uri()
    out_dir = tmp_path / f"capture-proxy-exit-cancel-{uuid4()}"

    from app.services.capture.ssrf_proxy import SsrfProxy

    original_exit = SsrfProxy.__aexit__

    async def cancel_after_proxy_close(self, *exc):
        await original_exit(self, *exc)
        raise asyncio.CancelledError("cancelled while exiting SSRF proxy")

    with patch("app.services.capture.capture.validate_url"), \
         patch.object(SsrfProxy, "__aexit__", new=cancel_after_proxy_close):
        with pytest.raises(asyncio.CancelledError):
            await capture_snapshot(url, settings, out_dir)

    staging_parent = out_dir / "staging"
    if staging_parent.exists():
        assert list(staging_parent.iterdir()) == []


async def test_capture_snapshot_blocks_file_subresource_from_remote_target(tmp_path: Path):
    settings = Settings()
    url = "http://example.com/page"
    out_dir = tmp_path / f"capture-{uuid4()}"
    settings.PAGE_STABILIZE_ENABLED = False

    mock_browser = AsyncMock()
    mock_context = AsyncMock()
    mock_page = AsyncMock()
    mock_response = AsyncMock()
    mock_page.goto.return_value = mock_response
    mock_page.content.return_value = "<html></html>"
    mock_page.inner_text.return_value = "text"
    mock_page.screenshot.return_value = b"screenshot"
    mock_page.title.return_value = "title"
    mock_page.url = "http://example.com/page"
    mock_response.status = 200
    mock_response.request = AsyncMock()
    mock_response.request.redirected_from = None
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    mock_playwright_instance = MagicMock()
    mock_playwright_instance.chromium.launch = AsyncMock(return_value=mock_browser)

    mock_ap = MagicMock()
    mock_ap.__aenter__ = AsyncMock(return_value=mock_playwright_instance)
    mock_ap.__aexit__ = AsyncMock(return_value=None)

    guard_handler = None

    async def capture_route(pattern, handler):
        nonlocal guard_handler
        if pattern == "**/*":
            guard_handler = handler

    mock_context.route = AsyncMock(side_effect=capture_route)

    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap):
        await capture_snapshot(url, settings, out_dir)

    assert guard_handler is not None

    # Test file:// subresource from remote target -> must be aborted
    mock_route = AsyncMock()
    mock_request = MagicMock()
    mock_request.url = "file:///etc/passwd"
    mock_request.is_navigation_request.return_value = False

    await guard_handler(mock_route, mock_request)
    mock_route.abort.assert_called_once()
    mock_route.continue_.assert_not_called()

    # Test data: / blob: / about: subresources -> allowed
    mock_route.reset_mock()
    mock_request.url = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    await guard_handler(mock_route, mock_request)
    mock_route.continue_.assert_called_once()
    mock_route.abort.assert_not_called()
