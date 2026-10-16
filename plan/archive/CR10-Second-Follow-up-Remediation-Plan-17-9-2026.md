# CR10 Second Follow-up Remediation Plan

Date: September 17, 2026  
Status: Source code and automated verification implemented — Runtime validation pending on Linux target  
Scope: Production security, test isolation, capture cleanup, and documentation consistency

References:
- [Main CR10 Plan](Code-Review-and-Remediation-Plan-CR10-17-9-2026.md)
- [First Follow-up Plan](CR10-Follow-up-Remediation-Plan-17-9-2026.md)
- [Follow-up Execution Log](../refinement/17-9-2026/Code-Review-Remediation-CR10-FollowUp-17-9-2026.md)
- [Project Plan](PROJECT_PLAN.md)

## 1. Objectives

This plan addresses secondary review findings following the first CR10 follow-up. It focuses on enforcing production security policies, strictly isolating test runs from production databases, guaranteeing cleanup across the entire capture coroutine lifecycle, and aligning documentation statuses with verified evidence.

Execution results are documented in [`Code-Review-Remediation-CR10-SecondFollowUp-17-9-2026.md`](../refinement/17-9-2026/Code-Review-Remediation-CR10-SecondFollowUp-17-9-2026.md). Tasks 3.1–3.5 have been implemented at the source/configuration level. Docker runtime testing on Windows was omitted as Linux is the target deployment environment; image, TLS, authenticated routing, and sandbox smoke checks are designated for Linux deployment stages.

## 2. Invariants to Maintain

- Never delete, reset, re-stamp, or modify data in `backend/data/app.db` during development or automated testing.
- Preserve all existing monitoring targets, snapshots, baselines, and historical check results.
- Maintain the single API worker (`--workers 1`), SSRF guard, CSRF validation, authentication, and detector thresholds.
- Regression tests must utilize isolated databases, directories, and mock network fixtures.
- Never contact live target endpoints from automated test runs.
- Do not mark production as ready or verified until relevant runtime integration checks pass on Linux.

## 3. Action Items

### 3.1 [P1] Enforce Production Environment and Secure Session Cookies

Affected files:
- `docker-compose.yml`
- `backend/.env.example`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `README.md`
- Reverse proxy / TLS configurations

**Finding:** `docker-compose.yml` was labeled for production but omitted explicit `ENVIRONMENT=production` and `SESSION_COOKIE_SECURE=true`. Defaults remained in development mode with unencrypted cookies, bypassing the production startup security guard.

**Action Items:**
1. Explicitly specify `ENVIRONMENT=production` in production deployment configurations.
2. Enforce `SESSION_COOKIE_SECURE=true` in production mode.
3. Configure HTTPS/TLS endpoints via reverse proxy or ingress before enabling secure cookies.
4. Set CORS trusted origins matching operational HTTPS domains.
5. Clarify development vs. production configuration defaults.
6. Update README detailing URLs, TLS certificates, cookies, and startup prerequisites.

**Acceptance Criteria:**
- Production backend refuses startup if secure cookies are disabled.
- Web dashboard operates over HTTPS with login, `/auth/me`, API mutations, and logout routing cleanly via same-origin `/api`.
- Session cookies exhibit `Secure`, `HttpOnly`, `SameSite`, and `Path` attributes.
- HTTP traffic redirects to HTTPS or is disabled per deployment design.

### 3.2 [P1] Enable Browser Sandbox or Apply Compensating Isolation Controls

Affected files:
- `docker-compose.yml`
- Backend Dockerfile & image configs
- `backend/app/services/capture/capture.py`
- Deployment documentation

**Finding:** Production Compose configured `BROWSER_DISABLE_SANDBOX=true` and `seccomp:unconfined` without enforcing non-root users, read-only root filesystems, or network isolation. Because captured pages may contain malicious payloads, this configuration presents severe exposure without compensating controls.

**Action Items:**
1. Prioritize enabling the Chromium sandbox in production.
2. Execute processes as an unprivileged non-root user and drop unnecessary Linux capabilities.
3. Eliminate `seccomp:unconfined`, adopting strict profiles.
4. Mount root filesystems as read-only, permitting writes strictly to dedicated temporary/artifact volumes.
5. Restrict container network reachability so browser processes cannot directly access internal networks outside the monitored proxy.
6. Verify Playwright captures complete reliably under these constraints.

**Acceptance Criteria:**
- Chromium operates sandboxed or under comprehensive, tested compensating isolation controls.
- Containers run unprivileged without excess capabilities.
- Unrestricted host or internal network access from browser processes is prevented.
- Capture, SSRF, and smoke checks pass in the production container image.

### 3.3 [P1] Decouple Foreign-Key Test Harness from Production Storage

Affected files:
- `backend/tests/test_checks.py`
- `backend/tests/conftest.py`
- Test database fixtures
- `backend/app/db/session.py`

