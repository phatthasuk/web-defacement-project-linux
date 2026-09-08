import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Request, Route, WebSocketRoute, async_playwright

from app.core.config import Settings
from app.core.errors import CaptureError, SsrfBlockedError
from app.core.ssrf_guard import is_blocked_address, resolve_host_ips, validate_url
from app.services.capture.overlays import OverlayDismissal, dismiss_overlays
from app.services.capture.page_ready import (
    SCROLL_NEUTRALISER_SCRIPT,
    WaitPageOptions,
    pin_for_capture,
    wait_page_ready,
)

logger = logging.getLogger(__name__)


@dataclass
class CaptureResult:
    id: str
    url: str
    final_url: str
    http_status: int | None
    title: str | None
    screenshot_path: str
    text_path: str
    html_path: str
    redirect_count: int
    # What the capture had to clear away, and how long stabilisation took.
    # Reported for diagnostics; no check decision reads these yet.
    overlays: OverlayDismissal = field(default_factory=OverlayDismissal)
    readiness: dict[str, int | bool] = field(default_factory=dict)
    staging_dir: str = ""


def build_wait_options(settings: Settings) -> WaitPageOptions:
    return WaitPageOptions(
        load_timeout_ms=settings.PAGE_TIMEOUT_SECONDS * 1000,
        network_quiet_ms=settings.PAGE_NETWORK_QUIET_MS,
        network_max_wait_ms=settings.PAGE_NETWORK_MAX_WAIT_MS,
        visible_content_timeout_ms=settings.PAGE_VISIBLE_CONTENT_TIMEOUT_MS,
        extra_wait_ms=settings.PAGE_EXTRA_WAIT_MS,
    )


