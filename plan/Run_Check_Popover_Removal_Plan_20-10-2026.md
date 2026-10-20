# Run Check Popover Removal — Implementation Plan

**Created:** 2026-10-20 (Asia/Bangkok)  
**Source inspected:** `6b260c407548ccae0b12042c24db70435d22dc52`  
**Implemented:** Implemented (scoped frontend changes). **Tested:** Partial. **Runtime verified:** Not verified.

## 1. Purpose and scope

Retire the frontend Run Check Popover because the user reports that the right
Active Checks panel works well. Use that panel as the dashboard's detailed
progress surface on wide screens, keeping plain result badges in the table.

This latest user direction supersedes the earlier hold on Popover changes. The
user subsequently asked to execute this plan. The scoped frontend implementation
is complete; production testing and browser acceptance remain separate evidence.
No deployment or live check is included.

Scope includes Popover uses on both the target list and target detail page,
their tests, and a small inline replacement on the detail page so progress
remains accessible when the right panel is hidden. Completed-card retention,
collapse/removal policy, Active Checks pagination, the left Overview and changes
to the 1680 px layout breakpoint are outside this plan.

## 2. Confirmed source inventory

| Source | Current responsibility | Planned action |
| :--- | :--- | :--- |
| `frontend/src/components/CheckProgressPopover.tsx` | Portal, hover/pin interaction, positioning, dismissal/focus handling and elapsed updates | Removed with retired interaction tests. |
| `frontend/src/components/CheckProgressPopover.test.tsx` | Popover interaction plus progress/lifecycle regressions | Retired; shared presentation and page tests now own the applicable progress assertions. |
| `frontend/src/pages/TargetListPage.tsx` | Wrapped Checking, queued and retry indicators | Uses plain badges/text and a narrow-screen View progress link. |
| `frontend/src/pages/TargetDetailPage.tsx` | Wrapped Checking/finished result badges | Uses a plain badge and inline progress section from the existing target query. |
| `frontend/src/components/ActiveChecksPanel.tsx` | Right panel with inline cards; currently visible at 1680 px and above | Keeps its selection and retention behavior and uses the shared progress presenter. |

Backend progress reporting and `check_progress` are shared with Active Checks.
Their names/history do not make them Popover-only code. Keep the registry,
durable run/retry state, API endpoint, schemas, types and authorization intact.

## 3. Intended behavior

### Target list

Render `TargetStatusBadge` directly. Keep Checking, queued and retry labels,
attempt/deadline information and existing result navigation. Hovering/focusing
a badge must no longer create a popup, pin controls, portals or hidden timers.
Run Check and Preview keep their existing behavior and permissions.

On wide screens, use the existing right Active Checks panel. Below 1680 px,
where that panel is currently hidden, provide an ordinary “View progress” link
for an active check to its authorized target detail page's `#check-progress`
section. Do not introduce another popup or a duplicate activity feed/query.
Keep table filters, sorting, pagination and target-name links intact.

### Target detail

Show a plain result badge and an accessible inline expandable “Check progress”
section for active/queued/retry state, and for a genuine finished progress record
where currently available. Give the section a stable `check-progress` anchor;
opening a View progress link should reveal the section and focus its heading
without a focus trap. Use the existing target query rather than polling all
active monitors. Completed results/history remain accessible on this page.

Share the phase/checklist presenter with Active Checks, for example through a
small `CheckProgressDetails.tsx` component. Preserve the panel's current selection
and retention policy. Do not keep a hidden Popover instance or import the
retired component to render inline content.

Preserve run/revision matching, attempt numbering, retry wait, skipped/failed
steps, finished outcomes and the unconfirmed-finalization diagnostic. Missing
telemetry, loading, confirmed empty and failed refresh are distinct states.
Timers run only while the corresponding visible details need them, and meaningful
phase/result announcements exclude elapsed seconds. Reset protected cached
content on logout, access denial and session/role changes through existing auth
and query behavior. Keep API dates displayed through `utils/date.ts`.

## 4. Implementation sequence

1. Inventory all Popover imports, helpers, test mocks and unique styles/listeners.
   Identify shared progress logic before deleting anything.
2. Extract reusable inline presentation with meaningful regressions for identity,
   retry, unavailable progress, finalization and refresh/access states. Keep
   Active Checks rendering and interaction unchanged.
3. Add the detail-page inline section and narrow-screen View progress navigation,
   including keyboard focus and direct anchor entry behavior.
4. Replace all list/detail wrappers with plain badges/text and the replacement
   navigation. Delete the Popover component and its retired interaction tests
   only after applicable regressions have new owners. Do not remove guards just
   to reduce the test count.
5. Scan frontend source/tests for remaining `CheckProgressPopover` references,
   orphaned Popover-only imports and handlers. Preserve historical documents.
6. Run checks and isolated browser acceptance, then record evidence and update
   the parent plans/index/status register. Archive nothing without a user request.

## 5. Verification and acceptance

| Area | Required result |
| :--- | :--- |
| Removal | No frontend component/import/wrapper remains; badge hover/focus/click creates no Popover or Popover-specific timers/listeners. |
| Dashboard | Active Checks cards continue to expand/switch/collapse and show real progress; table result, queue and retry indicators remain correct. |
| Detail/navigation | Inline progress works via direct detail navigation and `#check-progress`; the narrow-screen link reveals it with safe keyboard focus and no duplicate query. |
| Lifecycle/errors | Tests preserve valid run/revision identity, new runs, retry wait, finished outcomes, unavailable telemetry, refresh failure and unconfirmed finalization. |
| Access | Admin and assigned Operator UI, inaccessible target 404, unauthenticated access, logout and role/access change do not retain protected progress. |
| Browser | Widths 1920/1680/1600/1440/1280/768/390, 200% zoom, keyboard/touch and resize; progress remains reachable, no page-wide overflow, lost form input or duplicate detail surfaces. |

Run from `frontend/`: `npm run test -- --run`, `npm run lint` and
`npm run build`. Run relevant backend checks only if backend changes become
necessary and document that scope expansion. Test removal assertions and
replacement behavior rather than claiming success from a reduced test count.

For browser checks, use an isolated backend with disposable data or mocked local
API responses. Explicitly select a local API origin, install interception before
app load and block unexpected external requests. Do not use production sessions,
live data or real monitored sites. Record revision, exact commands/procedure,
Asia/Bangkok date/time, OS/browser version, screenshots, results and exclusions
in an English refinement record. Existing Windows/Linux limitations and past
failures remain historical; this feature does not close their acceptance.

Complete when Popover code is removed, replacement access works at all required
widths, shared progress/authorization regressions survive, and actual verification
is recorded. Production deployment/testing remains a separate authorized task.

## 6. Planning evidence

2026-10-20, Asia/Bangkok; Windows checkout at the source revision above. Inspected
the Popover source/tests, list/detail references, right-panel visibility/query
behavior, active plans and status register. The user reports the panel works;
no production verification was performed here. Application tests were not run
for this documentation-only task.

## 7. Execution record — 2026-10-20 (Asia/Bangkok)

Scoped source implementation is recorded in
[`../refinement/10-20-2026/Run-Check-Popover-Removal-20-10-2026.md`](../refinement/10-20-2026/Run-Check-Popover-Removal-20-10-2026.md).
It records the exact commands, Windows and Node versions, 107 passing frontend
tests, lint/build results, exclusions and next action. Browser width/zoom/touch
acceptance and Linux/runtime verification remain not verified. The checkout's
`.nvmrc` requests Node 20; this run used Node 24.7.0, so repeat the checks on
Node 20 and complete isolated browser acceptance before closing the plan.
