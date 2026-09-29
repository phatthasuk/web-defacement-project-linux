# Linux Environment Code Sync & Preservation Summary

**Date:** September 8, 2026  
**Target Environment:** `Web Defacement Project Linux` (Ubuntu Server / Docker Compose Deployment)  
**Server IP:** `10.117.10.68`  
**Frontend URL:** `http://10.117.10.68:3030`  
**Backend API URL:** `http://10.117.10.68:8000`  

---

## 1. Preserved Artifacts & Configurations (สิ่งที่คงไว้ ไม่ถูกเปลี่ยนแปลง)

To preserve the ongoing live soak test metrics, active targets, and production network configurations, the following items were strictly kept intact:

1. **Production Database & Historical Artifacts (`backend/data/`):**
   - **`backend/data/app.db`**: Live SQLite database containing **2 active targets** (Bangkok Chain Hospital & World Medical Hospital TH), **47 snapshots**, and **45 check results**.
   - **`backend/data/screenshots/`**: 52 full-page screenshot captures.
   - **`backend/data/html/`** & **`backend/data/text/`**: Captured DOM and text comparison assets.
2. **Container & Deployment Configuration (`docker-compose.yml`):**
   - Kept `image: node:20-slim` for the frontend service.
   - Kept host port mapping `"3030:5173"` to prevent port collision on the server.
3. **Environment Variables (`.env` files):**
   - **`backend/.env`**: Kept `CORS_ORIGINS=http://localhost:5173,http://localhost:3030,http://10.117.10.68:3030`.
   - **`frontend/.env`**: Kept `VITE_API_BASE_URL=http://10.117.10.68:8000`.

---

## 2. Updated Code & Feature Enhancements (สิ่งที่ได้รับการอัปเดต)

All latest fixes, security hardenings, and UX improvements from **CR-01 through CR-06** have been synchronized into this Linux environment folder:

### 2.1 Backend Core & API (`backend/app/`, `backend/tests/`)
* **CR-01: Playwright Chromium Sandbox Isolation (`capture.py` & `test_capture.py`):**
  - Explicitly passes `chromium_sandbox=not settings.BROWSER_DISABLE_SANDBOX` to Playwright launcher. Prevents Chromium sandbox from silently falling back to insecure `--no-sandbox` on Linux container environments.
* **CR-02 & CR-03: Baseline Approval Consistency & Retention Cap (`review.py`, `checks.py`, `config.py`):**
  - Added temporal integrity checks preventing older snapshots from displacing active baselines.
  - Preserves outage status (`STATUS_FAILED` / `STATUS_AVAILABILITY_ISSUE`) if approving historical snapshots.
  - Synchronizes session state with explicit `db.flush()` to ensure baseline retention cap is enforced even under `autoflush=False`.
  - Dynamically exposes `max_baselines_per_target` via `ConfigRead` schema and `/config` endpoint.
* **CR-04: Concurrency Guard for Target URL Modifications (`targets.py`, `errors.py`, `main.py`):**
  - Returns `HTTP 409 Conflict` (`ConflictError`) if a client attempts to edit the target URL while a check is running (`STATUS_CHECKING` or in-flight).
* **CR-06: Server-side Pagination (`targets.py`, `schemas/target.py`):**
  - Added `GET /targets/page` returning `PaginatedTargetsRead` with `items`, `total`, `limit`, and `offset`.

### 2.2 Frontend Application (`frontend/src/`)
* **CR-05: Continuous Scheduler Tracking & Cache Invalidation (`useTargetDetail.ts`, `TargetDetailPage.tsx`):**
  - Enabled continuous background polling (3s on Checking, 4s otherwise).
  - Unified `targetId` and `signature` into a composite ref to properly trigger query invalidations upon new check completions without stale data or React StrictMode mount issues.
  - Added regression test suite: `TargetDetailPage.cache.test.tsx`.
* **CR-06: Target List Pagination (`TargetListPage.tsx`, `useTargets.ts`, `types/target.ts`):**
  - Added `usePaginatedTargetsQuery` and pagination UI (Previous / Next buttons, page counter, showing range).
* **CR-04: Modal Safety (`EditTargetModal.tsx`):**
  - Automatically disables URL input and displays an amber warning banner if target is currently `Checking`.
* **UI Overflow & Details Navigation (`CheckDetailPage.tsx`, `TargetDetailPage.tsx`):**
  - Added `break-words [overflow-wrap:anywhere] min-w-0` to prevent result summary text overflow.
  - Added "View Full Details →" navigation link to `/checks/:id`.
* **Target Detail Action Buttons Repositioning (`TargetDetailPage.tsx`):**
  - Relocated target management buttons (`Edit` and `Delete`) under the target URL on the left side of the header, cleanly separating entity configuration from operational triage buttons (`Approve as Baseline`, `Confirm Defacement`, `Acknowledge Change`).

### 2.3 Documentation & Plans
* Added `README.md` and updated `PROJECT_STRUCTURE.md`.
* Synchronized `plan/PROJECT_PLAN.md` and all refinement logs in `refinement/`.

