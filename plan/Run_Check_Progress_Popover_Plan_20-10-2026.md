# Run Check Progress Popover — Implementation Plan

**Created:** 2026-10-20 (Asia/Bangkok)

**Source inspected:** `31cf6b279f075b13d830ad658ba40825e0c6f127`

**Scope:** Backend progress reporting and frontend popover implementation; no deployment.

**Implemented:** Partial (four defects found in follow-up review). **Tested:** Partial. **Runtime verified:** Not verified.

**Open corrective work:** [Remediation plan for the four review findings](Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md).

## 1. Objective and roadmap relationship

Show real check progress when an operator hovers over the `Checking` badge in
the target table. Keep the existing table compact. Support keyboard focus and
click/tap so the same information is accessible without a mouse.

This is a standalone operator UX add-on. The core [project plan](PROJECT_PLAN.md)
continues to own Stage priorities. This document does not add a Stage, close a
finding or authorize changes to the active Stage 2 observation run. Implementation
was requested on 2026-10-20; production deployment remains outside this change.

## 2. Current behavior confirmed in source

| Area | Source and behavior |
| :--- | :--- |
| Badge | `frontend/src/components/TargetStatusBadge.tsx` renders a styled span with an optional native title; there is no progress popover. |
| Table | `frontend/src/pages/TargetListPage.tsx` shows the badge, retry deadline and next scheduled check. The Run Check button becomes disabled during a check. |
| Refresh | `frontend/src/hooks/useTargets.ts` polls targets every four seconds and preserves previous paginated data. |
| API | `backend/app/schemas/target.py` exposes run ID, source, attempt count and next deadline, but no phase data. Target responses are assembled through `_target_read` in `api/routes/targets.py`. |
| Attempt | `services/attempts.py` creates a durable `CheckAttempt` before entering concurrency control and persists final status and retry scheduling afterward. |
| Waiting | `services/concurrency.py` acquires global and domain semaphores before `run_target_check`. A reserved or queued run can therefore retain its previous target status before `Checking` starts. |
| Capture | `services/capture/capture.py` navigates, optionally waits for readiness, reads HTML/text, and takes screenshots. Readiness is bounded/best effort; returning from it does not prove every asset loaded successfully. |
| Comparison | `services/checks.py` compares against approved baselines in a worker thread and selects the closest result. A capture without an approved baseline becomes `Awaiting Baseline`. |
| Recovery | `recover_stale_checks` and attempt-finalization recovery already handle interrupted durable state. Progress must complement these paths. |

## 3. User experience

### Trigger and layout

- Keep the current `Checking` badge appearance and table row height.
- Open after approximately 300 ms of pointer hover; open immediately on keyboard
  focus. Click/tap toggles a pinned popover.
- Keep it open while the pointer moves from the trigger into the popover.
  Use a short close delay to bridge the gap.
- Escape, outside click, and leaving both trigger and panel close it. Restore
  focus to the trigger after keyboard dismissal when the trigger still exists.
- Use a native button trigger with an accessible name, `aria-expanded`,
  `aria-controls`, and a labelled non-modal panel. Do not trap focus. Avoid a
  competing native `title` on the progress trigger.
- Position the panel outside table overflow using a React portal. Clamp/flip it
  within the viewport and reposition on scroll/resize. Use existing Tailwind,
  React and lucide-react; add no UI dependency.
- Use English labels consistent with the application. Limit width to about
  300–340 px and fit smaller screens without horizontal overflow.

### Contents

Show the current phase, elapsed attempt time, attempt number/max attempts,
last successful status-refresh time, and a small checklist. Use distinct icons
and text for completed, running, pending, skipped/unavailable, and failed steps.
Do not rely only on color. Do not show a percentage or estimated finish time.

Example (illustrative data):

```text
Check in progress                     Attempt 1/3
Elapsed: 24 seconds

Done       Open website
Done       Page readiness checks
Done       Capture page data
Running    Compare with baselines
Pending    Save result
```

