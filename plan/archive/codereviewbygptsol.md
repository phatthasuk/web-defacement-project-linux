# Code Review and Recommended Solutions

## Scope

This review covers the `frontend` and `backend` folders of the Web Defacement Monitor project. It focuses on security, correctness, reliability, and operational safety.

No application source code was modified as part of the review. At the time of review, the existing automated checks produced the following results:

- Backend tests: 49 passed.
- Frontend tests: 23 passed across 7 test files.
- Ruff: passed.
- Mypy: passed for 36 backend source files.
- ESLint: passed.
- TypeScript type checking: passed.

Passing tests do not cover all of the failure and attack scenarios described below.

## Executive Summary

Eight material issues were identified:

1. The backend exposes privileged operations without authentication or authorization.
2. The SSRF protection has a DNS-rebinding window for repeated subresource requests.
3. Artifact limits are enforced only after expensive content has already been loaded or generated.
4. The frontend can present failed artifact requests as valid comparison results.
5. Failed checks can leave untracked artifact files on disk.
6. WebSocket and other browser traffic can bypass request-route SSRF checks.
7. Chromium runs without its process sandbox while loading potentially hostile pages.
8. In-process background checks are not durable across process or container restarts.

Issues 1, 2, 6, and 7 should be resolved before exposing the application beyond a trusted local development environment. Issue 3 should follow immediately because it can affect service availability. Issues 4, 5, and 8 are important for monitoring accuracy and long-term operational stability.

---

## Finding 1: Backend Operations Have No Authentication or Authorization

**Severity:** P1 / Critical for any network-accessible deployment

### Problem

The backend is configured to listen on `0.0.0.0:8000`, and Docker publishes that port. The API routes do not require an authenticated identity or enforce permissions. Consequently, anyone who can reach the service may be able to:

- Create and deactivate monitoring targets.
- Trigger browser-based checks against arbitrary allowed public URLs.
- Read captured text and screenshots.
- Approve a new baseline.
- Acknowledge detected changes.

This can compromise the integrity of monitoring decisions, expose captured information, and allow unauthorized consumption of browser, CPU, memory, network, and disk resources.

### Evidence

- `docker-compose.yml`: backend command and published port at lines 13 and 16-17.
- `backend/app/api/routes/targets.py`: target creation starts at line 20.
- `backend/app/api/routes/checks.py`: check triggering starts at line 24.
- `backend/app/api/routes/review.py`: baseline approval starts at line 15.
- `backend/app/api/routes/snapshots.py`: artifact retrieval starts at lines 26 and 38.

### Recommended Solution

Require authentication for every endpoint except explicitly public operational endpoints such as `/health`.

For a production deployment, use an established OIDC/OAuth2 identity provider such as Microsoft Entra ID or Keycloak. Validate access tokens on the backend and implement role-based authorization. A practical role model would include:

- **Viewer:** may read targets, checks, and approved artifacts.
- **Operator:** may trigger checks and acknowledge findings.
- **Administrator:** may create or deactivate targets and approve baselines.

For a strictly internal prototype, an API key can be used as a temporary minimum control for service-to-service access or when a trusted reverse proxy injects the credential. An API key is not suitable as a browser SPA credential because users can inspect JavaScript, runtime configuration, browser storage, and network requests. It should be stored in an environment variable, compared safely by the backend, rotated periodically, and never embedded in a publicly served frontend bundle.

For the browser application, prefer OIDC Authorization Code Flow with PKCE or a Backend-for-Frontend architecture. If authentication uses cookies, use `HttpOnly`, `Secure`, and an appropriate `SameSite` policy, and protect state-changing requests against CSRF. Prefer short-lived access tokens and enforce role claims on the backend rather than relying on UI visibility.

Additional deployment controls should include:

- Bind Docker ports to `127.0.0.1` when remote access is unnecessary.
- Place the API behind an HTTPS reverse proxy.
- Restrict access with host firewall or security-group rules.
- Apply rate limits to mutation endpoints, especially check triggering.
- Record audit events for target changes, baseline approvals, and acknowledgements.

### Tests to Add