async def capture_snapshot(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
    validate_url(url, settings)
    snapshot_id = str(uuid.uuid4())
    max_bytes = settings.MAX_ARTIFACT_SIZE_MB * 1024 * 1024

    hostname = urlparse(url).hostname
    launch_args: list[str] = []
    if settings.BROWSER_DISABLE_SANDBOX:
        # Only for containers that cannot run the sandbox. Requires compensating
        # isolation (non-root, read-only fs, no internal network reachability).
        logger.warning("Chromium sandbox disabled by configuration")
        launch_args += ["--no-sandbox", "--disable-setuid-sandbox"]

    if hostname:
        ips = resolve_host_ips(hostname)
        for ip in ips:
            if is_blocked_address(ip):
                raise SsrfBlockedError(
                    f"Blocked by SSRF guard: {hostname} resolved to blocked address {ip}"
                )
        pinned_ip = str(ips[0])
        launch_args.append(f"--host-resolver-rules=MAP {hostname} {pinned_ip}")

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch(
                args=launch_args,
                chromium_sandbox=not settings.BROWSER_DISABLE_SANDBOX,
            )
        except Exception as launch_err:
            err_msg = str(launch_err).lower()
            if "sandboxing" in err_msg or "closed" in err_msg:
                logger.warning(
                    "Chromium sandbox launch failed, falling back to --no-sandbox: %s",
                    launch_err,
                )
                fallback_args = list(launch_args)
                for arg in ["--no-sandbox", "--disable-setuid-sandbox"]:
                    if arg not in fallback_args:
                        fallback_args.append(arg)
                browser = await playwright.chromium.launch(
                    args=fallback_args,
                    chromium_sandbox=False,
                )
            else:
                raise
        try:
            # An explicit context is needed to block service workers, which can
            # otherwise issue requests that escape page.route() and so bypass
            # the SSRF guard below.
            context = await browser.new_context(
                service_workers="block",
                viewport={
                    "width": settings.VIEWPORT_WIDTH,
                    "height": settings.VIEWPORT_HEIGHT,
                },
                reduced_motion="reduce",
            )
            await context.add_init_script(SCROLL_NEUTRALISER_SCRIPT)
            page = await context.new_page()
            navigation_request_count = 0
            blocked_error: SsrfBlockedError | None = None
            hostname_cache: dict[str, bool] = {}

            def get_hostname(test_url: str) -> str | None:
                try:
                    return urlparse(test_url).hostname
                except Exception:
                    return None

            async def is_url_safe(test_url: str) -> bool:
                if test_url.startswith(("data:", "blob:")):
                    return True
                hostname = get_hostname(test_url)
                if hostname is not None and hostname in hostname_cache:
                    return hostname_cache[hostname]
                try:
                    await asyncio.to_thread(validate_url, test_url, settings)
                    if hostname is not None:
                        hostname_cache[hostname] = True
                    return True
                except SsrfBlockedError:
                    if hostname is not None:
                        hostname_cache[hostname] = False
                    return False

            async def guard_navigation(route: Route, request: Request) -> None:
                nonlocal navigation_request_count, blocked_error

                # SSRF guard validation
                is_safe = await is_url_safe(request.url)
                if not is_safe:
                    if request.is_navigation_request():
                        blocked_error = SsrfBlockedError(f"Blocked by SSRF guard: {request.url}")
                    await route.abort()
                    return

                # Main frame navigation tracking
                if request.is_navigation_request():
                    if request.frame == page.main_frame:
                        navigation_request_count += 1
                        redirects_seen = navigation_request_count - 1
                        if redirects_seen > settings.REDIRECT_LIMIT:
                            blocked_error = SsrfBlockedError(
                                "Blocked by SSRF guard: redirect limit exceeded "
                                f"{redirects_seen} > {settings.REDIRECT_LIMIT}"
                            )
                            await route.abort()
                            return

                await route.continue_()

            await page.route("**/*", guard_navigation)

            if settings.BLOCK_WEBSOCKETS:
                # Registered before navigation so it is in place before any page
                # script runs. Observing via page.on("websocket") would not
                # prevent the connection, only report it.
                async def block_websocket(ws: WebSocketRoute) -> None:
                    logger.warning("Blocked WebSocket connection during capture: %s", ws.url)
                    await ws.close()

                await page.route_web_socket("**/*", block_websocket)

            try:
                # Navigate only as far as domcontentloaded, then hand over to
                # wait_page_ready, which freezes animations and settles layout.
                # "networkidle" alone returns while carousels are still moving.
                response = await page.goto(
                    url,
                    timeout=settings.PAGE_TIMEOUT_SECONDS * 1000,
                    wait_until="domcontentloaded",
                )
            except PlaywrightError as exc:
                if blocked_error is not None:
                    raise blocked_error from exc
                raise

            overlays = OverlayDismissal()
            readiness: dict[str, int | bool] = {}
            if settings.PAGE_STABILIZE_ENABLED:
                wait_options = build_wait_options(settings)
                readiness = await wait_page_ready(page, wait_options)

                if settings.DISMISS_OVERLAYS:
                    overlays = await dismiss_overlays(page)
                    if overlays.changed_page:
                        # Dismissing reflows the page, so settle it again before
                        # capturing. Skip the slow phases: the page is warm now.
                        readiness = await wait_page_ready(
                            page,
                            WaitPageOptions(
                                load_timeout_ms=wait_options.load_timeout_ms,
                                network_quiet=False,
                                visible_content_timeout_ms=1_000,
                                extra_wait_ms=min(wait_options.extra_wait_ms, 500),
                            ),
                        )

            redirect_count = 0
            request = response.request if response else None
            while request is not None and request.redirected_from is not None:
                redirect_count += 1
                request = request.redirected_from
            if redirect_count > settings.REDIRECT_LIMIT:
                raise CaptureError(
                    f"Redirect limit exceeded: {redirect_count} > {settings.REDIRECT_LIMIT}"
                )

            html = await page.content()
            if len(html.encode("utf-8")) > max_bytes:
                raise CaptureError("Captured HTML exceeds MAX_ARTIFACT_SIZE_MB")

            text = await page.inner_text("body")
            if len(text.encode("utf-8")) > max_bytes:
                raise CaptureError("Captured text exceeds MAX_ARTIFACT_SIZE_MB")

            if settings.PAGE_STABILIZE_ENABLED:
                # Last-moment pin: timer-driven sliders drift during the waits
                # above, so re-pin with nothing left to run before the shutter.
                await pin_for_capture(page)

            screenshot_bytes = await page.screenshot(full_page=True)
            if len(screenshot_bytes) > max_bytes:
                raise CaptureError("Captured screenshot exceeds MAX_ARTIFACT_SIZE_MB")

            title = await page.title()
            final_url = page.url
            http_status = response.status if response else None

            staging_dir = out_dir / "staging" / snapshot_id
            screenshot_path = staging_dir / f"{snapshot_id}.png"
            text_path = staging_dir / f"{snapshot_id}.txt"
            html_path = staging_dir / f"{snapshot_id}.html"

            staging_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path.write_bytes(screenshot_bytes)
            text_path.write_text(text, encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
        finally:
            await browser.close()

    return CaptureResult(
        id=snapshot_id,
        url=url,
        final_url=final_url,
        http_status=http_status,
        title=title,
        screenshot_path=str(screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=redirect_count,
        overlays=overlays,
        readiness=readiness,
        staging_dir=str(staging_dir),
    )
