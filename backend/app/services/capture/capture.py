import asyncio
import json
import logging
import shutil
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Request, Route, WebSocketRoute, async_playwright

from app.core.config import Settings
from app.core.errors import (
    CaptureError,
    DnsResolutionError,
    SsrfBlockedError,
    UpstreamConnectionError,
)
from app.core.ssrf_guard import validate_url
from app.services.capture.overlays import OverlayDismissal
from app.services.capture.page_ready import (
    SCROLL_NEUTRALISER_SCRIPT,
    WaitPageOptions,
    pin_for_capture,
    wait_page_ready,
)
from app.services.capture.ssrf_proxy import SsrfProxy

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


def _navigation_redirect_document(target_url: str) -> str:
    """Turn a server redirect into a new browser navigation intercepted by routing.

    Playwright does not route server-generated redirect hops. Capture navigation
    requests are GETs, so replacing the location keeps their redirect semantics
    while making every hop pass through the guard before it can connect.
    """
    script_url = json.dumps(target_url)
    return "<!doctype html><meta charset=utf-8>" f"<script>location.replace({script_url})</script>"


def _redirect_key(url: str) -> tuple[str, str, int | None, str, str]:
    parsed = urlsplit(url)
    return (
        parsed.scheme.lower(),
        (parsed.hostname or "").lower(),
        parsed.port,
        parsed.path or "/",
        parsed.query,
    )


def build_wait_options(settings: Settings) -> WaitPageOptions:
    return WaitPageOptions(
        load_timeout_ms=settings.PAGE_TIMEOUT_SECONDS * 1000,
        network_quiet_ms=settings.PAGE_NETWORK_QUIET_MS,
        network_max_wait_ms=settings.PAGE_NETWORK_MAX_WAIT_MS,
        visible_content_timeout_ms=settings.PAGE_VISIBLE_CONTENT_TIMEOUT_MS,
        extra_wait_ms=settings.PAGE_EXTRA_WAIT_MS,
    )


