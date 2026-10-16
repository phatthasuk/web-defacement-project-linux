# Capture Improvements Plan

A plan to port proven capture engine and visual diffing logic from the `python_project_website_checker/visual-checker` prototype (tested against real-world hospital websites) into the current project.

**Core Principle:** Port the *algorithms and logic* directly into existing services without importing architectural legacy components (JSONL event buses, log-tailing, filesystem-based `state/`, or Flet UI), as the current architecture already provides Database persistence, REST APIs, and automated scheduling.

**Problem Addressed:** The initial capture implementation ([backend/app/services/capture/capture.py](../backend/app/services/capture/capture.py)) simply ran `goto(wait_until="networkidle")` followed by an immediate screenshot without stabilizing page content. This caused animations, carousels, lazy-loaded images, and cookie banners to introduce pixel shifts, leading to frequent **false positives** (alerting on legitimate dynamic changes as defacements).

> Note: The auto-rebaseline and decision state machine component (formerly Item 4) has been separated due to security sensitivities; see [plan/archive/auto-rebaseline.md](auto-rebaseline.md).

---

## 1. ⭐ Page-Stabilization Pipeline (Including Cookie/Overlay Dismissal)

**Origin:** `page_ready.py` (`wait_page_ready`) + `accept_cookie.py` + CSS/init-scripts in `runner.py`.  
**Destination:** Integrated into [capture.py](../backend/app/services/capture/capture.py) prior to `page.screenshot()`.

### Multi-Phase Page Readiness (Replacing Standalone `networkidle`)
- **Phased Waits:** DOMContentLoaded → adaptive network-quiet → body attached → CSS patches → cookie dismissal → visible content timeout → readyState complete → layout stabilization → final stabilization wait.
- **Adaptive Network-Quiet:** Actively tracks in-flight requests, requiring a continuous quiet window of 1,200 ms (capped at 15,000 ms) instead of relying solely on `networkidle`, which fails on sites continuously issuing background XHR/telemetry.

### Visual Stabilization (Preventing False Positives)
- **Freeze Animations/Transitions Globally:** `*,*::before,*::after{animation:none!important;transition:none!important}`.
- **Halt Carousels/Sliders/Videos:** `slick('slickPause')`, `carousel.pause()`, `video.pause()` + `autoplay=false` (supporting Slick, OwlCarousel, Bootstrap).
- **Hide Preloaders/Spinners:** Hide loading overlays and force un-hiding of content styled with `visibility:hidden` during page loads.
- **Force Lazy Image Decoding:** Switch `loading:lazy` to `eager`, call `img.decode()`, and prefetch CSS `background-image` declarations (`fetch cache:'force-cache'`).
- **Wait on Visible Images:** Verify `complete && naturalWidth > 0` on visible images before capture (timeout 7s).
- **Enforce Layout Stability:** Poll `getBoundingClientRect()` on `<main>` until dimensions remain stationary for 400 ms.
- **Neutralize Scrolling:** Override `window.scrollTo` and `scrollBy` to prevent JavaScript from shifting the viewport during full-page captures.
- **Deterministic Emulation:** Set `emulate_media(reduced_motion="reduce")` with a fixed viewport dimensions across all runs.

### Cookie and Overlay Dismissal
- **Automated "Accept" Dismissal:** Two-tier detection: (1) `get_by_role("button", name=/Thai text|accept|agree|.../)` supporting Thai and English, and (2) Vendor-specific selectors (CookieYes `.cky-btn-accept`, OneTrust `#onetrust-accept-btn-handler`, Cookiebot).
- **Frame Traversal:** Search both top-level page and nested iframes (where many third-party consent dialogs reside).
- **CSS Fallback:** Apply `HIDE_CSS` fallback hiding if buttons cannot be programmatically clicked.
- **Visibility Verification:** Ensure banner elements disappear (`offsetParent === null`) before entering screenshot capture.
- **State Flagging:** Expose `cookie_dismissed` / `promo_closed` metadata for observability.

### Guardrails and SSRF Compatibility
- **PhaseRecorder:** Track per-phase execution time (in milliseconds) for diagnostic observability.
- ⚠️ **Maintain SSRF Guard Invariants:** All resource prefetching must respect existing `page.route("**/*")` intercepts and disallow private-range network access.

---

## 2. ⭐ Multi-Baseline Matching

**Origin:** `image_diff.py` (`find_best_baseline`) + `baseline_store.py`.  
**Destination:** [services/diff/diff.py](../backend/app/services/diff/diff.py) + `Snapshot` / `Target` models.

- **Multiple Approved Baselines per Target:** Sites featuring rotating hero banners or promotional cycles have multiple valid visual representations.
- **Best-Match Comparison:** Evaluate current snapshots against all approved baselines, selecting the lowest diff score (`best_ratio = min(...)`). This substantially eliminates false positives on dynamic pages.
- **Baseline Pruning:** Enforce a maximum baseline capacity (`MAX_BASELINES_PER_SITE=50`), demoting the oldest baselines upon reaching caps.
- **Timestamped File Naming:** Format baseline artifacts chronologically (e.g., `2026-09-02T14-30-00.png`).
- **Corrupt File Resilience:** Enable `LOAD_TRUNCATED_IMAGES=True` and catch `(OSError, ValueError)` so an unreadable image does not abort the entire evaluation run.
- **Matched Baseline Attribution:** Persist `matched_baseline_id` inside `CheckResult` so operators can inspect which baseline was used for comparison.

---

## 3. Diff Heatmap Previews (Three-Panel)

**Origin:** `image_diff.py` (`_diff_score_and_preview`).  
**Destination:** [services/diff/diff.py](../backend/app/services/diff/diff.py) + [ScreenshotCompare.tsx](../frontend/src/components/ScreenshotCompare.tsx).

- **Pixel Diff with Noise Mask:** `ImageChops.difference` → grayscale → brightness boost (2x) + contrast boost (2x) → threshold mask (`MASK_LEVEL=16`) to absorb compression artifacts and antialiasing noise.
- **Normalized Ratio:** Calculate changed pixels over total pixel count (0.0 to 1.0) against thresholds.
- **Three-Panel Composite:** Generate a combined preview `[Baseline | Current | Highlighted Overlay]`, where differences are highlighted with a semi-transparent red overlay (`blend 0.6`).
- **Dimension Normalization:** Automatically resize differing snapshot dimensions to match the baseline prior to calculation.
- **Early Exit:** Short-circuit evaluation if bounding box diff (`getbbox()`) is `None` (0.0% diff).
- **Resource Cleanup:** Enforce explicit context managers on image file handles to avoid resource leaks during continuous long-term monitoring.

---

## Recommended Execution Roadmap

| Item | Phase | Rationale |
|---|---|---|
| 1. Page Stabilization + Cookie Dismissal | Immediate | Solves the primary cause of false positives; low operational risk. |
| 2. Multi-Baseline Matching | Immediate / Next | Requires schema evolution but directly addresses dynamic content. |
| 3. Diff Heatmap Previews | Immediate / Next | Improves triage UX; low operational risk. |
| 4. Auto-Rebaseline (Separated) | Future | Security-sensitive; requires policy consensus. |

## Omitted Prototype Elements
- Standalone execution loops, JSONL event streaming, log tailing, and disk-based `state/` directories (superseded by PostgreSQL/SQLite, FastAPI REST endpoints, and background scheduler).
- All Flet UI components.
