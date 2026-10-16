# Code Review by GPT-6 Astra

Date: September 8, 2026  
Project: Website Defacement Monitoring System  
Status: Remediation fully completed — Historical record at [`refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`](../../refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)

## 1. Objectives and Scope

This document defines the remediation plan for 6 findings identified during the backend and frontend review, including evidence, root causes, remediation steps, test cases, and acceptance criteria. It aims to ensure remediation proceeds without compromising web monitoring accuracy or audit history integrity.

The creation of this document specifically produces the plan file as requested; it does not alter source code, tests, configuration, dependencies, artifacts, or actual databases. The remediation steps outlined hereafter represent future tasks and are not considered implemented.

This document serves as a companion remediation plan to `PROJECT_PLAN.md`; it does not replace the master roadmap, does not expand the system to multiple workers, and does not alter the deterministic detection approach. Where roadmap text states that the sandbox is enabled, this reflects system intent that the implementation had not yet achieved based on the evidence in CR-01; the master document should be updated once remediated and verified.

Limitations of this review:

- Evaluated from source code and locally installed Playwright source files.
- Simulated CR-02, CR-03, and CR-04 using in-memory SQLite with `autoflush=False` sessions matching production behavior.
- Did not connect to or write to live databases, nor dispatch real web check requests.
- Did not run the full regression suite or perform tests via actual browser UI during this review cycle.
- This inventory does not certify the absence of other defects, nor does it serve as an exhaustive security audit across all attack surfaces.

## 2. Summary of Findings and Priorities

P1 indicates issues that should be resolved before broader deployment, as they compromise security isolation or produce false alert statuses. P2 issues represent defects that should be resolved within the same remediation cycle.

| ID | Priority | Finding | Core Impact | Evidence |
| --- | --- | --- | --- | --- |
| CR-01 | P1 | Chromium sandbox not enabled per configuration | Renders web pages without the security protections intended by the system | Inspected launch call and Playwright driver |
| CR-02 | P1 | Approving older snapshot resets target status to OK | Masks latest unreviewed defacement/change status | Simulated: target=OK, latest check=Changed, acknowledged_at=None |
| CR-03 | P2 | Active baselines exceed retention cap in production | Discrepancy between UI baseline display and detector evaluation set | Configured cap=3 resulted in 4 active baselines |
| CR-04 | P2 | URL can be modified during active check | Records check results and baselines of old URL onto new target URL | Simulated: New URL has status OK but baseline references old URL |
| CR-05 | P2 | Detail page does not track scheduler when current status is OK | User observes stale status and check results | Inspected query polling and cache invalidation |
| CR-06 | P2 | Target list page lacks pagination | Displays only the first 50 items with inaccurate total count | Backend default limit=50 while frontend omits offset/limit |

## 3. Principles to Maintain During Remediation

1. Adding a baseline is not always proof that the website's latest issue has been resolved.
2. A single check task must strictly correlate with the exact URL inspected by that task.
3. Baselines designated as active by the system must match the set eligible for detector comparison.
4. Do not delete snapshots, CheckResults, or artifacts merely to satisfy baseline cap constraints.
5. Maintain the restriction against demoting the final baseline, and do not introduce auto-rebaselining that trusts the live page without review.
6. Retain authentication, CSRF protection, SSRF guards, WebSocket blocking, and existing detector thresholds.
7. Test business logic using database session configurations consistent with production.
8. Maintain single-worker deployment per current architecture; do not assume process-local guards support multiple workers.
9. Do not use production databases or live website checks as regression tests.

## 4. CR-01 — Enable Chromium Sandbox per Configuration

### 4.1 Location and Root Cause

- `backend/app/services/capture/capture.py`: `capture_snapshot()` and `playwright.chromium.launch()` invocation around line 77 at the time of review.
- `backend/app/core/config.py`: `BROWSER_DISABLE_SANDBOX=False`.
- `docker-compose.yml`: browser runtime environment and container execution user.
- `backend/tests/test_capture.py`: capture tests and launch configurations.

