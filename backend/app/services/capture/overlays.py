"""Dismiss consent banners and promo modals before capturing a page.

A PDPA/GDPR cookie banner or a promo popup covers real content and appears or
disappears depending on stored consent, so leaving it up produces pixel diffs
that have nothing to do with defacement. Nearly every Thai site shows one, which
makes this one of the largest sources of false positives.

This module only *clears the view* and reports what it dismissed. Deciding
whether a dismissal excuses a diff (and whether to re-baseline because of it) is
deliberately out of scope — see plan/archive/auto-rebaseline.md, which keeps that
decision out of the capture path because auto-re-baselining can mask a real
defacement.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from playwright.async_api import Frame, Locator, Page

logger = logging.getLogger(__name__)

__all__ = ["OverlayDismissal", "dismiss_overlays"]

# Patterns and selectors are combined into a single alternation / selector list
# each, because probing them one at a time costs a full click timeout per miss —
# roughly 40s on any page without an overlay, paid on every check.
#
# Thai first: most targets are Thai-language sites.
_ACCEPT_NAME_RE = re.compile(
    "|".join(
        (
            r"ยอมรับทั้งหมด",
            r"ยอมรับ",
            r"ตกลง",
            r"ยินยอม",
            r"accept all",
            r"allow all",
            r"accept",
            r"agree",
            r"got it",
        )
    ),
    re.IGNORECASE,
)

# Vendor-specific accept buttons, used when role+name matching fails.
_ACCEPT_SELECTOR = ", ".join(
    (
        "button.cky-btn-accept",
        ".cky-consent-container .cky-btn-accept",
        "[data-cky-tag='accept-button']",
        "button#cookieyes-accept-all",
        "#cookieyes-accept-all",
        "#onetrust-accept-btn-handler",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "#CybotCookiebotDialogBodyButtonAccept",
        "[aria-label*='accept' i]",
    )
)

_CONSENT_CONTAINER_SELECTORS: Sequence[str] = (
    ".cky-consent-container",
    ".cky-overlay",
    "#cookieyes-banner",
    "[id*='cookieyes' i]",
    "#onetrust-banner-sdk",
    "#onetrust-pc-sdk",
    ".ot-sdk-container",
    "#CybotCookiebotDialog",
    "#CookiebotWidget",
    "#cookie-notice",
    ".cookie-banner",
)

_CLOSE_NAME_RE = re.compile(
    "|".join((r"ปิด", r"ไม่สนใจ", r"close", r"dismiss", r"×")),
    re.IGNORECASE,
)

_CLOSE_SELECTOR = ", ".join(
    (
        "[data-bs-dismiss='modal']",
        ".modal .btn-close",
        ".modal .close",
        "button.btn-close",
        ".mfp-close",
        ".swal2-close",
        ".modal.show [aria-label*='close' i]",
    )
)

_PROMO_CONTAINER_SELECTORS: Sequence[str] = (
    ".modal",
    ".modal-backdrop",
    ".mfp-wrap",
    ".mfp-bg",
    ".swal2-container",
)

_CLICK_TIMEOUT_MS = 800
_SETTLE_MS = 300


@dataclass(frozen=True)
class OverlayDismissal:
    """What was dismissed. Reported only; nothing in the check logic reads it yet."""

    cookie_dismissed: bool = False
    promo_closed: bool = False

    @property
    def changed_page(self) -> bool:
        return self.cookie_dismissed or self.promo_closed


async def _try_click(locator: Locator, scope: Page | Frame) -> bool:
    """Click the first match, if there is one.

    `count()` resolves immediately, so an absent overlay costs one round trip
    instead of the full click timeout. Only a real match pays for waiting.
    """
    try:
        if await locator.count() == 0:
            return False
        await locator.first.click(timeout=_CLICK_TIMEOUT_MS)
        await scope.wait_for_timeout(_SETTLE_MS)
        return True
    except Exception:
        return False


async def _click_anywhere(page: Page, name_pattern: re.Pattern[str], selector: str) -> bool:
    """Try the main page, then every frame — consent UIs are often in an iframe."""
    scopes: list[Page | Frame] = [page, *page.frames]
    for scope in scopes:
        try:
            by_role = scope.get_by_role("button", name=name_pattern)
            if await _try_click(by_role, scope):
                return True
            if await _try_click(scope.locator(selector), scope):
                return True
        except Exception:
            continue
    return False


async def _wait_gone(page: Page, selectors: Sequence[str], timeout_ms: int = 3_000) -> None:
    """Wait for containers to actually disappear, not just for the click to land."""
    try:
        await page.wait_for_function(
            """
            (selectors) => selectors.every((selector) => {
              const nodes = [...document.querySelectorAll(selector)];
              return nodes.length === 0 || nodes.every((el) => el.offsetParent === null);
            })
            """,
            arg=list(selectors),
            timeout=timeout_ms,
        )
    except Exception:
        logger.debug("Overlay containers still present after dismissal")


async def dismiss_overlays(page: Page) -> OverlayDismissal:
    """Dismiss consent banners and promo modals by clicking their own controls.

    Nothing is ever hidden with injected CSS. Hiding an element with
    `display: none` removes it from the screenshot *and* from
    `inner_text("body")`, so a defacement delivered as an overlay — an injected
    `.modal` announcing the compromise, say — would disappear from both diffed
    artifacts and the check would report the page as unchanged. Clicking a
    dismiss control cannot cause that: if the click fails the overlay simply
    stays in the capture, which is honest.

    An overlay that will not close therefore becomes part of the page's normal
    appearance. That is stable rather than harmful: every capture uses a fresh
    browser context, so the same banner appears in the baseline and in every
    later snapshot and cancels out of the diff.

    Never raises: an overlay that cannot be dismissed must not fail the capture,
    since a partially covered screenshot is still worth more than no snapshot.
    """
    cookie_dismissed = False
    promo_closed = False

    try:
        cookie_dismissed = await _click_anywhere(page, _ACCEPT_NAME_RE, _ACCEPT_SELECTOR)
    except Exception:
        logger.debug("Cookie-consent dismissal raised", exc_info=True)

    if cookie_dismissed:
        logger.debug("Cookie consent accepted")
        await _wait_gone(page, _CONSENT_CONTAINER_SELECTORS)

    try:
        promo_closed = await _click_anywhere(page, _CLOSE_NAME_RE, _CLOSE_SELECTOR)
    except Exception:
        logger.debug("Promo dismissal raised", exc_info=True)

    if promo_closed:
        logger.debug("Promo overlay closed")
        await _wait_gone(page, _PROMO_CONTAINER_SELECTORS)

    return OverlayDismissal(
        cookie_dismissed=cookie_dismissed,
        promo_closed=promo_closed,
    )
