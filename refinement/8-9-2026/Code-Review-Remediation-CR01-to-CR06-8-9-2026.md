# Refinement Record: Code Review Remediation (CR-01 to CR-06)

**Date:** September 8, 2026  
**Document Name:** `Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`  
**Authoritative Plan Reference:** [`plan/archive/Code Review by GPT-6 Astra.md`](../../plan/archive/Code%20Review%20by%20GPT-6%20Astra.md), [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Hardening & Remediation / Soak Test)**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Code Review Remediation (CR-01 through CR-06) | Resolves all findings in **Code Review by GPT-6 Astra** | Hardened Playwright sandbox isolation, baseline approval state consistency, baseline retention cap under autoflush=False, URL modification concurrency guard, target detail polling/invalidation, and target list pagination. |

**Parent Records:**
- [`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](../7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md)
- [`refinement/7-9-2026/Check-Result-Summary-Text-Overflow-Fix-7-9-2026.md`](../7-9-2026/Check-Result-Summary-Text-Overflow-Fix-7-9-2026.md)
- [`refinement/4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md`](../4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md)

---

## 1. Executive Summary & Context

An in-depth code review of the Website Defacement Monitoring System by GPT-6 Astra (reference: `plan/archive/Code Review by GPT-6 Astra.md`) identified 6 critical issues impacting container security, state integrity, and scalability:
1. **CR-01 (P1):** Chromium sandbox was not enabled as configured, because Playwright silently appends `--no-sandbox` unless `chromium_sandbox` is explicitly passed.
2. **CR-02 (P1):** Approving an older historical snapshot reverted target status to `OK`, masking ongoing outages or recent unreviewed changes.
3. **CR-03 (P2):** Baseline retention exceeded configured caps when database sessions ran with `autoflush=False`, and UI modals hardcoded quota limits.
4. **CR-04 (P2):** Modifying a target URL while a check was in-flight caused artifacts from the previous URL to be recorded against the new URL.
5. **CR-05 (P2):** The Target Detail page (`TargetDetailPage`) suspended polling when a target was in `OK` status, leaving stale results on screen following background scheduler runs.
6. **CR-06 (P2):** The Target List page (`TargetListPage`) lacked server-side pagination, silently truncating results past the default 50-item limit and reporting inaccurate total counts.

In this development cycle, all 6 findings were remediated sequentially, supported by expanded automated test suites (Pytest, Vitest) and verified through static analysis (Ruff, Mypy, ESLint, TypeScript Build) with a 100% pass rate.

---

## 2. Technical Implementation Details

### 2.1 CR-01: Chromium Sandbox Configuration
- **Problem**: Playwright Python automatically injects `--no-sandbox` into Chromium launch arguments unless `chromium_sandbox` is explicitly specified in `playwright.chromium.launch()`.
- **Files Modified**:
  - [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py):
    - Updated `launch()` to explicitly pass `chromium_sandbox=not settings.BROWSER_DISABLE_SANDBOX`.
    - Restricted `--no-sandbox` launch argument injection strictly to when `settings.BROWSER_DISABLE_SANDBOX` is `True`.
  - [`backend/tests/test_capture.py`](../../backend/tests/test_capture.py):
    - Added unit tests verifying that when `BROWSER_DISABLE_SANDBOX = False`, `chromium_sandbox` is `True` and `--no-sandbox` is omitted, and when `True`, `--no-sandbox` is included and `chromium_sandbox` is `False`.

### 2.2 CR-03: Baseline Retention Cap & Session Auto-Flush Safety
- **Problem**: In environments with `autoflush=False` or during chained transactions, `prune_baselines` and baseline creation failed to detect uncommitted database rows, accumulating active baselines beyond configured limits.
- **Files Modified**:
  - [`backend/app/services/checks.py`](../../backend/app/services/checks.py):
    - Added boundary assertion in `prune_baselines`: `if keep < 1: raise ValueError("keep must be at least 1")`.
    - Added explicit `db.flush()` immediately after updating demoted baselines to synchronize state before subsequent queries.
  - [`backend/app/services/review.py`](../../backend/app/services/review.py):
    - Called `db.flush()` immediately after assigning `snapshot.is_baseline = True` prior to calling `prune_baselines`.
  - [`backend/app/schemas/config.py`](../../backend/app/schemas/config.py), [`backend/app/api/routes/config.py`](../../backend/app/api/routes/config.py), [`frontend/src/api/config.ts`](../../frontend/src/api/config.ts):
    - Exposed `max_baselines_per_target: int` in `ConfigRead` schema and config API endpoint.
  - [`frontend/src/components/BaselineManagerModal.tsx`](../../frontend/src/components/BaselineManagerModal.tsx):
    - Replaced hardcoded "20" with `config?.max_baselines_per_target ?? 20` for dynamic UI quota display.

### 2.3 CR-02: Baseline Approval State Masking & Consistency
- **Problem**: Approving an older historical snapshot previously set `target.status = STATUS_OK` unconditionally, masking production outages (`STATUS_FAILED` or `STATUS_AVAILABILITY_ISSUE`) and ignoring whether the snapshot reflected the latest check.
- **Files Modified**:
  - [`backend/app/services/review.py`](../../backend/app/services/review.py):
    - **Temporal Integrity Guard**: Rejects snapshot approval candidates whose `captured_at` timestamp is older than all currently active baselines (raises `InvalidBaselineCandidateError` &rarr; returns HTTP 400 Bad Request).
    - **Outage Protection**: Preserves target status if currently `STATUS_FAILED` or `STATUS_AVAILABILITY_ISSUE`, preventing outage masking.
    - **Latest Snapshot Match**: Transitions `target.status = STATUS_OK` only if the approved snapshot matches the target's most recent check.
    - Reordered target ID validation to precede `STATUS_NEVER_CHECKED` checks.
  - [`backend/tests/test_review.py`](../../backend/tests/test_review.py):
    - Configured session fixtures with `autoflush=False` to reproduce real session conditions.
    - Added test coverage for historical candidate rejection, outage state preservation, and latest snapshot matching.

### 2.4 CR-04: URL Modification Concurrency Guard
- **Problem**: Changing a target URL while a check was running created a race condition where screenshots from the old URL were recorded against the updated URL.
- **Files Modified**:
  - [`backend/app/core/errors.py`](../../backend/app/core/errors.py), [`backend/app/main.py`](../../backend/app/main.py):
    - Created `ConflictError` exception class mapped to HTTP 409 Conflict with descriptive client messaging.
  - [`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py):
    - In `update_target`, if the request modifies `url` while target status is `STATUS_CHECKING` or `is_target_in_flight(target_id)` is true, immediately raises `ConflictError`.
    - Modifications to other fields (such as `name` or `allowed_domains`) or resubmitting the identical URL proceed normally.
  - [`frontend/src/components/EditTargetModal.tsx`](../../frontend/src/components/EditTargetModal.tsx):
    - Detects `target.status === "Checking"`, disabling the URL input field and rendering an explanatory warning banner.
    - Handles HTTP 409 responses from the API gracefully without clearing user form input.
  - [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py):
    - Added regression tests verifying 409 Conflict rejection when attempting to alter a URL while a check is running.

