import asyncio
import json
import logging
import math
import shutil
import uuid
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from PIL import Image
from playwright.async_api import (
    BrowserContext,
    Page,
    Request,
    Route,
    WebSocketRoute,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError

from app.core.config import Settings
from app.core.errors import (
    CaptureBudgetExceeded,
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
from app.services.check_progress import set_phase, skip_phase

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
    # The raw artifact retains all document overflow for forensic review. The
    # regular screenshot is clipped to the configured viewport before it is
    # compared or shown in the application.
    raw_screenshot_path: str | None = None
    viewport_width: int | None = None
    document_width: int | None = None
    screenshot_format_version: int | None = None
    retry_after: str | None = None


def _crop_screenshot_to_viewport(
    screenshot_bytes: bytes,
    viewport_width: int,
) -> tuple[bytes, int, int]:
    """Return a PNG cropped to the viewport, plus raw image dimensions.

    Full-page Chromium screenshots include horizontal document overflow. That is
    useful evidence, but it must not expand the visual-diff canvas beyond the
    fixed viewport used to render every capture.
    """
    with Image.open(BytesIO(screenshot_bytes)) as image:
        raw_width, raw_height = image.size
        cropped = image.crop((0, 0, min(raw_width, viewport_width), raw_height))
        output = BytesIO()
        cropped.save(output, format="PNG")
    return output.getvalue(), raw_width, raw_height


async def _enforce_render_budget(context: BrowserContext, page: Page, settings: Settings) -> None:
    """Reject a page whose DOM or full-page bitmap is larger than the budget.

    The numbers come from the browser (CDP), not from page JavaScript, so a
    hostile page cannot understate them. This runs before the DOM is serialised
    and before a full-page screenshot is allocated.
    """
    session = await context.new_cdp_session(page)
    try:
        layout = await session.send("Page.getLayoutMetrics")
        counters = await session.send("Memory.getDOMCounters")
    finally:
        with suppress(PlaywrightError):
            await session.detach()

    content = layout.get("cssContentSize") or layout["contentSize"]
    width = math.ceil(content["width"])
    height = math.ceil(content["height"])
    nodes = int(counters["nodes"])
    if nodes > settings.MAX_DOM_NODES:
        raise CaptureBudgetExceeded(
            f"Page DOM has {nodes} nodes, over the limit of {settings.MAX_DOM_NODES}"
        )
    if height > settings.MAX_SCREENSHOT_HEIGHT_PX:
        raise CaptureBudgetExceeded(
            f"Page is {height}px tall, over the limit of {settings.MAX_SCREENSHOT_HEIGHT_PX}px"
        )
    if width * height > settings.MAX_SCREENSHOT_PIXELS:
        raise CaptureBudgetExceeded(
            f"Page screenshot would be {width}x{height}px, over the limit of "
            f"{settings.MAX_SCREENSHOT_PIXELS} pixels"
        )


def _navigation_redirect_document(target_url: str) -> str:
    """Turn a server redirect into a new browser navigation intercepted by routing.

    Playwright does not route server-generated redirect hops. Capture navigation
    requests are GETs, so replacing the location keeps their redirect semantics
    while making every hop pass through the guard before it can connect.
    """
    script_url = (
        json.dumps(target_url)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
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

    launch_args: list[str] = [
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--enforce-webrtc-ip-handling-policy",
    ]
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
                tuple[bool, tuple[str, str, int | None, str, str]], deque[int]
            ] = defaultdict(deque)
            main_navigation_complete = asyncio.Event()
            final_http_status: int | None = None
            final_document_url: str | None = None
            final_retry_after: str | None = None
            main_navigation_generation = 0

            def raise_navigation_error() -> None:
                if blocked_error is not None:
                    raise blocked_error
                if availability_error is not None:
                    raise availability_error
                if capture_error is not None:
                    raise capture_error

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
                nonlocal final_http_status, final_document_url, final_retry_after
                nonlocal main_redirect_count, main_navigation_generation

                url_to_check = request.url
                main_navigation = is_main_navigation(request)
                if main_navigation:
                    main_navigation_complete.clear()

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

                redirect_key = (
                    request.is_navigation_request(),
                    _redirect_key(url_to_check),
                )
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
                        elif isinstance(proxy_rejection, CaptureError):
                            capture_error = proxy_rejection
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
                            pending_redirect_depths[
                                (True, _redirect_key(target_url))
                            ].append(next_depth)
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
                    final_document_url = request.url
                    final_retry_after = response.headers.get("retry-after")
                    main_navigation_generation += 1
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
                set_phase("opening_page")
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
                raise_navigation_error()
                completed_navigation_generation = main_navigation_generation
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
                set_phase("waiting_page_ready")
                readiness = await wait_page_ready(page, wait_options)
                raise_navigation_error()
                if main_navigation_generation != completed_navigation_generation:
                    raise CaptureError("Main document navigated again while the page was settling")

                # Page-controlled dismissal handlers can erase defacement.
                # Preserve overlays in every artifact used by the detectors.
            else:
                skip_phase("waiting_page_ready")

            set_phase("capturing")

            redirect_count = max(
                redirect_depth(response.request) if response else 0,
                main_redirect_count,
            )
            if redirect_count > settings.REDIRECT_LIMIT:
                raise CaptureError(
                    f"Redirect limit exceeded: {redirect_count} > {settings.REDIRECT_LIMIT}"
                )

            if ssrf_proxy.budget_error is not None:
                raise ssrf_proxy.budget_error
            await _enforce_render_budget(context, page, settings)

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

            # The budget could have been spent while the page settled or while
            # the DOM was read; re-measure now that nothing else will run.
            if ssrf_proxy.budget_error is not None:
                raise ssrf_proxy.budget_error
            await _enforce_render_budget(context, page, settings)

            raw_screenshot_bytes = await page.screenshot(full_page=True)
            if ssrf_proxy.budget_error is not None:
                raise ssrf_proxy.budget_error
            if len(raw_screenshot_bytes) > max_bytes:
                raise CaptureError("Captured screenshot exceeds MAX_ARTIFACT_SIZE_MB")
            screenshot_bytes, raw_width, _ = _crop_screenshot_to_viewport(
                raw_screenshot_bytes,
                settings.VIEWPORT_WIDTH,
            )

            title = await page.title()
            final_url = page.url
            raise_navigation_error()
            if main_navigation_generation != completed_navigation_generation:
                raise CaptureError("Main document navigated while capture artifacts were collected")
            if final_document_url and _redirect_key(final_url) != _redirect_key(final_document_url):
                raise CaptureError(
                    "Main document navigated while capture artifacts were being collected"
                )
            http_status = final_http_status if final_http_status is not None else (
                response.status if response else None
            )

            staging_dir = out_dir / "staging" / snapshot_id
            screenshot_path = staging_dir / f"{snapshot_id}.png"
            raw_screenshot_path = staging_dir / f"{snapshot_id}.raw.png"
            text_path = staging_dir / f"{snapshot_id}.txt"
            html_path = staging_dir / f"{snapshot_id}.html"

            staging_dir.mkdir(parents=True, exist_ok=True)

            screenshot_path.write_bytes(screenshot_bytes)
            raw_screenshot_path.write_bytes(raw_screenshot_bytes)
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
        raw_screenshot_path=str(raw_screenshot_path),
        text_path=str(text_path),
        html_path=str(html_path),
        redirect_count=redirect_count,
        overlays=overlays,
        readiness=readiness,
        staging_dir=str(staging_dir),
        viewport_width=settings.VIEWPORT_WIDTH,
        document_width=raw_width,
        screenshot_format_version=2,
        retry_after=final_retry_after,
    )