- An unauthenticated request receives HTTP 401.
- An authenticated identity without the required role receives HTTP 403.
- A viewer cannot trigger a check, deactivate a target, or approve a baseline.
- An operator can trigger and acknowledge checks but cannot approve baselines.
- Health-check behavior remains consistent with the intended exposure policy.

---

## Finding 2: SSRF Protection Has a DNS-Rebinding Window

**Severity:** P1 / High

### Problem

During capture, `is_url_safe` caches a boolean result per hostname. After a hostname passes validation once, later requests to the same hostname are allowed without resolving and validating its addresses again.

The primary target hostname is pinned to a validated IP through Chromium's resolver rules, but additional subresource hostnames are not pinned in the same way. An attacker who controls DNS could initially return a public address, pass validation, and subsequently change the address to a private or otherwise blocked destination. The cached `True` value would bypass another application-level DNS check.

Network-layer DNS caching may reduce exploit reliability, but it is not a security boundary and should not be relied upon.

### Evidence

- `backend/app/services/capture/capture.py`: hostname cache lookup and boolean caching at lines 60-74.
- `backend/app/services/capture/capture.py`: requests continue after the cached safety decision at lines 76-100.
- `backend/app/core/ssrf_guard.py`: the module documents DNS rebinding as a known limitation at lines 4-7.

### Recommended Solution

Do not cache only a boolean safety result. Store the validated address set and the selected pinned address for each hostname:

```text
hostname -> validated IP set + pinned IP
```

For every hostname involved in navigation, redirects, frames, or subresources:

1. Resolve all addresses.
2. Reject the hostname if any returned address is blocked, unless the security design explicitly defines a safer alternative policy.
3. Select a validated address.
4. Pin the hostname to that address for the lifetime of the capture.
5. Reject or restart the capture if the address set changes unexpectedly.

The checks must cover IPv4, IPv6, IPv4-mapped IPv6, loopback, private, link-local, multicast, unspecified, reserved, and cloud metadata ranges.

Because browser-level request interception cannot completely eliminate DNS and network race conditions, use defense in depth:

- Run capture workers in a separate container or network namespace.
- Deny access to private networks and metadata services with egress firewall rules.
- Give capture workers no access to the database or internal control plane beyond the minimum required interface.
- Treat any uncertain resolution or interception failure as blocked.

### Tests to Add

- A subresource hostname changes from a public address to a private address.
- A redirect changes to a private or link-local destination.
- DNS returns a mixture of public and blocked addresses.
- A hostname resolves to an IPv4-mapped IPv6 address.
- Multiple requests to the same hostname remain pinned to the validated address.
- Cloud metadata destinations such as `169.254.169.254` remain blocked.

---

## Finding 3: Resource Limits Are Applied After Expensive Work

**Severity:** P2 / High availability risk

### Problem

`MAX_ARTIFACT_SIZE_MB` is checked only after the page has loaded and after HTML, body text, or a full-page screenshot has been materialized in memory. A target can therefore consume substantial bandwidth, browser memory, CPU, and rendering time before the application rejects the result.

A very long page is particularly risky because `page.screenshot(full_page=True)` creates the screenshot before its byte length is checked. Large responses and numerous subresources can also consume resources even when the final stored artifacts remain below the configured threshold.

### Evidence

- `backend/app/services/capture/capture.py`: navigation begins at lines 103-108.
- `backend/app/services/capture/capture.py`: HTML and text are produced before size validation at lines 124-130.
- `backend/app/services/capture/capture.py`: a full-page screenshot is produced before validation at lines 132-134.

### Recommended Solution

Enforce limits at several layers rather than relying on a final artifact-size check.

At the request and response layer:

- Reject responses whose declared `Content-Length` exceeds the per-response limit.
- Count response bytes and abort when a per-response or per-check total is exceeded.
- Limit the number of requests, redirects, frames, and distinct hosts per capture.
- Block unnecessary resource types such as video, audio, and downloads.
- Set explicit limits for individual resources and total downloaded bytes.

At the page and browser layer:

- Use a fixed viewport and define maximum document width, height, and pixel count.
- Check document dimensions before requesting a screenshot.
- Capture a bounded region, or split tall pages into controlled tiles.
- Set a hard deadline for the entire capture session.
- Apply container CPU, memory, process, and temporary-storage limits.