### 2.5 CR-05: Target Detail Scheduler Tracking & Query Reactivity
- **Problem**: `TargetDetailPage` previously polled only when `status === 'Checking'`. When background scheduler jobs finished, or when status shifted from `OK` to `Changed`/`Defaced`, the page failed to refresh without a manual browser reload.
- **Files Modified**:
  - [`frontend/src/hooks/useTargetDetail.ts`](../../frontend/src/hooks/useTargetDetail.ts):
    - Configured continuous polling in `useTargetQuery()` (3,000ms when `Checking`, 4,000ms otherwise) and `useTargetChecksQuery()` (every 4,000ms).
  - [`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx):
    - Implemented a unified `useRef` storing `{ targetId, signature }`, where `targetSignature` captures `status`, `updated_at`, `last_error`, and `checkSignature` captures `id`, `acknowledged_at`, `status` of the latest check.
    - Handled signature tracking and target switching inside a single effect. When a target's signature shifts, automatically invalidates `['snapshots', targetId]`, `['baseline', targetId]`, `['baselines', targetId]`, and `['checks', targetId]`.
    - Removed disconnected reset effects to prevent clearing initial cache reads in React StrictMode. (See Section 4).

### 2.6 CR-06: Target List Pagination & Total Count
- **Problem**: `GET /targets` defaulted to `limit=50, offset=0` and returned a plain array. The frontend omitted pagination parameters, silently truncating target lists over 50 items and displaying inaccurate counts.
- **Files Modified**:
  - [`backend/app/schemas/target.py`](../../backend/app/schemas/target.py), [`backend/app/schemas/__init__.py`](../../backend/app/schemas/__init__.py):
    - Created `PaginatedTargetsRead` schema: `items: list[TargetRead]`, `total: int`, `limit: int`, `offset: int`.
  - [`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py):
    - Added `GET /targets/page` positioned before `GET /targets/{target_id}` to avoid routing collisions, preserving `GET /targets` for backward compatibility.
    - Accepts `limit=50`, `offset=0`, `include_inactive=false`. Computes exact total with `select(func.count()).select_from(base_query.subquery())` after filtering and orders by `created_at DESC, id DESC`.
  - [`frontend/src/types/target.ts`](../../frontend/src/types/target.ts), [`frontend/src/api/targets.ts`](../../frontend/src/api/targets.ts):
    - Added interface `PaginatedTargets` and client function `getPaginatedTargets(limit = 50, offset = 0, includeInactive = false)`.
  - [`frontend/src/hooks/useTargets.ts`](../../frontend/src/hooks/useTargets.ts):
    - Added `usePaginatedTargetsQuery(limit = 50, offset = 0, includeInactive = false)` with query key `['targets', 'page', { limit, offset, includeInactive }]` and 4,000ms polling.
  - [`frontend/src/pages/TargetListPage.tsx`](../../frontend/src/pages/TargetListPage.tsx):
    - Switched to `usePaginatedTargetsQuery(pageSize, offset)` with `pageSize=50`.
    - Added pagination controls (Previous / Next buttons, page counter, "Showing X to Y of Z targets").
    - Updated table header to reflect true total target count.
  - [`frontend/src/pages/TargetListPage.test.tsx`](../../frontend/src/pages/TargetListPage.test.tsx):
    - Updated test mocks to support the paginated payload structure.

