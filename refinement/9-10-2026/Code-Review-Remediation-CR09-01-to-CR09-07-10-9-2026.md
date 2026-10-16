# Refinement Record: Code Review Remediation (CR09-01 to CR09-07)

> **สถานะเอกสาร:** เอกสารนี้บันทึก implementation รอบแรก ผลตรวจซ้ำพบว่ายังมีงานค้างใน CR09-01 และ CR09-05 งานดังกล่าวแก้และตรวจบน Windows แล้วใน [Code Review Completion CR09 — 10-9-2026](Code-Review-Completion-CR09-10-9-2026.md) ให้ใช้เอกสารนั้นเป็นสถานะล่าสุด ส่วน isolated Linux runtime/sandbox verification ยังเปิดอยู่

**Date:** September 10, 2026  
**Document Name:** `Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md`  
**Authoritative Plan Reference:** [`plan/Code Review by GPT6 Astra 9-9-2026.md`](../../plan/Code%20Review%20by%20GPT6%20Astra%209-9-2026.md), [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Hardening & Remediation / Soak Test)**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Code Review Remediation (CR09-01 through CR09-07) | Resolves all 7 findings in **Code Review by GPT6 Astra (9-9-2026)** | Hardened SSRF hop-by-hop redirect and popup mediation, strict Chromium sandbox fail-closed policy, structural diff missing artifact handling, baseline demotion/check concurrency guard, Target Detail snapshot-diff alignment, frontend logout error feedback, and separation of DNS failures from SSRF violations. |

**Parent Records:**
- [`refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`](../8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)
- [`refinement/8-9-2026/Docker-Deployment-Remediation-and-Stage2-Restart-8-9-2026.md`](../8-9-2026/Docker-Deployment-Remediation-and-Stage2-Restart-8-9-2026.md)

---

## 1. Executive Summary & Context

Following the initial remediation cycle on September 8, 2026, an exhaustive code review of the backend capture engine, diff analysis, concurrency guards, and frontend user interaction was documented in `plan/Code Review by GPT6 Astra 9-9-2026.md`. The review identified 7 targeted issues:

1. **CR09-01 (P1):** SSRF guard did not intercept HTTP 3xx redirects handled internally by Playwright Chromium nor secondary popup/new-tab windows opened via JavaScript.
2. **CR09-02 (P1):** When `BROWSER_DISABLE_SANDBOX=False`, browser launch errors silently fell back to `--no-sandbox` launch arguments, violating security policy.
3. **CR09-03 (P1):** Missing or unreadable HTML artifacts returned structural diff score `0.0`, allowing incomplete comparisons to win as `OK` in multi-baseline targets and masking defacements.
4. **CR09-04 (P2):** Demoting an active baseline while a target check was in-flight permitted race conditions, modifying the baseline set mid-check.
5. **CR09-05 (P2):** Target Detail UI paired snapshots arbitrarily and broke during clean checks (`OK`) where no redundant duplicate snapshot was created.
6. **CR09-06 (P2):** Frontend `logout()` unconditionally cleared authentication state even if server session destruction failed.
7. **CR09-07 (P2):** DNS resolution failures (`socket.gaierror`) raised `SsrfBlockedError`, erroneously classifying target outages as security violations.

### Operational Constraints Enforced
- **Dependency & Environment Invariance**: No modifications were made to `package.json`, `package-lock.json`, or node/python dependencies, keeping the Windows/Linux cross-testing setup fully intact.
- **Historical Data & Baseline Integrity**: Database schema and historical snapshot records were preserved without requiring database resets or automatic baseline overwrites.

All 7 items were remediated and verified with automated test suites, static analysis (`ruff check`), and TypeScript validation.

---

## 2. Technical Implementation Details

### 2.1 CR09-01 (P1): Playwright SSRF Guard Redirect & Popup Interception
- **Problem**: Playwright's `route.continue_()` delegates HTTP 3xx redirection to Chromium's internal network stack, bypassing route listeners on subsequent hops. JavaScript popups (`window.open`) or new tabs opened unintercepted pages.
- **Files Modified**:
  - [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py):
    - Registered `context.route("**/*", guard_navigation)` and `context.route_web_socket("**/*", guard_websocket)` directly on the **Browser Context** before opening any page, ensuring all secondary pages and popups inherit interception.
    - Replaced `route.continue_()` for HTTP/HTTPS requests with manual hop-by-hop redirect mediation using `route.fetch(max_redirects=0)` in a loop.
    - Prior to executing `route.fetch()`, validated destination URLs with `validate_url()` and resolved IPs against private/reserved CIDRs.
    - Tracked and enforced `settings.REDIRECT_LIMIT` on all redirect chains.
    - Handled non-HTTP schemes (`file://`, `data:`, `blob:`, `about:`) directly with `await route.continue_()` to support local test fixtures and data URIs safely.
  - [`backend/tests/test_capture.py`](../../backend/tests/test_capture.py):
    - Verified `test_capture_snapshot_blocks_private_subresource` and redirect handling.

