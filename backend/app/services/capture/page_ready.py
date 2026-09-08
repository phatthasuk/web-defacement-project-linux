"""Make a page visually stable before it is captured.

A screenshot taken as soon as the network goes idle is not reproducible: CSS
animations, carousels, lazy images and late-loading webfonts all keep moving, so
two captures of an *unchanged* page differ at the pixel level and the monitor
reports a change that never happened. Those false positives are the main reason
a defacement monitor stops being trusted.

`wait_page_ready` therefore does more than wait — it actively freezes the page:
animations and transitions are disabled, carousels and videos are paused, lazy
images are forced to load and decode, and layout is polled until it stops
moving.

One thing it must never do is hide anything. `display: none` removes content
from the screenshot *and* from `inner_text("body")`, so hiding an element by a
generic class name would let a defacement using that class disappear from both
diffed artifacts. Every rule here either stops motion or makes content more
visible.

Ported from the `visual-checker` prototype (see plan/archive/capture-improvements.md).
"""

import asyncio
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from urllib.parse import urlparse

from playwright.async_api import Frame, Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)

__all__ = ["WaitPageOptions", "pin_for_capture", "wait_page_ready"]


@dataclass(frozen=True)
class WaitPageOptions:
    # Waits
    load_timeout_ms: int = 30_000
    network_quiet: bool = True
    network_quiet_ms: int = 1_200
    network_max_wait_ms: int = 15_000
    visible_content_timeout_ms: int = 5_000
    extra_wait_ms: int = 1_000
    # Heuristics
    visible_min_wh: int = 40
    reduced_motion: bool = True
    apply_css_patch: bool = True
    # Scroll the page end to end before capturing, to trigger lazy loading and
    # scroll-reveal animations, then return to the top.
    prescroll: bool = True
    prescroll_step_pause_ms: int = 120
    prescroll_max_steps: int = 60
    # Layout stabilisation
    stabilize_selector: str = "main"
    stabilize_window_ms: int = 400
    stabilize_max_ms: int = 3_000


# Broad enough that virtually any real page (or a plain test fixture) matches,
# because this is a readiness signal, not a content assertion.
_MAIN_CONTENT_SELECTORS = (
    "main",
    "[role='main']",
    "#main",
    "#content",
    "#sp-main-body",
    "#sp-component",
    ".sppb-section",
    "article",
    "body",
)

# Nothing here may hide an element. `display: none` drops content from the
# screenshot *and* from inner_text("body"), so hiding — even something as
# innocuous-looking as `[class*="preload"]` or `.modal` — would let a defacement
# carrying that class name vanish from both diffed artifacts. Every rule below
# either stops motion or makes content *more* visible.
_FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  animation-play-state: paused !important;
  transition: none !important;
  scroll-behavior: auto !important;
}
html, body { overflow-anchor: none !important; }
/* Reveal-on-scroll libraries (AOS, WOW, ScrollReveal, SP Page Builder) park an
   element at opacity:0 and a translate offset until it enters the viewport, then
   transition it in. With transitions frozen above, anything not yet revealed
   would stay invisible forever — and whether it revealed at all depends on how
   far the page happened to scroll, which is exactly the nondeterminism that
   produces phantom visual diffs. Pin them to their final, revealed state. */
[data-aos], .aos-init, .aos-animate, .wow, .animate__animated,
.sppb-animated, [data-animate], [data-sr], [data-scroll-reveal],
[class*="reveal" i], [class*="fade-in" i], [class*="slide-in" i],
[class*="appear" i] {
  opacity: 1 !important;
  visibility: visible !important;
  transform: none !important;
  filter: none !important;
}
/* Pin simple carousel tracks to their first slide. `.swiper-wrapper` is
   deliberately excluded: Swiper positions each slide with its own transform, so
   blanking only the track leaves the slides scattered. Swiper is rewound
   through its own API in _PIN_FOR_CAPTURE_SCRIPT instead. */
