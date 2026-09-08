# Refinement Record: Linux Code Sync & Database Reset for Stage 2 Soak Test

**Date:** September 8, 2026  
**Document Name:** `Linux-Code-Sync-and-Database-Reset-8-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test) — Clean Reset**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Linux Code Synchronization & Stage 2 Clean Reset | **Stage 2** (Observation Period / Soak Test) | Synchronized remediated codebase (CR-01 through CR-06) to the Linux deployment directory, preserved production environment configs, and executed a clean database reset to guarantee untainted telemetry for the 2–4 week soak test. |

**Parent Records:**
- [`refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`](./Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)
- [`refinement/7-9-2026/Stage2-Reset-and-Restart-7-9-2026.md`](../7-9-2026/Stage2-Reset-and-Restart-7-9-2026.md)
- [`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](../7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md)

---

## 1. Executive Summary & Operational Rationale

### 1.1 Background
Following the resolution and testing of **CR-01 through CR-06** (covering Chromium sandbox isolation, baseline approval temporal integrity, concurrency guards, continuous polling reactivity, and server-side pagination), the deployment codebase on Linux (`Web Defacement Project Linux`) needed to be brought in sync with the primary workspace (`Web Defacement Project`).

### 1.2 Soak Test Reset Decision
The Linux server had accumulated 45 checks across ~24 hours of execution on the unhardened code version, with all 45 checks exhibiting constant `Changed` alerts prior to baseline stabilization. To ensure that telemetry (noise floor measurements, alert firing rates, false-positive distributions) collected during the 2–4 week Stage 2 observation period represents the final hardened engine:
- A clean reset was executed across both the Windows dev environment and the Linux staging environment.
- Pre-update historical data was backed up and purged.
- The active monitoring targets and administrative credentials were preserved.

---

## 2. Technical Actions & Execution Details

### 2.1 Preserved Items (สิ่งที่คงไว้)
To prevent operational disruptions and preserve deployment topology on the Ubuntu server (`10.117.10.68`):
1. **Network & Deployment Configurations (`docker-compose.yml`):**
   - Frontend container: `image: node:20-slim`
   - Port binding: `"3030:5173"` (avoids collision with local host services)
2. **Environment Variables (`.env` files):**
   - `backend/.env`: `CORS_ORIGINS=http://localhost:5173,http://localhost:3030,http://10.117.10.68:3030`
   - `frontend/.env`: `VITE_API_BASE_URL=http://10.117.10.68:8000`
3. **User Authentication (`users` table):**
   - Retained the `admin` account with hashed credentials intact in `app.db`.
4. **Target Definitions (`targets` table):**
   - `Web Defacement Project`: Kept `Bangkok Chain Hospital TH`.
   - `Web Defacement Project Linux`: Kept `Bangkok Chain Hospital` and `World Medical Hospital TH`.

### 2.2 Synchronized Codebase (สิ่งที่ได้รับการอัปเดต)
The following directories and files were synchronized from `Web Defacement Project` to `Web Defacement Project Linux`:
- `backend/app/`: Core services (`capture.py`, `checks.py`, `review.py`), API routes (`targets.py`, `config.py`), error definitions (`errors.py`), schemas (`target.py`, `config.py`).
- `backend/tests/`: Complete automated test suites (123 test cases).
- `backend/alembic/`: Alembic database migration scripts and metadata.
- `frontend/src/`: React UI components (`EditTargetModal.tsx`, `BaselineManagerModal.tsx`), pages (`TargetListPage.tsx`, `TargetDetailPage.tsx`, `CheckDetailPage.tsx`), query hooks (`useTargets.ts`, `useTargetDetail.ts`), and regression tests (`TargetDetailPage.cache.test.tsx`).
- Root & Documentation: `README.md`, `PROJECT_STRUCTURE.md`, `plan/PROJECT_PLAN.md`, and all refinement logs under `refinement/`.
- `.gitignore`: Appended secret mask pattern `Bch@Web2026!.txt`.

### 2.3 Safe Database & Artifact Reset (การเคลียร์ฐานข้อมูลและไฟล์ผลตรวจ)
A safe database purge script was executed simultaneously across both projects:
1. **Safety Backup:** Created `backend/data/app.db.bak` prior to modification.
2. **Check Results & Snapshots Purge:**
   - Linux environment: Deleted 45 `check_results`, 47 `snapshots`, 3 `sessions`.
   - Local environment: Deleted 3 `check_results`, 4 `snapshots`, 3 `sessions`.
3. **Target Status Reset:**
   - Targets reset to: `status = 'Never Checked'`, `last_error = NULL`.
4. **Storage Cleanout:**
   - Emptied `screenshots/` (47 files removed from Linux, 4 from local).
   - Emptied `html/` (47 files removed from Linux, 4 from local).
   - Emptied `text/` (47 files removed from Linux, 4 from local).
   - Compaction: SQLite `VACUUM` executed to reclaim disk space.

---

## 3. Verification & Quality Assurance

### 3.1 Backend Test Execution (Pytest)
Executed directly inside `Web Defacement Project Linux/backend`:
```bash
pytest backend/tests -q
```
- **Result:** **123 passed, 1 warning in 68.02s (100% Pass Rate)**.

### 3.2 Post-Reset Database State Verification
| Attribute | `Web Defacement Project` | `Web Defacement Project Linux` |
| :--- | :--- | :--- |
| `users` count | 1 (`admin` intact) | 1 (`admin` intact) |
| `targets` count | 1 | 2 |
| `targets.status` | `'Never Checked'` | `'Never Checked'` |
| `snapshots` count | 0 | 0 |
| `check_results` count | 0 | 0 |
| `screenshots/` count | 0 | 0 |
| `html/` count | 0 | 0 |
| `text/` count | 0 | 0 |
| Backup file exists | `backend/data/app.db.bak` | `backend/data/app.db.bak` |

---

## 4. Next Deployment Operational Step

When restarting the containers on the Linux server:
```bash
docker compose down
docker compose up -d --build
docker compose logs -f
```
The first automated check executed by the scheduler (or triggered manually) will be recorded as the clean Initial Baseline under the fully hardened engine.
