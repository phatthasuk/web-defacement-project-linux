# Summary: Stage 1 Implementation — Operational Stabilization
**Date:** September 3, 2026 (Updated post Opus 5 review)  
**Document Name:** `Stage1-Implementation-3-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md) (Sections 1.1, 1.2, 1.3, and Finding F5)  
**Review Cross-Reference:** [`plan/review stage 1 by opus 5.md`](../../plan/review%20stage%201%20by%20opus%205.md)

---

## 1. Executive Summary

This document records the complete implementation and post-review hardening of **Stage 1 (Operational Stabilization)** according to `plan/PROJECT_PLAN.md`.

Before this stage, checks could only be executed via manual API invocation or test calls, every single check wrote permanent disk files (accumulating ~480 MB/day for 6 targets checked hourly), failed runs leaked orphaned files on disk (Finding F5), and network/server availability errors (timeouts, DNS failures, HTTP 5xx) were lumped into generic failures or could trigger false change alerts.

Following an independent architectural review by Claude Opus 5, the scheduler was further hardened with task reference retention, exception logging, graceful shutdown draining, and in-flight retry delays, and all linter gates were cleanly satisfied.

### Scope Delivered

| Task | Plan Reference | Problem Solved | Status |
| :--- | :--- | :--- | :--- |
| **In-Process Scheduler** | **Stage 1.1** | Automatic periodic checks with per-target interval, random jitter (0–180s), strong task retention, and graceful shutdown draining. | ✅ Complete |
| **Discard Unchanged Artifacts & Staging Pipeline** | **Stage 1.2 & Finding F5** | Eliminates 480 MB/day disk accumulation by deleting temporary staging captures for `OK` checks and preventing orphan artifact leaks on failure. | ✅ Complete |
| **Reconcile Orphan Artifacts** | **Finding F5 & Section 9.3** | Startup reconciliation safely cleans expired staging directories and unreferenced disk files within `DATA_DIR` without risking runtime race conditions. | ✅ Complete |
| **Separate Availability Issue from Changed** | **Stage 1.3** | Distinguishes transient network/server failures (timeouts, DNS errors, connection resets, HTTP 5xx) from defacements (`Changed`) and application bugs (`Failed`). | ✅ Complete |
| **Frontend Status & Badge Integration** | **Stage 1.3 UI** | Amber status badge for `Availability Issue` with corresponding TypeScript types and tests. | ✅ Complete |

### Complete 6-Gate Verification Summary

Consistent with the standard quality gate checklist established in Phase A:

| Quality Gate | Command | Baseline Before Stage 1 | Result After Stage 1 & Review Hardening | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Tests** | `python -m pytest -q` | 99 passed, 1 warning | **109 passed, 1 warning** *(+10 tests)* | ✅ Clean |
| **Backend Types** | `python -m mypy app` | Clean (42 source files) | **Clean** (46 source files) | ✅ Clean |
| **Backend Lint** | `python -m ruff check .` | Clean | **Clean** (0 errors) | ✅ Clean |
| **Frontend Tests** | `npm test -- --run` | 33 passed (7 files) | **34 passed (7 files)** *(+1 test)* | ✅ Clean |
| **Frontend Types & Build** | `npm run build` (`tsc -b && vite build`) | Passed | **Passed** (0 errors, 8.21s bundle) | ✅ Clean |
| **Frontend Lint** | `npm run lint` (`eslint .`) | 0 errors, 1 warning | **0 errors, 1 pre-existing warning** (`useAuth.tsx:91`) | ✅ Clean |

*Note on test arithmetic:* The immediate baseline before Stage 1 was 99 passed (73 from Phase A + 9 multi-baseline matching + 17 structural detector). Stage 1 added 10 tests across scheduler, staging lifecycle, and status transitions, bringing the total to 109.

---

## 2. Stage 1.1: In-Process Automated Scheduler

### Background & Architecture
Running 240 checks/day across multiple sites requires steady execution without operator intervention. Relying on an external cron would bypass in-process concurrency semaphores.

### Implementation & Hardening Details
- **Location:** [`backend/app/services/scheduler.py`](../../backend/app/services/scheduler.py)
- **Engine:** `CheckScheduler`, an `asyncio.Task` loop running during FastAPI lifespan.
- **Interval & Jitter Tuning:**
  - `CHECK_INTERVAL_SECONDS = 3600` (1 hour default per target).
  - `CHECK_JITTER_MAX_SECONDS = 180` (uniform 0–180s random jitter).
  - `SCHEDULER_POLL_INTERVAL_SECONDS = 15` (governs loop tick frequency).
- **Initial Startup Staggering:** Newly registered targets receive a short initial delay (1 to 60 seconds) rather than running simultaneously at startup.
- **Strong Task Reference Retention (Opus 5 Review 4.2):**
  - Background checks are tracked in `self._background_tasks: set[asyncio.Task]`.
  - Prevents CPython garbage collection from dropping unreferenced weak-reference tasks mid-execution during long unattended soaks.
  - Done callbacks (`_on_task_done`) discard completed tasks and log unhandled exceptions immediately.
- **Graceful Shutdown Draining (Opus 5 Review 4.2):**
  - When the server shuts down, `stop()` cancels the scheduler loop and awaits all in-flight check tasks via `await asyncio.gather(*self._background_tasks, return_exceptions=True)`.
  - Prevents targets from being abruptly abandoned in `Checking` on clean server restarts.
- **In-flight Skip with 60s Retry Delay (Opus 5 Review 6.3):**
  - If a target is already `Checking` or in flight when its scheduled time arrives, the scheduler skips triggering and reschedules retry in **60 seconds** (`now + 60.0`) rather than advancing a full 1-hour interval. This avoids losing scheduled data points.

---

## 3. Stage 1.2 & Finding F5: Staging Pipeline & Artifact Lifecycle

### Staging Pipeline Architecture
1. **Staged Output**:
   - `capture_snapshot` in [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py) directs initial capture files to a private staging directory: `data/staging/{snapshot_id}/`.
2. **Conditional Promotion vs. Zero-Disk Discard**:
   - In [`backend/app/services/checks.py`](../../backend/app/services/checks.py):
     - **Baseline Capture** (`baseline is None`): Promotes staging files to permanent directories (`data/screenshots/`, `data/text/`, `data/html/`) and creates a database row (`is_baseline=True`).
     - **Genuine Change Detected** (`has_changes is True`): Promotes staging files to permanent directories, saves `Snapshot(is_baseline=False)`, and links `check_result.current_snapshot_id = snapshot.id`.
     - **Unchanged Check** (`has_changes is False`): **Discards staging artifacts immediately (`shutil.rmtree`)**. No files are saved to permanent storage. Links `check_result.current_snapshot_id = matched_baseline_id`.
       - **Disk consumption: 0 bytes** (eliminates 480 MB/day accumulation).
       - **Frontend Compatibility**: `TargetDetailPage.tsx` and `CheckDetailPage.tsx` check `isSameSnapshot = currentSnapshotId === baselineSnapshotId`, cleanly displaying the existing baseline without 404 errors.
3. **Leak-Proof Cleanup on Error (Finding F5)**:
   - All capture and diffing stages wrap artifact operations in `try ... except ... finally`. If any step raises an exception, `_discard_snapshot_files(capture)` immediately deletes the staging directory, preventing orphan leaks.
4. **Startup Reconciliation Routine (`reconcile_artifacts`)**:
   - Executed on application startup in [`backend/app/main.py`](../../backend/app/main.py):
     - Scans `data/staging/` and removes abandoned staging directories older than `STAGING_CLEANUP_MAX_AGE_SECONDS` (30 minutes).
     - Queries all valid `Snapshot.id` records from the database and deletes unreferenced orphan files in `data/{screenshots,text,html}/`.
     - Strictly enforces Section 9.3 security: verifies all deletion paths resolve strictly within `settings.data_dir_path`.
   - **Architectural Rationale for Startup-Only Execution (Opus 5 Review 5.1):** Artifact promotion moves files to permanent storage slightly before the snapshot row is committed to the database. Running reconciliation only at startup avoids a potential race condition where an active check's newly promoted files could be swept by a concurrent periodic cleanup.

---

## 4. Stage 1.3: Availability Issue Separation

### Problem Solved
Transient network hiccups, timeouts, DNS errors, or reverse proxy 5xx errors previously caused targets to enter `Failed` or, worse, compared error HTML against baselines to trigger false defacement alerts.

### Implementation Details
1. **Core Status State Machine** ([`backend/app/core/status.py`](../../backend/app/core/status.py)):
   - Added `STATUS_AVAILABILITY_ISSUE = "Availability Issue"`.
   - Allowed transitions: `Checking` -> `Availability Issue`, `Availability Issue` -> `Checking` / `OK`.
2. **Intelligent Error Classification** ([`backend/app/services/checks.py`](../../backend/app/services/checks.py)):
   - `is_availability_error`: Detects `TimeoutError`, DNS resolution errors (`gaierror`, `ERR_NAME_NOT_RESOLVED`), connection resets/refused (`ERR_CONNECTION_REFUSED`), and host unreachable errors.
   - **Security Boundary:** Explicitly excludes `SsrfBlockedError` — SSRF attempts remain classified as security violations (`Failed`), not availability issues.
3. **HTTP 5xx Interception**:
   - HTTP 500, 502, 503, 504 responses immediately trigger `Availability Issue`, discard staging files, and prevent false defacement diffs.
4. **Concurrency Layer Support** ([`backend/app/services/concurrency.py`](../../backend/app/services/concurrency.py)):
   - Worker timeout (`CHECK_TIMEOUT_SECONDS = 90`) is classified as `Availability Issue` via `mark_target_status`.
5. **Frontend Integration**:
   - Added `'Availability Issue'` to `TargetStatus` type union in [`frontend/src/types/target.ts`](../../frontend/src/types/target.ts).
   - Styled high-contrast orange badge in [`frontend/src/components/TargetStatusBadge.tsx`](../../frontend/src/components/TargetStatusBadge.tsx) (`bg-orange-950/60 border border-orange-800/50 text-orange-400`).

---

## 5. Design Observations & Trade-Offs Recorded

As noted in the Opus 5 review, these design characteristics are deliberately recorded for future stages:

1. **Quiet-Period Visual History Trade-Off (Review 6.1):**
   - By discarding artifacts for `OK` checks, no visual evidence is stored for hours when the page is quiet.
   - This was an explicit trade-off to keep disk growth at 0 bytes/day for the 1-person IT team. Baselines and changed snapshots remain fully preserved. Recorded in `PROJECT_PLAN.md` Section 5.2.
2. **Stage 3 Escalation for Persistent 5xx (Review 6.2):**
   - Because HTTP 5xx is treated as an `Availability Issue` (which does not trigger immediate defacement alerts), an attacker who crashes a site or whose payload causes 500 errors could remain unalerted.
   - **Requirement for Stage 3:** Added Item 3.4 to `PROJECT_PLAN.md` requiring an escalation alert if a target remains in `Availability Issue` across several consecutive checks (e.g. 2–3 hours).

---

## 6. File Inventory of Changes

### Backend Files
- **[`backend/app/core/config.py`](../../backend/app/core/config.py)**: Added scheduler interval, jitter, poll interval, and staging max age configuration settings.
- **[`backend/app/core/status.py`](../../backend/app/core/status.py)**: Added `STATUS_AVAILABILITY_ISSUE` and transition state mappings.
- **[`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py)**: Output directed to `data/staging/{snapshot_id}/`.
- **[`backend/app/services/checks.py`](../../backend/app/services/checks.py)**:
  - Added `_promote_staging_artifacts`, `_discard_snapshot_files`, `is_availability_error`, and `reconcile_artifacts`.
  - Updated `run_target_check` for 0-byte discard on `OK`, staging promotion on change, and HTTP 5xx handling.
