# Refinement Record: Code Review Remediation CR10 — Follow-up Hardening

**Date:** September 17, 2026  
**Document Name:** `Code-Review-Remediation-CR10-FollowUp-17-9-2026.md`  
**Authoritative Plan Reference:** [`plan/CR10-Follow-up-Remediation-Plan-17-9-2026.md`](../../plan/CR10-Follow-up-Remediation-Plan-17-9-2026.md)  
**Parent Plan:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Target Environment:** Ubuntu Server / Docker Compose Deployment (`10.117.10.68`)  
**Operational Status:** **Stage 2 (Hardening Implemented / Runtime Validation Assigned to Linux Deployment)**  

---

## 1. Scope & Follow-up Items

This refinement record details the implementation and verification of the five follow-up remediation items identified during the CR10 post-review assessment:

| Item | Priority | Component / File | Description | Status |
|---|---|---|---|---|
| **Item 1** | **P1 (High)** | `backend/app/services/checks.py` | Transaction ordering in `run_target_check`: flush `Snapshot` before constructing `CheckResult` under active foreign keys; rollback session & clean promoted files if commit fails. | **Completed & Verified** |
| **Item 2** | **P1 (High)** | `backend/tests/conftest.py`, `backend/tests/test_checks.py` | Attach `PRAGMA foreign_keys = ON` listener to `Engine` across all SQLite test sessions; add regression tests for referential integrity & orphan cleanup. | **Completed & Verified** |
| **Item 3** | **P2 (Medium)** | `backend/app/services/capture/capture.py`, `backend/tests/test_capture.py` | Self-cleanup of staging directories in `capture_snapshot` on task cancellation or write failure before returning `CaptureResult`. | **Completed & Verified** |
| **Item 4** | **P3 (Low)** | `frontend/Dockerfile`, `frontend/nginx.conf`, `docker-compose.yml`, `docker-compose.dev.yml` | Production container configuration: static frontend, HTTPS reverse proxy, secure backend image, removal of `--reload` in production compose, and separate dev compose. | **Implemented; runtime checks assigned to Linux deployment** |
| **Item 5** | **P2 (Medium)** | `refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md`, `UPDATE_SUMMARY.md` | Realign item numbering (CR10-08 to CR10-12) and correct migration filename to `d2b3c4e5f6a7_structural_detector.py`. | **Completed & Verified** |

### Strict Operational Invariants Preserved
- **Zero Production Data Loss**: `backend/data/app.db` remains 100% intact. Both monitoring targets (*Bangkok Chain Hospital* and *World Medical Hospital TH*) remain active and operational with zero database resets or data loss.
- **Single Worker Process Concurrency**: Single API worker architecture (`--workers 1`) and in-flight mutex locks are preserved.
- **Fail-Closed Security & Threshold Invariants**: SSRF guard, CSRF checks, session cookie authentication, and change thresholds remain strictly enforced.

---

## 2. Technical Implementation Summary

### 2.1 Item 1: Transaction Ordering & Rollback Cleanup in `run_target_check`
- **Root Cause**: In `backend/app/services/checks.py`, when a check detected differences, `snapshot` was added to the session, but `snapshot.id` was referenced to construct `CheckResult` before `db.flush()`. Under SQLite `PRAGMA foreign_keys=ON`, inserting or committing `CheckResult` before `Snapshot` exists in the database could violate foreign keys or record `current_snapshot_id=None`. Furthermore, if `db.commit()` failed after promoting files, calling `db.commit()` in the `except Exception` block without `db.rollback()` caused `PendingRollbackError` and left promoted permanent files orphaned on disk.
- **Modifications**:
  - In `backend/app/services/checks.py`:
    - Added `_cleanup_promoted_files(*paths: str | None)` helper to remove promoted permanent files upon failure.
    - Tracked `perm_screenshot`, `perm_text`, `perm_html` at top of `run_target_check`.
    - Added explicit `db.flush()` after `db.add(snapshot)` and before `CheckResult` creation.
    - Updated `except Exception as exc:` to execute `db.rollback()` first, remove any promoted permanent files or discard staging files, re-fetch/update `target.last_error` on the clean session, and commit the status transition safely.

### 2.2 Item 2: Test Foreign Key Enforcement & Regression Tests
- **Modifications**:
  - In `backend/tests/conftest.py`:
    - Registered `@event.listens_for(Engine, "connect")` with `PRAGMA foreign_keys=ON` for all SQLite connections opened during tests.
  - In `backend/tests/test_checks.py`:
    - Added `test_run_target_check_foreign_key_ordering_on_change`: verifies that a changed check persists `Snapshot` and `CheckResult` in correct foreign key order and both snapshot IDs exist in the database.
    - Added `test_check_result_foreign_key_violation_on_invalid_snapshot_id`: verifies that invalid snapshot foreign keys raise `IntegrityError`.
    - Added `test_run_target_check_rollback_and_promoted_files_cleanup_on_commit_error`: verifies that simulated commit failure rolls back transaction, sets target status to `Failed`, and unlinks promoted permanent files (0 orphan files left).

### 2.3 Item 3: Capture Staging Self-Cleanup
- **Modifications**:
  - In `backend/app/services/capture/capture.py`:
    - Added `import shutil`.
    - Tracked `staging_dir: Path | None = None` and `capture_succeeded = False` in `capture_snapshot`.
    - Wrapped `browser.close()` in an inner `finally:` block:
      ```python
      finally:
          try:
              await browser.close()
          finally:
              if not capture_succeeded and staging_dir and staging_dir.exists():
                  shutil.rmtree(staging_dir, ignore_errors=True)
      ```
    - Set `capture_succeeded = True` only after all staging files (screenshot, text, html) are successfully written.
    - Added explicit cleanup when `browser.close()` raises or the task is cancelled, including the case where artifact writes completed but no `CaptureResult` can be returned.
  - In `backend/tests/test_capture.py`:
    - Added `test_capture_snapshot_cleans_staging_on_failure_during_write`: verifies that staging directory is completely removed if an exception occurs during artifact writing.

