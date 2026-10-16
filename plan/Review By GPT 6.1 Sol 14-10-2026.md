# Review By GPT 6.1 Sol 14-10-2026

Review Date: October 14, 2026 (Asia/Bangkok)  
Project: Web Defacement Monitoring System  
Status: Proposed remediation items from audit — source code not yet modified

## 1. Scope and Limitations

Reviewed backend code, capture/baseline/review workflows, authentication and authorization, related frontend components, and deployment configuration, alongside running test suites and static checks on Windows using current files. This folder does not contain Git metadata, so no comparison against specific commits or branches was performed.

Linux production deployment has not yet been tested in a live environment, and dependency vulnerabilities have not been verified against external vulnerability advisory databases. Consequently, these findings do not constitute a complete security certification of the system.

This document serves as an actionable task list from the review to be used alongside `PROJECT_PLAN.md` and `MEMBER_MANAGEMENT_PLAN.md`. It does not alter roadmap status or declare remediation complete.

## 2. Action Items

P1 = Must be resolved before trusting monitoring results in production; P2 = Should be resolved in the next cycle to enhance accuracy and confidence; P3 = Code/documentation consistency and quality.

| ID | Priority | Task | Status |
| --- | --- | --- | --- |
| RV-01 | P1 | Require operator approval for initial baseline | Pending |
| RV-02 | P2 | Add event handler and JavaScript URL inspection to structural detector | Pending |
| RV-03 | P2 | Re-check navigation errors after page wait and before returning capture | Pending |
| RV-04 | P2 | Validate origin completely across scheme, hostname, and port | Pending |
| RV-05 | P3 | Standardize Target response serialization across all endpoints | Pending |
| RV-06 | P2 | Fix frontend test setup to provide authentication context | Pending |
| RV-07 | P3 | Resolve Ruff findings in project environment | Pending |
| RV-08 | P3 | Adjust test temporary paths on Windows and verification info in README | Pending |

### RV-01 — Initial Baseline Automatically Trusted

**Evidence:** `backend/app/services/checks.py:257` sets `is_baseline=target.url_revision == 1`, and line 261 assigns status `OK` for the initial revision.

**Impact:** If a website is defaced prior to being registered as a target, the system stores the defaced content as a trusted baseline and reports `OK` without operator review. This represents an architectural risk upon initiating monitoring, even though this behavior was originally implemented deliberately.

**Action Items:**

- [ ] Store initial capture as a candidate (`is_baseline=False`) and set status to `Awaiting Baseline`.
- [ ] Update approval workflow to support the first revision lacking a baseline, transitioning to `OK` only upon successful approval.
- [ ] Update scheduler to apply candidate review hold conditions to all revisions, not just `url_revision > 1`.
- [ ] Verify UI displays candidate and approval actions when no baseline or check result exists yet.
- [ ] Retain candidate until reviewed, defining clear behavior for manual recapture.

**Acceptance Criteria:** A newly added target successfully captured must not show `OK` before approval; scheduler must not generate duplicate candidates every interval while awaiting review; after approval, subsequent checks compare accurately against the baseline; URL change workflows and assigned Operator permissions continue functioning correctly.

### RV-02 — Structural Detector Omits Event Handlers

**Evidence:** `backend/app/services/diff/structure.py:104` collects facts for specific element types but omits event attributes on general elements. An experiment adding `onclick="console.log(1)"` to a button with unmodified text yielded a structural score of `0.0`.

**Impact:** Code triggered by user interactions can be injected without altering page visuals or text, resulting in all three detectors reporting no change.

**Action Items:**

- [ ] Extract facts for event-handler attributes such as `onclick`, `onerror`, `onload`, hashing attribute values rather than embedding raw code in summaries.
- [ ] Detect JavaScript URLs in relevant attributes (e.g., `href="javascript:..."`) with defined normalization.
- [ ] Add unit test cases for addition, modification, and removal of event handlers where text/pixels remain identical.
- [ ] Evaluate false-positive impact and summary presentation before enabling.