.slick-track, .owl-stage, .carousel-inner {
  transform: none !important;
}
"""

# Runs before any page script, so the page cannot scroll itself mid-capture and
# shift a full-page screenshot. The real scroller is stashed on
# window.__captureScrollTo so this module can still drive scrolling itself —
# without it, the override below would silently swallow our own prescroll.
SCROLL_NEUTRALISER_SCRIPT = """
(() => {
  const realScrollTo = window.scrollTo.bind(window);
  window.__captureScrollTo = realScrollTo;
  window.scrollTo = (x, y) => { if (y === 0) realScrollTo(x, y); };
  const realScrollBy = window.scrollBy ? window.scrollBy.bind(window) : null;
  if (realScrollBy) window.scrollBy = (x, y) => { if ((y | 0) === 0) realScrollBy(x, y); };
})();
"""

_FREEZE_MEDIA_SCRIPT = """
async () => {
  const body = document.body;
  body?.removeAttribute('hidden');
  body?.classList?.remove('offcanvas-active', 'offcanvas-open');

  const freeze = (el) => {
    if (!el) return;
    el.style.animation = 'none';
    el.style.transition = 'none';
  };
  document.querySelectorAll(
    '.slick-slider,.owl-carousel,.swiper,[data-bs-ride="carousel"]'
  ).forEach(freeze);

  for (const video of document.querySelectorAll('video')) {
    try { video.pause(); video.autoplay = false; } catch {}
  }
  try {
    if (window.jQuery && jQuery('.slick-slider').slick) {
      jQuery('.slick-slider').slick('slickPause');
    }
  } catch {}
  try {
    document.querySelectorAll('[data-bs-ride="carousel"]').forEach((c) => {
      try { c.carousel?.pause?.(); } catch {}
    });
  } catch {}

  // Reveal libraries set opacity/transform as *inline* styles. Stylesheet
  // !important already wins, but clearing them (and marking AOS elements as
  // animated) also fixes libraries that read the inline value back.
  document.querySelectorAll(
    '[data-aos],.wow,.animate__animated,.sppb-animated,[data-animate],[data-sr],[data-scroll-reveal]'
  ).forEach((el) => {
    try {
      el.style.removeProperty('opacity');
      el.style.removeProperty('transform');
      el.style.removeProperty('visibility');
      el.classList.add('aos-animate');
    } catch {}
  });

  const isVisible = (el) => {
    if (!el) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };

  // Force lazy images to load now, then wait for them to decode.
  const images = [...document.images].filter(isVisible);
  await Promise.all(images.map(async (img) => {
    try { if (img.loading === 'lazy') img.loading = 'eager'; } catch {}
    try { await img.decode(); } catch {}
  }));

  // Warm CSS background images so they are painted, not blank.
  const urlPattern = /url\\((?:"|')?([^"')]+)(?:"|')?\\)/g;
  const urls = new Set();
  for (const el of [...document.querySelectorAll('*')].filter(isVisible)) {
    const bg = getComputedStyle(el).backgroundImage;
    if (!bg || bg === 'none') continue;
    let match;
    while ((match = urlPattern.exec(bg)) !== null) urls.add(match[1]);
  }
  await Promise.all([...urls].map((u) => fetch(u, { cache: 'force-cache' }).catch(() => {})));
}
"""

# Run immediately before the screenshot, never earlier.
#
# Sliders driven by a JS timer (setInterval moving scrollLeft) are untouched by
# `animation: none`, so anything reset earlier in the pipeline drifts again
# during the remaining waits — which is why the same unchanged page scored
# 0.011 on one run and 0.049 on the next. Pinning at the last possible moment
# leaves the timer no window to advance before the shutter.
_PIN_FOR_CAPTURE_SCRIPT = """
() => {
  // Rewind sliders through their own API. A looping Swiper clones slides and
  // positions each one with its own transform, so which slide is showing (and
  // at what offset) depends on when autoplay last fired — the single largest
  // source of phantom diffs on a marketing homepage. Freezing CSS cannot fix
  // this; only telling the library to stop and rewind can.
  document.querySelectorAll('.swiper, .swiper-container').forEach((el) => {
    const swiper = el.swiper;
    if (!swiper) return;
    try { swiper.autoplay?.stop?.(); } catch {}
    // update() first: Swiper caches slide widths from whenever it initialised,
    // and if that happened before webfonts and images settled, the translate it
    // lands on differs by a few pixels between runs — enough to shift a whole
    // section sideways in the screenshot. Recomputing against the final layout
    // makes the rewind land in the same place every time.
    try { swiper.update(); } catch {}
    try {
      if (swiper.params?.loop) swiper.slideToLoop(0, 0, false);
      else swiper.slideTo(0, 0, false);
    } catch {}
  });
  try {
    if (window.jQuery) {
      jQuery('.slick-slider').each(function () {
        try { jQuery(this).slick('slickPause'); } catch {}
        try { jQuery(this).slick('slickGoTo', 0, true); } catch {}
      });
      jQuery('.owl-carousel').each(function () {
        try { jQuery(this).trigger('stop.owl.autoplay'); } catch {}
        try { jQuery(this).trigger('to.owl.carousel', [0, 0, true]); } catch {}
      });
    }
  } catch {}

  // Rewind every inner scroll container (horizontal sliders, carousels).
  for (const el of document.querySelectorAll('*')) {
    try {
      if (el.scrollLeft) el.scrollLeft = 0;
      if (el !== document.scrollingElement && el.scrollTop) el.scrollTop = 0;
    } catch {}
  }
  // Re-assert the revealed state, in case a library reapplied its start values.
  document.querySelectorAll(
    '[data-aos],.wow,.animate__animated,.sppb-animated,[data-animate],[data-sr],[data-scroll-reveal]'
  ).forEach((el) => {
    try {
      el.style.removeProperty('opacity');
      el.style.removeProperty('transform');
      el.style.removeProperty('visibility');
      el.classList.add('aos-animate');
    } catch {}
  });
  // Full-page capture stitches from the top.
  const scrollTo = window.__captureScrollTo;
  if (scrollTo) scrollTo(0, 0);
  document.documentElement.scrollTop = 0;
  if (document.body) document.body.scrollTop = 0;
}
"""

_IMAGES_SETTLED_SCRIPT = """
() => Array.from(document.images)
  .filter((img) => {
    const r = img.getBoundingClientRect();
    const cs = getComputedStyle(img);
    return cs.visibility !== 'hidden' && cs.display !== 'none' && r.width > 1 && r.height > 1;
  })
  .every((img) => img.complete && img.naturalWidth > 0)