The code appended `--no-sandbox` only when `BROWSER_DISABLE_SANDBOX=True`, but omitted passing `chromium_sandbox=True` when configured as False. Concurrently, the installed Playwright driver itself injects `--no-sandbox` whenever `chromiumSandbox` is not explicitly True. Omitting the flag in application code was therefore not equivalent to enabling the sandbox.

### 4.2 Target Behavior

| Configuration | Required Behavior |
| --- | --- |
| `BROWSER_DISABLE_SANDBOX=False` | Explicitly pass `chromium_sandbox=True`, with no launch args disabling sandbox |
| `BROWSER_DISABLE_SANDBOX=True` | Explicitly pass `chromium_sandbox=False`, logging existing warnings |
| Runtime does not support sandbox but configured to enable | Report failure; do not automatically fall back to disabling sandbox |

### 4.3 Remediation Steps

1. Verify Python package and browser runtime versions prior to changes without upgrading dependencies as part of this task.
2. Add launch options bound directly to configuration and harmonize redundant args so they do not contradict options.
3. Preserve host-resolver rules, service worker blocking, viewport settings, and WebSocket blocking.
4. Verify runtime environments separately for Windows and Linux containers, as passing options is not proof that OS-level policies fully support sandboxing.
5. If the container runs as root and cannot support sandboxing, establish a compatible runtime (e.g., non-root user and appropriate permissions) and smoke test before adoption; do not resolve issues with silent fallbacks.
6. Update configuration descriptions, `.env.example`, and related documentation to reflect testable behavior, including container prerequisites if modifications are necessary.

### 4.4 Test Cases and Acceptance Criteria

- Mock browser launch to verify options for both True and False configurations.
- Simulate launch errors and verify that no retry with disabled sandbox occurs.
- Regression tests for redirect limits, private subresources, service workers, and WebSocket blocking continue to pass.
- Smoke test with controlled fixtures in the deployment environment and verify actual launch arguments passed.
- Clearly document sandbox support status across environments; never assert multi-platform security solely from mock tests.

## 5. CR-02 — Decouple Baseline Approval from Clearing Latest Status

### 5.1 Location and Root Cause

- `backend/app/services/review.py`: `approve_baseline()` lines 47–73.
- `backend/app/core/status.py`: state transitions.
- `backend/tests/test_review.py` and `backend/tests/test_api_routes.py`.
- Detail page and approve mutations that display approval results.

The function allowed approving any target snapshot, subsequently setting `target.status=OK` and clearing `last_error` indiscriminately, even if the latest CheckResult referenced a different snapshot or if a capture failure occurred after the snapshot being approved.

Simulated evidence: Approving an older baseline turned the target to OK while the latest check remained Changed and `acknowledged_at=None`.

### 5.2 Proposed Rules

| Scenario | Effect on Baseline | Effect on Target |
| --- | --- | --- |
| Currently Checking | Reject per existing concurrency constraint | Maintain current status |
| Approving snapshot from latest Changed check while current status is Changed/Acknowledged/Defaced | Approve and acknowledge associated check | Transition to OK permitted |
| Approving older snapshot that is not the current snapshot of latest check | Add to active baseline set within cap | Maintain latest status and error |
| Currently Failed or Availability Issue | Permit approval as baseline if other criteria pass | Retain status and last_error until a new check succeeds |
| Target is already OK | Permit approval per baseline rules | Remain OK |
| Re-approving an already active baseline | Idempotent operation | Do not alter unrelated latest results |

Rationale for retaining Failed/Availability Issue: Capture failures do not generate a new CheckResult in every case; thus, latest CheckResult alone cannot confirm that recent failures are resolved.

### 5.3 Remediation Steps

