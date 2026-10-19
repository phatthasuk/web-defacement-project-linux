# Audit Findings Remediation Plan

**Created / last updated:** October 19, 2026  
**Audit reference:** [Audit Report (Archive)](archive/codebase_audit_report_by_argon_comment_by_sol.md)  
**Baseline Commit SHA:** `e2934813f81d5660dccf9cdd54273de58c4105ec` (`e293481` — `docs(plan): archive artifact cleanup dry-run and record plan review`)

---

## 1. Baseline Environment Metadata

| Item | Environment used for verification | Plan standard / target |
| :--- | :--- | :--- |
| **OS (Local Audit Host)** | Windows 10/11 (`win32-x64`, PowerShell) | Used for development and unit/integration tests that do not depend on the Linux kernel or Docker |
| **Target Deployment OS** | Ubuntu Linux (`x86_64`, Docker Compose) | Used to verify container isolation, seccomp, cgroups, WebRTC egress, and `dir_fd` cleanup |
| **Python (`backend/.venv`)** | Python `3.13.7` (`fastapi 0.128.8`, `starlette 0.52.1`, `playwright 1.63.0`, `mypy 1.13.0`, `ruff 0.7.4`, `pytest 8.3.3`) | Use versions pinned in `backend/requirements.txt` and record tool versions for CI |
| **Node.js (`frontend`)** | Node `v24.7.0`, `vitest 4.1.9`, TypeScript (`tsc -b`), ESLint; Windows native bindings matching `package-lock.json` are installed (`@esbuild/win32-x64@0.21.5`, `@rolldown/binding-win32-x64-msvc@1.1.4`, `@rollup/rollup-win32-x64-msvc@4.62.2`, `lightningcss-win32-x64-msvc@1.32.0`) without modifying the lockfile | Run `tsc -b --pretty false`, `eslint src`, and `vitest run` successfully across all files |

