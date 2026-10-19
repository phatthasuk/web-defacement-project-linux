# Review Security — 14-10-2026

> October 19 source reconciliation: transfer/render budgets, Compose resource limits and actor-attributed audit exist. Statements below that these are absent are historical. Full container acceptance, form policy/owner association and report-specific follow-ups remain open; no finding is closed by this update.
> See [current implementation, test/runtime status and open backlog](ROADMAP_STATUS_AND_BACKLOG.md).

Review Date: October 14, 2026 (Asia/Bangkok)  
Project: Web Defacement Monitoring System  
Status: Audit report and remediation proposals — **partially addressed in source code (see Section 7), but not yet deployed or validated on real Linux/container environments; no finding is considered closed.**  
Latest Remediation Update: October 14, 2026 (Asia/Bangkok)

> Sections 1–6 represent the original report as written during the audit. Section 7 was added to record subsequent implementation actions, outstanding tasks, and engineering rationale.

## 1. Scope and Limitations

Reviewed the current codebase across backend, frontend, and deployment configurations, focusing on authentication, authorization, CSRF, SSRF, the capture pipeline, structural detection, and security audit trails, alongside external vulnerability advisory reviews for associated dependencies.

- This folder lacks Git metadata; reviews evaluated existing files directly rather than commit diffs.
- Python package versions were inspected from the project `.venv`; versions deployed in actual Linux production have not been verified.
- Chromium 130.0.6723.31 was identified in the Playwright 1.48.0 browser manifest; the production Dockerfile uses a corresponding base image, but container binaries in active deployments have not been inspected.
- No production attack simulations, browser exploit attempts, out-of-memory (OOM) stress tests, or DoS load tests were conducted.
- Full vulnerability scanning across all Python dependencies, OS packages, and container images was not performed.
- Detector findings indicate gaps in spotting malicious behavior rather than proof of a system intrusion or SSRF bypass.
- Severity classifications reflect project-specific risk assessments rather than raw CVSS scores.

## 2. Summary of Findings

Identified 2 High and 5 Medium severity issues requiring remediation:

| ID | Severity | Issue | Evidence / Status |
| --- | --- | --- | --- |
| SEC-01 | High | Outdated capture browser | Verified via version manifest and Dockerfile; compared against Chromium security releases |
| SEC-02 | High | Starlette FileResponse Range header DoS vulnerability | Version falls within affected range; screenshot routes use FileResponse; verified via bounded parser test |
| SEC-03 | Medium | Unchecked HTTP/HTTPS formaction destinations | Confirmed via offline Chromium probe |
| SEC-04 | Medium | Tab-embedded javascript: URLs evade detector | Confirmed via offline Chromium probe |
| SEC-05 | Medium | Script transition from inert to executable leaves facts identical | Confirmed via offline Chromium probe |
| SEC-06 | Medium | Artifact limits enforced post-allocation; missing container resource constraints | Observed in code/config; OOM test not yet executed |
| SEC-07 | Medium | Baseline/review mutations lack actor audit trails | Observed in route handlers and service code |

Recommended remediation order: Browser → FastAPI/Starlette → Resource Limits → Detectors → Audit Trail.

## 3. Findings

### SEC-01 — Outdated Chromium Capture Browser

**Location:** `backend/Dockerfile:1`, `backend/requirements.txt:7`

The Dockerfile specifies `mcr.microsoft.com/playwright/python:v1.48.0-noble` and requirements pin `playwright==1.48.0`, with the package manifest referencing Chromium `130.0.6723.31`. Because the service navigates to and evaluates JavaScript on untrusted websites, the browser engine represents a direct attack surface.

The pinned version predates numerous critical security patches. For example, Chrome 131.0.6778.108 resolved CVE-2024-12053 (High: Type Confusion in V8). This highlights the urgent necessity of upgrading the browser runtime (though not proving an active exploit on this application).

**Impact:** Malicious target pages could compromise an unpatched browser engine. The potential impact on the host system or API depends on container and sandbox isolation; container escapes or remote code execution have not been demonstrated in this system.

