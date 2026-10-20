# Dashboard Left Overview Panel — Implementation Plan

**Created:** 2026-10-20 (Asia/Bangkok)
**Source inspected:** `06adbb6923713acf327da7798591da58462fe229` plus current local changes.
**Implemented:** Not started. **Tested:** Not run. **Runtime verified:** Not verified.

## 1. Purpose, sequence and boundaries

Use the wide-screen left area for a compact Overview of the current results of
monitors the signed-in user can access. Counts act as shortcuts into the central
target table. The [right Active Checks plan](Dashboard_Right_Active_Checks_Plan_20-10-2026.md)
owns live check progress and the shared responsive layout; implement that layout
first, then add this independently deliverable panel.

The left panel is a target-status overview, not proof of scheduler, database,
capture-service or whole-system health. It does not define severity, confirmed
incidents, daily check totals or notification policy. Those require separate
data/roadmap work. Use the [core roadmap](PROJECT_PLAN.md) and
[status register](ROADMAP_STATUS_AND_BACKLOG.md) for those dependencies.

This task plans the feature only. No application implementation, deployment,
Stage 2 operational change or real monitoring capture is included.

## 2. Contents and scope

Show “Overview” and the scope label “All active monitors you can access”. Ignore
the table's search, tag, status and pagination controls for these overview counts.
Inactive monitors are excluded in the first version. An Operator sees only
assigned active monitors; an Admin sees all active monitors.

Provide Total monitors and a compact list of all existing status counts:

| Status | Meaning in this panel |
| :--- | :--- |
| Never Checked | Target has no completed check result yet. |
| Checking | Current durable target status is Checking. Queue/retry details live in Active Checks. |
| Awaiting Baseline | Human baseline approval is still required. |
| OK | Most recent recorded target result is OK; not a system-health guarantee. |
| Changed | Recorded differences await the existing review workflow; not confirmed defacement. |
| Failed | Recorded failed check status. |
| Availability Issue | Recorded availability problem; distinct from Failed. |
| Acknowledged | Existing acknowledged target status. |
| Defaced | Existing operator-confirmed target status. |

Keep each status separate, retain zero counts after a successful response, and
show text with color/icon rather than color alone. Do not introduce a combined
“needs attention” severity number whose meaning has not been approved. The sum
of status counts must equal Total monitors for the same authorized population.
If a future unknown status occurs, expose it as unrecognized data rather than
drop it into OK or silently exclude it from the total.

## 3. Filter interaction and responsive placement

Make each status a labelled button such as “Changed: 4 monitors”. The active
table status is indicated with `aria-pressed`; a short note explains that a
shortcut resets other table filters so the count and result population match.

On selection, set the chosen status, reset to page 1, clear both live/debounced
search and tag/tag-match filters, and preserve the selected sort order. Total
monitors clears the status as well. Cancel stale search debounce work so a prior
typed query cannot reapply after the shortcut. Preserve unrelated supported URL
parameters. Updating filters must not submit the Add New Monitor form or trigger
a check. Keep keyboard focus on the selected shortcut and announce updated table
results after successful refresh. Counts may change between polls; do not promise
the table is a transactional snapshot of the earlier number.

At the wide layout threshold defined by the right-panel plan (initially 1600
CSS px), put the Overview in the reserved approximately 240 px left column.
Below it, render one compact expandable Overview section above table controls;
do not leave an empty sidebar or squeeze the target table. Reuse the same data
and one accessible component instance. Align the three areas without a second
Admin form column; preserve the form behavior from the layout plan.

At narrow widths allow labelled status rows to wrap. Test large counts and
browser zoom. Keep announcements restrained; polling count changes must not
repeat the complete status list to screen readers.

## 4. Data contract and authorization

The current table is paginated (50 items; API maximum 200) and filtered.
Never compute global totals by counting its returned rows, fetching only the
default `/targets` page, or collecting every page in the browser.