**Finding:** `test_sqlite_foreign_keys_pragma` directly connected to `app.db.session.engine`, which defaults to `backend/data/app.db`. Connecting triggered connection event listeners executing `PRAGMA journal_mode=WAL`, violating test database isolation.

**Action Items:**
1. Refactor PRAGMA tests to instantiate SQLite engines in temporary directories or in-memory.
2. Utilize identical PRAGMA initialization logic to test actual implementation behavior without connecting to the production engine.
3. Forbid imports or connections to `SessionLocal`/`engine` pointing to production storage inside tests.
4. Add assertion guards rejecting `DATABASE_URL` resolving to `backend/data/app.db` during test runs.
5. Add regression tests validating foreign key rejections and restricted deletions.

**Acceptance Criteria:**
- Executing backend pytest never touches, opens, or locks `backend/data/app.db`, `app.db-wal`, or `app.db-shm`.
- All test engines simulating production SQLite enforce `PRAGMA foreign_keys=1`.
- Invalid foreign keys and parent deletion attempts fail with `IntegrityError`.
- Test suites pass cleanly even if production database storage is absent or read-only.

### 3.4 [P2] End-to-End Staging Artifact Cleanup Through Coroutine Completion

Affected files:
- `backend/app/services/capture/capture.py`
- `backend/app/services/capture/ssrf_proxy.py`
- `backend/tests/test_capture.py`
- `backend/tests/test_concurrency.py`

**Finding:** Capture cleanup covered write failures and cancellations during `browser.close()`. However, if cancellation occurred while exiting Playwright or `SsrfProxy` async context managers, the coroutine aborted without returning `CaptureResult`, leaving staging directories uncollected.

**Action Items:**
1. Enclose the capture lifecycle in comprehensive `try/finally` blocks ensuring cleanup executes until `CaptureResult` is returned.
2. Mark capture operations successful strictly after all async context managers cleanly exit.
3. Automatically delete staging directories upon unhandled exceptions or `CancelledError` before results are delivered.
4. Propagate original `CancelledError` exceptions cleanly.
5. Verify in-flight reservations and target statuses are released upon timeout or cancellation.

**Acceptance Criteria:**
- Task cancellations during artifact generation, browser shutdown, Playwright exit, or proxy exit leave zero orphaned staging directories.
- Successful captures preserve staging directories for caller promotion or discard.
- `CancelledError` propagates without transformation into internal errors.

### 3.5 [P3] Synchronize Status Documentation with Verification Realities

Affected files:
- `refinement/17-9-2026/Code-Review-Remediation-CR10-FollowUp-17-9-2026.md`
- `refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md`
- `UPDATE_SUMMARY.md`
- `README.md`

**Finding:** Follow-up logs stated Docker validation was pending, whereas Phase 3 claimed CR10 was 100% verified. Furthermore, Follow-up items 2–3 were marked Completed despite test isolation and full capture cleanup remaining incomplete.

**Action Items:**
1. Adjust item statuses to reflect outstanding runtime verification.
2. Avoid claiming production storage is "untouched" until test harnesses are verified decoupled.
3. Explicitly distinguish between code implementation, automated testing, and live runtime deployment verification.
4. Record Docker/TLS/Nginx validation results following actual Linux deployment runs.

**Acceptance Criteria:**
- All tracking documents reflect consistent status for each CR10 deliverable.
- No document asserts full verification without supporting runtime evidence.

## 4. Execution Order

1. Decouple test database engines per Item 3.3.
2. Complete capture lifecycle cleanup and regression tests per Item 3.4.
3. Finalize production HTTPS and session configuration per Item 3.1.
4. Configure browser container isolation per Item 3.2.
5. Run automated test suites in isolated test environments.
6. Validate Docker Compose, TLS, Nginx routing, and smoke capture on target deployment hosts.
7. Update documentation per Item 3.5.

## 5. Verification Matrix

| Area | Required Validation |
|---|---|
| Database Isolation | Full backend suite runs while production database path is read-only or deleted |
| Foreign Keys | Enforced PRAGMA, invalid insert rejections, and restricted deletes on test SQLite engines |
| Capture Cleanup | Verified clean on write failures, browser cancellations, context exits, and timeouts |
| Code Quality | Pytest, Ruff, and Mypy passing clean |
| Frontend Quality | Vitest, TypeScript typecheck, and production build passing |
| Container Security | Non-root users, seccomp enforcement, health checks, and smoke capture |
| HTTPS & Auth | Secure cookie flags, login, `/auth/me`, CSRF validation, and logout |
| Routing | HTML5 history fallback, static asset caching, and `/api` reverse proxy routing |
| Data Integrity | Target, snapshot, baseline, and check counts preserved across validation runs |

## 6. Closure Conditions

This plan is considered closed once all P1 and P2 items satisfy acceptance criteria, tests are decoupled from production storage, runtime integration passes on Linux, and all CR10 documentation aligns with verified results.