1. Read the latest CheckResult within the approval transaction, ordered by `created_at DESC, id DESC` consistent with the rest of the system.
2. Decouple the conditions for adding a baseline, acknowledging checks, and transitioning target status.
3. Allow transitioning to OK only when matching the rules above; eliminate unconditional global assignments upon approval.
4. Preserve historical `CheckResult.status` semantics, updating only acknowledgments correlated with the approval.
5. Execute approval and baseline pruning in the same transaction as CR-03; if any step fails, roll back completely.
6. Ensure UI messaging communicates successful baseline addition without implying that the latest failure was resolved if the target remains in an abnormal state.
7. Adjust existing tests expecting approval from Failed to clear errors, as that legacy expectation was part of the defect being corrected.

### 5.4 Test Cases and Acceptance Criteria

- Approving an older snapshot while latest check is Changed: Target and latest acknowledgment must not be cleared.
- Approving current snapshot of latest Changed check: Target transitions to OK and acknowledgment is recorded.
- Failed/Availability Issue occurring after latest check: Approving an older snapshot leaves error intact.
- Approving from Defaced/Acknowledged: Transition to OK permitted only for snapshots correlated with the latest result per rules.
- Cross-target snapshots and active Checking status must remain rejected.
- Duplicate approval must not acknowledge unrelated checks.
- Add API regression tests verifying committed data via fresh database sessions, rather than testing in-memory objects alone.

## 6. CR-03 — Enforce Baseline Cap Using Real System Sessions

### 6.1 Location and Root Cause

- `backend/app/services/review.py`: Sets `snapshot.is_baseline=True` and calls prune.
- `backend/app/services/checks.py`: `prune_baselines()` and `get_baseline_snapshots()`.
- `backend/app/db/session.py`: `SessionLocal(..., autoflush=False)`.
- `backend/tests/test_review.py`: `sessionmaker(bind=engine)` used default autoflush.
- `backend/tests/conftest.py`: API test session had identical discrepancies.
- `frontend/src/components/BaselineManagerModal.tsx`: Displayed hardcoded limit of 20.

When autoflush is disabled, the query selecting `is_baseline=True` does not see the snapshot whose flag was just modified, pruning against the previous set; subsequent commit then adds the new candidate, exceeding the cap.

### 6.2 Remediation Steps

1. After setting the flag, flush within the transaction before querying for pruning, without introducing intermediate commits.
2. Restrict the cap to an integer of at least 1 to prevent configuration from stripping all active baselines.
3. Preserve ordering by `captured_at DESC, id DESC` and demote by flag toggling only, never deleting records or artifacts.
4. Define behavior when a candidate is older than all existing active baselines and would not meet the cap: Validate upfront and reject with clear messaging; do not report successful approval when the candidate would be instantly demoted, and do not silently switch retention policies to approval timestamps.
5. Align test factories covering business logic and APIs to use `autoflush=False` matching production; verify observed failures and distinguish required fixture flushes from production bugs.
6. If the UI needs to display the cap, supply it via a config API accessible to the frontend rather than hardcoding 20, exposing only necessary parameters without exposing full settings.
7. Prepare a read-only assessment for existing data that may have exceeded caps due to legacy bugs, summarizing affected targets and snapshots for review prior to repair.

### 6.3 Historical Data Management

- Strictly forbid demoting or deleting live data during plan preparation or testing.
- For future repairs, apply the same rule as detectors: Retain the N newest entries and demote excess baselines only.
- Record IDs and flags prior to repair to facilitate rollback; never transition target status to OK as a side effect of repair.
- If data inconsistencies are found (e.g., snapshots missing artifacts), flag them for investigation rather than deleting or auto-approving.

### 6.4 Test Cases and Acceptance Criteria

- Cap of 3 with 3 active baselines prior to new approval: Post-commit must leave exactly 3, demoting the oldest.
- Cap of 1: Existing baseline is demoted and newer candidate remains active.
- Below cap: Existing baselines and candidate all remain active.
- Duplicate approval: Count does not increase and does not demote other baselines unnecessarily.
- Candidate older than cap window: Explicitly rejected and rolled back without state or acknowledgment changes.
- Identical capture timestamp: Tie-breaking by ID yields deterministic outcomes.
- Cap value 0 or negative: Rejected by configuration validation.
- API and service tests pass under `autoflush=False`, verifying data from a fresh session post-commit.
- UI display count, active query set, and detector loading set must align identically.