“Done” means that the named operation returned successfully; it does not mean
the website is safe or that every resource loaded. Detector coverage or missing
HTML must never be represented as a clean structural result.

### Queue, retry, completion and errors

- During an accepted run waiting for capacity, expose `Waiting for a check slot`
  on a small transient activity trigger beside the existing status badge. Keep
  the previous result visible and do not add `Queued` to target business statuses.
  Disable duplicate Run Check actions while this activity is confirmed active.
- Before the accepted run's progress arrives, show `Check requested` without
  inventing a backend phase. A rejected duplicate request is not a new run.
- During retry waiting, preserve the failure/availability badge and existing
  `Retry n/max · deadline` line. Make that line the progress trigger; do not label
  the target `Checking` while no attempt is executing. Use the persisted deadline.
- If an open popover sees completion, show the actual terminal result and stop
  its running indicator. It may stay open until dismissed; leave no permanent
  checklist or extra result row in the table.
- No approved baseline: show comparison as skipped with `No approved baseline`,
  and the final outcome as `Awaiting Baseline`.
- Readiness disabled: mark that step skipped, not completed.
- If a poll fails, retain the last known phase with `Unable to refresh progress`
  and the last successful refresh time. Keep initial loading, missing progress,
  refresh failure and actual check failure distinct. A failed status request
  never changes the target's check outcome.
- If the component unmounts, the target disappears, or access is revoked, close
  the popover and clear timers/listeners and cached sensitive target state using
  existing authentication/query behavior.

## 4. Backend design

### Phase vocabulary and boundaries

| Phase | Enter at | Leave at |
| :--- | :--- | :--- |
| `queued` | Accepted reservation / scheduled dispatch | Both required concurrency slots acquired |
| `opening_page` | Browser setup and navigation begin | Navigation and existing redirect validation return |
| `waiting_page_ready` | Existing readiness operation begins | Operation returns, or is explicitly skipped |
| `capturing` | Artifact extraction begins | Existing HTML/text/screenshot capture and validation return |
| `comparing` | Baseline comparison begins | All required baseline comparisons and best-match selection return |
| `saving_result` | Result/artifact finalization begins | Result and attempt/schedule persistence finish |
| `retry_wait` | Durable retry deadline committed | Next attempt is dispatched |
| `finished` | Attempt/run finalization succeeds | Replaced by newer activity or bounded cache eviction |

On error, retain the failed phase and terminal outcome; do not mark later phases
completed. `retry_wait` is run activity between attempts, not an extra detector.
Comparison remains one coarse step: per-detector or per-baseline live progress
is outside the first version.

### Storage and API contract

Use a small process-local progress registry for transient phase information,
consistent with the required single uvicorn worker. Keep `Target`, `CheckAttempt`
and `CheckResult` authoritative for outcomes, run ownership, attempts and retry
deadlines. Do not add phase writes to SQLite or change `Target.updated_at` on
every phase, which would distort Last Activity and add write contention.

Add an optional `check_progress` object to `TargetRead`, assembled through the
existing authorized target list/detail response path. Proposed fields:

| Field | Meaning |
| :--- | :--- |
| `run_id`, `url_revision`, `attempt_number` | Ownership and attempt identity |
| `phase`, `state` | Stable phase enum; state `queued`, `running`, `retry_wait` or `finished` |
| `attempt_started_at`, `phase_started_at`, `updated_at`, `finished_at` | UTC timestamps; nullable when not applicable |
| `steps` | Bounded phase records with state and start/end timestamps; no page content |
| `outcome`, `error_code`, `failed_phase` | Safe result metadata; nullable while executing |

Reuse existing maximum-attempt and retry-deadline fields rather than inventing
independent scheduling values. Define null semantics explicitly: no matching
transient progress is available; null never means the check succeeded. An active
durable attempt without telemetry must display `Progress details unavailable`.

Bound the registry to one current run per target and one attempt's phase list;
retain finished records for a short documented TTL (initial proposal: 60 seconds)
and enforce a fixed size cap. Evict safely on target removal/new runs. Read no
historical attempts per row: avoid N+1 queries, and batch any durable enrichment.
No schema migration is planned for this transient design. Any later decision to
persist phase history requires a separately reviewed reversible migration.

