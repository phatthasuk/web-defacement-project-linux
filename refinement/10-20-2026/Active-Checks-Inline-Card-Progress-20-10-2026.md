# Active Checks Inline Card Progress — 20-10-2026

## Issue

The Active Checks panel showed each selected monitor's progress in a separate
block below the activity list, repeating the monitor name and separating the
status from its card. The requested interaction is to expand progress in the
card the operator selects.

## Implementation

Changed `frontend/src/components/ActiveChecksPanel.tsx` so every card begins
collapsed and expands its detail in place. Only one card expands at once;
selecting another collapses the first, and clicking the expanded summary
collapses it. The card header contains the monitor name once, a separate
accessible View link and an expansion indicator. User expansion reveals the
card within the panel's own scroll area. Phase announcements are polite; elapsed
seconds are outside the live region and the timer stops when details are closed
or terminal.

Kept selected activity in the panel when it leaves the current page, reconciled
it through one selected-target query, required run/revision identity before
showing cached progress and retained a confirmed terminal result for up to 60
seconds. A 404 clears the selected card and cached target/activity data and
shows a generic availability message. Existing logout/access-denied handling
also clears selection. The Popover component was not changed.

Added component regressions for collapsed initial state, inline placement,
single-card expansion, switching/collapse, staying collapsed through a refresh,
terminal retention expiry and 404 cleanup. Existing missing-progress and
refresh-error tests remain.

## Verification

**Date/time:** 2026-10-20, 15:14–15:19 Asia/Bangkok.  
**Source revision:** `a074e0b9a7c797759b9881dc6ec9afd78600e30d` plus the
uncommitted inline-card changes in this checkout.  
**Environment:** Windows 11 checkout; Node/npm dependencies from the repository;
Python Playwright from `backend/.venv`; local Vite development server; Chromium
153.0.8010.12, headless, viewport 1920×1080. All API responses in the browser
check were fulfilled by local mocks before network access. No production request
reached the network.

- Focused tests:
  `npm run test -- --run src/components/ActiveChecksPanel.test.tsx`
  — **6 passed**.
- Full frontend suite:
  `npm run test -- --run`
  — **16 files, 107 tests passed**. Vite emitted its existing esbuild/oxc
  deprecation notices.
- Lint: `npm run lint` — **passed with no warnings**.
- Build: `npm run build` — **passed**; TypeScript project build and Vite
  production bundle completed.
- Browser procedure: started local Vite using `npm run dev -- --host 127.0.0.1`;
  fulfilled `/auth/me`, `/targets/page`, `/targets/check-activity` and `/tags`
  responses with in-memory fixtures; expanded one card, checked its detail
  region was inside that card and its name appeared once, expanded a second
  card, confirmed the first collapsed, pressed Enter to collapse the second,
  then checked `document.documentElement.scrollWidth <= window.innerWidth`.
  **Passed** at 1920×1080. Screenshot saved temporarily as
  `%TEMP%/active-checks-inline-card-expanded.png` (captured with the first card
  expanded). The local Vite process was stopped after verification.
- No backend/API/schema changes were made, so backend checks were not run for this
  frontend-only follow-up. No live target was added and no capture was triggered.

**Not checked:** widths 1680/1600/1440/768/390 and 200% zoom; touch behavior;
reduced motion; pagination changes while expanded; Admin/Operator browser
sessions; keyboard focus restoration after card expiration or access revocation;
browser positioning when an expanded card is clipped at the bottom of the panel;
production/Linux runtime and production testing. These remain open and prevent
closing this plan. The focused 1920×1080 browser check preceded the final scoped
scroll adjustment; full frontend tests, lint and build were rerun afterward.
The user-directed Popover hold remains in force until the parent Right Active
Checks work passes production acceptance.