At the application layer:

- Limit pending jobs and reject excess work with HTTP 429 or 503.
- Apply per-user and per-target rate limits.
- Move browser work to a dedicated worker queue rather than executing it in the API process.
- Record downloaded bytes, request count, page dimensions, and capture duration as metrics.
- Return a specific error such as `ResourceLimitExceeded` instead of an unclassified failure string.

### Tests to Add

- A response with an excessive `Content-Length` is aborted before its body is consumed.
- Streaming content is aborted when the byte counter exceeds the limit.
- A page exceeding the maximum document height does not create a full-page screenshot.
- Excessive request count and redirect count terminate the capture.
- Overall capture timeout closes the browser and releases concurrency slots.
- Queue and rate limits return the intended status and retry guidance.

---

## Finding 4: Frontend Artifact Errors Can Be Displayed as Valid Diffs

**Severity:** P2 / High correctness risk

### Problem

The frontend defaults snapshot text query results to empty strings and checks loading state but does not handle query errors before rendering `TextDiffView`.

This creates two misleading outcomes:

- If both text requests fail, both values become empty strings and the UI can report that no textual differences were detected.
- If only one request fails, the UI can display a large artificial diff between an empty string and the successfully loaded artifact.

For a defacement-monitoring system, a retrieval failure must be represented as an unknown or failed comparison, never as evidence that content is unchanged.

### Evidence

- `frontend/src/pages/CheckDetailPage.tsx`: text query defaults at lines 23-33 and diff rendering at lines 187-201.
- `frontend/src/pages/TargetDetailPage.tsx`: text query defaults at lines 50-60 and diff rendering at lines 309-327.

### Recommended Solution

Capture `isError`, `error`, and `refetch` from each artifact query. Render the comparison only when both required queries have succeeded.

The UI state order should be explicit:

```text
loading -> loading indicator
error   -> artifact error message and retry action
success -> render the comparison
```

Do not use an empty string as a fallback until the request has successfully returned an intentionally empty artifact. Distinguish these states in the component model:

- Not requested.
- Loading.
- Failed.
- Successfully loaded and empty.
- Successfully loaded with content.

Apply the same principle to snapshot lists, baselines, check history, configuration, and screenshot images. Use image `onError` handling so a missing screenshot does not appear as a valid blank comparison.

Error messages should identify which artifact failed and provide a retry action. Diagnostic details may be logged, but sensitive backend details should not be shown indiscriminately to end users.

### Tests to Add

- Baseline text retrieval fails.
- Current text retrieval fails.
- Both text requests fail.
- A successfully retrieved empty document remains distinguishable from a request failure.
- Retry succeeds and renders the correct comparison.
- A failed screenshot request displays an explicit error state.
- `No textual differences detected` is never rendered while an artifact query is in an error state.

---

## Finding 5: Failed Checks Can Leave Orphan Artifact Files

**Severity:** P2 / Medium to high operational risk

### Problem

Capture writes screenshot, text, and HTML files before diff calculation and the final database commit. If diffing, image decoding, status transition, or database commit fails, the database transaction is rolled back and the target is marked failed, but the files already written to disk are not removed.

These files have no corresponding snapshot record. Repeated failures can gradually consume disk space, while the application has no database-backed way to discover or manage the files.

### Evidence

- `backend/app/services/capture/capture.py`: artifact files are written at lines 148-150.
- `backend/app/services/checks.py`: diff and database commit occur later at lines 90-115.
- `backend/app/services/concurrency.py`: unexpected errors are converted to failed results at lines 163-177 without artifact cleanup.

### Recommended Solution

Use a staging-and-finalization workflow with an explicit snapshot lifecycle. A database commit followed by a file move is not atomic: if the commit succeeds and the move fails, the database points to missing files. Represent this state directly instead of assuming the filesystem and database can participate in one transaction.

1. Create a server-generated check or snapshot identifier.
2. Create a snapshot record with lifecycle status `Pending`.
3. Write all files under `DATA_DIR/staging/<identifier>/`.
4. Complete capture, validation, and diff processing.
5. Move the staged artifacts to immutable final paths on the same filesystem.
6. Verify that every required final artifact exists and matches its expected metadata.
7. Update the snapshot lifecycle status to `Ready` in a database transaction.
8. If processing fails, mark the snapshot `Failed` or remove its pending record, then safely remove its staging files.