> [!IMPORTANT]
> **Items excluded from remediation (excluded / refuted):**
> - **B-04:** Removed from the backlog after reproducing the case on Python `3.13.7`. `urllib.parse.urlsplit` filters `\t`, `\r`, and `\n` (CVE-2022-0391 patch / CPython issue #88048) and strips leading C0 controls and spaces automatically. Together with the project's `.strip()`, `extract_structure()` detects the external URL and returns a difference score of `1.0` as expected.
> - **B-05 (whitespace handling in script `type`):** Do not trim or remove characters inside the `module`, `importmap`, or `speculationrules` tokens arbitrarily; retain behavior consistent with the HTML Standard and Chromium.

---

## 2. Master Backlog: Code and Verification Status

The table distinguishes **Code Status** from **Verification Status** and splits findings that previously combined multiple issues (`B-06`, `B-08`, `B-09`, `B-11`, `F-06`, `F-08`, `F-09`) into independent items:

| ID | Phase | Severity | Code Status | Verification Status | Target Files | Scope and Verification Summary |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- |
| **ENV-01** | Phase 0 | — | Completed | **Verified** | `backend/.venv`, `frontend/node_modules` | Synced `backend/.venv` packages with `requirements.txt` and installed the Windows native bindings for `vitest`/`vite` matching `package-lock.json`; verified with `pytest` and `vitest run` |
| **B-03** | Phase 1 | **High** | Implemented | **Verified** | [routes/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/checks.py#L50-L72), [scheduler.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/scheduler.py#L171-L209) | Wrap `db.commit()` in `try ... except Exception: release_in_flight(target_id); raise` immediately after `try_acquire_in_flight()`; verified by `test_check_trigger_releases_reservation_when_commit_fails` and `test_poll_once_releases_reservation_when_commit_fails` |
| **B-02** | Phase 1 | **High** | Implemented | **Verified** | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L124-L133) | Escape `<`, `>`, `&`, `\u2028`, and `\u2029` in `_navigation_redirect_document()` and reset `main_navigation_complete`; verified by `test_navigation_redirect_document_escapes_script_terminators` and `test_capture_redirect_with_script_terminator_redirects_without_html_injection` |
| **B-08a** | Phase 1 | **Medium** | Implemented | **Verified** | [services/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L476-L485) | Guard `db.refresh(check_result)` and `db.refresh(matched_baseline)` with `try/except` after `db.commit()` on the `OK` path; verified by `test_ok_attempt_keeps_ok_status_and_ids_after_check_result_refresh_failure` |
| **B-08b** | Phase 1 | **Low** | Implemented | **Verified** | [attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L145) | Use a separate `refreshed_attempt` variable and guard the `finally` block in `run_check_attempt` with `try/except`; verified by `mypy app` and `test_attempts.py` |
| **F-02** | Phase 2 | **Medium-High** | Implemented | **Verified** | [client.ts](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/api/client.ts#L65-L68), [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L76-L95) | Handle `401` (clear the session and `queryClient.clear()`) separately from resource-specific `403`/`404` responses so those responses do not clear the entire app cache; verified by tests in `useAuth.test.tsx` |
| **F-04** | Phase 2 | **Medium** | Implemented | **Verified** | [TargetDetailPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/TargetDetailPage.tsx#L39-L65) | Check query `isError` states in `TargetDetailPage` and pass `title`, `failedArtifacts`, `onRetry`, and `isRetrying` to `<ArtifactError />`; verified by `TargetDetailPage.test.tsx`, including showing an error instead of `"Initial Baseline Capture"` and invoking `Retry` |
| **F-05** | Phase 2 | **Medium** | Implemented | **Verified** | [ScreenshotCompare.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/components/ScreenshotCompare.tsx#L202-L265) | Add `hasDiffError` and a `Retry` button to `ScreenshotPanel`, and throw when `computeDiffHeatmap` returns `null`; verified by `ScreenshotCompare.test.tsx` for both image-load and heatmap-calculation failures followed by retry |
| **B-05a** | Phase 3 | **Medium** | Implemented | **Verified** | [structure.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L92-L113) | Classify `<script nomodule>` as `classic-nomodule`; verified by `test_removing_nomodule_from_classic_script_changes_structure` in `test_structure.py` |
| **B-05b** | Phase 3 | **Medium** | Implemented | **Verified** | [structure.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L216-L235) | Record the `<iframe>` `sandbox` state and normalized sandbox tokens; verified by `test_removing_or_weakening_iframe_sandbox_changes_structure` in `test_structure.py` |
| **F-03** | Phase 3 | **Medium** | Implemented | **Verified** | [MembersPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.tsx#L14-L95) | Separate member/site list state and search terms between the Members and Website Assignments tabs, and update `selected` after mutations; verified by `MembersPage.test.tsx` |
| **F-01 / F-06a** | Phase 3 | **Medium** | Implemented | **Verified** | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L40-L85), [useAuth.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L108-L220) | Prevent paired `visibilitychange` and `focus` events from calling `invalidateQueries()` twice; tests cover both inside and outside the 15-second cooldown |
| **F-06b** | Phase 3 | **Medium** | Implemented | **Verified** | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L25-L120), [useAuth.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L220-L290) | Add `authEpochRef` and `clearSession()` so an in-flight `/auth/me` request cannot overwrite state after logout or a `401`; verified with a deferred `/auth/me` response resolving after logout |
| **F-07** | Phase 3 | **Medium** | Implemented | **Verified** | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L28-L45), [useAuth.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L220-L290) | Call `queryClient.clear()` when `role` or `must_change_password` changes in `applyAuth`; verified by `useAuth.test.tsx` |
| **F-09a / F-09b** | Phase 3 | **Low** | Implemented | **Verified** | [MembersPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.tsx#L55-L215), [MembersPage.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.test.tsx) | Cancel the rejection request when the prompt is cancelled (`rawReason === null`) and replace password reset via `window.prompt()` with a masked `<input type="password" />` form; verified by `MembersPage.test.tsx` |
| **B-09a** | Phase 4 | **Medium** | Implemented | **Verified** | [services/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L290-L480) | Record `target.last_http_status = capture.http_status` on successful check paths (`Awaiting Baseline`, `Changed`, `OK`); verified by `test_checks.py` |
| **B-09b** | Phase 4 | **Low-Medium** | Implemented | **Verified (3/3 code-defect cases pass; 2 POSIX cases await Linux)** | [cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py#L144-L162) | Close the connection in `open_database()` when an exception occurs after connecting, and normalize paths with `.resolve()` in `sqlite_protected_paths()`; all 3 code-defect cases in `test_cleanup_artifacts.py` pass (7/9 total passed on Windows) |
| **B-09c** | Phase 4 | **Low-Medium** | Implemented | **Verified** | [routes/targets.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/targets.py#L202-L235), [services/review.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/review.py#L103-L230) | Prevent acknowledging/confirming defacement or disabling a target while a check is in flight, and clear `last_error_code = None` when approving a baseline; verified by `test_api_routes.py` |
| **LINT-01** | Phase 4 | **Low** | Implemented | **Verified** | `backend/app/`, `backend/scripts/`, `backend/tests/` | Resolve all `mypy app` and `ruff check app scripts tests` findings; both pass with **0 errors** |
| **B-06a** | Phase 4/5 | **Medium** | Implemented | **Verified** | [routes/auth.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/auth.py#L267-L320), [test_auth.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/tests/test_auth.py) | Add rate limiting and count repeated incorrect current-password attempts, with account lockout on `POST /auth/change-password`; verified by a regression test in `test_auth.py` |
| **B-06b** | Phase 4/5 | **Medium** | Implemented | **Verified** | [routes/auth.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/auth.py), [routes/snapshots.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/snapshots.py) | Run Argon2 password hash/verification (login/register/change-password) and Pillow image processing in `snapshots.py` on worker threads via `anyio.to_thread.run_sync`, avoiding blocking the asyncio event loop; verified by `test_auth.py` and `test_api_routes.py` |
| **B-07** | Phase 4/5 | **Medium** | Implemented | **Unit/capture tests verified; Linux container recheck pending** | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L302-L345) | Separate `pending_redirect_depths` queues by request type (`navigation` vs. `resource`) so subresources cannot consume the main navigation's redirect depth; verified by `test_capture.py` (50 passed) |
| **F-08a / F-08b / F-09c** | Phase 4/5 | **Medium** | Implemented | **Configuration/static checks verified; live Nginx headers pending** | [nginx.conf](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/nginx.conf), [frontend/Dockerfile](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/Dockerfile) | Add a CSP (`default-src 'self'`, `script-src 'self'`, `object-src 'none'`, etc.), use `PUBLIC_HOST` for canonical HTTP-to-HTTPS redirects instead of reflecting `$host`, and set `VITE_API_BASE_URL=/api` in the production image |
| **B-01** | Phase 5 | **High (Verify)** | Launch flags implemented | **Linux container runtime verification pending** | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L184-L196) | Add `--force-webrtc-ip-handling-policy=disable_non_proxied_udp` and `--enforce-webrtc-ip-handling-policy`; verify egress blocking against a STUN UDP listener in the deployment Linux container |
| **B-10** | Phase 5 | **Medium** | Resource limits implemented (seccomp unchanged pending runtime results) | **Linux container runtime verification pending** | [docker-compose.yml](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/docker-compose.yml), [playwright-seccomp.json](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/deploy/playwright-seccomp.json) | Add `mem_limit`, `cpus`, and `pids_limit` in `docker-compose.yml`; defer removing `ptrace` and `io_uring_*` allowances from `playwright-seccomp.json` until Chromium has been tested in the actual Linux container |
| **B-11a / B-11b / B-11c** | Future backlog | **Low** | **Deferred** | **Not implemented (rationale and acceptance criteria documented)** | [ssrf_guard.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/core/ssrf_guard.py), [routes/members.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/members.py), [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py) | Scope, verification method, and deferral rationale are documented in Section 4 |

---

## 3. Implementation Details and Added Regression Tests (Phases 0–4)

### Phase 0: Test Environment Standardization — **Acceptance Criteria Met**
1. **Backend (`backend/.venv`):** Use Python `3.13.7` with packages matching `requirements.txt`; run `pytest` with `-p no:cacheprovider` and a writable temporary directory.
2. **Frontend (`frontend/node_modules`):** Install all four Windows native bindings (`@esbuild/win32-x64@0.21.5`, `@rolldown/binding-win32-x64-msvc@1.1.4`, `@rollup/rollup-win32-x64-msvc@4.62.2`, `lightningcss-win32-x64-msvc@1.32.0`) into `frontend/node_modules` without changing `package.json` or `package-lock.json`, enabling Vitest to run on Windows.

---

### Phase 1: Backend Stability and Early Findings (`B-03`, `B-02`, `B-08`) — **Implemented and Verified**
1. **`B-03` (In-flight target lock leak when `db.commit()` fails):**
   - **Fix:** Wrap `try ... except Exception: release_in_flight(target_id); raise` immediately after `try_acquire_in_flight(target_id)` in [routes/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/checks.py#L50-L72) (manual trigger) and [scheduler.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/scheduler.py#L171-L209) (scheduled poll).
   - **Behavioral regression tests:**
     - `tests/test_api_routes.py::test_check_trigger_releases_reservation_when_commit_fails`
     - `tests/test_scheduler.py::test_poll_once_releases_reservation_when_commit_fails`
2. **`B-02` (HTML/script escaping in `_navigation_redirect_document`):**
   - **Fix:** Convert `<`, `>`, `&`, `\u2028`, and `\u2029` to Unicode escapes in `_navigation_redirect_document()` and reset `main_navigation_complete.clear()` when a new navigation starts.
   - **Behavioral regression tests:**
     - `tests/test_capture.py::test_navigation_redirect_document_escapes_script_terminators`
     - `tests/test_capture.py::test_capture_redirect_with_script_terminator_redirects_without_html_injection` (confirms that a 302 `Location` containing `</script><h1>SPOOFED</h1>` does not inject HTML into the DOM and still redirects to the intended destination)
3. **`B-08a` and `B-08b` (Post-commit refresh guards on the `OK` path and in `attempts.py`):**
   - **Fix:** Guard `db.refresh(check_result)` and `db.refresh(matched_baseline)` with `try/except` after `db.commit()` on the `OK` path in [services/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L476-L485). Use a separate `refreshed_attempt` variable and guard the `finally` block in [attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L145).
   - **Behavioral regression test:**
     - `tests/test_attempts.py::test_ok_attempt_keeps_ok_status_and_ids_after_check_result_refresh_failure` (confirms that if `db.refresh(check_result)` raises `OperationalError` after commit on the `OK` path, the `Target` and `CheckAttempt` remain `OK` and retain `check_result_id` and `snapshot_id`.)

---

### Phase 2: Frontend Cache Handling and Error UI (`F-02`, `F-04`, `F-05`) — **Implemented and Verified**
1. **`F-02` (Keep `403`/`404` from clearing the app-wide cache):**
   - **Fix:** Separate the `api:unauthorized` event (`401` clears the session and calls `queryClient.clear()`) from `api:access-denied` (`403` calls `checkAuth(false)` to recheck authorization without clearing the entire cache; `404` remains a query-specific error).
   - **Behavioral regression tests (`useAuth.test.tsx`):**
     - `does not clear app-wide query cache on 403 or 404 responses`
     - `clears session and app-wide query cache on 401 unauthorized event`
2. **`F-04` (Show `<ArtifactError />` with a Retry button when checks/baselines fail to load):**
   - **Fix:** In [TargetDetailPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/TargetDetailPage.tsx), check `isChecksError`, `isBaselineError`, and `isBaselinesError`; pass `title="Check results unavailable"`, `failedArtifacts`, `onRetry={() => void refetchChecks()}`, and `isRetrying={isChecksFetching}` to `<ArtifactError />`. Also pass `targetId: target?.id || targetId` to `useTargetTriageActions`.
   - **Behavioral regression test (`TargetDetailPage.test.tsx`):**
     - `renders an artifact error instead of the initial baseline empty state when checks fail to load` (confirms that `"Initial Baseline Capture"` is not shown and clicking `Retry` calls `refetchChecks` again).
3. **`F-05` (Show an error and Retry button when image loading or heatmap calculation fails):**
   - **Fix:** In [ScreenshotCompare.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/components/ScreenshotCompare.tsx), add a `Retry` button in `ScreenshotPanel` for image-load failures, throw when `computeDiffHeatmap` returns `null`, and add `diffRetryNonce` so the heatmap `Retry` button actually recalculates the diff.
   - **Behavioral regression tests (`ScreenshotCompare.test.tsx`):**
     - `shows an error message and retries when an authenticated screenshot fetch fails`
     - `shows an error message and retries when heatmap diff calculation fails`

---

### Phase 3: Structural Detection (`nomodule`/`sandbox`) and Frontend State/Auth (`B-05`, `F-03`, `F-01`, `F-06`, `F-07`, `F-09`) — **Implemented and Verified**
1. **`B-05a` and `B-05b` (`<script nomodule>` and `<iframe sandbox>`):**
   - **Fix:** Classify `<script nomodule>` as `classic-nomodule` and record normalized `<iframe>` sandbox tokens in [structure.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py).
   - **Behavioral regression tests (`test_structure.py`):**
     - `test_removing_nomodule_from_classic_script_changes_structure`
     - `test_removing_or_weakening_iframe_sandbox_changes_structure`
2. **`F-03` and `F-09a`/`F-09b` (`MembersPage.tsx`):**
   - **Fix:** Separate state for the Members and Website Assignments tabs, update `selected` after mutations, cancel the rejection request when the user cancels the prompt (`rawReason === null`), and replace `window.prompt` password reset with a masked `<input type="password" />` form.
   - **Behavioral regression tests (`MembersPage.test.tsx`):**
     - `preserves active search/status filters and updates selected member details after mutation`
     - `does not submit rejection when prompt is cancelled`
     - `uses a masked password input instead of window.prompt for resetting passwords`
3. **`F-01`, `F-06a`, `F-06b`, and `F-07` (`useAuth.tsx`):**
   - **Fix:** Prevent paired `visibilitychange` and `focus` events from calling `invalidateQueries()` twice, clear `queryClient.clear()` when `role` or `must_change_password` changes, and add `authEpochRef` plus `clearSession()` so an in-flight `/auth/me` request cannot overwrite state after logout.
   - **Behavioral regression tests (`useAuth.test.tsx`):**
     - Cover focus both within 15 seconds (suppressed by the cooldown) and after 15 seconds (a new `/auth/me` request is sent).
     - `does not call invalidateQueries twice on paired visibilitychange and focus events`
     - `clears query cache when user role or must_change_password changes`
     - `ignores stale in-flight /auth/me response that resolves after logout`

---

### Phase 4: State Machine, `cleanup_artifacts.py`, and Static Analysis (`B-09`, `LINT-01`) — **Implemented and Verified**
1. **`B-09a` (`target.last_http_status`):** Set `target.last_http_status = capture.http_status` for `Awaiting Baseline`, `Changed`, and `OK` states.
2. **`B-09b` (`cleanup_artifacts.py`):** Close the connection in `open_database()` when an exception occurs after connecting, and normalize `sqlite_protected_paths(database)` with `.resolve()`. All three code-defect regression cases in `test_cleanup_artifacts.py` pass.
3. **`B-09c` (In-flight guards and error reset):** Prevent acknowledging/confirming defacement or disabling a target while a check is in flight, and clear `target.last_error_code = None` when approving a baseline.
4. **`LINT-01` (`mypy` and `ruff`):** `mypy app` and `ruff check app scripts tests` pass with **0 errors**.

---

## 4. Additional Review and Deferred Items

The following items were reviewed with their scope, verification method, and status recorded:

| Item | Scope | Verification Method | Status and Decision |
| :--- | :--- | :--- | :--- |
| **`B-06a` (Password Change Rate Limit & Lockout)** | Rate-limit `POST /auth/change-password` and temporarily lock accounts after repeated incorrect current-password attempts. | Run `pytest tests/test_auth.py` to check failure counting and account-lockout state. | **Implemented and verified** |
| **`B-06b` (Async Offloading for Argon2 & Pillow)** | Move Argon2 password hashing/verification in `auth.py` and Pillow image opening/resizing in `snapshots.py` to worker threads using `anyio.to_thread.run_sync`. | Run `pytest tests/test_auth.py tests/test_api_routes.py` and `mypy app`. | **Implemented and verified** |
| **`F-06b` (Logout vs. In-flight `/auth/me` Race)** | Prevent an `/auth/me` request started before logout from restoring `user` or the CSRF token if it responds afterward. | Add `authEpochRef` in `useAuth.tsx` and run `ignores stale in-flight /auth/me response that resolves after logout` in `useAuth.test.tsx`. | **Implemented and verified** |
| **`F-08a` & `F-08b` (Nginx CSP & Canonical Host Redirect)** | Set a restrictive `Content-Security-Policy` in `frontend/nginx.conf` and make HTTP port 80 redirect to `https://${PUBLIC_HOST}$request_uri`. | Inspect `frontend/nginx.conf`; verify actual HTTP response headers when the Nginx container runs in Phase 5. | **Code implemented; Linux container runtime verification pending (Phase 5)** |
| **`F-09a` & `F-09b` (Masked Password Reset & Reject Cancel)** | Replace `window.prompt()` password reset in `MembersPage.tsx` with `<input type="password" />`, and do not submit a member rejection when the rejection prompt is cancelled. | Run `vitest run src/pages/MembersPage.test.tsx` (3/3 passed). | **Implemented and verified** |
| **`F-09c` (Production vs. Local Development API URL)** | Set `ENV VITE_API_BASE_URL=/api` in `frontend/Dockerfile` for production builds; keep `frontend/.env` for local development. | Inspect `frontend/Dockerfile` and test the production container in Phase 5. | **Code implemented; Linux container runtime verification pending (Phase 5)** |
| **`B-11a` (URL Port Validation in `ssrf_guard.py`)** | Validate `parsed.port` in `validate_url()` against an agreed range, or convert invalid-port `ValueError` to `SsrfBlockedError`. | Add unit tests in `tests/test_ssrf_guard.py` for malformed and out-of-policy ports. | **Deferred — Low severity:** `urlparse` and `SsrfProxy` already block private IPs. Agree whether to permit only ports `80/443` or custom ports for target sites before setting a port policy. |
| **`B-11b` (UTC `"Z"` Suffix in `/members`)** | Serialize time fields in `_member_read()` (`backend/app/api/routes/members.py`) with an explicit UTC marker (`Z` or `+00:00`), consistent with other endpoints. | Add an assertion in `tests/test_members.py` for ISO-8601 UTC timestamp formatting. | **Deferred — Low severity:** This is a serialization-format issue and does not currently affect `MembersPage`. |
| **`B-11c` (Upper Bound on `width` in `_enforce_render_budget`)** | Add a maximum width (`max_width`) in addition to the total-pixel check (`width * height`) in `capture.py`. | Add a unit test in `tests/test_capture.py` for an unusually wide, short viewport/image. | **Deferred — Low severity:** Total pixel area and file size are already limited, so the current risk is low. |

---

## 5. Phase 5: Linux Container Runtime Verification

Phase 5 scope, prerequisites, verification steps, acceptance criteria, and execution records are documented separately in [Phase_5_Linux_Container_Runtime_Verification.md](Phase_5_Linux_Container_Runtime_Verification.md).

**Current status:** Hardening changes are in place, but runtime verification on a Linux Docker Engine is still pending for WebRTC UDP egress, POSIX cleanup, resource limits/seccomp, and production Nginx responses.

---

## 6. Verified Test Execution Record

**Verification date:** October 19, 2026  
**Baseline Commit SHA:** `e2934813f81d5660dccf9cdd54273de58c4105ec` (`e293481`)

### 6.1 Test and Tool Results

| Check | Command actually run | Result | Details and limitations |
| :--- | :--- | :--- | :--- |
| **Frontend Typecheck** | `.\node_modules\.bin\tsc.cmd -b --pretty false` (from `frontend/`) | **Passed (`0 errors`)** | Passed for the application and all test files. |
| **Frontend ESLint** | `.\node_modules\.bin\eslint.cmd src` (from `frontend/`) | **Passed (`0 errors`)** | No errors or warnings. |
| **Frontend Vitest** | `node node_modules/vitest/vitest.mjs run` (from `frontend/`) | **Passed (`14 / 14 files`, `94 / 94 tests`)** | Took `11.73s`; included `useAuth.test.tsx` (15 tests), `TargetDetailPage.test.tsx` (7), `ScreenshotCompare.test.tsx` (7), `MembersPage.test.tsx` (3), and all remaining test files. |
| **Backend Typecheck** | `.\.venv\Scripts\python.exe -m mypy app` (from `backend/`) | **Passed (`0 errors`)** | `Success: no issues found in 61 source files` |
| **Backend Ruff Lint** | `.\.venv\Scripts\python.exe -m ruff check app scripts tests` (from `backend/`) | **Passed (`0 errors`)** | `All checks passed!` |
| **Backend Pytest (Main Suite)** | `.\.venv\Scripts\python.exe -m pytest tests/ -k "not test_cleanup_artifacts" -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_all"` | **Passed (`264 passed, 0 failed, 9 deselected`)** | Took `140.33s` (`0:02:20`). `test_cleanup_artifacts.py` was run separately to isolate POSIX-specific limitations on Windows. |
| **Backend Pytest (Artifact Cleanup)** | `.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_artifacts.py -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_cleanup"` | **`7 passed, 2 failed`** *(project total: `271 / 273 passed`)* | All three code-defect cases fixed under `B-09b` passed. The two Windows failures are OS-related: `WinError 1314` when creating a symlink in `test_artifact_symlink_file_and_directory_are_rejected`, and `PermissionError [Errno 13]` when calling `os.open()` on a directory for `dir_fd` in `test_deletes_only_approved_expired_orphans_and_keeps_history`. |

### 6.2 Verification Log Excerpts

```text
# 1. Frontend Typecheck, Lint & Vitest (frontend/)
$ .\node_modules\.bin\tsc.cmd -b --pretty false
(exit code 0)

$ .\node_modules\.bin\eslint.cmd src
(exit code 0)

$ node node_modules/vitest/vitest.mjs run
 RUN  v4.1.9 C:/Users/phatthasuk.pi/Desktop/Web Defacement Project Linux/frontend
 ✓ src/pages/SettingsPage.test.tsx (1 test)
 ✓ src/pages/AlertsPage.test.tsx (1 test)
 ✓ src/pages/ChangePasswordPage.test.tsx (2 tests)
 ✓ src/pages/RegisterPage.test.tsx (2 tests)
 ✓ src/pages/UsersPage.test.tsx (5 tests)
 ✓ src/pages/LoginPage.test.tsx (2 tests)
 ✓ src/pages/MembersPage.test.tsx (3 tests)
 ✓ src/components/ScreenshotCompare.test.tsx (7 tests)
 ✓ src/components/HtmlDiffViewer.test.tsx (14 tests)
 ✓ src/pages/TargetsListPage.test.tsx (8 tests)
 ✓ src/hooks/useAuth.test.tsx (15 tests)
 ✓ src/components/AppShell.test.tsx (6 tests)
 ✓ src/pages/TargetDetailPage.test.tsx (7 tests)
 ✓ src/utils/formatDateTime.test.ts (21 tests)

 Test Files  14 passed (14)
      Tests  94 passed (94)
   Duration  11.73s

# 2. Backend Static Analysis & Pytest (backend/)
$ .\.venv\Scripts\python.exe -m mypy app
Success: no issues found in 61 source files

$ .\.venv\Scripts\python.exe -m ruff check app scripts tests
All checks passed!

$ .\.venv\Scripts\python.exe -m pytest tests/ -k "not test_cleanup_artifacts" -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_all"
264 passed, 9 deselected in 140.33s (0:02:20)

$ .\.venv\Scripts\python.exe -m pytest tests/test_cleanup_artifacts.py -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_cleanup"
2 failed, 7 passed in 1.40s
  - FAILED tests/test_cleanup_artifacts.py::test_artifact_symlink_file_and_directory_are_rejected (OSError: [WinError 1314] A required privilege is not held by the client)
  - FAILED tests/test_cleanup_artifacts.py::test_deletes_only_approved_expired_orphans_and_keeps_history (PermissionError: [Errno 13] Permission denied on os.open(directory) for POSIX dir_fd)
```

---

### 6.3 Phase Gate Summary

| Phase | Code Status | Verification Status | Evidence Summary |
| :--- | :---: | :---: | :--- |
| **Phase 0: Environment Standardization** | **Complete** | **Verified (acceptance criteria met)** | Synced `.venv` and Windows Vitest native bindings; both `pytest` and `vitest` run successfully. |
| **Phase 1: Backend Stability (`B-03`, `B-02`, `B-08`)** | **Implemented** | **Verified (acceptance criteria met)** | Regression tests for manual/scheduled reservation release, redirect script escaping, and post-commit refresh failures all passed in `pytest` (264 passed). |
| **Phase 2: Frontend Cache & Error UI (`F-02`, `F-04`, `F-05`)** | **Implemented** | **Verified (acceptance criteria met)** | `tsc -b`, `eslint src`, and Vitest behavior tests for 401/403/404 cache isolation and `<ArtifactError />` with `Retry` all passed (94/94 tests). |
| **Phase 3: Detector & Frontend State/Auth (`B-05`, `F-01`, `F-03`, `F-06`, `F-07`, `F-09`)** | **Implemented** | **Verified (acceptance criteria met)** | Regression tests for `nomodule`, `iframe sandbox`, `MembersPage` filters/selection/cancel/masked password, and `useAuth` cooldown/paired focus/role change/logout race all passed. |
| **Phase 4: State Machine, Cleanup & Lint (`B-09`, `LINT-01`)** | **Implemented** | **Verified on Windows (acceptance criteria met)** | `mypy app` (0 errors), Ruff (0 errors), `test_checks.py`, and `test_api_routes.py` passed; all 3 code-defect cases in `test_cleanup_artifacts.py` passed (2 POSIX-dependent cases remain for Linux). |
| **Phase 5: Linux Container Runtime & Hardening (`B-01`, `B-06`, `B-07`, `B-10`, `F-08`)** | **Hardening implemented** (`B-06` and `B-07` also have unit/integration test coverage) | **Linux container runtime verification pending** | Run the WebRTC UDP egress test (`B-01`), the 2 POSIX `dir_fd`/symlink cleanup tests (`B-09b`), container cgroups/seccomp checks (`B-10`), and Nginx header checks (`F-08`) on a Linux host with Docker Engine. |