### Instrumentation and lifecycle

1. Register waiting activity after reservation succeeds for manual and scheduled
   runs. Bind updates to target ID, run ID, URL revision and attempt number.
2. Add a lightweight reporting interface across attempts, concurrency, checks and
   capture. Preserve existing injected three-argument `CaptureFunc` fixtures;
   choose a scoped reporter/context or a compatible adapter instead of requiring
   every test fake to change its signature.
3. Emit only at actual boundaries. Capture telemetry must not add navigation,
   readiness waits, DOM operations, network requests or overlay interactions.
4. Update comparison progress on the event loop before/after the existing worker
   operation. Do not share an ORM session with the comparison worker.
5. Guard every update/cleanup by run and attempt identity. A timed-out worker's
   late report or old run finalizer must not overwrite a newer run.
6. Do not report a finished run before attempt finalization and retry scheduling
   are known. If result persistence succeeds but attempt finalization fails,
   preserve the real result and surface unavailable finalization telemetry;
   do not fabricate a fully successful checklist.
7. Clean up on cancellation, timeout, rejected/skipped work, startup and shutdown.
   A restart clears transient data; expose the existing durable recovery result
   instead of reconstructing unrecorded completed steps.
8. Reporter failures are diagnostic only: log safe IDs/codes, keep detection and
   artifact handling unchanged, and let the UI show telemetry unavailable.

Use `core.time.utcnow()` for stored/comparable timestamps and explicit UTC API
serialization. Use a monotonic clock for internal durations where appropriate.
Do not expose raw exception strings, target URLs, artifact paths or page content
in the new progress object.

## 5. Frontend integration

- Add matching TypeScript progress types and a reusable
  `CheckProgressPopover` wrapper. Keep `TargetStatusBadge` usable for static
  statuses elsewhere.
- Integrate first in `TargetListPage`; reuse in `TargetDetailPage` where its
  existing badge provides the same activity context.
- Consume `check_progress` from existing TanStack Query target responses. Keep
  the four-second list polling and previous-data behavior; do not add a request
  per row, hover request storm, WebSocket, SSE or direct `fetch`.
- Short phases may finish between polls. Display backend-recorded completed
  steps without animating fabricated intermediate states.
- Update elapsed text locally only while visible, from the backend attempt
  timestamp. Clamp negative elapsed values, avoid treating client clock skew as
  a failure, and stop timers on terminal state/unmount. Queue/retry labels must
  distinguish waiting time from active attempt time.
- Preserve existing result filters, sorting, Last Activity, triage protections,
  retry deadlines and silent focus revalidation. A stale cached phase cannot
  override a newer terminal target response or a different run/revision.
- Use restrained live announcements for phase changes; do not announce an elapsed
  counter every second. Respect reduced-motion preferences.

## 6. Delivery sequence

| Order | Deliverable | Acceptance gate |
| :--- | :--- | :--- |
| 1 | Progress enums/types, registry and API contract tests | Null/ownership/UTC/expiry semantics and scoped responses established |
| 2 | Pipeline instrumentation and lifecycle tests | Manual, scheduled, queue, retry, skip, cancellation and recovery paths are accurate |
| 3 | Popover component and target page integration | Compact layout, accessible input modes and explicit loading/error states |
| 4 | Regression suite and isolated browser checks | Required commands and scenarios recorded against the actual source |
| 5 | Documentation and evidence | Refinement record and status register reflect actual results only |

**Execution:** The four reviewed defects in phase completion, recovery outcome
and popover dismissal have been fixed with regression coverage. Focused backend
tests passed (54 tests across progress, attempts and checks); frontend tests
passed (100 tests), ESLint passed, and the production build passed. The full
backend suite passed 276 tests and failed two cleanup-artifact tests because
Windows lacks the symlink privilege and POSIX directory operations those tests
require. Targeted Ruff and mypy passed; full Ruff still reports six existing
findings in an applied migration. Isolated browser and Linux runtime verification
remain open. See the [remediation plan](Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md)
and [remediation evidence](../refinement/10-20-2026/Run-Check-Progress-Popover-Remediation-20-10-2026.md).