## 7. CR-04 — Prevent URL Modifications During Active Checks

### 7.1 Location and Root Cause

- `backend/app/api/routes/targets.py`: `update_target()` lines 71–80.
- `backend/app/services/concurrency.py`: `is_target_in_flight()` and worker.
- `backend/app/services/checks.py`: `run_target_check()`.
- `frontend/src/components/EditTargetModal.tsx`.
- `frontend/src/pages/TargetListPage.tsx` and `TargetDetailPage.tsx`.

PATCH requests updating URL lacked concurrency guards while Checking; capture operations began with the old URL, but upon completion wrote results to the target ID whose URL had already changed.

Simulated evidence: Updated target URL showed OK status while `baseline.final_url` contained the old URL.

### 7.2 Resolution in Current Architecture

1. Check whether incoming URL values actually differ from current values; resubmitting identical values from modals should not count as a URL modification.
2. If the URL changes and the target is Checking or in the in-flight set (including tasks awaiting semaphore acquisition), reject with HTTP 409 and user-facing error messaging.
3. Validate guards and commit without opening race windows for worker pickup under the current single event loop/worker architecture; re-evaluate synchronization if future refactoring introduces `await`.
4. Allow modifying `name` during active checks, as it does not affect detector inputs.
5. In the modal, disable URL editing when target is known to be checking, accompanied by explanatory tooltips, while retaining backend guards as the authoritative defense against stale UI state.
6. Upon HTTP 409, retain user input in the form, display error notifications, and refresh target status without closing modals prematurely.
7. Review queued tasks: Pre-queued domain keys must not diverge from the capture URL at task execution; verify this with tests once guards are added.

### 7.3 Scope of Idle URL Changes

Fixing this race does not necessitate clearing baselines or history when URLs change during idle states, nor does it allow auto-adopting new URLs as baselines. Retain existing history retention behaviors, noting that URL updates continue evaluating against previously approved baselines. If dedicated workflows for domain migration and baseline resets are desired, address them in a separate design effort.

### 7.4 Test Cases and Acceptance Criteria

- Use async events to pause mock capture post-initiation, then send PATCH to modify URL: Must receive 409 and URL remains unchanged.
- Resume task to completion and reload data: Target URL and baseline must correspond to the URL originally captured.
- Tasks waiting for semaphores with status not yet Checking: URL modifications rejected by in-flight guard.
- Renaming target during active check: Succeeds without altering URL.
- Submitting identical URL with updated name: Succeeds.
- Updating URL during idle state: Passes SSRF validation and persists.
- Requests initiated prior to worker and committed successfully: Worker must capture the new URL, avoiding cached stale URLs.
- Guard must not inadvertently impact soft delete or inactive semantics.
- Confirm behavior with API tests using two sessions coordinated via events rather than brittle sleeps.

## 8. CR-05 — Enable Target Detail Page to Track Scheduler Results

### 8.1 Location and Root Cause

- `frontend/src/hooks/useTargetDetail.ts`: `useTargetQuery()` and check/snapshot/baseline queries.
- `frontend/src/pages/TargetDetailPage.tsx`: Effect triggering refresh after Checking transitions to another state.
- `frontend/src/pages/TargetDetailPage.test.tsx`: Existing tests mocked hooks, failing to cover real polling mechanics.

When cached data reflects OK, `refetchInterval` is set to false, preventing the page from detecting when the scheduler initiates new checks. Furthermore, checks may start and complete between polling intervals, causing the UI to never observe the Checking state, especially when consecutive checks maintain identical statuses (e.g., Changed → Changed).

### 8.2 Remediation Steps