Readers must only serve artifacts from `Ready` snapshots. Once an artifact becomes `Ready`, treat it as immutable. A reconciliation job must recover failure windows, including a process crash after the final file move but before the `Ready` update.

Cleanup code must verify that every path resolves beneath the configured `DATA_DIR` before deleting anything. It must never delete a path merely because that path came from the database.

Because cleanup in `finally` cannot handle process crashes or machine termination, add a periodic reconciliation job that:

- Deletes staging directories older than a safe threshold.
- Finds artifact files without matching database records.
- Finds database records whose files are missing.
- Applies the configured snapshot-retention policy.
- Logs every cleanup decision for audit and troubleshooting.

### Tests to Add

- Diff failure removes all staged artifacts.
- Database commit failure removes all staged artifacts.
- Successful checks preserve and serve finalized artifacts.
- The reconciliation job removes expired staging directories.
- Cleanup does not remove artifacts referenced by successful snapshots.
- A path outside `DATA_DIR` is rejected and never deleted.
- A process-crash simulation leaves recoverable staging data for the reconciliation job.
- A crash after the final file move but before the `Ready` update is reconciled safely.
- APIs never serve artifacts from `Pending` or `Failed` snapshots.

---

## Additional Findings (Post-Review Verification)

The following gaps were identified during an independent verification of this review against the codebase. They are not covered by Findings 1-5.

### Finding 6: WebSocket and Other Browser Traffic Can Bypass the SSRF Guard

**Severity:** P1 / High

#### Problem

The SSRF guard is implemented through Playwright HTTP request interception (`page.route("**/*")`). This does not, by itself, apply the same URL validation to WebSocket connections. Requests handled by service workers can also escape ordinary page routing unless service workers are disabled. A compromised or attacker-controlled page can therefore attempt to use a non-covered browser channel to reach an internal address without passing through `is_url_safe`.

Because this system's core function is to load pages that may already be defaced or attacker-controlled, these bypass channels must be treated as hostile.

#### Evidence

- `backend/app/services/capture/capture.py`: HTTP interception is registered at line 102 via `page.route("**/*", guard_navigation)`; no WebSocket routing or service-worker blocking exists in the capture pipeline.
- `backend/requirements.txt`: Playwright 1.48.0 is installed and provides WebSocket routing support.

#### Recommended Solution

- Register `page.route_web_socket("**/*", handler)` before navigation. Prefer blocking all WebSocket connections during capture unless the monitoring requirements explicitly need them. If WebSockets must be supported, validate and pin their destinations with the same policy used for HTTP requests.
- Create the browser context with service workers blocked so service-worker-controlled requests cannot bypass page routing.
- Do not rely on `page.on("websocket")` as the primary control because an observation callback is not equivalent to preventing the initial connection.
- Treat egress firewall rules that deny private networks and metadata services (already recommended in Finding 2) as the primary boundary; browser-level interception remains defense in depth.
- Apply the same scrutiny to channels that are not reliably controlled by ordinary request routing, including WebRTC and DNS prefetching. Enforce their restrictions through browser policy and network isolation.

#### Tests to Add

- A page that opens a WebSocket to a private address does not establish the connection.
- A page that registers a service worker cannot use it to reach blocked destinations.
- Capture of a page attempting WebRTC connections to internal addresses completes without leaking requests.
- WebSocket blocking is installed before any page script executes.

### Finding 7: Chromium Runs Without a Sandbox

**Severity:** P2 / High for this threat model

#### Problem

The browser is launched with `--no-sandbox --disable-setuid-sandbox`. This system deliberately loads pages that may have been compromised, which is precisely the scenario where a renderer exploit is most likely. Without the Chromium sandbox, a renderer-level exploit escalates directly to the capture process's privileges on the host.

#### Evidence

- `backend/app/services/capture/capture.py`: launch arguments at line 34.

#### Recommended Solution

