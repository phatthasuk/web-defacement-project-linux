# Codebase and Test Suite Audit Report (by Argon)

**Audit Date:** October 19, 2026  
**Scope of Audit:**
- Automated test execution and static analysis across Backend (`pytest`, `ruff`, `mypy`) and Frontend (`eslint`, `tsc`, `vitest`).
- In-depth codebase inspection of Backend (`backend/app/`, `backend/scripts/`), Frontend (`frontend/src/`), and deployment/infrastructure configurations (`docker-compose.yml`, `Dockerfile`, `frontend/nginx.conf`, `deploy/playwright-seccomp.json`).
- Verification of previous review remediations (`Review Security 14-10-2026.md`, `Review By GPT 6.1 Sol`, `Review Round 2`, `Review issue by Argon Edit by Sol`, `Page-Flicker-On-Window-Focus-Fix`).

---

## 1. Test Suite & Static Analysis Results

| Tool / Test Suite | Result | Details & Root Cause |
| :--- | :--- | :--- |
| **Backend `pytest`** | **260 / 265 Passed** *(5 failed in `test_cleanup_artifacts.py` on Windows)* | - Running under `.venv` revealed outdated packages relative to [requirements.txt](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/requirements.txt) (`playwright==1.48.0`, `fastapi==0.115.5`, `starlette==0.41.3`), causing 38 capture tests to fail looking for Chromium binary.<br>- Running capture tests (49 tests) with Global Python (`playwright 1.62.0`) resulted in **49/49 Passed**.<br>- 5 tests in [test_cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/tests/test_cleanup_artifacts.py) failed due to file handle / unclosed connection / path resolution issues in [cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py) (see **B-09**). |
| **Backend `mypy app`** | **Failed (1 error)** | - [attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L145): `Incompatible types in assignment (expression has type "CheckAttempt | None", variable has type "CheckAttempt")` due to reusing the `attempt` variable which was initially typed as `CheckAttempt` and then assigned from `db.get(CheckAttempt, attempt_id)`. |
| **Backend `ruff check`** | **Failed (21 errors)** | - Detected `I001` (import sorting), `E501` (line length > 100), `F401` (unused import `pytest` in [test_attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/tests/test_attempts.py#L8)), and `UP036` across [checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py), [attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py), [check_attempt.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/models/check_attempt.py), [config.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/core/config.py), and [cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py). |
| **Frontend `eslint src`** | **Passed (0 errors)** | Clean pass with zero errors and zero warnings. |
| **Frontend `tsc -b --pretty false`** | **Passed (0 errors)** | Clean pass with zero TypeScript project-reference build/type errors. |
| **Frontend `vitest`** | **Blocked on Windows + 4 Logic Failures** | - Execution blocked on Windows host with `Cannot find module '@rolldown/binding-win32-x64-msvc'` because `node_modules` was installed in a Linux environment.<br>- Static code tracing revealed that all 4 focus revalidation tests in [useAuth.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L108-L165) fail due to the `15,000ms` cooldown being armed on mount (see **F-01**). |

---

## 2. Summary of Identified Vulnerabilities & Bugs (Executive Summary Table)

### Backend & Security

| ID | Severity | Category | Location | Summary |
| :--- | :--- | :--- | :--- | :--- |
| **B-01** | **High** | Security / SSRF | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L184-L196) | WebRTC (`RTCPeerConnection` with STUN/TURN) opens direct UDP sockets, completely bypassing `SsrfProxy` and `context.route()`. |
| **B-02** | **High** | Security / Capture | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L124-L133) | [`_navigation_redirect_document`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L124-L133) uses `json.dumps()` without escaping `</script>`, allowing a 3xx `Location` containing `</script>` to break the script tag, abort redirection, and spoof the captured DOM. |
| **B-03** | **High** | Concurrency / Lock Leak | [routes/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/checks.py#L50-L72), [scheduler.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/scheduler.py#L171-L209) | Calls [`try_acquire_in_flight(target_id)`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/concurrency.py#L46-L52) before `db.commit()` outside the `try/except` cleanup block. If `db.commit()` fails, `target_id` leaks into `_in_flight_targets` permanently until process restart. |
| **B-04** | **Medium** | Detector Bypass (SEC-04) | [structure.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L78-L90) | [`_normalise_url_value`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L78-L85) is only called when testing for `javascript:`. Embedded tabs/newlines in scheme (`ht&#9;tps://...`) in `<script src>`, `<iframe src>`, `<form action>`, `formaction`, and `<a href>` evade external domain detection (`score = 0.0`). |
| **B-05** | **Medium** | Detector Bypass (SEC-05) | [structure.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L92-L113) | [`classify_script`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L92-L113) does not inspect `nomodule`, and `<iframe>` does not record `sandbox` state. Enabling `<script nomodule>` or un-sandboxing an `<iframe>` yields `score = 0.0`. |
| **B-06** | **Medium** | Auth / DoS | [routes/auth.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/auth.py#L267-L300), [snapshots.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/snapshots.py#L53-L65) | `POST /auth/change-password` lacks rate limiting and failed attempt lockout; synchronous Argon2 and Pillow operations run inside `async def` route handlers, blocking the main asyncio event loop. |
| **B-07** | **Medium** | Capture / Redirect | [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L302-L320) | Subresource 3xx redirects are never counted against `REDIRECT_LIMIT` and can pop/steal queued depth values intended for main navigations in `pending_redirect_depths`. |
| **B-08** | **Medium** | DB / ORM Lifecycle | [services/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L460-L508), [attempts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L145) | In the `OK` branch of [`run_target_check`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L476-L477), `db.refresh(check_result)` is called without `try/except` after `db.commit()` (failure overwrites `OK` status to `Failed`), and `matched_baseline` is returned expired/detached. |
| **B-09** | **Medium** | State Machine & Scripts | [services/checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L227), [routes/targets.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/targets.py#L342-L364), [cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py#L144-L162) | `target.last_http_status` remains `None` on 2xx responses; disabling a target or acknowledging defacement does not check for in-flight checks; [cleanup_artifacts.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py) leaks connections on lock failure and fails to `.resolve()` paths in `sqlite_protected_paths`. |
| **B-10** | **Medium** | Container / Seccomp | [playwright-seccomp.json](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/deploy/playwright-seccomp.json#L190-L192), [docker-compose.yml](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/docker-compose.yml#L4-L51) | `playwright-seccomp.json` unconditionally allows `ptrace` and `io_uring_*`; `docker-compose.yml` still lacks container resource constraints (`mem_limit`, `cpus`, `pids_limit`). |
| **B-11** | **Low** | Validation / Serialization | [ssrf_guard.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/core/ssrf_guard.py#L23-L42), [routes/members.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/members.py#L66-L92) | [`validate_url`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/core/ssrf_guard.py#L23-L42) does not validate `parsed.port`; `/members` returns datetime without `"Z"` suffix; `_enforce_render_budget` does not place an upper bound on `width`. |

---

### Frontend & Nginx

| ID | Severity | Category | Location | Summary |
| :--- | :--- | :--- | :--- | :--- |
| **F-01** | **High** | Logic / Tests | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L35-L38), [useAuth.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L108-L165) | Initial `checkAuth(true)` on mount sets `lastCheckedAtRef`, causing immediate window focus events (and all 4 focus unit tests in `useAuth.test.tsx`) to be suppressed by the 15s cooldown. |
| **F-02** | **High** | Cache / State | [client.ts](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/api/client.ts#L65-L68), [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L76-L86) | Any `403` or `404` response from `apiFetch` dispatches `api:access-denied`, which unconditionally triggers `queryClient.clear()` and wipes the entire TanStack Query cache. |
| **F-03** | **High** | State Clobbering | [MembersPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.tsx#L27-L40) | `act()` calls `loadAssignments()` immediately after `loadMembers()` and `loadMemberSites()`, completely overwriting `members` (wiping active filters/pagination) and `websites`; both tabs also share a single `search` state. |
| **F-04** | **Medium** | Error Handling (F4) | [TargetDetailPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/TargetDetailPage.tsx#L39-L50) | Missing `isError` checks on `useTargetChecksQuery`, `useTargetBaselineSnapshotQuery`, and `useTargetBaselinesQuery`. On API failure, the UI falsely renders `"Initial Baseline Capture"` and `"No differences to calculate"` (violating Principle F4). |
| **F-05** | **Medium** | Error Handling (F4) | [ScreenshotCompare.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/components/ScreenshotCompare.tsx#L248-L259) | When image fetching or heatmap generation fails, `diffUrl` is set to `null` with no error state recorded, falsely rendering `"Diff preview requires both baseline and latest captures"` instead of an error banner. |
| **F-06** | **Medium** | Race / Cooldown | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L23-L75) | Switching tabs triggers duplicate `queryClient.invalidateQueries()` calls via paired `visibilitychange` + `focus` events; `applyAuth` login and 5xx errors do not update `lastCheckedAtRef`; `logout()` does not cancel in-flight `checkAuth`. |
| **F-07** | **Medium** | Auth / Cache | [useAuth.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L23-L28) | `applyAuth` only clears cache when `user.id` changes, failing to evict cached data when an account is downgraded (`admin` -> `operator`) or forced to change password (`must_change_password: true`). |
| **F-08** | **Medium** | Nginx / Security | [nginx.conf](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/nginx.conf#L25) | Minimal CSP sets only `frame-ancestors 'self';`; HTTP port 80 redirect reflects user-supplied `$host` header directly. |
| **F-09** | **Low** | UX / Prompt / Env | [MembersPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.tsx#L55), [frontend/.env](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/.env) | Password reset uses `window.prompt()` exposing passwords in plaintext; clicking Cancel on the rejection prompt still submits the rejection; committed `.env` specifies an internal HTTP address (`http://10.117.10.68:8000`). |

---

## 3. In-Depth Details and Recommended Remediations

### 3.1 Backend & Security

#### [B-01] (High) WebRTC UDP/STUN/TURN Bypasses `SsrfProxy` and `context.route()`
- **Location:** [`_capture_snapshot_impl`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L184-L196)
- **Root Cause:** In Chromium, WebRTC (`RTCPeerConnection` with STUN/TURN servers) initiates UDP sockets directly without routing through `--proxy-server` or Playwright's `context.route()` / `context.route_web_socket()`.
- **Remediation:** Add WebRTC lockdown flags to Chromium `launch_args`:
  ```python
  launch_args: list[str] = [
      "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
      "--enforce-webrtc-ip-handling-policy",
  ]
  ```

#### [B-02] (High) Unescaped `</script>` in 3xx `Location` Header Breaks `_navigation_redirect_document` and Allows DOM Spoofing
- **Location:** [`_navigation_redirect_document`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/capture/capture.py#L124-L133)
- **Root Cause:** `json.dumps(target_url)` does not escape `<`, `>`, or `&`. If an endpoint responds with `Location: https://example.com/?a=</script><h1>Fake</h1>`, HTML parsers terminate the `<script>` tag immediately and render the remaining HTML into the document.
- **Remediation:** Replace `<`, `>`, and `&` with `\u003c`, `\u003e`, and `\u0026` after `json.dumps(target_url)`, and invoke `main_navigation_complete.clear()` when initiating each new navigation.

#### [B-03] (High) Target Permanently Wedged in `_in_flight_targets` on `db.commit()` Failure
- **Location:** [`trigger_check`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/api/routes/checks.py#L50-L72) and [`_poll_once`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/scheduler.py#L171-L209)
- **Root Cause:** `try_acquire_in_flight(target_id)` is called before `db.commit()`, but the `try ... except Exception: release_in_flight(target_id)` block only surrounds the background task scheduling. If `db.commit()` encounters a database lock (`sqlite3.OperationalError`), `target_id` leaks into memory and remains in `_in_flight_targets` until server restart.
- **Remediation:** Expand the `try:` block to begin immediately following `try_acquire_in_flight(target_id)`, enclosing `db.commit()`.

#### [B-04] & [B-05] (Medium) Structural Detector Bypasses (Incomplete Fixes for SEC-04 & SEC-05)
- **Location:** [`_normalise_url_value`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L78-L113) and [`_StructureParser.handle_starttag`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/diff/structure.py#L206-L253)
- **Root Cause:**
  1. `_normalise_url_value` is only applied during `_is_javascript_url`. If a standard URL contains `\t` or `\n` in the scheme (e.g. `ht&#9;tps://evil.example/a.js`), the browser fetches from `evil.example`, but Python's `urljoin` interprets it as a relative path under the target's own domain (`target.example`), evading external domain detection.
  2. `classify_script` does not check the `nomodule` attribute and fails to strip `_URL_STRIP_CHARS` when comparing `module`/`importmap`/`speculationrules`. In addition, `<iframe>` elements do not record their `sandbox` attribute state.
- **Remediation:** Apply `_normalise_url_value` to all extracted URL attributes before resolving, classify `nomodule` classic scripts as inert, and track normalized `iframe-sandbox` states.

#### [B-08] & [B-09] (Medium) ORM Session Bugs, `last_http_status`, and `cleanup_artifacts.py`
- **Location:**
  - [`run_target_check`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L227) and lines [460-508](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/checks.py#L460-L508)
  - [`run_check_attempt`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L145) and lines [218-225](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/app/services/attempts.py#L218-L225)
  - [`cleanup_artifacts.py`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/backend/scripts/cleanup_artifacts.py#L144-L162)
- **Root Cause:**
  1. `checks.py:227` sets `target.last_http_status = None` at check start. When a check succeeds (HTTP 2xx), `target.last_http_status = capture.http_status` is never set, leaving it permanently `None` for healthy targets.
  2. `checks.py:477` invokes `db.refresh(check_result)` without a `try/except` guard following `db.commit()`, and leaves `matched_baseline` expired/detached.
  3. `attempts.py:145` triggers a `mypy` type error by reusing the `attempt` variable name, and opens an unguarded session in its `finally` block (lines 221-225).
  4. `cleanup_artifacts.py:144-162` does not close `connection` when `BEGIN EXCLUSIVE` fails, and does not `.resolve()` paths in `sqlite_protected_paths`, failing to match short 8.3 or unresolved paths on Windows/symlinks.

---

### 3.2 Frontend & Nginx

#### [F-01] (High) Initial `checkAuth(true)` Sets `lastCheckedAtRef`, Breaking Focus Revalidation Tests
- **Location:** [`useAuth.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L35-L38) and [`useAuth.test.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.test.tsx#L108-L165)
- **Root Cause:** Initial `checkAuth(true)` inside the mount `useEffect` sets `lastCheckedAtRef.current = Date.now()` once `/auth/me` resolves. When `useAuth.test.tsx` fires `fireEvent.focus(window)` on the next line, the cooldown check `Date.now() - lastCheckedAtRef.current < 15_000` evaluates to true and suppresses revalidation.
- **Remediation:** Update `lastCheckedAtRef.current` inside `onFocus` prior to calling `checkAuth(false)` (which also prevents duplicate runs from paired `visibilitychange` + `focus` events), or advance mock timers in `useAuth.test.tsx`.

#### [F-02] (High) Global `queryClient.clear()` Dispatched on Any `403` or `404`
- **Location:** [`apiFetch`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/api/client.ts#L65-L68) and [`useAuth.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/hooks/useAuth.tsx#L76-L86)
- **Root Cause:** `apiFetch` emits `api:access-denied` on every `403` or `404` status code. The listener in `useAuth.tsx` catches this event and immediately runs `queryClient.clear()`, wiping the entire app cache and causing `TargetDetailPage` to flash a full-screen loading spinner when a sub-resource artifact returns 404.
- **Remediation:** Restrict `queryClient.clear()` to `401` (session expiration) or explicit user/role mutations in `applyAuth`.

#### [F-03] (High) Inter-Tab and Intra-Function State Clobbering in `MembersPage.tsx`
- **Location:** [`MembersPage.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/MembersPage.tsx#L14-L40)
- **Root Cause:**
  1. `act()` calls `loadMembers()` and immediately follows with `loadAssignments()`, which fetches an unfiltered `/members?limit=200` and calls `setMembers()`, discarding active status filters and search pagination. It also overwrites `websites` fetched by `loadMemberSites()`.
  2. The single state variable `search` is shared between the Members search bar and Website Assignments search bar.
  3. The `selected` member object is never updated after mutating display names or statuses.

#### [F-04] & [F-05] (Medium) False Success / Fallback States on API Failure (Principle F4 Violations)
- **Location:** [`TargetDetailPage.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/pages/TargetDetailPage.tsx#L39-L50) and [`ScreenshotCompare.tsx`](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/frontend/src/components/ScreenshotCompare.tsx#L248-L259)
- **Root Cause:**
  1. `TargetDetailPage.tsx` does not inspect `isError` on `useTargetChecksQuery` or `useTargetBaselineSnapshotQuery`. When these queries fail, `latestCheck` defaults to `null`, causing the card to display `"Initial Baseline Capture"` and `"No differences to calculate"`.
  2. `ScreenshotCompare.tsx` catches canvas heatmap diff errors and sets `diffUrl = null` without recording an error state, rendering a message stating that both baseline and latest captures are required instead of displaying `<ArtifactError />`.

---

## 4. Sol's Review Comments

**Review date:** October 19, 2026  
**Scope:** Compared selected findings in Argon's report against the source code, exercised the structural detector, and reran selected tools on Windows. This review does not verify every finding or reproduce the complete production Linux test run.

### 4.1 Overall assessment

The report identifies several real issues and provides a useful starting point for remediation. Some findings should be corrected or assigned a lower severity before the full list becomes a work queue. B-04 is the clearest example: its main reproduction did not occur. Other claims remain code-based inferences or could not be tested in the available environment.

### 4.2 Findings supported by this review

| Finding | Result and comment |
| :--- | :--- |
| **B-02** | `_navigation_redirect_document()` inserts `json.dumps(target_url)` into a `<script>` element without escaping `<`. This is a real HTML construction issue that should be fixed. I confirmed the source pattern, but did not run a complete browser exploit. |
| **B-03** | Both the manual trigger and scheduler acquire an in-flight reservation before `db.commit()`, which is outside the cleanup block. If the commit fails, the reservation can remain held. Prioritize this fix. |
| **B-05, in part** | Direct calls to `extract_structure()` and `compare_structure()` returned a score of **0.0** after removing `nomodule` from a script or removing `sandbox` from an iframe while keeping the other markup unchanged. The detector does not currently record these changes. |
| **B-08, in part** | The OK branch calls `db.refresh(check_result)` after commit without a local guard. If refresh fails, the outer exception handler can mark the target Failed even though the OK result was committed. The impact of returning an expired or detached baseline requires tracing its callers and attribute access before drawing a broader conclusion. |
| **B-09, in part** | The code clears `target.last_http_status` and records status for non-2xx results, but does not appear to store a successful status on the target. `open_database()` also leaves a connection open if a post-connect operation raises. I could not reproduce the cleanup test failures described in the original report. |
| **F-02** | `apiFetch()` dispatches an event for 401/403/404, and the listener clears the entire query cache for those statuses. This can make a resource-specific error affect the whole application. Review the 403/404 behavior in light of resource and permission changes. |
| **F-03** | `act()` calls `loadMembers()` and then `loadAssignments()`, which replaces the member list with an unfiltered list. The two tabs also share search and website state. This creates real filter and pagination issues. |
| **F-04 / F-05** | Some query errors fall through to empty-state messaging, and the heatmap catch only resets `diffUrl`. These paths can present an error as missing data. Give these user-facing states priority because operators rely on them to interpret check results. |

### 4.3 Findings that need narrower claims

#### B-04: The tab/newline example did not reproduce

On **Python 3.13.7**, using the project's code, the following URL was resolved as HTTPS:

```text
urljoin('https://target.example/', 'ht\ttps://evil.example/a.js')
=> 'https://evil.example/a.js'
```

Markup containing `ht&#9;tps://evil.example/a.js` was still detected as an external destination for scripts, iframes, forms, and links. Comparing each result with an empty fact set produced a score of **1.0**, not 0.0 as claimed.

Remove or revise B-04 based on this example. If another bypass is suspected, include reproducible baseline/current HTML, allowed hosts, Python version, and observed output. This test does not prove every URL normalization case is correct; it refutes the report's primary reproduction in the tested environment.

#### B-05: Separate `nomodule`/`sandbox` from script-type whitespace

The `nomodule` and iframe `sandbox` findings have direct reproduction evidence. The original recommendation about trimming whitespace around `module`, `importmap`, or `speculationrules` should not be applied automatically. Their token rules differ from JavaScript MIME type matching. Compare the behavior with the deployed Chromium version and the [HTML Standard's script processing rules](https://html.spec.whatwg.org/multipage/scripting.html) before changing the detector.

#### F-01: A test/cooldown mismatch, not yet a High-severity defect

Mount calls `checkAuth(true)` and stores `lastCheckedAtRef` after the request succeeds, so an immediate focus event is suppressed for 15 seconds. If the intended requirement is a cooldown after mount, update the tests to advance time before asserting revalidation, and retain a test proving that an event within the cooldown does not trigger another request. A focus event immediately after mount being suppressed is not by itself enough evidence for High severity.

#### B-01: Important risk requiring runtime evidence

The launch configuration has no WebRTC lockdown, but a claim that a page can reach an internal network should be demonstrated with the deployed Chromium and container configuration. Verify that the proposed flags actually prevent the relevant egress. Chromium documents the `disable_non_proxied_udp` policy in its [policy definition](https://chromium.googlesource.com/chromium/src/+/376fc41e87a058f7a7b300b0ec3a4982b4ec0960/components/policy/resources/policy_definitions/Miscellaneous/WebRtcIPHandling.yaml); the policy name alone does not prove that every proposed launch argument is effective in the current runtime.

Treat B-01 as a high-priority risk awaiting verification, rather than a fully reproduced SSRF bypass.

#### Severity and combined finding IDs

- **F-03:** Medium better matches the observed state/filter/pagination impact unless additional evidence shows broader harm.
- **F-02:** The behavior is real and merits a prompt fix. A High rating should cite availability or data impact criteria beyond the fact that the cache is cleared.
- **B-06, B-09, B-11, and F-09:** Each combines issues with different causes and fixes. Split them into independent tasks with their own severity, regression tests, and acceptance criteria.
- Findings not discussed here were neither confirmed nor refuted by this review.

### 4.4 Rerun results and limitations

| Command or experiment | Result in this review |
| :--- | :--- |
| `python -m mypy app` from `backend/` | **5 errors in 2 files:** `attempts.py:145` and `members.py:215, 257, 317, 430`. The additional members errors concern `Result[Any].rowcount`. |
| `python -m ruff check app scripts tests --output-format concise` from `backend/` | **22 errors**, compared with 21 in the report. Counts can vary by command scope and tool version. |
| `node node_modules/vitest/vitest.mjs run src/hooks/useAuth.test.tsx` from `frontend/` | The test runner could not start because `@rolldown/binding-win32-x64-msvc` was missing. This confirms an environment limitation, not a logic-test failure. |
| `python -m pytest tests/test_cleanup_artifacts.py -q -p no:cacheprovider --basetemp=.audit-tmp-review` from `backend/` | Failed with `PermissionError [WinError 5]` on the temporary directory. This run could not confirm that the five failures in the report were cleanup code defects. |
| Structural detector reproduction | B-04's example detected the external URL. The `nomodule` and `sandbox` changes in B-05 were not detected. |

I did not rerun the full backend suite, capture integration suite, frontend lint/typecheck, or production Linux container tests. The reported **260/265** and **49/49** totals therefore remain unverified by this review. Differences in mypy/ruff results may be related to the environment or tool versions; record those versions before attributing the cause.

### 4.5 Recommended order of work

1. Fix B-03, B-02, and the post-commit B-08 path, with regression tests that simulate commit/refresh failures.
2. Verify B-01 in the deployment runtime and test the proposed WebRTC egress restriction.
3. Fix F-02 and F-04/F-05 so resource errors do not affect the whole application or appear as successful empty states.
4. Fix the proven `nomodule`/`sandbox` gaps and F-03; document the intended cooldown behavior for F-01/F-06.
5. Standardize test environments, rerun the suites, and record results before using them as release criteria.

Before treating the report as a remediation backlog, record the commit SHA, OS, Python/Node/tool versions, command and scope, and supporting logs. Mark each finding as reproduced by execution, confirmed from source, still a hypothesis, or blocked by test environment.

This section is Sol's appended review. Argon's original report is retained above.

---

## 5. Argon's Follow-up Clarification and Reconciled Scope

**Updated:** October 19, 2026  
**Purpose:** Record the follow-up review with evidence boundaries and environment limits before using the findings as a remediation backlog.

### 5.1 Verified points and evidence boundaries

- **B-04 (withdraw the original reproduction and correct the Python issue reference):**
  - **Reproduced result:** On Python 3.13.7, calling `extract_structure('<script src="ht\ttps://evil.example/a.js"></script>', 'https://target.example/')` returned `{'script:https://evil.example/a.js'}`. Comparing this with an empty baseline produced a score of `1.0`, so this example does not bypass external-domain detection.
  - **Technical correction:** `urllib.parse.urlsplit` removes ASCII tab/newline characters (`\t`, `\r`, `\n`) because of **CVE-2022-0391** ([CPython issue #88048](https://github.com/python/cpython/issues/88048)), not CVE-2021-23336. The [Python `urllib.parse` documentation](https://docs.python.org/3/library/urllib.parse.html) says leading C0 control and space characters are stripped. The project's `.strip()` also removes leading/trailing characters before resolving URLs.

- **B-05 (`nomodule`/`sandbox` state changes, separate from script-type whitespace):**
  - **`<script nomodule>`:** Removing `nomodule` from a classic script may cause it to run in a browser that supports ES modules, such as Chromium. The current detector still produces the same fact (`score = 0.0`).
  - **`<iframe sandbox>`:** Removing or changing `sandbox` changes or expands iframe capabilities. It does not mean the iframe was inert before, because behavior depends on the sandbox tokens (such as `allow-scripts`, `allow-same-origin`, and `allow-top-navigation`). The detector does not currently record the sandbox state.
  - **Whitespace around script types in `classify_script()`:** The earlier clarification cited code that does not exist (`type_attr.strip(...)`). The code reads `attributes["type"]`; it trims `type_string` only for JavaScript MIME-type matching, while it compares `module`, `importmap`, and `speculationrules` using `type_string.lower()` directly. Trimming the ends of a string differs from removing characters embedded within it. Compare browser behavior with the [HTML Standard's script preparation rules](https://html.spec.whatwg.org/multipage/scripting.html#prepare-the-script-element) and the deployed Chromium version before changing this logic.

- **F-01 and F-06 (mount cooldown and duplicate invalidation are separate concerns):**
  - **F-01:** If the requirement is a 15-second cooldown after the initial `/auth/me` request, update `useAuth.test.tsx` to advance time for revalidation cases and retain a test proving that focus within the cooldown does not trigger a duplicate request.
  - **F-06:** Paired `visibilitychange` and `focus` events can occur before the first `/auth/me` call finishes. `checkInFlightRef` prevents a second request, but `queryClient.invalidateQueries()` was outside that guard and could still run more than once.

- **B-01 (WebRTC UDP egress risk):** Keep it high priority as a risk awaiting Linux container verification. Missing exploit evidence does not resolve the configuration gap. The actual egress behavior and mitigation must be verified in the target runtime.

### 5.2 Environment and cleanup test results

#### 1. Mypy and the standard environment

The project `.venv` reported **1 error** at `attempts.py:145`; Global Python reported **5 errors**, adding four `Result[Any].rowcount` errors in `members.py` at lines 215, 257, 317, and 430. Package versions were not compared, so the additional errors cannot yet be attributed to specific packages.

**Recommended action:** Define the project/CI environment and its pinned versions, then resolve typing errors against that standard environment.

#### 2. The five reported `test_cleanup_artifacts.py` failures

The failures were attributed to **two code causes affecting three tests** and **two Windows mechanism/permission issues affecting two tests**:

1. **Connection not closed after a post-connect failure (one test: `test_apply_refuses_when_another_connection_holds_writer_lock`):** In `open_database()`, if `connection.execute("BEGIN EXCLUSIVE")` raises `sqlite3.OperationalError: database is locked`, the connection is not closed before the exception propagates. The retained handle can cause `PermissionError [WinError 32]` when Windows removes the temporary directory during teardown.

2. **Unnormalized paths in helper comparisons (two tests: `test_manifest_output_cannot_replace_database_or_artifact` and `test_manifest_output_cannot_replace_sqlite_sidecars`):** `assert_manifest_path_is_safe()` resolves the output parent, which can turn a Windows 8.3 path such as `C:\Users\PHATTH~1.PI\...` into `C:\Users\phatthasuk.pi\...`, then compares it with the unresolved path returned by `sqlite_protected_paths(database)`.
   - **Impact boundary:** Normal CLI execution calls `canonical_database(args.database, data_root)` and resolves the database path first. This helper-path mismatch alone does not establish that the normal CLI can overwrite the database. The demonstrated risk is direct helper use with an unresolved path, as in tests.

3. **Directory file descriptors and symlink permissions (two tests):**
   - **`test_deletes_only_approved_expired_orphans_and_keeps_history`:** Opening a directory with `os.open()` for `dir_fd` operations fails on the tested Windows environment with `PermissionError [Errno 13]`. The reported traceback points to `apply_approved_orphans()` around line 403.
   - **`test_artifact_symlink_file_and_directory_are_rejected`:** Windows can create symlinks when the process has `SeCreateSymbolicLinkPrivilege` or Developer Mode is enabled. The tested session lacked that permission and failed during test setup with `OSError [WinError 1314]`.

The two Windows cases depend on OS support and permissions. Keep their traceback evidence separate from the three code-related failures, and rerun them in the target Linux environment.

### 5.3 Post-Remediation Verification Record (6-Phase Plan)

The reconciled findings were organized into **6 phases (Phase 0 to Phase 5)** in [plan/Remediation_Plan_19-10-2026.md](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project%20Linux/plan/Remediation_Plan_19-10-2026.md), strictly separating **Code Implemented** status from **Verified by Tests** status:

- **Baseline Commit SHA:** `e2934813f81d5660dccf9cdd54273de58c4105ec` (`e293481`)
- **Backend Environment (`backend/.venv`):** Python `3.13.7`, `pytest 8.3.3`, `mypy 1.13.0`, `ruff 0.7.4`, `fastapi 0.128.8`, `starlette 0.52.1`, `playwright 1.63.0`
- **Frontend Environment (`frontend/`):** Node `v24.7.0`, `vitest 4.1.9`, TypeScript (`tsc -b`), ESLint, with lockfile-pinned Windows native bindings restored (`@esbuild/win32-x64@0.21.5`, `@rolldown/binding-win32-x64-msvc@1.1.4`, `@rollup/rollup-win32-x64-msvc@4.62.2`, `lightningcss-win32-x64-msvc@1.32.0`)

| Phase | Scope | Code Status | Test / Runtime Verification Status |
| :--- | :--- | :---: | :---: |
| **Phase 0** | Environment standardization (`backend/.venv` & Windows native bindings for Vitest) | Completed | **Verified** (`pytest` and `vitest` execute reproducibly) |
| **Phase 1** | Backend stability & security (`B-03`, `B-02`, `B-08a`, `B-08b`) | Implemented | **Verified by behavioral `pytest` tests** |
| **Phase 2** | Frontend cache isolation & Principle F4 error states with retry (`F-02`, `F-04`, `F-05`) | Implemented | **Verified by `tsc -b`, `eslint`, and behavioral `vitest` tests** |
| **Phase 3** | Structural detector (`B-05a` `nomodule`, `B-05b` `iframe sandbox`) & frontend state/auth (`F-01`, `F-03`, `F-06a/b`, `F-07`, `F-09a/b`) | Implemented | **Verified by `pytest` (`test_structure.py`) and `vitest` (`useAuth.test.tsx`, `MembersPage.test.tsx`)** |
| **Phase 4** | State machine consistency (`B-09a`, `B-09c`), `cleanup_artifacts.py` (`B-09b`), and static analysis (`LINT-01`) | Implemented | **Verified on Windows** (`mypy app`: 0 errors; `ruff check`: 0 errors; 3/3 code-defect tests in `test_cleanup_artifacts.py` pass) |
| **Phase 5** | Linux container runtime & hardening (`B-01`, `B-06a/b`, `B-07`, `B-10`, `F-08a/b`, `F-09c`) | Hardening Implemented (`B-06a/b` & `B-07` verified by unit/integration tests; `B-11` deferred with documented criteria) | **Awaiting Linux Container Runtime Verification** (`B-01` WebRTC UDP egress, 2 POSIX `dir_fd`/symlink cleanup tests, `B-10` cgroups/seccomp, and `F-08` Nginx live headers) |

#### Post-Remediation Verification Commands and Results

| Check / Suite | Exact Command | Verified Result |
| :--- | :--- | :--- |
| **Frontend Typecheck** | `.\node_modules\.bin\tsc.cmd -b --pretty false` | **Passed (`0 errors`)** |
| **Frontend Lint** | `.\node_modules\.bin\eslint.cmd src` | **Passed (`0 errors`)** |
| **Frontend Unit/Integration (`vitest`)** | `node node_modules/vitest/vitest.mjs run` | **Passed (`14 / 14 files`, `94 / 94 tests` in `11.73s`)** |
| **Backend Typecheck (`mypy`)** | `.\.venv\Scripts\python.exe -m mypy app` | **Passed (`Success: no issues found in 61 source files`)** |
| **Backend Lint (`ruff`)** | `.\.venv\Scripts\python.exe -m ruff check app scripts tests` | **Passed (`All checks passed!`)** |
| **Backend Main Suite (`pytest`)** | `.\.venv\Scripts\python.exe -m pytest tests/ -k "not test_cleanup_artifacts" -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_all"` | **Passed (`264 passed, 0 failed, 9 deselected` in `140.33s`)** |
| **Backend Cleanup Suite (`pytest`)** | `.\.venv\Scripts\python.exe -m pytest tests/test_cleanup_artifacts.py -q -p no:cacheprovider --basetemp="C:\Users\phatthasuk.pi\AppData\Local\Temp\wdm_pytest_cleanup"` | **`7 passed, 2 failed` in `1.40s`** *(3/3 code-defect fixes pass; 2 failures are Windows OS mechanism/privilege limits: `WinError 1314` on `os.symlink` and `PermissionError [Errno 13]` on `os.open` directory `dir_fd`, scheduled for Phase 5 Linux container run)* |