async def capture_snapshot(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
    """Capture a page and retain staging only after the complete lifecycle succeeds."""
    snapshot_id = str(uuid.uuid4())
    staging_dir = out_dir / "staging" / snapshot_id
    completed = False
    try:
        result = await _capture_snapshot_impl(url, settings, out_dir, snapshot_id)
        completed = True
        return result
    finally:
        # Context-manager shutdown happens after browser.close(). If cancellation
        # lands there, no CaptureResult reaches the caller and this function still
        # owns the staging directory.
        if not completed and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


async def _capture_snapshot_impl(
    url: str,
    settings: Settings,
    out_dir: Path,
    snapshot_id: str,
) -> CaptureResult:
    validate_url(url, settings)
    max_bytes = settings.MAX_ARTIFACT_SIZE_MB * 1024 * 1024
    staging_dir: Path | None = None
    capture_succeeded = False

    launch_args: list[str] = []
    if settings.BROWSER_DISABLE_SANDBOX:
        # Only for containers that cannot run the sandbox. Requires compensating
        # isolation (non-root, read-only fs, no internal network reachability).
        logger.warning("Chromium sandbox disabled by configuration")
        launch_args += ["--no-sandbox", "--disable-setuid-sandbox"]

    async with SsrfProxy(settings) as ssrf_proxy, async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            args=launch_args,
            chromium_sandbox=not settings.BROWSER_DISABLE_SANDBOX,
            proxy=ssrf_proxy.playwright_proxy,
        )
        try:
            # An explicit context is needed to block service workers, which can
            # otherwise issue requests that escape context.route() and so bypass
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

            blocked_error: SsrfBlockedError | None = None
            availability_error: DnsResolutionError | UpstreamConnectionError | None = None
            capture_error: CaptureError | None = None
            main_redirect_count = 0
            pending_redirect_depths: dict[
                tuple[str, str, int | None, str, str], deque[int]
            ] = defaultdict(deque)
            main_navigation_complete = asyncio.Event()
            final_http_status: int | None = None

            def is_main_navigation(request: Request) -> bool:
                if not request.is_navigation_request():
                    return False
                try:
                    frame = request.frame
                    return frame == page.main_frame or (
                        frame.parent_frame is None and frame.page == page
                    )
                except PlaywrightError:
                    # Popup navigation can start before its frame exists.  It is
                    # still guarded and gets its own redirect-chain limit, but it
                    # is not the capture's main document.
                    return False

            def redirect_depth(request: Request) -> int:
                depth = 0
                previous = request.redirected_from
                while previous is not None:
                    depth += 1
                    previous = previous.redirected_from
                return depth

            async def guard_navigation(route: Route, request: Request) -> None:
                nonlocal blocked_error, availability_error, capture_error
                nonlocal final_http_status, main_redirect_count

                url_to_check = request.url
                main_navigation = is_main_navigation(request)

                # In-memory browser schemes never open an external socket.
                if url_to_check.startswith(("data:", "blob:", "about:")):
                    await route.continue_()
                    return

                # Local file scheme is permitted ONLY if the initial target URL itself
                # is a local file URL (e.g. offline test fixtures), never when monitoring
                # an external HTTP/HTTPS target.
                if url_to_check.startswith("file://"):
                    if url.startswith("file://"):
                        await route.continue_()
                        return
                    logger.warning(
                        "Blocked file:// subresource from remote target: %s", url_to_check
                    )
                    await route.abort()
                    return

                # SSRF guard validation before connection
                try:
                    await asyncio.to_thread(validate_url, url_to_check, settings)
                except SsrfBlockedError as exc:
                    if main_navigation:
                        blocked_error = exc
                        main_navigation_complete.set()
                    await route.abort()
                    return
                except DnsResolutionError as exc:
                    if main_navigation:
                        availability_error = exc
                        main_navigation_complete.set()
                    await route.abort()
                    return
                except Exception as exc:
                    if main_navigation:
                        capture_error = CaptureError(f"Request validation failed: {exc}")
                        main_navigation_complete.set()
                    await route.abort()
                    return

                redirect_key = _redirect_key(url_to_check)
                queued_depths = pending_redirect_depths.get(redirect_key)
                redirects_seen = (
                    queued_depths.popleft()
                    if queued_depths
                    else redirect_depth(request)
                )
                if queued_depths is not None and not queued_depths:
                    pending_redirect_depths.pop(redirect_key, None)
                if request.is_navigation_request() and redirects_seen > settings.REDIRECT_LIMIT:
                    error = SsrfBlockedError(
                        "Blocked by SSRF guard: redirect limit exceeded "
                        f"{redirects_seen} > {settings.REDIRECT_LIMIT}"
                    )
                    if main_navigation:
                        blocked_error = error
                        main_navigation_complete.set()
                    await route.abort()
                    return

                # Fetch exactly one response through the validating proxy. For a
                # navigation, a 3xx becomes a fresh browser navigation so routing
                # sees every hop. Resource redirects remain browser-managed, but
                # every connection still has to pass through the proxy.
                try:
                    response = await route.fetch(max_redirects=0)
                except Exception as exc:
                    # Pop even for subresources so a stale rejection cannot be
                    # attributed to a later request to the same host.
                    proxy_rejection = ssrf_proxy.pop_rejection(url_to_check)
                    if main_navigation:
                        if isinstance(proxy_rejection, SsrfBlockedError):
                            blocked_error = proxy_rejection
                        elif isinstance(
                            proxy_rejection, DnsResolutionError | UpstreamConnectionError
                        ):
                            availability_error = proxy_rejection
                        elif isinstance(proxy_rejection, CaptureError):
                            capture_error = proxy_rejection
                        else:
                            capture_error = CaptureError(f"Guarded request failed: {exc}")
                        main_navigation_complete.set()
                    await route.abort()
                    return

                proxy_rejection = ssrf_proxy.pop_rejection(url_to_check)
                if proxy_rejection is not None:
                    if main_navigation:
                        if isinstance(proxy_rejection, SsrfBlockedError):
                            blocked_error = proxy_rejection
                        elif isinstance(
                            proxy_rejection, DnsResolutionError | UpstreamConnectionError
                        ):
                            availability_error = proxy_rejection
                        else:
                            capture_error = CaptureError(str(proxy_rejection))
                        main_navigation_complete.set()
                    await route.abort()
                    return

                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if location:
                        target_url = urljoin(url_to_check, location)
                        if redirects_seen >= settings.REDIRECT_LIMIT:
                            error = SsrfBlockedError(
                                "Blocked by SSRF guard: redirect limit exceeded "
                                f"{redirects_seen + 1} > {settings.REDIRECT_LIMIT}"
                            )
                            if main_navigation:
                                blocked_error = error
                                main_navigation_complete.set()
                            await route.abort()
                            return
                        try:
                            await asyncio.to_thread(validate_url, target_url, settings)
                        except SsrfBlockedError as exc:
                            if main_navigation:
                                blocked_error = exc
                                main_navigation_complete.set()
                            await route.abort()
                            return
                        except DnsResolutionError as exc:
                            if main_navigation:
                                availability_error = exc
                                main_navigation_complete.set()
                            await route.abort()
                            return
                        except Exception as exc:
                            if main_navigation:
                                capture_error = CaptureError(
                                    f"Redirect validation failed: {exc}"
                                )
                                main_navigation_complete.set()
                            await route.abort()
                            return

                        if request.is_navigation_request():
                            next_depth = redirects_seen + 1
                            pending_redirect_depths[_redirect_key(target_url)].append(next_depth)
                            if main_navigation:
                                main_redirect_count = next_depth
                            await route.fulfill(
                                status=200,
                                headers={
                                    "cache-control": "no-store",
                                    "content-type": "text/html; charset=utf-8",
                                },
                                body=_navigation_redirect_document(target_url),
                            )
                            return

                await route.fulfill(response=response)
                if main_navigation:
                    main_redirect_count = max(main_redirect_count, redirects_seen)
                    final_http_status = response.status
                    main_navigation_complete.set()

            await context.route("**/*", guard_navigation)

            if settings.BLOCK_WEBSOCKETS:
                async def block_websocket(ws: WebSocketRoute) -> None:
                    logger.warning("Blocked WebSocket connection during capture: %s", ws.url)
                    await ws.close()

                await context.route_web_socket("**/*", block_websocket)

            page = await context.new_page()

            try:
                # Navigate only as far as domcontentloaded, then hand over to
                # wait_page_ready, which freezes animations and settles layout.
                # "networkidle" alone returns while carousels are still moving.
                response = await page.goto(
                    url,
                    timeout=settings.PAGE_TIMEOUT_SECONDS * 1000,
                    wait_until="domcontentloaded",
                )
                if main_redirect_count > 0 and not main_navigation_complete.is_set():
                    await asyncio.wait_for(
                        main_navigation_complete.wait(),
                        timeout=float(settings.PAGE_TIMEOUT_SECONDS),
                    )
                if blocked_error is not None:
                    raise blocked_error
                if availability_error is not None:
                    raise availability_error
                if capture_error is not None:
                    raise capture_error
            except PlaywrightError as exc:
                if blocked_error is not None:
                    raise blocked_error from exc
                if availability_error is not None:
                    raise availability_error from exc
                if capture_error is not None:
                    raise capture_error from exc
                raise

            overlays = OverlayDismissal()
            readiness: dict[str, int | bool] = {}
            if settings.PAGE_STABILIZE_ENABLED:
                wait_options = build_wait_options(settings)
                readiness = await wait_page_ready(page, wait_options)

                # Page-controlled dismissal handlers can erase defacement.
                # Preserve overlays in every artifact used by the detectors.

            redirect_count = max(
                redirect_depth(response.request) if response else 0,
                main_redirect_count,
            )
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
            http_status = final_http_status if final_http_status is not None else (
                response.status if response else None
            )

            staging_dir = out_dir / "staging" / snapshot_id
            screenshot_path = staging_dir / f"{snapshot_id}.png"
            text_path = staging_dir / f"{snapshot_id}.txt"
            html_path = staging_dir / f"{snapshot_id}.html"

            staging_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path.write_bytes(screenshot_bytes)
            text_path.write_text(text, encoding="utf-8")
            html_path.write_text(html, encoding="utf-8")
            capture_succeeded = True
        finally:
            try:
                await browser.close()
            except BaseException:
                # No CaptureResult reaches the caller when shutdown is cancelled
                # or fails, so staged artifacts must be reclaimed here.
                if staging_dir and staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)
                raise
            finally:
                if not capture_succeeded and staging_dir and staging_dir.exists():
                    shutil.rmtree(staging_dir, ignore_errors=True)

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
