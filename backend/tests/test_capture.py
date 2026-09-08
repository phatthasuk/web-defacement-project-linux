import ipaddress
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

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


async def test_capture_snapshot_pins_ip_via_host_resolver_rules(tmp_path: Path):
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

    resolved_ips = [ipaddress.ip_address("93.184.216.34")]
    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.resolve_host_ips", return_value=resolved_ips), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap):
        await capture_snapshot(url, settings, out_dir)

    mock_playwright_instance.chromium.launch.assert_called_once()
    called_kwargs = mock_playwright_instance.chromium.launch.call_args[1]
    called_args = called_kwargs["args"]
    assert "--host-resolver-rules=MAP example.com 93.184.216.34" in called_args
    assert called_kwargs.get("chromium_sandbox") is True


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

    resolved_ips = [ipaddress.ip_address("93.184.216.34")]

    # 1. BROWSER_DISABLE_SANDBOX = False -> chromium_sandbox=True, no --no-sandbox
    mock_ap_1, mock_launch_1 = build_mock_ap()
    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.resolve_host_ips", return_value=resolved_ips), \
         patch("app.services.capture.capture.async_playwright", return_value=mock_ap_1):
        await capture_snapshot(url, settings_enabled, out_dir)

    kwargs_1 = mock_launch_1.chromium.launch.call_args[1]
    assert kwargs_1["chromium_sandbox"] is True
    assert "--no-sandbox" not in kwargs_1["args"]

    # 2. BROWSER_DISABLE_SANDBOX = True -> chromium_sandbox=False, has --no-sandbox
    mock_ap_2, mock_launch_2 = build_mock_ap()
    with patch("app.services.capture.capture.validate_url"), \
         patch("app.services.capture.capture.resolve_host_ips", return_value=resolved_ips), \
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