## 7. Verification plan and acceptance criteria

### Backend

- Test actual phase ordering with injectable captures; readiness-disabled and
  no-baseline paths must explicitly skip the appropriate steps.
- Test capacity waits, accepted/rejected manual triggers, scheduled checks,
  retry deadlines/exhaustion, SSRF blocks, budget failures, HTTP/network errors,
  comparison errors, persistence errors and cancellation/timeouts.
- Test stale reports after a newer run, thread completion after timeout, URL
  revision changes, restart recovery, registry expiry/cap and telemetry failures.
- Preserve result scores, thresholds, artifact promotion/discard and duplicate
  suppression; compare outcomes with progress reporting enabled and unavailable.
- Exercise list/detail visibility for Admin, assigned Operator, unassigned
  Operator (404 for inaccessible detail, no list entry), and unauthenticated
  requests (401). Verify existing trigger mutations still enforce CSRF.
- Confirm progress does not change Last Activity or introduce per-target SQL
  queries during list serialization.

Run from `backend/` with its venv:

```text
python -m pytest --basetemp=.pytest-tmp tests -q
ruff check app tests scripts alembic
mypy app
```

Report actual failures, including platform-dependent cleanup failures if present;
historical results are not an exemption or a current pass.

### Frontend and browser

- Test hover delay, leaving/crossing into the panel, click/tap pinning, keyboard
  focus, Escape/outside click, focus restoration and timer/listener cleanup.
- Test every phase and skipped/unavailable state, retries, completion while open,
  request failures, stale responses, access loss and rapid run replacement.
- Verify stable row layout, portal positioning near viewport/table edges,
  scrolling, zoom, small screens, and multiple targets running concurrently.
- Use `src/test-utils.tsx` and meaningful interaction tests with mocked responses.

Run from `frontend/` using the repository Node version:

```text
npm run test
npm run lint
npm run build
```

Run the UI with `backend-isolated` / `scripts/run_isolated_dev.py` and the frontend
on the configured development port. Use disposable test users and mocked API
responses or controlled local fixtures. Never use the plain live-data backend or
trigger real monitored websites. Record browser/version and screenshots of key
states. If isolation is unavailable, record browser verification as not run.

Capture instrumentation also requires Linux Docker fixture verification under
the existing SSRF protections and container hardening before claiming runtime
verification. Keep this separate from Windows test evidence and the broader
Phase 5 acceptance; this feature does not close Phase 5 findings.

## 8. Boundaries, evidence and completion

No detector/sensitivity changes, auto-baseline approval, overlay dismissal,
capture budget changes, dependency upgrades, multi-worker support, persistent
queue, production restart, live-data edits, new credentials outside disposable
test databases, or deployment configuration changes are included.

After implementation, create
`refinement/<M-D-YYYY>/Run-Check-Progress-Popover-<D-M-YYYY>.md` with **Issue**,
**Implementation**, and **Verification**. Record source revision, exact commands,
date/time in Asia/Bangkok, OS, browser/image versions and digest where relevant,
results, exclusions and next action. Update the status register with independent
Implemented, Tested and Runtime verified values. Update API/operator documentation
if behavior changes. Do not mark implementation complete until all applicable
acceptance checks have evidence or explicit reported limitations.

### Planning verification record

- Date/environment: 2026-10-20, Asia/Bangkok; Windows PowerShell checkout.
- Procedure: inspected the source paths in section 2 and reviewed the core
  roadmap, status register, security review and Linux runtime verification plan.
- Implementation record: see
  [`refinement/10-20-2026/Run-Check-Progress-Popover-20-10-2026.md`](../refinement/10-20-2026/Run-Check-Progress-Popover-20-10-2026.md)
  for exact commands, results and limitations.
