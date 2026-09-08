# Walkthrough of Code Review Revisions

We have successfully resolved all findings described in the [code-review-revision-guide.md](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/plan/code-review-revision-guide.md). The details of the modifications are summarized below.

---

## Summary of Changes

### 1. SSRF DNS Rebinding Mitigation (#1)
- **Problem**: Hostname checks were subject to DNS rebinding (TOCTOU) between Python-side validation and Chromium-side dynamic resolution.
- **Solution**:
  - Updated [capture_snapshot](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/capture/capture.py#L29) in [capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/capture/capture.py) to resolve the target hostname's IPs, validate all returned IPs against the SSRF private blocklist, and pin Chromium's connection requests to the first safe IP using the launch arg `--host-resolver-rules=MAP {hostname} {pinned_ip}` (avoiding TOCTOU by ensuring the pinned IP itself is validated).
  - Added module docstring describing the DNS rebinding limits and recommended egress restrictions in [ssrf_guard.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/core/ssrf_guard.py#L1).
  - Added a unit test in [test_capture.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/tests/test_capture.py#L110) validating that `--host-resolver-rules` are applied on HTTP capture launch.

### 2. approve_baseline 409 on Failed targets (#2)
- **Problem**: Approving baseline on `Failed` targets returned a 409 because state machine transitions from `Failed` to `OK` were disallowed.
- **Solution**:
  - Updated `ALLOWED_TARGET_STATUS_TRANSITIONS` in [status.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/core/status.py#L25) to allow `Failed` -> `OK`.
  - Updated [approve_baseline](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/review.py#L16) in [review.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/review.py) to clear `target.last_error` and reject approvals during active `Checking` state with a `ValidationError`.
  - Appended unit tests in [test_review.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/tests/test_review.py#L190) validating recovery from `Failed` and checking status block.

### 3. DB connection leak across Semaphore wait (#3)
- **Problem**: DB session was kept open while async worker queued on concurrency semaphores, risking connection pool exhaustion.
- **Solution**:
  - Refactored `run_checks_for_targets` in [concurrency.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/concurrency.py#L84) to execute pre-flight database queries in a short-lived DB session, await semaphores outside the DB session block, and fetch the target in a new session only after acquiring slots.

### 4. Concurrency warning & Worker limit constraint (#4)
- **Problem**: Concurrency global variables are process-local, rendering them invalid under multi-worker scaling.
- **Solution**:
  - Added warning comment block in [concurrency.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/concurrency.py#L23) clarifying this constraint.
  - Added `--workers 1` to uvicorn deployment command in [docker-compose.yml](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/docker-compose.yml#L13).

### 5. mark_target_failed State Machine Guard (#5)
- **Problem**: Crash/timeout target status updates bypassed transitions checks in state machine.
- **Solution**:
  - Updated [mark_target_failed](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/concurrency.py#L201) in [concurrency.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/services/concurrency.py) to assert valid state machine transition using [is_valid_transition](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/core/status.py#L33) before transitioning, with warning logging if skipped.

### 6. Dialect-conditional SQLite Config (#6)
- **Problem**: SQLite pragmas and connection parameters caused crashes if DATABASE_URL pointed to another dialect like Postgres.
- **Solution**:
  - Updated [session.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/db/session.py#L10) to conditionally apply SQLite connection parameters and connection listener only if URL starts with `sqlite`.

### 7. Schema Tightening (#7)
- **Problem**: Schema inconsistency between creation and updates, and lack of length boundaries on name/url parameters.
- **Solution**:
  - Standardized `TargetCreate` and `TargetUpdate` in [target.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/schemas/target.py#L6) schemas using `model_config = ConfigDict(extra="forbid")`.
  - Added `Field` validator constraints mapping `min_length`/`max_length` bounds (name: 1-200, url: 1-2048).

### 8. Query Pagination and Dedicated Baseline Endpoint (#8)
- **Problem**: Unpaginated query lists on endpoints caused scaling issues. Standard pagination could cause frontend visual comparison to fail if baseline fell off the first page.
- **Solution**:
  - Added `limit`/`offset` pagination query params on routes `/targets`, `/targets/{id}/snapshots`, and `/targets/{id}/checks` in [targets.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/api/routes/targets.py#L34) and [checks.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/api/routes/checks.py#L59).
  - Created dedicated endpoint `/targets/{id}/baseline` in [targets.py](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/api/routes/targets.py#L105) returning only the active baseline.
  - Implemented `getTargetBaselineSnapshot` API function in [snapshots.ts](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/snapshots.ts#L8).
  - Implemented react hook `useTargetBaselineSnapshotQuery` in [useTargetDetail.ts](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/hooks/useTargetDetail.ts#L29) and integrated it in [TargetDetailPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.tsx#L22) to query the baseline snapshot separately.
  - Updated frontend mocks in [TargetDetailPage.test.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.test.tsx#L8) to stub the baseline snapshot query hook.

### 9. Disable Button per row pending state (#9)
- **Problem**: "Run Check" disabled states in target list disabled every row simultaneously.
- **Solution**:
  - Updated disabled condition in [TargetListPage.tsx](file:///c:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetListPage.tsx#L240) to disable button exclusively when `triggerCheckMutation.isPending && triggerCheckMutation.variables === target.id`.

---

## Verification Results
All tests pass successfully:
- **Backend (Pytest)**: 49 / 49 tests passed.
- **Frontend (Vitest)**: 23 / 23 tests passed.

### Visual Verification Screenshots
Below are the screenshots captured during visual verification of the Target Detail page:

![Target Details Comparison](C:\Users\phatthasuk.pi\.gemini\antigravity-ide\brain\656366b5-2ea2-475a-918b-c417f381f02b\target_details_comparison_1783054740782.png)

![Target Details Visual Diffs](C:\Users\phatthasuk.pi\.gemini\antigravity-ide\brain\656366b5-2ea2-475a-918b-c417f381f02b\target_details_visuals_1783054745500.png)