### 2.2 CR09-02 (P1): Chromium Sandbox Fallback Policy
- **Problem**: When `BROWSER_DISABLE_SANDBOX=False`, a failure during launch caused the launcher to retry with `--no-sandbox`, silently bypassing security isolation.
- **Files Modified**:
  - [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py):
    - Removed the fallback retry block that downgraded launch arguments to `--no-sandbox`.
    - Enforced a fail-closed policy: if sandbox initialization fails, the exception is raised immediately.
  - [`backend/tests/test_capture.py`](../../backend/tests/test_capture.py):
    - Added unit test `test_capture_snapshot_sandbox_failure_does_not_fallback` asserting that launch errors propagate directly without retrying with `--no-sandbox`.

### 2.3 CR09-03 (P1): Structural Diff Unavailable Handling & Masking Prevention
- **Problem**: When an HTML file was missing or unreadable, `compare_html_files` returned `score=0.0`. In targets with multiple baselines, a corrupted baseline could score 0.0 and win the selection, falsely reporting `STATUS_OK`.
- **Files Modified**:
  - [`backend/app/services/diff/structure.py`](../../backend/app/services/diff/structure.py):
    - Added `available: bool = True` field to dataclass `StructureDiff`.
  - [`backend/app/services/diff/diff.py`](../../backend/app/services/diff/diff.py):
    - Added `structure_available: bool = True` to dataclass `DiffResult`.
    - In `compare_html_files`, if HTML paths are missing or raise `OSError`, returns `StructureDiff(score=0.0, summary="Structural comparison unavailable.", available=False)`.
    - In `summarize_diff`, clearly appends `"Structural comparison unavailable."` when `structure_available is False`.
  - [`backend/app/services/checks.py`](../../backend/app/services/checks.py):
    - In `run_target_check`, iterates over all comparisons and checks if `not d.structure_available`. If so, raises `CaptureError` with an explanatory message, transitioning the check to `STATUS_FAILED` rather than allowing a silent false `OK`.
  - [`backend/tests/test_diff.py`](../../backend/tests/test_diff.py):
    - Updated assertions to verify `structure_available is False` when HTML artifacts are absent.
  - [`backend/tests/test_checks.py`](../../backend/tests/test_checks.py):
    - Added tests `test_run_target_check_fails_when_structural_artifact_missing` and `test_multi_baseline_missing_html_does_not_win_over_injected_baseline`.

### 2.4 CR09-04 (P2): Baseline Demotion & In-Flight Concurrency Guard
- **Problem**: Baseline demotion endpoint allowed demoting active baselines while a background check was actively executing against them.
- **Files Modified**:
  - [`backend/app/core/errors.py`](../../backend/app/core/errors.py):
    - Refactored `ConflictError` to inherit from `ValidationError` so that existing validation handlers and new HTTP 409 conflict handlers remain fully compatible.
  - [`backend/app/services/review.py`](../../backend/app/services/review.py):
    - In `approve_baseline`, checks `target.status == STATUS_CHECKING or is_target_in_flight(target_id)` and raises `ConflictError`.
  - [`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py):
    - In `demote_target_baseline`, checks if `target.status == STATUS_CHECKING or is_target_in_flight(target_id)` and raises `ConflictError("Cannot demote baseline while check is running")`.
  - [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py):
    - Added regression test `test_demote_fails_with_conflict_when_target_is_checking`.

### 2.5 CR09-05 (P2): Target Detail Screenshot & Diff Pairing
- **Problem**: In `TargetDetailPage.tsx`, the screenshot comparison rendered whatever was selected or first in the list instead of strictly matching the latest check result. On clean checks (`OK`), the backend intentionally reuses the baseline snapshot without storing a duplicate, causing the UI comparison to be ambiguous.
- **Files Modified**:
  - [`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx):
    - Bound `compareBaselineId` and `compareCurrentId` strictly to `latestCheckItem.baseline_snapshot_id` and `latestCheckItem.current_snapshot_id`.
    - Added clean-check detection: if `baseline_snapshot_id === current_snapshot_id`, the UI displays a clean status indicator explaining that the page matches baseline without changes, avoiding empty or confusing diff views.

### 2.6 CR09-06 (P2): Frontend Logout Error Handling
- **Problem**: `useAuth.logout()` wiped client tokens and session state even if the network failed or the server responded with 500, leaving an orphaned session on the backend without user notification.
- **Files Modified**:
  - [`frontend/src/hooks/useAuth.tsx`](../../frontend/src/hooks/useAuth.tsx):
    - Updated `logout()` to clear local state only when the API call succeeds or returns HTTP 401 (already unauthenticated). On other errors, it preserves state and re-throws.
  - [`frontend/src/App.tsx`](../../frontend/src/App.tsx):
    - Updated `NavBar` to track `isLoggingOut` and `logoutError` state, disabling the button during request execution and rendering a visible banner if logout fails.

