# Dashboard Right Active Checks Panel — Implementation Plan

**Created:** 2026-10-20 (Asia/Bangkok)
**Source inspected:** `06adbb6923713acf327da7798591da58462fe229` plus current local changes.
**Implemented:** Partial. **Tested:** Partial. **Runtime verified:** Partial.

## 1. Purpose and ownership

Use the wide-screen space to the right of Monitor Management for an Active
Checks panel. Keep the target table central and the result badge on every row.
Show detailed progress in the right panel on wide screens; retain the existing
popover on narrower screens and on the target detail page initially.

This plan owns the responsive layout, activity feed and replacement of the
wide-screen list popover. The separate [left Overview plan](Dashboard_Left_Overview_Plan_20-10-2026.md)
owns summary counts and filter shortcuts. Implement this plan first and support
the left panel as an optional later addition. The [core roadmap](PROJECT_PLAN.md)
and [status register](ROADMAP_STATUS_AND_BACKLOG.md) retain Stage ownership.
The user has explicitly paused all Popover changes until Right Active Checks
passes production testing. Accordingly, the existing popover remains in place
and is not modified by this implementation; the planned wide-screen replacement
and deduplication are still open. No production operation or deployment is
included in this implementation.

## 2. Confirmed source and existing limitations

- `TargetListPage.tsx` uses a centered `max-w-7xl` container. Its Admin-only Add
  New Monitor form already consumes a 320–384 px column beside the table.
  Simply adding two outer columns would leave insufficient table width.
- `usePaginatedTargetsQuery` polls the current filtered page every four seconds.
  Page size is 50; the backend enforces a maximum of 200. Other pages and targets
  hidden by search/tag/status filters cannot be inferred from those items.
- Progress is already included in authorized target responses. The process-local
  registry has a size cap of 500 and a finished TTL of 60 seconds. Durable run
  ownership, attempt history and retry deadlines remain authoritative.
- The [popover feature plan](Run_Check_Progress_Popover_Plan_20-10-2026.md)
  remains Partial. Four reviewed code defects were remediated, but its wider
  browser, authorization/lifecycle and Linux acceptance must not be presumed
  complete. See the [archived remediation plan](archive/implemented-20261020/Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md)
  and [evidence](../refinement/10-20-2026/Run-Check-Progress-Popover-Remediation-20-10-2026.md).

## 3. Layout and responsive behavior

| Viewport | Target list behavior |
| :--- | :--- |
| At least 1600 CSS px, initial design threshold | Grid with optional 240 px left Overview slot, flexible center (minimum about 800 px), and 300–320 px Active Checks panel. Use measured widths and browser checks to confirm the threshold. |
| Below the wide-screen threshold | Centered management content and current row popovers. No right panel or reserved empty side columns. Left Overview follows its own compact layout plan. |
| Narrow mobile and browser zoom | Stacked controls and existing table overflow containment; progress stays accessible from the badge. No page-wide horizontal overflow. |

Replace the rigid outer maximum width with a bounded responsive grid. Keep the
center table width by moving the Admin-only Add New Monitor form into an
expandable section above the table on the wide layout. Preserve entered values,
labels, validation, permissions and focus across layout changes. Keep one form
instance; never duplicate IDs or discard unsaved form input on resize.

The right panel is sticky below the application header, with its own bounded
scroll area for a long list. Reserve its width while wide mode is enabled so a
new check does not shift the table. An idle panel says “No active checks” only
after a successful response. It must not overlay the table or header.

Render one detailed progress surface for the selected target. Share phase labels
and step rendering between the panel and popover. Do not keep a hidden duplicate
popover with running timers, live regions or focusable controls on wide screens.
On resize, preserve selection where possible and safely restore focus if its
current control disappears. A plain row badge remains visible at every width.

## 4. Activity content and interaction

**Follow-up design, 2026-10-20:** The user requested planning to expand details
inside the selected activity card and remove the panel's separate bottom detail
block. The [inline card progress plan](Active_Checks_Inline_Card_Progress_Plan_20-10-2026.md)
owns this focused frontend change and its acceptance. Its implementation and
verification are Partial; the desktop mocked-browser check passed, while the
full lifecycle/accessibility/production acceptance remains open. It does not
release the Popover hold or close parent-plan acceptance.

- Label scope “All active monitors you can access”; activity ignores table search,
  tags, status filters and the current table page. An off-table active target
  links to its authorized detail page. Do not clear filters merely to view progress.
- List target name, queue/running/retry state and attempt number. Select an item
  to show the current phase, elapsed attempt time and six-step checklist. Keep
  one expanded item. Prefer an explicit current selection over automatic changes.
- Clicking a Checking/queued/retry trigger in a wide-screen table row selects
  the corresponding activity item and focuses its heading/control. Use native
  buttons, labelled regions and visible focus; no focus trap.
- Queue and retry waiting are activity states, not new target result statuses.
  Retain Failed/Availability Issue badges during retry wait and use persisted
  retry deadlines. Display dates through `utils/date.ts`.
- Preserve skipped, failed, pending, unavailable and completed states. Show the
  real result and the unconfirmed-finalization diagnostic when applicable. Do not
  invent percentage completion, remaining duration or intermediate phases.
- Keep a selected terminal result briefly (up to the existing 60-second retention
  policy) when it is confirmed. Removal from an activity feed alone only means
  “no longer listed”; it does not prove success. Reconcile a disappearing selected
  item through one existing target-detail query, then display its actual result
  or an explicit unavailable/error state. Never fetch every disappeared row.
