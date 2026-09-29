# Refinement Record: CR10 Second Follow-up Remediation

**Date:** September 17, 2026  
**Plan:** [`plan/CR10-Second-Follow-up-Remediation-Plan-17-9-2026.md`](../../plan/CR10-Second-Follow-up-Remediation-Plan-17-9-2026.md)  
**Status:** **Implementation and automated verification complete; runtime checks assigned to Linux deployment**

## 1. Implemented Changes

### 1.1 Production HTTPS and session policy

- Production Compose now forces `ENVIRONMENT=production`, `SESSION_COOKIE_SECURE=true`, strict SameSite cookies, and `ROOT_PATH=/api`.
- Nginx uses TLS on container port 8443 and redirects HTTP port 8080 to the configured public HTTPS port.
- Certificates are mounted as read-only Compose secrets from `deploy/certs/fullchain.pem` and `deploy/certs/privkey.pem`.
- The backend port is no longer published to the host; all operator traffic goes through the TLS frontend and same-origin `/api` proxy.
- `CORS_ORIGINS` is derived from `PUBLIC_HOST` and `PUBLIC_HTTPS_PORT` in production Compose.
- FastAPI receives `/api` as its root path so generated Swagger/OpenAPI URLs work through the reverse proxy.

### 1.2 Container and browser isolation

- Added `backend/Dockerfile`; Python dependencies and application source are installed at image-build time instead of startup.
- Backend runs with a non-root UID/GID, read-only root filesystem, all Linux capabilities dropped, `no-new-privileges`, private `/tmp`, and a single worker.
- Production Chromium sandbox is enabled (`BROWSER_DISABLE_SANDBOX=false`).
- Removed `seccomp:unconfined`, `ipc: host`, the writable source-code mount, and direct host publication of port 8000.
- Only `/app/data` and `/tmp` are writable for the backend.
- Frontend uses `nginxinc/nginx-unprivileged`, a read-only root filesystem, all capabilities dropped, `no-new-privileges`, and tmpfs mounts for required runtime paths.

### 1.3 Test database isolation

- `backend/tests/conftest.py` sets `DATABASE_URL=sqlite:///:memory:` before importing application modules and disables the scheduler for tests.
- SQLite PRAGMA setup is exposed as `set_sqlite_pragmas` and applied to isolated test engines.
- `test_sqlite_foreign_keys_pragma` no longer imports or connects the application engine.
- Added a restricted-parent-delete foreign-key regression test.
- Full-suite verification confirmed that `backend/data/app.db` retained the same length (57,344 bytes) and UTC modification timestamp (`2026-09-17 04:16:47`), with no `app.db-wal` or `app.db-shm` created.

### 1.4 Capture lifecycle ownership

- `capture_snapshot` now owns a known staging directory for the entire coroutine lifecycle.
- Cleanup is controlled by an outer `try/finally`; success is recorded only after Playwright and `SsrfProxy` context managers exit and a `CaptureResult` is ready to return.
- Existing cleanup for write failure and browser-close cancellation remains active.
- Added a regression test that cancels during `SsrfProxy.__aexit__()` and verifies no staging artifacts remain.

### 1.5 Documentation

- README now documents TLS certificates, `PUBLIC_HOST`, non-root data ownership, HTTPS URLs, the HTTP redirect port, and the fact that the backend is not publicly exposed.
- The prior Phase 3 record no longer claims full production verification while Docker runtime checks remain pending.
- Certificate requirements and a temporary self-signed smoke-test procedure are documented under `deploy/certs/README.md`; certificate material is ignored by Git.

## 2. Verification Results

| Check | Result |
|---|---|
| Backend Pytest | **152 passed, 1 existing warning** |
| Frontend Vitest | **70 passed across 11 files** |
| Ruff | **Passed** |
| Mypy | **Passed — 47 source files** |
| TypeScript | **Passed** |
| Vite production build | **Passed — 1,494 modules** |
| `docker compose config` | **Passed** |
| Production DB isolation | **Passed — size/timestamp unchanged; no WAL/SHM files** |

The first full backend run used a long Windows pytest base path and produced five
`FileNotFoundError` failures when artifact filenames exceeded the Windows path
limit. Re-running with the short isolated base path `C:\ct2` passed all 152 tests.
This was a test-environment path-length issue, not an application failure.

## 3. Linux Deployment Validation

The target runtime is Linux. Local Docker Desktop validation on Windows was
explicitly waived and no production services were started on the Windows host.
Container behavior that depends on the Linux kernel, Chromium sandbox, file
ownership and TLS secrets must be checked during Linux deployment rather than
treated as a Windows acceptance requirement.

During Linux deployment, run these checks with trusted certificate files and a
temporary/isolated data directory before switching to the preserved production
data directory:

1. Build both images successfully.
2. Confirm the backend starts as non-root with Chromium sandbox enabled.
3. Confirm HTTP redirects to HTTPS and TLS certificate validation succeeds.
4. Confirm login, `/auth/me`, CSRF-protected mutation, logout, `/api/docs`, and SPA fallback through Nginx.
5. Confirm a smoke capture succeeds with read-only root filesystems and the restricted capability sets.
6. Confirm production `backend/data/app.db` is not used by integration tests.

No production database data, monitoring targets, baselines, check history, or
detector thresholds were intentionally modified by this remediation.