1. Establish polling for target metadata across all statuses while the detail page is open, using an initial interval of ~4 seconds aligned with the list page, reducing to ~3 seconds during Checking.
2. Periodically poll check lists with lightweight queries to detect new check IDs even when status remains unchanged, decoupling refreshes from Checking state transitions.
3. Construct a signature from the latest check (e.g., ID and acknowledgment) combined with target metadata (status, updated_at, last_error) to detect meaningful changes.
4. When signatures change, invalidate caches for snapshots, baseline, and active baselines, as well as check detail caches if review actions made prior data stale.
5. Accommodate initial captures generating baselines without CheckResults: Target transitioning from Never Checked to OK must refresh baselines and snapshots.
6. Poll metadata only; avoid redundant downloads of screenshots and diff text on each interval, preserving snapshot ID as cache key for artifact queries.
7. Stop polling upon component unmount or when target ID is unavailable, adhering strictly to query library background and window focus behaviors.
8. Validate error states to communicate failure to load current data rather than masking errors as fresh successful results.
9. Guard against effect invalidation loops: Track processed signatures and avoid invalidating caches simply due to new object references.

### 8.3 Test Cases and Acceptance Criteria

- Open detail page in OK state and simulate scheduler transitioning Checking → Changed: Badge and latest data update without page reload.
- Status transitions OK → Changed between polls without the UI observing Checking: Must display latest check and new snapshot.
- Consecutive check results are Changed with different check IDs: Must refresh latest results.
- Initial capture: Displays new baseline despite absent check records.
- Capture failure without new check: Status and error display update accordingly.
- Baseline approval/demotion: Gallery and baseline views refresh with correct data sets.
- Invariant metadata: Does not generate unnecessary artifact requests.
- Navigating away from page: Timers and requests terminate with no post-unmount updates.
- Test hook behaviors using real QueryClient instances and mock APIs with fake timers, rather than relying on mocked hook returns.
- Foreground tabs must reflect updates within the polling window plus API latency; do not mandate identical SLAs for throttled background tabs.

## 9. CR-06 — Add Pagination and Accurate Target Counts

### 9.1 Location and Root Cause

- `backend/app/api/routes/targets.py`: `list_targets()` default limit=50.
- `backend/app/schemas/target.py` and schema exports.
- `frontend/src/api/targets.ts`: `listTargets()` omitted offset/limit parameters.
- `frontend/src/hooks/useTargets.ts`: query key and polling logic.
- `frontend/src/pages/TargetListPage.tsx`: Rendered `targets.length` as total count.
- Relevant API and page tests.

### 9.2 Proposed API Contract

Introduce an endpoint for paginated responses while retaining `GET /targets` returning arrays to preserve backwards compatibility for existing consumers, e.g., `GET /targets/page?limit=50&offset=0&include_inactive=false`.

Proposed response:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

- `total` represents the count matching filters prior to limit/offset application.
- Enforce validation limits between 1–200 and offset >= 0 per existing API conventions.
- Sort by `created_at DESC, id DESC` for deterministic ordering across identical timestamps.
- Declare static route `/targets/page` before dynamic route `/targets/{target_id}`, backed by regression tests.
- New endpoints must reside under identical authentication schemes as target routes.
- Offset pagination: Additions or deletions across requests may cause boundary shifts; document that this does not provide cross-request snapshot isolation.

### 9.3 Remediation Steps

1. Add response schemas and endpoints, executing item queries and count calculations using identical filters within a single request context.
2. Add types and API client functions for paginated targets, preserving legacy API functions where consumers remain.
3. Introduce page/offset state in the list page, incorporating `limit`, `offset`, and `includeInactive` into query keys to prevent cross-page cache collisions.
4. Add Previous/Next pagination controls and range labels (e.g., "51–100 of 126 targets") rather than utilizing `items.length` as total.
5. If displaying previous page data while loading new pages, render clear loading placeholders without presenting stale data as fresh completed loads.
6. Restrict polling to the currently active page; avoid polling all system targets every 4 seconds.
7. Upon target creation, navigate to page 1 and refresh; upon editing, retain current page and refresh; upon deleting the last item on the final page, step back to the preceding valid page.
8. Adjust cache invalidation across create/update/delete/check mutations to cover query key prefixes for paginated lists.
9. Differentiate zero-target states globally from empty pages resulting from deletions or out-of-range offsets.
10. Table headers must reflect `total`, reserving `items.length` strictly for currently rendered rows.