### 2.4 Item 4: Production Containerization & Dev Compose Profile
- **Modifications**:
  - Created `frontend/Dockerfile`: Multi-stage Dockerfile (Stage 1: `node:20-slim` runs `npm ci` and `npm run build`; Stage 2: `nginx:alpine` serves static files on port 80).
  - Created `frontend/nginx.conf`: Nginx server configuration with gzip compression, 1-year immutable caching for static assets, SPA client-side fallback (`try_files $uri $uri/ /index.html`), and `/api/` reverse proxy to backend.
  - Created `frontend/.dockerignore`: Prevents `node_modules`, `dist`, `.env`, and git history from polluting build context.
  - Updated `docker-compose.yml`: Configured for production deployment by removing `--reload --reload-dir app` from backend (maintaining `--workers 1`), and building frontend using `frontend/Dockerfile` on port `3030:80`.
  - Created `docker-compose.dev.yml`: Dedicated development compose file maintaining live hot-reloading (`--reload --reload-dir app` and `node:20-slim npm run dev` on port `3030:5173`).
  - Updated `README.md`: Documented production vs development compose usage.
  - Updated the frontend API default to same-origin `/api`; production no longer depends on a runtime `frontend/.env`, which cannot modify an already-built Vite bundle.
  - Updated Nginx `proxy_pass` to strip `/api/` before forwarding because FastAPI routes are registered at `/targets`, `/snapshots`, `/auth`, and other root paths.

### 2.5 Item 5: Documentation Realignment
- **Modifications**:
  - Updated `refinement/17-9-2026/Code-Review-Remediation-CR10-Phase3-17-9-2026.md` table and section headers:
    - CR10-08: Production Database Alembic Migration Version Initialization (`d2b3c4e5f6a7_structural_detector.py`)
    - CR10-09: Triage Action Guards and User-Facing Error Banner
    - CR10-10: Manual "Check Now" Button on Target Detail Page Header & Cache Invalidation
  - Updated `UPDATE_SUMMARY.md` with complete details of all follow-up remediations.

---

## 3. Verification & Test Execution Results

### 3.1 Backend Test Suite (Pytest)
- **Command**: `pytest`
- **Result after post-review corrections**: **149 passed, 1 warning** with zero failures.

### 3.2 Frontend Test Suite (Vitest)
- **Command**: `vitest run`
- **Result**: **70 passed (11 test files)**.

### 3.3 Static Analysis & Production Build
- **Ruff**: `All checks passed!`
- **Mypy**: `Success: no issues found in 47 source files`
- **Vite Build**: Compiled with zero errors (`dist/assets/index-Di9mWx_A.js` [294.25 kB], `dist/assets/index-CNU5fAno.css` [34.81 kB]).

### 3.4 Compose and Container Validation
- `docker compose config`: Passed; production frontend publishes `3030:80`, backend remains single-worker, and the frontend has no runtime `env_file` dependency.
- Windows Docker runtime testing was waived because the deployment target is Linux. Image build and live Nginx-to-FastAPI checks are Linux deployment steps.

### 3.5 Production Database Integrity Verification
- SQLite database `backend/data/app.db`:
  - `alembic_version`: `('d2b3c4e5f6a7',)`
  - Active targets count: `2`
    - `Bangkok Chain Hospital` (`84300ac1-1f23-42cb-af6f-b39d6f0d892e`)
    - `World Medical Hospital TH` (`441a36ef-6b4e-41b2-b3a1-eff7c0dc389c`)
  - Referential integrity: Valid, foreign keys enforced, zero data corruption or data loss.

---

## 4. Post-Review Corrections

The first review of this Follow-up record found four gaps. The implementation was corrected as follows:

1. **Production API URL**: `frontend/src/api/client.ts` now defaults to `/api`. The production Docker build excludes `.env`, so the generated application uses the same host and port from which it was loaded. Development can still override the URL through `frontend/.env`.
2. **Nginx route mapping**: `frontend/nginx.conf` now forwards `/api/<path>` to `http://backend:8000/<path>`, matching the actual FastAPI route layout.
3. **Post-commit artifact safety**: `run_target_check` now distinguishes promoted artifacts from committed artifacts. Refresh failures after a successful commit are logged without deleting files or attempting an invalid `OK -> Failed`/`Changed -> Failed` transition. Regression coverage verifies that the committed Snapshot and all three artifacts remain present.
4. **Cancellation during browser shutdown**: `capture_snapshot` now catches `BaseException` from `browser.close()`, deletes the staging directory, and re-raises cancellation or shutdown failure. Regression coverage simulates `CancelledError` during browser close and verifies that staging is empty.

### Verification added for these corrections
- `test_run_target_check_keeps_committed_artifacts_when_refresh_fails`
- `test_capture_snapshot_cleans_staging_when_browser_close_is_cancelled`
- Targeted backend regression checks: 5 passed.
- Frontend API client checks: 4 passed.
- Full backend suite: 149 passed, 1 existing passlib/argon2 deprecation warning.
- Full frontend suite: 70 passed across 11 files.
- Ruff, Mypy, TypeScript and Vite production build: passed.

The second follow-up isolated the application engine during tests. A full suite
run preserved the production database file length and UTC modification timestamp,
and did not create `app.db-wal` or `app.db-shm`. Runtime container validation is
recorded separately in the second follow-up document.
