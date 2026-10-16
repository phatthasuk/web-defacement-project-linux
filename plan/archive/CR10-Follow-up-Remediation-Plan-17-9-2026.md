# CR10 Follow-up Remediation Plan

Date: September 17, 2026  
Status: Proposed Plan — Code modifications pending

References: [CR10 Plan](Code-Review-and-Remediation-Plan-CR10-17-9-2026.md), [Main Project Plan](PROJECT_PLAN.md), and refinement documents [Phase 1](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase1-17-9-2026.md), [Phase 2](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase2-17-9-2026.md), and [Phase 3](../refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md).

## Scope and Invariants

- This document records remediation items resulting from review; creating this plan does not imply code execution.
- Maintain production database records, baseline histories, and configured monitoring targets without truncation or reset.
- Preserve single API worker constraint, session/CSRF/SSRF defenses, and detector thresholds.
- Test suites must utilize isolated SQLite databases and sandbox directory paths, never contacting live target endpoints.
- Due to missing Git history and absence of `walkthrough.md`, review was conducted against existing file state.

## 1. [P1] Resolve Changed Status Persistence under Enabled Foreign Keys

Affected files: `backend/app/services/checks.py`, `backend/app/models/snapshot.py`, `backend/app/models/check_result.py`

**Finding:** The check pipeline attempts to insert a Snapshot and a referencing CheckResult in the same database transaction without an explicit ORM flush or relationship ordering. In an in-memory SQLite database with foreign keys enabled, this yields `FOREIGN KEY constraint failed` when CheckResult is flushed prior to the referenced Snapshot.

**Action Items:**

- Explicitly flush Snapshot before persisting referencing CheckResult rows, or establish ORM relationships that guarantee insertion order while retaining transaction atomicity.
- Issue transaction rollbacks before handling errors from flush/commit to prevent reusing sessions in a failed state.
- Handle orphaned promoted files if database transactions fail, cleaning unreferenced files without affecting committed artifacts.

**Acceptance Criteria:**

- When an active baseline exists and alterations are detected, Snapshot and CheckResult are successfully inserted under enabled foreign keys with status `Changed`.
- Zero IntegrityError or PendingRollbackError occurrences on standard success paths.
- Simulated commit failures execute clean rollbacks and artifact cleanup without corrupting historical data.

## 2. [P1] Align Test Fixtures with Production Foreign Key Enforcement

Affected files: `backend/tests/conftest.py`, `backend/tests/test_checks.py`, and standalone SQLite engine fixtures.

**Finding:** The primary test SQLite engine does not enforce foreign keys, whereas application engines do. Validating `PRAGMA foreign_keys` solely on the app engine fails to detect constraint errors during test execution.

**Action Items:**

- Enforce `PRAGMA foreign_keys=ON` across all test database connections.
- Add regression tests verifying: Baseline present → Difference detected → `Changed` status written successfully.
- Add test assertions validating that unresolvable foreign keys raise `IntegrityError` (per CR10-06).
- Isolate PRAGMA checks to dedicated test databases without attaching live databases.

**Acceptance Criteria:**

- Regression tests fail on item 1 before remediation and pass post-fix.
- Unreferenced foreign keys are rejected with IntegrityError.
- Database test suites pass with foreign keys enabled on test-only storage.

## 3. [P2] End-to-End Staging Artifact Cleanup During Capture Cancellation

Affected files: `backend/app/services/capture/capture.py`, `backend/app/services/checks.py`, tests in capture/checks/concurrency.

**Finding:** The `finally` cleanup block in `run_target_check` executes only after `capture_snapshot` returns. If coroutine cancellation occurs after staging files are written but during `await browser.close()`, no `CaptureResult` is returned to the caller, abandoning staging directories until periodic cleanup runs.

**Action Items:**

- Mandate that the staging creator handles cleanup if execution aborts or is canceled prior to returning a completed result.
- Cover cancellation during browser teardown and async context manager exits.
- Preserve CancelledError propagation and guarantee in-flight reservation release.
- Add tests simulating task cancellation post-write but pre-return.

**Acceptance Criteria:**

- No orphaned staging directories remain immediately following task cancellation.
- In-flight target reservations are promptly discarded without blocking subsequent checks.
- Normal captures and promotions retain required artifacts cleanly.

## 4. [P3] Formalize Production Deployment Configurations

Affected files: `docker-compose.yml`, frontend static build configurations, development compose configurations, `README.md`.

**Finding:** Docker Compose continues executing frontend via `npm run dev` and backend with `--reload --reload-dir app`, which represents development tooling rather than production Stage 2 deployment.

**Action Items:**

- Implement a multi-stage Docker build for the frontend, serving compiled static assets via an optimized web server (e.g., Nginx) with proper caching headers.
- Remove `--reload` from production backend runtime configurations while retaining `--workers 1`.
- Provide isolated `docker-compose.dev.yml` and `docker-compose.yml` with clear usage documentation in README.
- Verify reverse proxy routing, frontend client routing (HTML5 history mode), and API proxying.

**Acceptance Criteria:**

- Production deployment serves minified static assets instead of the Vite dev server.
- Backend processes do not restart upon writing local capture files.
- Clean production builds pass with documentation matching actual Compose topology.

## 5. [P2] Synchronize Phase 3 Documentation with Plan Specifications

Affected files: Refinement Phase 3 docs, `UPDATE_SUMMARY.md`, `README.md`.

**Action Items:**

- Reconcile tracking identifiers to match original specifications:
  - CR10-08: Alembic migration alignment
  - CR10-09: Triage guards and error banner
  - CR10-10: Run Check trigger on Target Detail
  - CR10-12: Production frontend deployment
- Correct misnamed migration references to `d2b3c4e5f6a7_structural_detector.py`.
- Document schema verification procedures accurately without re-stamping live databases.
- Adjust "100% completed" claims to reflect verified delivered scope.

**Acceptance Criteria:**

- All 12 items align accurately with verified implementation evidence.
- Migration filenames match repository source files.
- Documentation reflects current verification metrics without relying on stale test logs.

## 6. Verification and Acceptance Workflow

1. Resolve Item 1 and verify with regression tests from Item 2.
2. Verify cancellation cleanup via Item 3 using isolated mock runs.
3. Execute backend suites, frontend tests, linting, and production builds.
4. Verify production Compose configurations in a clean testing sandbox.
5. Update project documentation with verified outputs and remaining constraints.