### 9.4 Test Cases and Acceptance Criteria

| Target Count | Expected Behavior (page size=50) |
| --- | --- |
| 0 | Empty state, total=0, Next disabled |
| 1 | Displays 1 row, total=1 |
| 50 | Single complete page, Next disabled |
| 51 | Page 1 contains 50, Page 2 contains 1, total=51 |
| 126 | Navigates across 3 pages: 50 / 50 / 26 |

- Test multiple items created with identical timestamps to confirm deterministic tie-breaking.
- Invariant datasets across requests: Paging through all pages exhibits no duplicate or missing entries.
- Verify `include_inactive` applies identical filtering to both total count and returned items.
- Validate invalid limit/offset inputs and ensure authentication on new endpoints.
- Deleting the sole item on the final page: UI navigates back to the preceding page rather than sticking in a false empty state.
- Adding a target from a subsequent page: Navigates back to page 1 and displays new entry.
- Polling preserves current page position without mixing cache entries across pages.
- Existing `GET /targets` and `GET /targets/{target_id}` continue operating per legacy contracts.

## 10. Execution Sequence and Milestones

| Phase | Tasks | Prerequisites for Advancement |
| --- | --- | --- |
| A | Verify current source and prepare isolated test environment | Baseline tests, runtime, and configurations documented |
| B | CR-01 | Launch configuration tests and deployment environment smoke tests pass |
| C | CR-03 followed by CR-02 | Approval/pruning functions correctly with `autoflush=False` without masking latest results |
| D | CR-04 | API race tests under Checking and queued states pass |
| E | CR-05 | Detail page tracks scheduler results even when Checking is unobserved |
| F | CR-06 | Access targets beyond 50 with accurate total counts |
| G | Integration regression and documentation | Zero regressions in auth, capture, scheduler, review, and web UI |
| H | Rollout preparation and legacy data evaluation | Anomalies documented and verifiable repair steps established |

CR-03 precedes CR-02 within approval refactoring because they share transactions and fixtures, but both should be delivered together without deferring CR-02 outside this remediation cycle.

## 11. Integrated Test Plan

### 11.1 Environment

- Backend uses an isolated test database or in-memory SQLite with `autoflush=False`, with environment variables configured to avoid connecting to live databases.
- Artifact tests write strictly to test runner temporary directories.
- Avoid initiating application lifespans against actual `SessionLocal` in tests without overrides, as startup executes recovery/reconciliation and initializes schedulers.
- Browser smoke tests rely on controlled fixtures, avoiding external websites as volatile assertions.
- Frontend instantiates fresh `QueryClient` instances per test and cleans up timers/cache completely.

### 11.2 Sample Commands for Implementation Phase

The following commands are intended for use upon receiving actual remediation tasks; they were not run during plan drafting. Certain commands generate build/cache artifacts and should be executed in designated test workspaces.

