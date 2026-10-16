# Code Review Completion Plan — CR09 (September 10, 2026)

**Status as of September 10, 2026: Source code remediated and verified on Windows; isolated Linux runtime/sandbox verification remains open due to inactive Docker daemon.**  
Review Series Base Plan: [Code Review by GPT6 Astra 9-9-2026](Code%20Review%20by%20GPT6%20Astra%209-9-2026.md)  
Master Plan: [PROJECT_PLAN.md](PROJECT_PLAN.md)  
Verified Refinement Log: [Refinement CR09 — September 10](../refinement/10-9-2026/Code-Review-Remediation-CR09-01-to-CR09-07-10-9-2026.md)

## 1. Scope and Invariants

This plan builds upon existing remediations to resolve outstanding requirements in CR09-01 and CR09-05 while consolidating verification evidence across all seven review items. Correctly implemented components are preserved.

Implementation covers source code, regression suites, and local verification without applying changes to production runtimes.

Invariants to maintain:
- Preserve the single API worker and concurrency limits defined in the system architecture.
- Do not drop databases, snapshot histories, or baseline records; avoid auto-rebaselining or shifting thresholds to force passing tests.
- Maintain authentication, CSRF validation, service-worker blocking, and WebSocket blocking.
- Utilize isolated test databases and mock network fixtures decoupled from production storage.
- Do not modify active Linux sandbox configurations without runtime evidence and documented rollback procedures.
- Do not reset Stage 2 or soak-testing histories automatically as part of remediation.
- Clearly delineate "Code Remediated", "Tested", and "Deployed" statuses supported by concrete evidence.

## 2. Initial Assessment Status

| ID | Verified Code Status | Outstanding Tasks |
| --- | --- | --- |
| CR09-01 | Partially addressed | Eliminate fetch-error fallback, bind IP policies to live connections, preserve redirect semantics, handle pre-frame requests, and prove zero egress |
| CR09-02 | Automatic fallback removed | Add error/configuration tests and separate Linux runtime verification from code policies |
| CR09-03 | Structural unavailability marked Failed | Verify missing path, permission, and corruption cases with clean rollback |
| CR09-04 | Added Checking/in-flight guards for single worker | Test concurrency interleaving during diff execution and semaphore waits for approve/demote |
| CR09-05 | Screenshot/text linked to check IDs | Align metadata and approval with the identical snapshot; clarify historical results during check failures |
| CR09-06 | Addressed logout state/error feedback | Test 200, 401, network/5xx/403 errors, and response-loss retries |
| CR09-07 | Separated DNS exceptions from availability | Test via capture routing and create/update APIs with timeouts and cleanup |

## 3. Work Sequence and Milestones

| Step | Milestone | Prerequisites |
| --- | --- | --- |
| 0 | Environment Documentation & Fixture Setup | Record environment metadata, browser versions, and verify test storage isolation |
| 1 | Design & Proof of Concept for CR09-01 | Demonstrate complete network bypass mitigation while preserving web behavior |
| 2 | Implementation of CR09-01 & CR09-05 | Pass criteria defined in Sections 4 and 5 |
| 3 | Verification of Remaining 5 Items | Pass test matrix in Section 6; isolate Linux sandbox tracking |
| 4 | Comprehensive Regression & Static Analysis | Execute clean Pytest, Vitest, Ruff, Mypy, and TypeScript builds |
| 5 | Isolated Linux Runtime Testing | Verify capture, redirects, egress limits, and effective sandboxing |
| 6 | Delivery & Rollback Documentation | Mark items closed only with complete verification evidence |

## 4. CR09-01 — Enforce SSRF Mitigation and Preserve Capture Fidelity

Key files: `backend/app/services/capture/capture.py`, `backend/app/core/ssrf_guard.py`, `backend/app/core/errors.py`, `backend/tests/test_capture.py`, `backend/tests/test_ssrf_guard.py`.

### 4.1 Controlled Request Abort Paths
1. Remove all fallback calls to `route.continue_()` upon fetch, validation, or redirect failures.
2. Propagate explicit error classifications: SSRF policy rejection, DNS failure, timeout, or capture failure. Never swallow errors to produce false OK statuses.
3. Distinguish main document navigations from popups, iframes, and subresources to maintain accurate availability classifications.
4. Safely handle unready `request.frame` exceptions without relying on naive `hasattr()` checks.
5. Validate destination schemes strictly per policy; do not introduce production bypasses for `file://` to satisfy tests.

### 4.2 Transport Architecture Decision
The transport mechanism must simultaneously satisfy: verifying destination IPs prior to connection, eliminating direct fallbacks, validating every redirect hop, and preserving browser cookie/origin/method semantics.