- Prefer running Chromium with its sandbox enabled. If the container environment prevents this, run capture in a dedicated, minimal-privilege container with a read-only filesystem, no shared network namespace with the API or database, seccomp/AppArmor profiles, and strict egress rules.
- Do not run the capture process as root.
- Combine with the worker isolation recommended in Findings 2 and 3 so that browser compromise cannot reach the control plane.

#### Tests to Add

- Deployment configuration verifies the sandbox is active, or documents and enforces the compensating container isolation.
- Capture workers cannot reach the database or internal API from within their runtime environment.

### Finding 8: In-Process Background Checks Are Not Durable

**Severity:** P2 / High operational reliability risk

#### Problem

Check execution is scheduled with FastAPI `BackgroundTasks`, which is in-process and has no persistent queue. `run_target_check` commits the target status as `Checking` before capture starts. If the API process, container, or host stops after that commit, the job disappears but the persisted target can remain `Checking` indefinitely.

The trigger endpoint rejects targets already marked `Checking`, and application startup currently creates directories and database tables but does not recover stale checks. This can leave a target permanently unable to run another check without direct administrative intervention.

#### Evidence

- `backend/app/api/routes/checks.py`: checks are scheduled with `background_tasks.add_task` at lines 41-47.
- `backend/app/services/checks.py`: the target transitions to `Checking` and commits before capture at lines 43-48.
- `backend/app/api/routes/checks.py`: a target in `Checking` is not accepted for another check at lines 38-39.
- `backend/app/main.py`: startup creates data directories and tables at lines 17-22 but performs no stale-check recovery.

#### Recommended Solution

- Move check execution to a durable queue such as Celery, Dramatiq, RQ, or an equivalent organizational job platform.
- Persist job metadata including `job_id`, `started_at`, `heartbeat_at`, `attempt`, `worker_id`, and terminal outcome.
- Model execution ownership as a time-limited lease rather than relying only on a `Checking` status.
- Renew the lease with worker heartbeats. Allow recovery when the lease expires.
- During startup or scheduled reconciliation, mark stale checks as `Failed` or `Timed Out` and release their targets for retry.
- Make check execution idempotent so redelivery does not create duplicate snapshots or artifacts.
- Define bounded retry behavior and dead-letter handling for repeatedly failing jobs.
- Enforce duplicate suppression with a database constraint, transactional claim, or distributed lock rather than process-local memory alone.

#### Tests to Add

- A process stops immediately after committing `Checking`.
- Startup recovery converts a stale check to a terminal failure state.
- An expired worker heartbeat releases the job lease.
- Duplicate queue delivery does not create duplicate snapshots or artifacts.
- A retry cleans up or reuses artifacts according to the lifecycle policy.
- A live worker renewing its lease is not incorrectly recovered by another worker.

### Minor: Stale docker-compose Comment

The header comment in `docker-compose.yml` (lines 4-6) states that application code is not written yet. The application is fully implemented; the comment should be removed to avoid confusion.

---

## Recommended Implementation Order

1. Add authentication, authorization, network restrictions, and rate limiting.
2. Strengthen SSRF protection and isolate browser workers with egress controls, including WebSocket routing, service-worker blocking, and browser sandboxing (Findings 2, 6, and 7).
3. Enforce bounded network, page, screenshot, queue, CPU, and memory usage.
4. Replace in-process background execution with durable jobs, leases, heartbeats, and stale-check recovery.
5. Correct frontend loading, error, and success state handling.
6. Introduce snapshot lifecycle states, staged artifact writes, and periodic reconciliation.

## Completion Criteria

The remediation should be considered complete when:

- Privileged endpoints cannot be used anonymously or by an insufficiently privileged role.
- Every browser destination is validated and pinned, with private-network access denied at the network layer.
- Oversized or excessively complex pages are terminated before unbounded resources are consumed.
- The frontend never presents an artifact-loading failure as a successful no-change result.
- Failed or interrupted checks do not cause indefinite growth of untracked files.
- Process or container restarts do not leave targets permanently stuck in `Checking`.
- WebSocket, service-worker, WebRTC, and other browser channels cannot bypass network policy.
- Only `Ready` snapshots can serve immutable artifacts.
- New automated tests cover the security and failure scenarios listed in this document.