From the backend directory:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_capture.py tests/test_review.py tests/test_api_routes.py tests/test_checks.py tests/test_concurrency.py tests/test_scheduler.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
.\.venv\Scripts\python.exe -m mypy app
```

From the frontend directory:

```powershell
npm run test
npm run lint
npm run typecheck
npm run build
```

If the development environment lacks specified tooling, inspect dev dependencies and prepare the environment beforehand; do not interpret unrunnable commands as passing checks.

### 11.3 End-to-End Acceptance Scenario

1. Seed 51 targets in the test database and confirm the 51st item is accessible from the dashboard.
2. Open the detail page of a target with an active baseline and OK status.
3. Trigger the scheduler against a fixture with modified content, verifying the UI reflects Changed and latest check results without page reload.
4. Approve an older snapshot that is not the latest current snapshot: Target must remain in Changed status.
5. Approve the latest current snapshot: Target transitions to OK and baseline count does not exceed cap.
6. Initiate a new check, temporarily pause mock capture, and submit a PATCH to modify URL via API: Must receive HTTP 409.
7. Resume capture to completion and verify snapshots correlate with the original capture URL.
8. Simulate an availability failure, then approve an older baseline: Target must continue displaying the availability error.
9. Verify sandbox launch evidence in the test runtime, distinguishing mock results from actual browser execution in reports.

## 12. Deployment, Legacy Data, and Rollback

### 12.1 Pre-Rollout

- Compile test results and modified file lists broken down by CR ID.
- The core plan does not require database schema alterations; paginated responses utilize an API schema. If implementation necessitates DB schema updates, draft a dedicated migration plan first.
- Back up the database using techniques compatible with SQLite WAL (e.g., backup APIs or cleanly stopping the service); never copy `app.db` while WAL writes are active and assume backup completeness.
- Back up artifacts associated with the database and verify backup restorability in an isolated environment.
- Verify sandbox support and runtime permissions prior to switching environments.

### 12.2 Evaluating Impact from Legacy Bugs

- CR-03: Assess active baseline counts per target and generate a dry-run list of excess baselines to demote.
- CR-02: Identify cases where `target=OK` but `latest_check=Changed` and unacknowledged for operator inspection; do not alter statuses automatically solely on this condition without reviewing history and approvals.
- CR-04: Note that `final_url` differing from `target.url` is not definitive proof of a race condition, as normal redirects occur; inspect event sequences or request operator review before marking results invalid.
- Do not delete existing baselines or auto-adopt new live pages to patch questionable records.
- Live data repair constitutes a distinct phase from code deployment and requires an auditable change log.

### 12.3 Post-Rollout

- Confirm operation under a single worker with a single scheduler instance per architecture constraints.
- Monitor capture success/failure, sandbox errors, baseline counts, and API 409 responses against designed scenarios.
- Keep detail pages open across controlled check cycles to confirm automated UI refresh.
- Verify pagination and totals against existing data without injecting unnecessary test targets into production.

### 12.4 Rollback

- Revert code and configuration to compatible previous versions, documenting which known defects will re-emerge.
- Never disable sandboxing automatically as a rollback measure; if the browser fails, halt failing capture pipelines and troubleshoot runtime errors.
- If baseline data repairs were executed, restore values using backed-up ID/flag tables rather than restoring the entire database over new check results collected post-rollout.
- Preserve snapshots and CheckResults to maintain historical auditability.

## 13. Definition of Done

- [ ] CR-01 passes launch-option regression and browser smoke tests in target environment.
- [ ] CR-02 approving older snapshots does not clear statuses/errors of recent check events.
- [ ] CR-03 active baseline counts do not exceed cap under `autoflush=False`, with UI and detector sets aligned.
- [ ] CR-04 URLs cannot be modified during Checking, queued, or in-flight states.
- [ ] CR-05 detail page reflects fresh results without observing Checking, avoiding unnecessary artifact polling.
- [ ] CR-06 renders targets exceeding 50 items via pagination with accurate total counts.
- [ ] Regression suites for auth, CSRF, SSRF, scheduler, capture, review, and soft deletes continue to pass.
- [ ] Backend tests/static checks and frontend tests/lint/typecheck/build results are fully documented.
- [ ] Distinguish pre-existing environment failures from regressions caused by modifications, providing evidence without falsely asserting full suite passes.
- [ ] Configuration documentation and user workflows match post-remediation implementation.
- [ ] Potentially impacted historical data has an audit report with zero silent repairs.
- [ ] Delivery report details modified files, test outputs, runtime constraints, and pending backlog items truthfully.

## 14. Task Status as of Creation Date

| Item | Status |
| --- | --- |
| Review and compile findings | Completed |
| Simulate CR-02/CR-03/CR-04 in memory | Issues confirmed |
| Draft remediation plan | This document |
| Remediate source code, tests, and configuration | Pending execution |
| Execute regression suite and browser acceptance tests | Pending execution |
| Inspect and repair live data | Pending execution |
| Deployment | Pending execution |