**Acceptance Criteria:** Adding or modifying an executable attribute must yield a structural score > `0`; existing attributes must not trigger false positives; external domain allowlists must not automatically ignore event handlers.

### RV-03 — Capture Returns Success Following Blocked Late Navigation

**Evidence:** `backend/app/services/capture/capture.py:388` checks guard errors following `page.goto`, but does not re-check after `wait_page_ready` at line 407. Mocked navigation experiments during readiness confirmed `route.abort()` was invoked once, yet capture returned HTTP status `200`.

**Impact:** Navigation blocked or failing after initial document load may be masked by artifacts/status of the prior page, wrongly indicating a successful capture. (Note: this reflects an error propagation flaw, not a socket-level SSRF bypass).

**Action Items:**

- [ ] Consolidate `blocked_error`, `availability_error`, and `capture_error` evaluations into a reusable helper.
- [ ] Re-check errors following readiness and prior to returning capture results.
- [ ] Ensure final URL, HTTP status, and artifacts reference the identical navigation; if navigation occurs during artifact extraction, explicitly retry or reject.
- [ ] Add regression tests for late main-frame navigation triggering SSRF block, DNS failure, and upstream failure.
- [ ] Ensure rejected captures leave behind zero staging artifacts.

**Acceptance Criteria:** Blocked late main-frame navigation must not return success using prior page artifacts; errors are classified accurately; subresource/popup blocks must not unintentionally cause main-document failure.

### RV-04 — Origin Validation Ignores Port

**Evidence:** `backend/app/main.py:135` strips the port from Host and compares only hostname/scheme. Invoking `_is_trusted_origin` with origin `https://monitor.example:9999` and Host `monitor.example:3030` without matching allowlist entries returned `True`.

**Impact:** Origins sharing a hostname across different ports are treated as trusted, violating strict same-origin boundaries. (Note: While not yet verified as an exploitable bypass via CORS preflight or CSRF tokens, origin validation remains overly permissive).

**Action Items:**

- [ ] Compare scheme, hostname, and effective port completely, normalizing default HTTP/HTTPS ports.
- [ ] Support IPv6 hosts without naive `split(':')[0]`.
- [ ] Preserve correct external host/port from reverse proxy; adjust proxy headers alongside validation since Nginx currently forwards `$host` without public port.
- [ ] Trust forwarding headers only under defined proxy trust policy while preventing client header forgery.
- [ ] Add tests for port mismatches, default ports, explicit allowlists, IPv6, and production reverse proxy configurations.

**Acceptance Criteria:** Mismatched ports are rejected unless explicitly allowlisted; valid operator origins pass; CSRF token enforcement and production login/logout continue operating.

### RV-05 — Inconsistent Target Response Serialization

**Evidence:** `backend/app/api/routes/targets.py:242` returns ORM Target directly from PATCH, whereas GET uses `_target_read` at line 293. Testing `test_target_patch_rejects_null_required_fields_and_allows_omission` showed GET returns `assignees: []` while empty PATCH body returns `assignees: null`.

**Impact:** Response contracts vary across endpoints, potentially causing frontend cache corruption regarding assignees following mutations.

**Action Items:**

- [ ] Utilize consistent Target serialization across create/update/delete and read endpoints in accordance with user role permissions.
- [ ] Align route return types and response models with serialization output.
- [ ] Add assertions for targets with active assignments and prevent leaking assignees to unauthorized roles.

**Acceptance Criteria:** Empty PATCH body returns data identical to GET for the same user; mutation responses do not clear assignees; failing backend test passes.

### RV-06 — Frontend Test Setup Missing Authentication Context

**Evidence:** Frontend test suite had 47 passed and 25 failed out of 72 tests across 11 files; 3 files failed (`TargetListPage.test.tsx`, `TargetDetailPage.test.tsx`, and `TargetDetailPage.cache.test.tsx`), reporting `useAuth must be used within an AuthProvider`. Example setup at `frontend/src/pages/TargetDetailPage.test.tsx:190`.

**Impact:** Tests fail before reaching component behavior assertions, preventing verification of post-member-management workflows. (Note: production pages already wrap in AuthProvider).