---

## 3. Recommended Deployment / Restart Steps on Linux Server

To apply the updated code on the Ubuntu server, execute the following commands in the project directory:

```bash
# 1. Stop running containers (data volume backend/data will remain preserved)
docker compose down

# 2. Rebuild and start containers in detached mode
docker compose up -d --build

# 3. Verify container logs
docker compose logs -f
```

---

## 4. Database & Artifact Clean Reset (บันทึกการรีเซ็ตข้อมูล)

**Executed Date:** September 8, 2026  
**Action:** Fresh Start Reset for Stage 2 Soak Test

1. **Backup:** Created `backend/data/app.db.bak` before making changes.
2. **Tables Cleaned:**
   - Deleted all historical rows in `check_results` (45 rows removed).
   - Deleted all historical rows in `snapshots` (47 rows removed).
   - Cleared active tokens in `sessions` (3 rows removed).
3. **Targets State:**
   - Preserved **2 targets** (*Bangkok Chain Hospital* & *World Medical Hospital TH*).
   - Reset their status to `'Never Checked'` (`last_error = NULL`).
4. **User Authentication:**
   - Preserved `users` table with `admin` account intact (login credentials unchanged).
5. **Storage Cleanup:**
   - Emptied `screenshots/` (47 files removed).
   - Emptied `html/` (47 files removed).
   - Emptied `text/` (47 files removed).
   - Database compacted via `VACUUM`.

---

## 5. CR10 Remediation & Follow-up Hardening (กันยายน 17, 2026)

**Execution Date:** September 17, 2026  
**Plan References:**  
- [`plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md`](plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md)  
- [`plan/CR10-Follow-up-Remediation-Plan-17-9-2026.md`](plan/CR10-Follow-up-Remediation-Plan-17-9-2026.md)  
- Refinement Logs: [`refinement/17-9-2026/`](refinement/17-9-2026/)

### 5.1 CR10 Core Remediations (Phases 1 - 3)
- **CR10-01 (SSRF Guard):** Added RFC 6598 CGNAT (`100.64.0.0/10`) and benchmark (`198.18.0.0/15`) blocked subnets.
- **CR10-02 (Uvicorn Reload):** Restricted file reload watch directory to `app` (`--reload-dir app`).
- **CR10-03 & CR10-11 (Snapshot Route Security & UTF-8):** Added strict path traversal containment checks and explicit `charset=utf-8` on text snapshots.
- **CR10-04 (Concurrency Lock):** Eagerly acquired in-flight concurrency lock in `trigger_target_check` before returning HTTP 202.
- **CR10-05 (Artifact Cleanup on Cancellation):** Handled `BaseException` (`CancelledError`) in `run_target_check` to discard staging files.
- **CR10-06 (Database Foreign Keys):** Enabled `PRAGMA foreign_keys=ON` on production SQLite engine in `backend/app/db/session.py`.
- **CR10-07 (Structural Parser):** Replaced streaming string chunks with complete token tree in HTML structural parser.
- **CR10-08 (Database Migrations):** Stamped production `app.db` with Alembic head revision `d2b3c4e5f6a7` (`d2b3c4e5f6a7_structural_detector.py`) with zero data loss or resets.
- **CR10-09 (Triage Safety):** Disabled triage action buttons during check execution (`Checking`) and added user-facing error banner on triage failures.
- **CR10-10 (Check Now & Cache Coherence):** Added on-demand "Check Now" button to Target Detail page header and full query cache invalidation.

### 5.2 Follow-up Hardening Remediations
- **Item 1 (Transaction Ordering):** In `backend/app/services/checks.py`, explicitly flushed `Snapshot` before creating `CheckResult` to satisfy foreign keys; added rollback and unlinking of promoted permanent files if commit fails.
- **Item 2 (Test Foreign Keys):** Attached `PRAGMA foreign_keys=ON` listener to `Engine` across all test sessions in `conftest.py` and added regression tests for foreign key enforcement and rollback file cleanup.
- **Item 3 (Capture Staging Self-Cleanup):** Enhanced `capture_snapshot` in `backend/app/services/capture/capture.py` to clean its own staging folder on task cancellation or disk write failure.
- **Item 4 (Production Docker Configuration):** Added multi-stage `frontend/Dockerfile` with `nginx:alpine`, SPA fallback, gzip, caching headers, production `docker-compose.yml`, and `docker-compose.dev.yml` for local development.
- **Item 5 (Documentation Realignment):** Realigned CR10 item numbering and migration filename across refinement documents.

### 5.3 Invariant & Health Verification
- **Target Database:** The second follow-up test run used an isolated in-memory
  application engine. `backend/data/app.db` retained its original 57,344-byte
  length and UTC modification timestamp (`2026-09-17 04:16:47`), and no WAL/SHM
  side files were created.
- **Tests:** Pytest (146 passed), Vitest (70 passed in 11 test files), Ruff (clean), Mypy (clean), Vite build (clean).