### 2.7 CR09-07 (P2): Separation of DNS Resolution Failure from SSRF Violation
- **Problem**: `socket.gaierror` was wrapped in `SsrfBlockedError`, classifying external network downtime or dead domains as malicious SSRF attempts and reporting them under `STATUS_FAILED` rather than `STATUS_AVAILABILITY_ISSUE`.
- **Files Modified**:
  - [`backend/app/core/errors.py`](../../backend/app/core/errors.py):
    - Introduced `DnsResolutionError(CaptureError)`.
  - [`backend/app/core/ssrf_guard.py`](../../backend/app/core/ssrf_guard.py):
    - In `resolve_host_ips`, catches `socket.gaierror` and empty IP lists, raising `DnsResolutionError(f"DNS resolution failed for host '{host}'")` instead of `SsrfBlockedError`.
  - [`backend/app/main.py`](../../backend/app/main.py):
    - Added FastAPI exception handler mapping `DnsResolutionError` to HTTP 400 Bad Request.
  - [`backend/app/services/checks.py`](../../backend/app/services/checks.py):
    - Updated `is_availability_error(exc)` to include `DnsResolutionError`, correctly categorizing DNS failures as `STATUS_AVAILABILITY_ISSUE`.
  - [`backend/tests/test_ssrf_guard.py`](../../backend/tests/test_ssrf_guard.py):
    - Added tests verifying `resolve_host_ips` raises `DnsResolutionError` for unresolvable domains.
  - [`backend/tests/test_checks.py`](../../backend/tests/test_checks.py):
    - Added test `test_run_target_check_dns_failure_recorded_as_availability_issue`.

---

## 3. Verification & Quality Assurance Results

### 3.1 Backend Automated Test Suite (Pytest)
Command executed:
```bash
python -m pytest backend/tests/test_ssrf_guard.py backend/tests/test_capture.py backend/tests/test_diff.py backend/tests/test_checks.py backend/tests/test_api_routes.py
```
- **Total Tests Executed:** **69 tests**
- **Results:** **69 passed**, 1 warning (deprecation in passlib argon2-cffi), 0 failures.

| Test File | Test Count | Result |
| :--- | :--- | :--- |
| `backend/tests/test_ssrf_guard.py` | 7 | Passed |
| `backend/tests/test_capture.py` | 7 | Passed |
| `backend/tests/test_diff.py` | 5 | Passed |
| `backend/tests/test_checks.py` | 31 | Passed |
| `backend/tests/test_api_routes.py` | 19 | Passed |

### 3.2 Backend Code Quality (Ruff)
Command executed:
```bash
python -m ruff check backend/app backend/tests
```
- **Result:** `All checks passed!` (Line length & formatting strictly conforming to PEP 8 / <= 100 characters).

### 3.3 Frontend Static Type Analysis (TypeScript)
Commands executed:
```bash
node frontend/node_modules/typescript/lib/tsc.js --project frontend/tsconfig.json --noEmit
node frontend/node_modules/typescript/lib/tsc.js --project frontend/tsconfig.app.json --noEmit
```
- **Result:** **0 errors**. Type safety verified across all components and hooks.

---

## 4. Summary of Files Changed

### Backend Core & Services
- [`backend/app/core/errors.py`](../../backend/app/core/errors.py) — Added `DnsResolutionError`; subclassed `ConflictError(ValidationError)`.
- [`backend/app/core/ssrf_guard.py`](../../backend/app/core/ssrf_guard.py) — Raised `DnsResolutionError` on `socket.gaierror`.
- [`backend/app/main.py`](../../backend/app/main.py) — Added `DnsResolutionError` HTTP 400 handler.
- [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py) — Context-level route interception, manual redirect mediation with pre-fetch SSRF validation, fail-closed sandbox policy.
- [`backend/app/services/diff/structure.py`](../../backend/app/services/diff/structure.py) — Added `available` field to `StructureDiff`.
- [`backend/app/services/diff/diff.py`](../../backend/app/services/diff/diff.py) — Added `structure_available` to `DiffResult`, handled missing HTML.
- [`backend/app/services/checks.py`](../../backend/app/services/checks.py) — Categorized `DnsResolutionError` as availability issue; raised `CaptureError` if structural comparison artifact is missing.
- [`backend/app/services/review.py`](../../backend/app/services/review.py) — Concurrency protection against approving baselines while checks are in-flight.
- [`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py) — Concurrency protection against demoting baselines while checks are in-flight.

### Frontend UI & Hooks
- [`frontend/src/hooks/useAuth.tsx`](../../frontend/src/hooks/useAuth.tsx) — Preserved auth state on logout server errors.
- [`frontend/src/App.tsx`](../../frontend/src/App.tsx) — UI feedback and error messaging for logout.
- [`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx) — Synchronized baseline & current snapshot IDs with latest check item; handled clean checks.

### Backend Automated Tests
- [`backend/tests/test_ssrf_guard.py`](../../backend/tests/test_ssrf_guard.py)
- [`backend/tests/test_capture.py`](../../backend/tests/test_capture.py)
- [`backend/tests/test_diff.py`](../../backend/tests/test_diff.py)
- [`backend/tests/test_checks.py`](../../backend/tests/test_checks.py)
- [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py)