**Action Items:**

- [ ] Create test render helper providing authentication context alongside QueryClient and Router.
- [ ] Supply Admin and Operator role fixtures corresponding to test scenarios.
- [ ] Update outdated mocks/expectations to match current hooks and UI.
- [ ] Test cache eviction on logout/user switch and permission/assignment changes.

**Acceptance Criteria:** Frontend test suite passes completely; tests verify actual role behaviors; no unhandled context errors or bypassed tests.

### RV-07 — Ruff Linter Findings

**Evidence:** Ruff within project virtual environment reported 5 errors across `app tests scripts alembic`:

| File | Issue |
| --- | --- |
| `backend/alembic/env.py` | I001: import order |
| `backend/alembic/versions/a5b6c7d8e9f0_tags.py` | I001: import order |
| `backend/alembic/versions/b7c8d9e0f1a2_nested_tags.py` | I001: import order |
| `backend/app/models/__init__.py` | I001: import order and E501: line length |

**Action Items:**

- [ ] Organize imports and split `__all__` per configuration without affecting migration semantics.
- [ ] Run Ruff using identical environment and versions locally and in CI.

**Acceptance Criteria:** Ruff passes clean; mypy passes; model registration and migrations operate smoothly.

### RV-08 — Windows Test Paths and README Verification

**Evidence:** Backend test suite full run had 199 passed / 8 failed out of 207 tests; 7 capture failures were caused by path length limits when writing artifacts to temporary paths on Windows. Re-running those 7 with `--basetemp=.audit-t` passed all 7, leaving only the contract failure in RV-05. Additionally, README outdated test counts indicated 123/61.

**Action Items:**

- [ ] Specify short temporary path for Windows verification or shorten fixture temp directory paths.
- [ ] Distinguish environment-specific failures from application bugs in test reporting.
- [ ] Update README to reference project environment commands and correct/remove outdated test counts.
- [ ] Execute Linux verification on target deployment environment and record fresh results post-remediation.

**Acceptance Criteria:** Tests do not fail due to Windows temporary path length; documentation accurately reflects verification commands and metrics.

## 3. Verification Results as of Review Date

| Item | Verified Result |
| --- | --- |
| Backend pytest (Full run) | 199 passed / 8 failed / 207 tests |
| Retry capture failures with short path | 7 passed / 11 deselected |
| Remaining backend failure | Target GET/PATCH response: `assignees []` vs `null` |
| Frontend Vitest | 47 passed / 25 failed / 72 tests; 8 files passed / 3 failed |
| Backend mypy in `.venv` | Passed across 55 source files |
| Backend Ruff in `.venv` | 5 errors |
| Frontend ESLint | Passed |
| Frontend production build | Passed |
| Linux deployment verification | Pending execution |

Note: Backend results above reflect an initial full run plus targeted retry, not a clean single run of 206 passing tests. Project virtual environment (`.venv`) is the authoritative environment.

## 4. Execution Order and Overall Acceptance

1. RV-01: Extend baseline approval to cover initial monitoring setup.
2. RV-02 & RV-03: Close detector gaps and ensure capture validity.
3. RV-04: Fix origin validation and reverse proxy configuration.
4. RV-05 & RV-06: Fix API contracts and restore functional test coverage.
5. RV-07 & RV-08: Standardize static checks and verification workflow.

- [ ] Add regression tests for RV-01 through RV-05 per criteria.
- [ ] Run backend suite cleanly in project virtual environment.
- [ ] Run frontend suite, lint, type-check/build, and backend Ruff/mypy.
- [ ] Verify Linux deployment: HTTPS login, baseline approval, scheduled capture, error classification, and Admin/Operator authorization.
- [ ] Document verified outcomes and remaining constraints before marking tasks complete.

## 5. Existing Security Controls to Preserve

The inspected code includes robust session/CSRF protection, Admin–Operator authorization, connection-time IP validation via SSRF proxy, and artifact path containment. Remediation must preserve these controls, including raw screenshot retention for audit evidence and retaining overlays without suppression during capture.