**Recommendations:**

- [ ] Update Playwright and its container base image to a supported version containing current security fixes.
- [ ] Verify the installed browser binary version within the live deployed container.
- [ ] Maintain Chromium sandboxing and unprivileged runtime; do not deploy development Compose files to production.
- [ ] Isolate the capture worker from API and database services to restrict lateral movement if the browser is compromised.
- [ ] Validate capture execution, SSRF proxy routing, redirects, WebSocket blocking, and sandboxing on Linux post-upgrade.

**Acceptance Criteria:** Package, container image, and browser binaries are synchronized with no unresolved advisories; capture and SSRF regression suites pass on the target deployment platform.

**Reference:** [Chrome Stable Channel Update — Dec 3, 2024](https://chromereleases.googleblog.com/2024/12/stable-channel-update-for-desktop.html)

### SEC-02 — Starlette FileResponse DoS via Crafted Range Headers

**Location:** `backend/requirements.txt:1`, `backend/app/api/routes/snapshots.py:61`, `backend/app/api/routes/snapshots.py:77`

The virtual environment utilizes FastAPI 0.115.5 and Starlette 0.41.3. FastAPI specifies `starlette>=0.40.0,<0.42.0`, requiring coordinated version upgrades.

Starlette 0.41.3 is affected by CVE-2025-62727 / GHSA-7f5h-v6xp-fcq8, involving quadratic algorithmic complexity during `FileResponse` Range header parsing and merging. Screenshot endpoints utilize `FileResponse`, exposing this code path.

**Project Context:** Exploitation requires an authenticated session with access to the target snapshot, differing from generic public file-serving scenarios.

Offline testing of the parser in an isolated process with bounded range headers yielded:

| Range Count | Header Size | Measured Processing Time |
| --- | --- | --- |
| 500 | 3,895 bytes | 5.56 ms |
| 1,000 | 8,895 bytes | 20.34 ms |
| 2,000 | 18,895 bytes | 82.95 ms |

The quadratic increase mirrors the vulnerability description. Note that upstream reverse proxies (e.g., Nginx) may reject excessively large headers before reaching the application.

**Impact:** Authorized users could submit crafted Range requests to induce high CPU consumption, degrading backend availability in single-worker deployments.

**Recommendations:**

- [ ] Upgrade FastAPI and Starlette to patched versions; official patches begin in Starlette 0.49.1.
- [ ] In the interim, reject or strip multi-range requests at the reverse proxy if unused by clients.
- [ ] Verify screenshot endpoint behavior across single-range, multi-range, and malformed requests post-fix.

**Acceptance Criteria:** Runtime versions fall outside affected ranges, dependency constraints are satisfied, and crafted headers do not trigger exponential parsing overhead.

**Reference:** [Starlette Security Advisory GHSA-7f5h-v6xp-fcq8](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8)

### SEC-03 — Undetected Form Submission Target Modification via `formaction`

**Location:** `backend/app/services/diff/structure.py:114`, `:142`

The structural parser records `form.action` but ignores HTTP/HTTPS `button.formaction` and `input.formaction` attributes that override form endpoints. The inclusion of `formaction` in executable attributes only evaluated entries prefixed with `javascript:`.

**Evidence:** An offline Chromium probe changed the effective submission endpoint from `https://example.com/save` to `https://collector.example/save`. Visible text and screenshot bytes remained identical, resulting in a structural change score of 0.0.

**Impact:** Exfiltration of submitted form data to third-party endpoints could evade detection if no visual or text changes occur.

**Recommendations:**

- [ ] Extract facts for `formaction` on buttons and inputs, resolving relative URLs against the document base.
- [ ] Define explicit allowed domain policies for form targets.
- [ ] Add regression tests covering addition, modification, and deletion of formaction attributes.

**Acceptance Criteria:** Unauthorized modification of form submission endpoints triggers a Changed status even when visual and text comparisons show 0% change.

### SEC-04 — Tab-Embedded JavaScript URLs Evade Detection

**Location:** `backend/app/services/diff/structure.py:114`

Evaluating `value.lstrip().lower().startswith('javascript:')` fails to account for browser handling of embedded ASCII tabs and newlines within the scheme name (e.g., `href="java&#9;script:void(window.auditProbe=1)"`).

**Evidence:** An offline Chromium probe clicked a link containing embedded tabs in its scheme; `window.auditProbe` was set to 1 while visible text, PNG screenshots, and structural scores remained unchanged at 0.0.

**Impact:** Injected executable JavaScript URLs could evade monitoring alerts.

**Recommendations:**

- [ ] Normalize ASCII tabs, LF, and CR characters before classifying URL schemes.
- [ ] Preserve the original script body semantics after classification.
- [ ] Add test cases for control characters, HTML entities, and mixed casing.
- [ ] Prevent domain allowlists from ignoring executable URLs.

**Acceptance Criteria:** Any URL parsed by browsers as JavaScript is recorded as an executable fact, reliably raising alerts upon introduction.

### SEC-05 — Script Transition from Inert to Executable Yields Identical Facts

**Location:** `backend/app/services/diff/structure.py:124`, `:252`

The parser hashes inline script bodies without evaluating the script `type` attribute or distinguishing inert from executable scripts. Transitioning `<script type="text/plain">` to `<script type="text/javascript">` preserves the identical hash.

**Evidence:** An offline Chromium probe confirmed that baseline left script content dormant, whereas current executed the script (`window.auditProbe = 1`), with structural score remaining 0.0.

**Impact:** Enabling pre-existing dormant code does not trigger change alerts. External scripts similarly lacked type tracking.

**Recommendations:**

- [ ] Record normalized script type and executable classification for both inline and external scripts.
- [ ] Add tests for transitions between inert and classic/module scripts.
- [ ] Do not drop inert script content without tracking classification changes.

**Acceptance Criteria:** Changing the execution capability of a script produces distinct structural facts, triggering alerts regardless of body consistency.

*(Note: SEC-03 through SEC-05 correspond directly to findings R2-01 through R2-03 in `Review Round 2 By GPT 6.1 Sol 14-10-2026.md`)*.

### SEC-06 — Artifact Resource Budgets Lack Early Allocation Controls

**Location:** `backend/app/services/capture/capture.py:281`, `:433`, `:446`, `docker-compose.yml`

Capture invokes `route.fetch(max_redirects=0)` prior to inspecting DOM size and produces full-page screenshots before checking the encoded PNG file size. The `MAX_ARTIFACT_SIZE_MB` threshold does not restrict in-flight network bytes or decoded bitmap memory allocation.

Playwright retains response buffers in memory until disposal. Furthermore, production Compose lacks memory, CPU, or PID limits.

**Impact:** A hostile target could consume substantial memory through massive responses, oversized DOM trees, or extreme image dimensions before being rejected, risking process crashes or denial of service.

**Recommendations:**

- [ ] Enforce streaming byte limits and aggregate transfer budgets during transmission.
- [ ] Enforce upper bounds on full-page screenshot dimensions and total pixels.
- [ ] Configure container memory, CPU, and PID limits.
- [ ] Isolate capture workers from the API backend.
- [ ] Ensure clean teardown of browser contexts and staging directories upon cancellation.

**Acceptance Criteria:** Over-budget pages are rejected within bounded memory limits without degrading API availability.

### SEC-07 — Missing Actor Attribution in Review and Baseline Auditing

**Location:** `backend/app/api/routes/review.py:19`, `backend/app/services/review.py:25`, `backend/app/api/routes/targets.py` (`demote_target_baseline`)

While endpoints verify user session and target permissions, operations including baseline approval, check acknowledgement, defacement confirmation, and baseline demotion did not record the responsible actor in an audit trail.

**Impact:** If a compromised baseline is approved or incident status modified, forensic attribution cannot determine which operator performed the action.

**Recommendations:**

- [ ] Pass the authenticated actor to mutation services and record structured audit events in the same database transaction.
- [ ] Log actor identity, timestamp, action name, target/snapshot/check IDs, and before-and-after states.
- [ ] Record automated baseline cap demotions with source indicators.
- [ ] Define retention periods and restrict audit viewing to administrators.

**Acceptance Criteria:** Every review and baseline state change logs an immutable audit event linking the actor and affected entities; failed transactions roll back cleanly without phantom logs.

## 4. Existing Controls

Inspection identified key pre-existing security controls:

- Argon2 password hashing with brute-force account lockout.
- Cryptographically random session tokens with hashed database storage.
- HttpOnly session cookies; production Compose specifies Secure and SameSite Strict.
- Synchronizer CSRF tokens enforced on state-changing API mutations.
- Role-based access control separating Admin and Operator roles.
- Path traversal validation ensuring snapshot files remain within designated data directories.
- SSRF proxy resolving and verifying destination IPs at connection time to prevent DNS rebinding.
- Default blocking of service workers and WebSockets during capture.
- Production Compose with non-root user, read-only root filesystem, dropped capabilities, and custom seccomp.
- Unexposed backend host ports, routing exclusively through reverse proxy.
- Mandatory baseline review for initial URLs and revisions before monitoring begins.

## 5. Review Verification Results

| Evaluation | Outcome |
| --- | --- |
| Backend security & API regression subset | 71 passed, 105 warnings, 43.61s |
| Offline Chromium detector probes | Confirmed SEC-03, SEC-04, and SEC-05 |
| Bounded Starlette Range parser test | Confirmed quadratic scaling per SEC-02 |
| Frontend npm audit | 0 vulnerabilities across 411 dependencies |
| Full Python/container vulnerability scan | Pending |
| Linux production verification / load test | Pending |

The regression subset evaluated `test_auth.py`, `test_member_management.py`, `test_ssrf_guard.py`, `test_ssrf_proxy.py`, and `test_api_routes.py`. Note that `conftest.py` disables the SlowAPI limiter in test harnesses, so rate-limiting efficacy under concurrent load requires dedicated staging tests.

### Reproduction Commands

Execute from `backend/` in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_member_management.py tests/test_ssrf_guard.py tests/test_ssrf_proxy.py tests/test_api_routes.py -q --basetemp=.security-audit-rerun -p no:cacheprovider

$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/audit_round2_probe.py
```

Execute from `frontend/`:

```powershell
npm.cmd audit --json
```

## 6. Related Documentation

- [Audit Round 2 — October 14, 2026](Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Review By GPT 6.1 Sol 14-10-2026](archive/implemented-20261019/Review%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Project Plan](PROJECT_PLAN.md)
- [Member Management Plan](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md)

---

## 7. Remediation Status (Updated October 14, 2026)

This section documents code remediations applied following the audit. Results reflect Windows development testing and have not yet been validated on Linux production.

**Summary:** Source-level fixes for all 7 items have been applied to the extent possible on local workstations. No finding is considered fully closed until acceptance criteria are proven on target deployment environments.

### 7.1 Status Summary Table

| ID | Status | Completed Actions | Pending Verification |
| --- | --- | --- | --- |
| SEC-01 | Addressed in source | Upgraded Playwright package and image tag | Inspect container binary, verify seccomp/sandbox on Linux, isolate capture worker |
| SEC-02 | Partially mitigated | Upgraded FastAPI/Starlette; stripped `Range` headers on screenshot routes | Verify upstream patch details and Linux behavior |
| SEC-03 | Addressed in source | Extracted `formaction` on submit controls | Configurable allowed domains for formaction; form owner association |
| SEC-04 | Addressed in source | Normalized control characters and tabs in URL schemes | — |
| SEC-05 | Addressed in source | Implemented HTML5-compliant script classification | — |
| SEC-06 | Addressed in source | Implemented byte transfer limits, pixel/height limits, and DOM node caps | Configure container cgroups; isolate capture worker |
| SEC-07 | Addressed in source | Recorded review/baseline mutations in `member_audit_events` | Frontend log inspection UI, retention policy |

### 7.2 Implemented Changes

**SEC-01 & SEC-02 (Dependencies and Routes)**
- `backend/requirements.txt`: FastAPI upgraded to 0.128.8, Starlette pinned to 0.52.1, Playwright upgraded to 1.63.0 (manifest referencing Chromium 153.0.8010.12).
- `backend/Dockerfile` & `docker-compose.dev.yml`: Updated to `mcr.microsoft.com/playwright/python:v1.63.0-noble`.
- `backend/app/api/routes/snapshots.py`: Implemented `WholeFileResponse`, stripping `Range`/`If-Range` headers and emitting `Accept-Ranges: none` on screenshot endpoints.
- `backend/tests/test_api_routes.py`: Added tests asserting single-range, 2,000-range, and malformed range requests return full 200 responses.

**SEC-03 to SEC-05 (Structural Detector)**
- Recorded `formaction:<URL>` on submit-capable buttons and inputs, resolving relative URLs against base URL.
- Normalized URLs prior to scheme detection, stripping whitespace and control characters across literal, entity, and mixed-case representations.
- Implemented strict script classification distinguishing `classic`, `module`, `importmap`, `speculationrules`, and `inert`.
- `backend/tests/test_structure.py`: Added 12 regression tests. No database migration was required as diffs are computed on-the-fly.

**SEC-06 (Capture Budgets)**
- `ssrf_proxy.py`: Tracks aggregate transfer bytes in real-time, severing connections if transfer limits are exceeded.
- `capture.py`: Inspects DOM node count, layout dimensions, and pixel counts via CDP metrics (`Page.getLayoutMetrics`, `Memory.getDOMCounters`) before extracting full-page captures.
- `config.py`: Added `MAX_CAPTURE_TRANSFER_MB=100`, `MAX_SCREENSHOT_HEIGHT_PX=30000`, `MAX_SCREENSHOT_PIXELS=64000000`, and `MAX_DOM_NODES=300000`.
- Added `CaptureBudgetExceeded` error and verified via `tests/test_capture_budgets.py`.

**SEC-07 (Audit Logging)**
- `backend/app/services/audit.py`: Reused `member_audit_events` table to record `baseline.approved`, `check.acknowledged`, `check.defacement_confirmed`, and `baseline.demoted` alongside actor IDs.
- Added `GET /audit-events` endpoint restricted to Admins for query and pagination.

### 7.3 Post-Fix Verification

| Test Run | Result |
| --- | --- |
| Pre-fix test suite | 218 passed |
| Post-dependency & Range update | 219 passed |
| Post-detector enhancements | 230 passed |
| Post-SEC-06 & SEC-07 fixes | **244 passed** |
| Ruff & Mypy (`app`) | Passed across 58 source files |
| Offline Chromium probe (v153) | Detects formaction (0.5), script-type (1.0), and javascript-tab (1.0) with zero visual/text differences |

### 7.4 Outstanding Items and Rationale

- Container Image Validation: Could not inspect Docker daemon on Linux host due to `/var/run/docker.sock` permission restrictions.
- Seccomp Comparison: Project profile contains additional syscall rules compared to upstream Playwright 1.63 profile; requires testing inside container before updating.
- Worker Separation: Separating browser processes from the API requires substantial architectural refactoring (queues, inter-process communication) and is scheduled for subsequent phases.
- Container Resource Limits: `docker-compose.yml` does not specify cgroup CPU/memory/PID limits; requires benchmark tuning on production Linux hardware.

### 7.5 Pre-Deployment Requirements

1. Manually review screenshot shifts resulting from Chromium 153 on staging prior to production deployment.
2. Complete verification inside real Linux containers with seccomp and sandboxing enabled.
3. Configure container cgroup resource limits in production Compose files.

### 7.6 Verification Update (Oct 15, 2026, Asia/Bangkok)

Evaluated on Linux host (`7.0.0-30-generic` x86_64, Python 3.12.3). Automated tests for SSRF guard, Range mitigation, and capture budgets passed cleanly. Full production container verification remains blocked pending elevated Docker daemon socket access.