"""


class _PhaseRecorder:
    """Records how long each readiness phase took, for diagnosing slow targets."""

    def __init__(self) -> None:
        self._start = time.perf_counter()
        self.data: dict[str, int | bool] = {"css_fallback_used": False}

    def mark(self, name: str) -> None:
        self.data[name] = int((time.perf_counter() - self._start) * 1000)

    def total(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)


def _same_origin(first: str, second: str) -> bool:
    a, b = urlparse(first), urlparse(second)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


async def _wait_network_quiet(page: Page, quiet_ms: int, max_wait_ms: int) -> None:
    """Wait until no request has been in flight for `quiet_ms`.

    Playwright's own ``networkidle`` gives up on pages that poll continuously,
    so in-flight requests are counted here instead.
    """
    in_flight = {"count": 0}

    def increment(_: object) -> None:
        in_flight["count"] += 1

    def decrement(_: object) -> None:
        in_flight["count"] = max(0, in_flight["count"] - 1)

    page.on("request", increment)
    page.on("requestfinished", decrement)
    page.on("requestfailed", decrement)
    try:
        async with asyncio.timeout(max_wait_ms / 1000):
            quiet_since: float | None = None
            idle = 0.05
            while True:
                if page.is_closed():
                    raise RuntimeError("page closed while waiting for network quiet")
                if in_flight["count"] == 0:
                    if quiet_since is None:
                        quiet_since = time.perf_counter()
                    if (time.perf_counter() - quiet_since) * 1000 >= quiet_ms:
                        return
                    idle = 0.02
                else:
                    quiet_since = None
                    idle = min(idle * 1.5, 0.2)
                await asyncio.sleep(idle)
    finally:
        with suppress(Exception):
            page.remove_listener("request", increment)
            page.remove_listener("requestfinished", decrement)
            page.remove_listener("requestfailed", decrement)


async def _scroll_through_page(page: Page, options: WaitPageOptions) -> None:
    """Scroll end to end, then back to the top.

    Lazy images and scroll-reveal animations only fire once their element enters
    the viewport. `screenshot(full_page=True)` scrolls internally to stitch the
    image, so without this pass those effects trigger *during* capture and each
    check sees a different half-revealed page. Visiting every offset first, then
    returning to the top, makes the captured state the same every time.

    Scrolling goes through window.__captureScrollTo (stashed by
    SCROLL_NEUTRALISER_SCRIPT) because the neutralised window.scrollTo ignores
    any non-zero y — including ours.
    """
    viewport = page.viewport_size
    step = (viewport["height"] if viewport else 800) or 800

    for index in range(options.prescroll_max_steps):
        target = step * (index + 1)
        reached_bottom = await page.evaluate(
            """
            (target) => {
              const doc = document.documentElement;
              const scrollTo = window.__captureScrollTo;
              if (scrollTo) scrollTo(0, target);
              else doc.scrollTop = target;
              const current = window.scrollY || doc.scrollTop || 0;
              const limit = doc.scrollHeight - window.innerHeight;
              return current >= limit - 1;
            }
            """,
            target,
        )
        await page.wait_for_timeout(options.prescroll_step_pause_ms)
        if reached_bottom:
            break

    await _scroll_to_top(page)


async def _scroll_to_top(page: Page, timeout_ms: int = 1_500) -> None:
    await page.evaluate(
        """() => {
          window.scrollTo(0, 0);
          document.documentElement.scrollTop = 0;
          if (document.body) document.body.scrollTop = 0;
        }"""
    )
    with suppress(Exception):
        await page.wait_for_function(
            "() => (window.scrollY || document.documentElement.scrollTop || 0) <= 1",
            timeout=timeout_ms,
        )


async def _wait_visible_content(frame: Frame, min_wh: int, timeout_ms: int) -> None:
    await frame.wait_for_function(
        """
        ([selectors, minSize]) => {
          for (const selector of selectors) {
            for (const el of document.querySelectorAll(selector)) {
              if (!el) continue;
              const cs = getComputedStyle(el);
              if (cs.display === 'none' || cs.visibility === 'hidden') continue;
              const r = el.getBoundingClientRect();
              if (r.width > minSize && r.height > minSize) return true;
            }
          }
          return false;
        }
        """,
        arg=[list(_MAIN_CONTENT_SELECTORS), min_wh],
        timeout=timeout_ms,
    )


async def _wait_stable_layout(
    frame: Frame,
    selector: str,
    window_ms: int,
    max_ms: int,
) -> None:
    """Poll an element's box until it stops moving for `window_ms`."""
    async with asyncio.timeout(max_ms / 1000):
        last: list[float] | None = None
        stable_since: float | None = None
        while True:
            if frame.page.is_closed():
                raise RuntimeError("page closed while stabilising layout")
            box = await frame.evaluate(
                """
                (selector) => {
                  const el = document.querySelector(selector);
                  if (!el) return null;
                  const r = el.getBoundingClientRect();
                  return [r.x, r.y, r.width, r.height];
                }
                """,
                selector,
            )
            if box is None:
                return  # Nothing to stabilise against.
            now = time.perf_counter()
            if last == box:
                if stable_since is None:
                    stable_since = now
                if (now - stable_since) * 1000 >= window_ms:
                    return
            else:
                stable_since = None
                last = box
            await asyncio.sleep(0.08)