---

## 3. Verification & Quality Assurance Results

### 3.1 Backend Test Suite (Pytest)
```bash
pytest backend/tests -v
```
- **Result**: **123 tests passed** (expanded from 116 tests).
- Verified new test cases:
  - `test_capture.py`: Chromium sandbox launch flags (enabled/disabled).
  - `test_review.py`: Historical baseline candidate rejection, autoflush=False resilience, outage preservation.
  - `test_api_routes.py`: Paginated endpoint `/targets/page` and URL change rejection during checks (409 Conflict).

### 3.2 Backend Code Quality (Ruff & Mypy)
```bash
ruff check backend
mypy app  # from backend directory per pyproject.toml
```
- **Ruff**: `All checks passed!` (Line length <= 100, formatting clean).
- **Mypy**: `Success: no issues found in 46 source files`.

### 3.3 Frontend Test Suite (Vitest)
```bash
npm run test
```
- **Result**: **61 tests passed** across 10 test suites (expanded from 55 tests in 9 suites).
- Added `TargetDetailPage.cache.test.tsx` covering 6 regression scenarios verifying query cache refresh on background polling updates.

### 3.4 Frontend Lint & Build (TypeScript / Vite)
```bash
npm run lint
npm run build
```
- **ESLint**: 0 errors (1 pre-existing warning in `useAuth.tsx`).
- **Vite Build**: Succeeded (`tsc -b && vite build`), generating production bundles cleanly.

---

## 4. CR-05 Follow-up: Cached Detail First-Result Refresh

**Date:** September 8, 2026  
**Status:** Resolved and verified with frontend regression suite.

### 4.1 Root Cause Analysis
During testing of cached page navigations, an effect separation issue was identified: an initial effect recorded `currentSignature`, but a secondary effect keyed on `targetId` reset the ref to `null` post-mount. When the first polling result arrived, it evaluated as an initial mount and returned before triggering invalidation, leaving historical snapshots and image IDs displayed on screen. This occurred even under React StrictMode.

### 4.2 Resolution
- Updated `frontend/src/pages/TargetDetailPage.tsx` to store `targetId` and `signature` within a single composite ref.
- Unified evaluation into a single effect that reads previous state and records current state atomically, preventing post-mount resets.
- Compares signatures strictly within the same target.
- Automatically refreshes snapshots, baseline, baselines, and checks on signature changes without re-requesting static artifacts unnecessarily.

### 4.3 Regression Test Results
Added `frontend/src/pages/TargetDetailPage.cache.test.tsx` using real QueryClient and query hooks while mocking API boundaries:

| Test Case | Result |
| :--- | :--- |
| First result from cache without seeing Checking (standard mode) | Passed |
| First result from cache (React StrictMode) | Passed |
| Only latest check updates while target metadata remains constant | Passed |
| Initial load without prior cache data followed by subsequent check | Passed |
| Target switching and return, refreshing only current target cache | Passed |
| Unchanged metadata suppresses duplicate artifact fetching | Passed |

- **Before component fix:** Regression suite caught the bug with 4 failures and 2 passes.
- **After component fix:** Entire frontend suite passed with **61/61 tests across 10 suites**.