- **[`backend/app/services/concurrency.py`](../../backend/app/services/concurrency.py)**: Added `mark_target_status` supporting `STATUS_AVAILABILITY_ISSUE` and line wrapping for ruff.
- **[NEW] [`backend/app/services/scheduler.py`](../../backend/app/services/scheduler.py)**: Implemented background scheduler loop with jitter, strong task reference retention, exception logging, graceful shutdown draining, and 60s retry on in-flight targets.
- **[`backend/app/main.py`](../../backend/app/main.py)**: Wired `CheckScheduler` and `reconcile_artifacts` into FastAPI `lifespan`.
- **[`backend/tests/test_checks.py`](../../backend/tests/test_checks.py)**: Unit tests for staging discard, promotion, diff error cleanup, timeout/5xx classification, and startup reconciliation.
- **[`backend/tests/test_status.py`](../../backend/tests/test_status.py)**: Sorted imports and added transition test coverage for `STATUS_AVAILABILITY_ISSUE`.
- **[NEW] [`backend/tests/test_scheduler.py`](../../backend/tests/test_scheduler.py)**: Unit tests for scheduler start/stop, jitter calculation, in-flight skips with 60s retry delay, task draining on stop, and inactive target purging.
- **[`backend/tests/test_concurrency.py`](../../backend/tests/test_concurrency.py)**: Updated timeout test assertions to match `STATUS_AVAILABILITY_ISSUE`.

### Frontend Files
- **[`frontend/src/types/target.ts`](../../frontend/src/types/target.ts)**: Added `'Availability Issue'` to `TargetStatus`.
- **[`frontend/src/components/TargetStatusBadge.tsx`](../../frontend/src/components/TargetStatusBadge.tsx)**: Added orange status badge design.
- **[`frontend/src/components/TargetStatusBadge.test.tsx`](../../frontend/src/components/TargetStatusBadge.test.tsx)**: Added test verification for badge rendering.

### Documentation Files
- **[`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)**: Updated Section 5.2 (quiet-period trade-off), marked Finding F5 as done, and added Stage 3.4 (sustained availability escalation alert).
- **[`refinement/3-9-2026/Stage1-Implementation-3-9-2026.md`](../../refinement/3-9-2026/Stage1-Implementation-3-9-2026.md)**: Completely updated with 6-gate checklist, hardened scheduler documentation, and accurate test delta metrics.