async def _apply_freeze_css(page: Page, options: WaitPageOptions, rec: _PhaseRecorder) -> None:
    css = _FREEZE_CSS

    try:
        await page.add_style_tag(content=css)
    except PlaywrightTimeoutError:
        # A strict Content-Security-Policy can block add_style_tag; injecting the
        # same rules through the DOM still works.
        rec.data["css_fallback_used"] = True
        await page.evaluate(
            """(css) => {
              const style = document.createElement('style');
              style.textContent = css;
              document.documentElement.appendChild(style);
            }""",
            css,
        )


async def wait_page_ready(
    page: Page,
    options: WaitPageOptions | None = None,
) -> dict[str, int | bool]:
    """Freeze and settle `page`, returning per-phase timings in milliseconds.

    Every phase past the mandatory ones is best-effort: a page that never
    reaches network quiet, never exposes a main-content block, or never settles
    its layout still gets captured. Failing the whole check because a target is
    slow would turn a rendering quirk into a fake "Failed" status.
    """
    opts = options or WaitPageOptions()
    if page.is_closed():
        raise RuntimeError("page already closed")

    rec = _PhaseRecorder()

    await page.wait_for_load_state("domcontentloaded", timeout=opts.load_timeout_ms)
    rec.mark("domcontentloaded")

    # Before waiting for quiet: scrolling itself starts lazy-image requests, so
    # the quiet wait below should cover them.
    if opts.prescroll:
        with suppress(Exception):
            await _scroll_through_page(page, opts)
        rec.mark("prescrolled")

    if opts.network_quiet:
        with suppress(asyncio.TimeoutError, TimeoutError, RuntimeError):
            await _wait_network_quiet(page, opts.network_quiet_ms, opts.network_max_wait_ms)
        rec.mark("network_quiet")

    with suppress(PlaywrightTimeoutError):
        await page.wait_for_selector("body", state="attached", timeout=5_000)
    rec.mark("body_attached")

    if opts.apply_css_patch:
        with suppress(Exception):
            await _apply_freeze_css(page, opts, rec)
        with suppress(Exception):
            await page.evaluate(_FREEZE_MEDIA_SCRIPT)
        rec.mark("frozen")

    if opts.reduced_motion:
        with suppress(Exception):
            await page.emulate_media(reduced_motion="reduce")

    with suppress(Exception):
        await page.wait_for_function(_IMAGES_SETTLED_SCRIPT, timeout=opts.load_timeout_ms // 4)
    rec.mark("images_settled")

    try:
        await _wait_visible_content(
            page.main_frame, opts.visible_min_wh, opts.visible_content_timeout_ms
        )
    except Exception:
        logger.debug("No main-content block became visible; capturing anyway")
    for frame in page.frames:
        if frame is page.main_frame:
            continue
        with suppress(Exception):
            if frame.url and _same_origin(frame.url, page.url):
                with suppress(Exception):
                    await _wait_visible_content(frame, opts.visible_min_wh, 3_000)
                break
    rec.mark("visible_content")

    with suppress(PlaywrightTimeoutError):
        await page.wait_for_function("document.readyState === 'complete'", timeout=5_000)
    rec.mark("ready_state_complete")

    with suppress(Exception):
        await _wait_stable_layout(
            page.main_frame,
            opts.stabilize_selector,
            opts.stabilize_window_ms,
            opts.stabilize_max_ms,
        )
    rec.mark("layout_stable")

    if opts.extra_wait_ms > 0:
        await page.wait_for_timeout(opts.extra_wait_ms)
    rec.mark("extra_wait")

    # Deliberately last: pin_for_capture must be the final thing to touch the
    # page, so call it again from the caller right before the screenshot.
    await pin_for_capture(page)
    rec.mark("pinned")

    rec.data["total_ms"] = rec.total()
    return rec.data


async def pin_for_capture(page: Page) -> None:
    """Freeze slider/scroll positions. Call immediately before `screenshot`.

    Cheap and idempotent by design, so it can be re-run right before the
    shutter without adding meaningful latency.
    """
    with suppress(Exception):
        await page.evaluate(_PIN_FOR_CAPTURE_SCRIPT)
    with suppress(Exception):
        await _scroll_to_top(page)