Evaluated options:
- **Egress Proxy / Network Isolation:** A local proxy resolves and connects strictly to verified IPs, blocking direct browser egress.
- **Request Interception:** Manually handling hops via `route.fulfill()`. Note that naive `route.fetch()` fails because it re-resolves hostnames without IP pinning.

### 4.3 Acceptance Test Cases
- Direct requests to blocked IP ranges receive 0 requests.
- Main redirects, popup targets, iframes, and subresource redirects to blocked IPs receive 0 requests.
- DNS rebinding between validation and socket connection is blocked.
- Fetch errors and connection resets trigger clean failure without unhandled fallbacks.
- Redirect limits are strictly enforced.
- Allowed redirects across schemes (HTTP→HTTPS) preserve cookies, headers, and relative resource references.

## 5. CR09-05 — Synchronize Screenshot, Text, Metadata, and Approval Targets

Key files: `frontend/src/pages/TargetDetailPage.tsx`, `frontend/src/hooks/useTargetDetail.ts`, `frontend/src/api/snapshots.ts`.

1. Derive comparison data strictly from a single `CheckResult`, using baseline and current IDs as the authoritative reference for screenshots, text, metadata, and scores.
2. Fetch snapshot metadata by ID directly when absent from cache rather than assuming the first 50 snapshots contain historical baselines.
3. Remove fallback logic that renders mismatched baseline metadata or falls back to the latest snapshot during approval.
4. The Approve button must explicitly indicate which snapshot ID is being approved, matching the rendered comparison.
5. Identify initial baseline states by the absence of a `CheckResult` rather than checking if snapshot count equals 1.
6. For clean OK checks sharing identical baseline/current IDs, explicitly indicate that the baseline image is displayed.
7. During Failed or Availability Issue checks, clearly display the current failure error alongside the timestamp of the last successful comparison.

## 6. Verification Matrix for Remaining Items

| ID | Required Verification | Acceptance Criteria |
| --- | --- | --- |
| CR09-02 | Mock sandbox enabled/disabled and launch errors | Accurate launch arguments; no silent downgrade; precedence documented |
| CR09-02 Linux | Inspect UID/GID, seccomp profiles, and AppArmor logs | Clearly distinguish "capture succeeds" from "sandbox actively enforced" |
| CR09-03 | Missing paths, permission errors, and corrupted baseline images | Structural failures report Failed; staging artifacts cleaned up |
| CR09-04 | Concurrency barriers during diff execution vs. approve/demote | Mutations during active checks return 409 Conflict; last baseline cannot be demoted |
| CR09-06 | Frontend integration tests for 200, 401, 500, 403, and network failures | Failed sessions do not clear auth state incorrectly; expired sessions route to login |
| CR09-07 | DNS resolution failures, private IP rejections, and timeouts | Unresolved domains classified as Availability Issue; blocked IPs classified as Security / Failed |

## 7. Delivery Commands and Verification Suites

Execute using virtual environment interpreters:

From `backend/`:
```text
python -m pytest tests
python -m ruff check --no-cache app tests scripts
python -m mypy app scripts
```

From `frontend/`:
```text
npm run test
node node_modules/typescript/lib/tsc.js --project tsconfig.app.json --noEmit
node node_modules/typescript/lib/tsc.js --project tsconfig.node.json --noEmit
npm run lint
npm run build
```

## 8. Deployment and Rollback Protocols

Before submitting production deployment proposals:
1. Provide source and configurations verified in isolated Linux environments without secrets.
2. Establish verified database and artifact backup procedures without altering production source data.
3. Define graceful shutdown procedures allowing in-flight jobs to drain.
4. Execute smoke tests covering login/logout, capture, and status triage post-deployment.
5. Document explicit rollback steps.

## 9. Closure Checklist

- [x] CR09-01: Fallbacks and DNS rebinding gaps closed; blocked destinations receive zero requests.
- [x] Capture redirects preserve final URLs, origins, and relative subresources via validating proxy.
- [x] CR09-05: Visuals, text diffs, metadata, and approval actions reference the identical snapshot.
- [x] CR09-02/03/04/06/07 pass regression test matrices.
- [x] Backend and frontend test suites, linters, and production builds pass cleanly.
- [ ] Isolated Linux capture/egress and sandbox enforcement verified with live container evidence.
- [x] Zero data loss, zero auto-rebaseline, and zero threshold inflation.
- [x] Refinement documentation accurately reflects verified scope.
- [ ] Production deployment executed upon explicit instruction.

## 10. Post-Execution Status

Source code remediated and verified on Windows per [Code Review Completion CR09 — 10-9-2026](../refinement/10-9-2026/Code-Review-Completion-CR09-10-9-2026.md). No production deployment was conducted. Verification of effective Chromium sandboxing on Linux remains open pending access to an active Docker daemon.