- Pause elapsed updates after completion and when the detailed surface is absent.
  Announce meaningful phase changes politely; do not announce every elapsed second.
- Initial loading, confirmed empty, missing telemetry and refresh failure have
  different messages. Keep cached data with its last successful refresh time on
  transient failure. Reset all sensitive cached activity immediately on logout,
  access denial or a session/role change through the existing auth/query behavior.

## 5. Backend and query design

Add a read-only `GET /targets/check-activity` endpoint before dynamic target-ID
routes. Use an explicit Pydantic response and matching TypeScript types. Proposed
response: `items`, `total`, `limit`, `offset`, `observed_at`. Each item contains
the permitted target identity/name, current durable result/run/revision/attempt,
retry fields and matching optional progress. Exclude page content, artifact paths
and raw exception messages.

Use `accessible_targets(...)`, active-target filtering and durable non-null
`check_run_id` as the activity population. Match registry records to run/revision;
registry eviction or a restart must yield unavailable phase details rather than
omit an executing durable run. Do not scan the registry as the sole source of
active targets. No database schema, scheduler or detector changes are required.

Bound responses with server pagination (default 20, maximum 100), stable ordering
and an accurate authorized total. Show “Showing X of Y active checks” and paging
controls if truncated. Do not download every target/page or issue one request per
card. Keep a selected item outside the current activity page through the single
selected-target query, with no disclosure if it becomes inaccessible.

Put calls in `src/api/targets.ts` via `apiFetch` and use exported query-key
constants in TanStack Query hooks. Poll activity every four seconds only while
the wide panel is mounted/visible; retain previous data during revalidation.
Mutations invalidate relevant activity/table keys. Narrow mode relies on existing
target polling. Authentication revocation must still clear retained data.
Avoid extra polling for elapsed counters, WebSockets/SSE or per-card SQL queries.

## 6. Delivery and verification

1. Record the current source and outstanding popover acceptance. Build shared
   presentation without losing the four existing defect regressions.
2. Add scoped activity endpoint/types and query tests, including pagination and
   queued runs without registry records. Avoid N+1 serialization.
3. Implement the responsive grid and one persistent Add New Monitor form; add
   the right panel and responsive badge behavior. Keep narrow popovers until
   replacement behavior and equivalent accessibility pass.
4. Verify selections, completion, filters, retries and access changes with local
   mocked/injected responses. Test more than 50 targets, off-page/off-filter
   active items, multiple concurrent runs, registry eviction, stale run/revision
   data, recovery and missing progress. Assert no fabricated outcomes.
5. Run backend pytest with short disposable Windows basetemp, Ruff and mypy;
   frontend test, lint and build. Test Admin, assigned Operator, unassigned
   Operator (404 for inaccessible detail; no list leakage), and unauthenticated
   access (401). Preserve CSRF checks for existing trigger mutations.
6. Launch `backend-isolated` and the frontend for browser verification using
   disposable test users and local mocks/fixtures. Check both roles, widths
   1920/1600/1440/1280/768/390, 200% zoom, table edges, sticky scrolling, tab
   navigation, Escape, touch selection, hover fallback and resizing while open.
   Capture screenshots and browser version. Never trigger real monitored sites.
7. Add a dated English refinement record with Issue, Implementation and
   Verification, source revision, exact commands/results, environment and
   exclusions. Update this plan and the status register independently.

Commands, from their respective directories and repository runtimes:

```text
backend:  python -m pytest --basetemp=<short-disposable-directory> tests -q
backend:  ruff check app tests scripts alembic
backend:  mypy app
frontend: npm run test
frontend: npm run lint
frontend: npm run build
```

Preserve historical evidence: the prior full Windows backend run had 276 passes
and two cleanup failures; full Ruff had six findings in an applied migration.
Report current failures; do not skip tests or edit applied migrations to hide
them. Existing component tests are not browser evidence. Linux capture/runtime
acceptance stays under the original feature plan and Phase 5; this layout change
does not close those criteria.

## 7. Completion and planning evidence

Complete when scoped activity is correct across pages/filters and permissions,
wide-screen progress has one detailed surface, narrow-screen interaction remains
accessible, form state survives resize, the table remains usable, and actual
test/browser evidence is recorded. Keep incomplete acceptance open in the active
register. No dependency upgrade, production restart, live-data edit, capture
change, human-baseline bypass or new monitoring Stage belongs to this plan.

## 7.1 Implementation execution — 2026-10-20 (Asia/Bangkok)

Implemented the scoped, paginated activity endpoint and dashboard panel. The
endpoint scopes results to accessible active targets with durable run IDs,
matches progress by target/run/revision, and excludes raw URLs and exception
messages. The UI polls only while the 1680 px wide layout is active, preserves
distinct loading/empty/error states, supports selection and pagination, and
keeps narrow-screen behavior. The existing progress popover remains unchanged
and duplicates the detailed surface on wide screens by explicit user direction;
replacement, one-surface behavior and the original plan's 1600 px breakpoint
remain unresolved. The 1680 px threshold is provisional pending browser
measurement.

Verification record: [Right Active Checks execution](../refinement/10-20-2026/Dashboard-Right-Active-Checks-20-10-2026.md).
Full test suites and targeted static checks were run on Windows. Browser
verification could not start because Vite/esbuild failed with `spawn EPERM`.
Linux runtime and production acceptance were not run. Production testing remains
an explicit outstanding gate and must use the authorized production procedure;
no live check or deployment was performed here.