Add read-only `GET /targets/summary` before dynamic target-ID routes. Proposed
typed response: `total`, `by_status`, `observed_at`, with explicit active-target
scope. Use an authorization-scoped aggregate over `accessible_targets(...)`
with `Target.is_active == true`, grouped by current target status. Derive total
from the same aggregate to avoid contradictory counts during concurrent updates.
Do not count historical CheckResults or return unassigned target identities.
Keep business/aggregation logic in the service layer; the route supplies auth,
session and response serialization. No migration or capture behavior change is
expected. `observed_at` is UTC; render timestamps with `utils/date.ts`.

An authenticated Operator with no assignments receives a successful zero summary.
Unauthenticated requests receive 401. Inaccessible target IDs are never revealed;
existing drill-down/detail access must retain 404 behavior. Counts cannot leak
targets through tag filters, deactivation, assignment removal or session caching.

Use `apiFetch` in `src/api/targets.ts`, mirrored backend/frontend types, and an
exported TanStack Query key for the summary. Poll at the existing four-second
cadence while this dashboard is visible, with retained data during revalidation.
Invalidate on create/update/delete, checks, review decisions and relevant member
assignment changes; background polling covers other users' changes. Follow the
existing auth/access-denial cache-clearing behavior. Do not fetch on hover or add
per-status requests.

## 5. Loading, failure and consistency

- Initial loading: show placeholders without invented zeros.
- Successful empty response: show Total 0 and an explicit empty population message.
- Initial failure: show an error and retry control; never “all OK” or “no monitors”.
- Refresh failure: retain previous counts, label them stale, and show last
  successful refresh time. Do not treat a failed poll as a status transition.
- Logout, revocation or changed user: remove retained counts immediately; never
  show the previous user's summary while the new session loads.
- Run start, retry wait and completion: counts follow authoritative target status;
  do not independently increment/decrement them from registry activity events.

## 6. Delivery and acceptance

1. Complete the shared responsive frame from the right-panel plan and confirm
   space and form placement at intended widths.
2. Add aggregate service, scoped endpoint, types/API/hook and query invalidation.
3. Build the Overview and its responsive presentation, filter shortcuts and
   distinct loading/error/stale/empty states.
4. Test more than 200 targets, multiple pages, every status, empty assignments,
   inactive records, concurrent status changes and off-filter targets. Assert
   exact counts and total consistency without per-target SQL/API requests.
5. Test Admin, assigned/unassigned/no-assignment Operators, unauthenticated
   requests, logout, revocation and assignment changes. Verify filter shortcuts
   with search debounce, URL tags/status, sort and pagination; preserve existing
   mutation authorization and CSRF behavior.
6. Run the repository backend pytest/Ruff/mypy and frontend test/lint/build
   commands as listed in the right-panel plan. Record current failures separately
   from historical Windows cleanup or migration lint findings.
7. Run the isolated app with disposable users and mocked/local fixtures. Check
   both roles, 1920/1600/1440/1280/768/390 px widths, 200% zoom, keyboard-only
   shortcuts, selected state, error/retry/stale/empty views and right-panel
   coexistence. Record browser version and screenshots. Do not use live data or
   trigger captures against real websites.
8. Add a dated English refinement record (Issue, Implementation, Verification)
   with source commit, exact commands/procedures, date/time/timezone, environment,
   results, exclusions and next action. Update status fields independently.

Completion requires correct authorized full-population counts, matching filter
behavior, accessible responsive layout, no loss of form input, and recorded test
and isolated browser evidence. New work starts as Not started / Not run / Not
verified. Existence of this plan is not an implementation or verification pass.

## 7. Future candidates outside this delivery

Overdue-check reporting, scheduler health, check-duration trends, daily results
and notification statistics need separately defined metrics, retention and scoped
APIs. Do not add decorative placeholders claiming these are available. The left
panel can grow later when those features have accurate data and acceptance.

Planning evidence: 2026-10-20 Asia/Bangkok, Windows checkout; inspected paginated
target routes, frontend filters/hooks/API and the current status model. No
application test, runtime check or production operation was performed for this
documentation-only task.
