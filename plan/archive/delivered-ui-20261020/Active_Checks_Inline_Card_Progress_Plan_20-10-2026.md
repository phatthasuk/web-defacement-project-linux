# Active Checks Inline Card Progress — Implementation Plan

**Archived:** 2026-10-20 (Asia/Bangkok). Delivered UI work; implementation/test/runtime statuses remain as recorded. Remaining work is tracked in [the active status register](../../ROADMAP_STATUS_AND_BACKLOG.md#archived-ui-deliveries-and-remaining-work).

**Created:** 2026-10-20 (Asia/Bangkok)  
**Source inspected:** `a074e0b9a7c797759b9881dc6ec9afd78600e30d`  
**Implemented:** Partial. **Tested:** Partial. **Runtime verified:** Partial.

**Latest direction, 2026-10-20:** The separate
[Run Check Popover removal plan](../../Run_Check_Popover_Removal_Plan_20-10-2026.md)
supersedes earlier Popover-hold statements below. It does not change this plan's
completed-card retention or verification results.

## 1. Purpose and ownership

Expand progress inside the selected Active Checks card so its name, current
phase and checklist remain together. Remove the separate bottom detail block
from this panel. This is a focused frontend follow-up to the
[Right Active Checks plan](Dashboard_Right_Active_Checks_Plan_20-10-2026.md).

The user requested planning only in this task. Do not implement application
changes as part of this documentation update. The existing Run Check Popover
remains paused until Right Active Checks passes production testing. This plan
does not change the Popover, left Overview, layout breakpoint, backend endpoint,
capture pipeline, permissions or polling frequency. Production deployment and
live checks require a separate authorized procedure.

## 2. Confirmed current behavior

`frontend/src/components/ActiveChecksPanel.tsx` maps activity items into compact
buttons, then renders `ProgressDetail` below the scrollable list. Selection is
tracked by target ID and initially opens the first item. The selected target's
name appears both in the list and in the bottom detail block. The selected
detail query reconciles a target that disappears from the activity page.

The attached screenshot illustrates this separation; it does not establish
production acceptance. Existing component tests cover basic progress, selection
and refresh states, but do not verify details belong inside the selected card.

## 3. Intended interaction

- Initially show all cards collapsed. Clicking or pressing Enter/Space on a
  card's summary expands that card directly below its summary. Clicking the
  same summary collapses it; choosing another card collapses the previous card.
  At most one detail region is mounted.
- Keep the monitor name once in the card header. Place the View link outside
  the summary button, with a monitor-specific accessible name. The expanded
  body shows elapsed time, attempt, phase checklist, retry deadline and genuine
  result/diagnostic states using existing data. Never nest a link in a button.
- Highlight the expanded card and show an expansion indicator. Keep other
  cards compact and available in the same bounded panel scroll area. Remove
  the old standalone bottom detail block entirely.
- Retain explicit expansion across normal refreshes. Polling, item reordering,
  new arrivals and elapsed ticks must not open another card, steal focus or
  trigger scrolling. After manual collapse, the first-item effect must not
  reopen a card automatically.
- On user expansion, reveal the header and beginning of the body only if
  clipped by the panel. Scroll the panel by the smallest necessary distance;
  do not scroll the dashboard or force an oversized card wholly into view.
  Respect reduced-motion preferences.
- Use a native summary button with `aria-expanded` and `aria-controls`, a stable
  detail-region ID and a region labelled by its card header. Keep keyboard focus
  on the summary when toggling. Tab reaches View and other visible controls;
  collapsed content has no focusable descendants. No focus trap is introduced.
- Announce meaningful phase/result changes through a small polite status region.
  Elapsed seconds must not be inside that live region. Run an elapsed timer only
  while an expanded, visible, nonterminal detail needs it; stop on collapse,
  completion, narrow mode and unmount.

## 4. Lifecycle, pagination and unavailable data

Keep progress associated with the correct target, run and URL revision. When a
new run starts for the selected monitor, reset run-specific elapsed/result data;
never reuse a finished checklist from the previous run. Missing telemetry is
unavailable, not a fabricated queue phase or successful completion.

If the selected monitor disappears from the current activity page, reconcile it
through the existing single selected-target query. Preserve it as one labelled
selected card inside the panel list, without a duplicate bottom surface. If
still active outside the current page, label it as outside that page; exclude
this retained card from the page's displayed item range and avoid duplicates
when it reappears. Selecting a visible card replaces the retained selection.

Only a confirmed terminal response may display a terminal result. Retain a
confirmed terminal card for at most 60 seconds from confirmation, then remove
it; stop unnecessary result polling and timers. Disappearance alone does not
prove completion. A reconciliation error displays an explicit unavailable/error
state, and access denial clears protected data immediately. If a removed card
contains keyboard focus, restore focus to a safe panel control without moving
focus during passive refreshes elsewhere.

Keep initial loading, confirmed empty, cached-data refresh failure and missing
telemetry distinct. Preserve retry-wait result badges, skipped/failed steps and
the unconfirmed-finalization diagnostic. Logout, role changes and revoked access
must retain the existing cache-clearing behavior. Table filters must not change
the panel's authorized activity population.

## 5. Implementation sequence

1. Add component regressions for inline placement, single expansion, switching,
   collapse persistence and accessible controls. Assert the old bottom duplicate
   is absent, using assertions that fail against the current behavior.
2. Refactor card rendering in `ActiveChecksPanel.tsx`; render the progress body
   inside the selected card and remove duplicate headings/standalone details.
   Keep API/query changes limited to lifecycle handling proven necessary here.
3. Add stable region identifiers, scoped scrolling and timer/focus cleanup.
   Preserve the selected-target reconciliation path and bounded retention.
4. Run the verification matrix below, record actual evidence, and update this
   plan and the status register independently. Leave unverified criteria open.

## 6. Verification and acceptance

| Area | Required checks |
| :--- | :--- |
| Selection | Expand first/middle/last card; switch and collapse; one detail body; one monitor heading per card; no reopen after polling. |
| Lifecycle | Phase updates, retry wait, missing telemetry, failed/skipped steps, confirmed finish, 60-second expiry, a new run/revision, disappearance without success and reconciliation error. |
| Pagination | More than 20 active items; change page while expanded; selected off-page item remains identifiable without duplicate cards or incorrect ranges. |
| Access | Admin and assigned Operator views; logout/access revocation clears retained details; inaccessible selected-target response exposes no old content. |
| Timers and focus | Fake timers prove cleanup on collapse/finish/narrow mode/unmount; no elapsed live announcements; keyboard focus survives toggles and safe removal. |
| Browser | Long names, several expanded-height scenarios, panel scrolling, keyboard/touch, reduced motion and 200% zoom; widths 1920/1680/1600/1440/768/390; resize while expanded without page overflow. |

From `frontend/`, run `npm run test -- --run`, `npm run lint` and `npm run build`.
Use the repository's render helper and mocked responses; do not delete or weaken
existing regressions. If backend code becomes necessary, run its relevant
checks and document the reason for the scope change.

For visible UI acceptance, launch `backend-isolated` and the frontend against
disposable data and local mocks/fixtures. Never trigger captures against real
monitors. The earlier Vite `spawn EPERM` limitation must be resolved or reported
as an unperformed browser check, not presumed fixed. Record revision, commands,
Asia/Bangkok date/time, environment/browser version, results and exclusions in a
dated English refinement record. No current production acceptance is inferred.

Complete this follow-up only when inline behavior, lifecycle and accessibility
checks have evidence. This does not close the parent plan's remaining layout,
browser, Linux or production acceptance, and does not release the Popover hold.

## 7. Implementation execution — 2026-10-20 (Asia/Bangkok)

Implemented inline, single-card expansion, initially collapsed cards, a single
monitor name per card, a monitor-specific View link, scoped panel scrolling and
polite phase/result announcements without elapsed-second announcements. The
elapsed timer runs only for the expanded active check. A selected monitor that
leaves the current activity page is retained in the list and reconciled through
the existing single-target query. Matching run/revision checks prevent stale
progress from being shown; confirmed terminal results expire after 60 seconds.
Access-denied events clear the selection; a selected-target 404 also clears
retained and cached data and returns focus safely. No API, backend, database,
Popover or capture behavior changed.

Implementation and verification details are in the
[execution record](../../../refinement/10-20-2026/Active-Checks-Inline-Card-Progress-20-10-2026.md).
The focused component tests cover inline placement, one expanded card, switching
and manual collapse persistence, terminal retention expiry, missing progress,
refresh failure and 404 clearing. Full frontend tests, lint and build pass.
Isolated Chromium verification passed at 1920×1080 with mocked API responses.

Still open: the full width and 200% zoom matrix, touch and reduced-motion checks,
focus restoration by keyboard after expiration/access revocation, page changes
while expanded, broader Admin/Operator session/access cases and production
acceptance. The Popover remains paused until the parent Right Active Checks plan
passes production testing. No production request reached the network and no
deployment or live capture was performed.
