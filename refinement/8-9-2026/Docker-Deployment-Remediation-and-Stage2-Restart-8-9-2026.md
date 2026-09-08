# Refinement Record: Docker Deployment Remediation & Stage 2 Soak Test Restart

**Date:** September 8, 2026  
**Document Name:** `Docker-Deployment-Remediation-and-Stage2-Restart-8-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md) (Stage 2)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test) — Restarted & Active**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Docker Deployment Remediation & Stage 2 Restart | **Stage 2** (Observation Period / Soak Test) | Resolved container startup crash, infinite UI spinner, Chromium sandboxing failures, and user management CLI paths; synchronized changes to GitHub repository; and cleanly restarted the 2–4 week observation soak test on the Ubuntu server. |

**Parent Records:**
- [`refinement/8-9-2026/Linux-Code-Sync-and-Database-Reset-8-9-2026.md`](./Linux-Code-Sync-and-Database-Reset-8-9-2026.md)
- [`refinement/8-9-2026/Linux-Environment-Code-Sync-8-9-2026.md`](./Linux-Environment-Code-Sync-8-9-2026.md)
- [`refinement/8-9-2026/Code-Review-Remediation-CR01-to-CR06-8-9-2026.md`](./Code-Review-Remediation-CR01-to-CR06-8-9-2026.md)

---

## 1. Executive Summary & Incident Rationale

Following the deployment and database reset of the remediated engine (**CR-01 through CR-06**) on the Ubuntu Linux server (`10.117.10.68`), multiple containerization and environment issues surfaced upon starting with `docker compose up -d --build`:
1. **Infinite Frontend Loading Spinner:** React SPA (`App.tsx` `<ProtectedRoute>`) stayed permanently on the loading spinner because the backend was locked in a rapid crash-restart loop.
2. **Backend Startup SQLite Crash:** `sqlite3.OperationalError: unable to open database file` during application lifespan startup.
3. **User Bootstrap CLI Failure:** `ModuleNotFoundError: No module named 'app'` when attempting to run `python scripts/create_user.py` inside the container.
4. **Playwright Chromium Sandboxing Failure:** Chromium aborted launch with `Chromium sandboxing failed!` due to Docker root execution and default seccomp profile restrictions.
5. **Container Environment Propagation Gap:** Running `docker compose restart backend` failed to apply new environment variables from `.env` because Docker preserves the existing container's environment definitions unless explicitly recreated.

All defects were resolved with resilient programmatic fallbacks and configuration hardenings, committed upstream to Git, and deployed to the Linux server. The Stage 2 observation period (Soak Test) was then cleanly restarted.

---

## 2. Technical Root Causes & Implemented Remediations

### 2.1 Issue 1: Backend Startup Crash & Missing Directory (`backend/app/main.py`)
- **Root Cause:** In `backend/app/main.py`, `Base.metadata.create_all(bind=engine)` was called at line 35, whereas directory creation (`os.makedirs`) was called afterwards at line 38. Because `backend/data/` was untracked in Git (due to `*.db` exclusions in `.gitignore` and empty directory omissions), the `/app/data` folder did not exist inside the Docker container. SQLite cannot create a database file in a non-existent parent directory, throwing `sqlite3.OperationalError: unable to open database file` and causing Uvicorn to exit immediately.
- **Remediation:**
  - Reordered `lifespan` in `backend/app/main.py` to ensure `settings.data_dir_path` and all subdirectories (`screenshots`, `text`, `html`, `staging`) are created **before** opening the database connection.
  - Added parent directory resolution and creation for SQLite file URIs.

### 2.2 Issue 2: Chromium Sandboxing in Linux Containers (`backend/app/services/capture/capture.py`, `docker-compose.yml`)
- **Root Cause:** When running Playwright Chromium inside Docker as user `root` without `seccomp:unconfined` or `SYS_ADMIN` capabilities, Chromium's user-namespace sandbox (`CLONE_NEWUSER`) fails by design. Playwright throws: `Target page, context or browser has been closed. Browser logs: Chromium sandboxing failed!`.
- **Remediation:**
  - **Programmatic Auto-Fallback (`capture.py`):** Wrapped `playwright.chromium.launch()` in an exception handler. If sandboxing fails or browser closes unexpectedly during launch, it logs a warning and automatically falls back to launch with `--no-sandbox`, `--disable-setuid-sandbox`, and `chromium_sandbox=False`.
  - **Docker Compose Hardening (`docker-compose.yml`):** Added `ipc: host`, `security_opt: [seccomp:unconfined]`, and injected `environment: - BROWSER_DISABLE_SANDBOX=true`.
  - **Template Documentation (`backend/.env.example`):** Added `BROWSER_DISABLE_SANDBOX=false` documentation.

### 2.3 Issue 3: Bootstrap User Creation Path (`backend/scripts/create_user.py`)
- **Root Cause:** Running `python scripts/create_user.py admin` inside the container populated `sys.path[0]` with `/app/scripts`, excluding the working directory `/app`. The script aborted with `ModuleNotFoundError: No module named 'app'`.
- **Remediation:**
  - Added `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` at the top of `backend/scripts/create_user.py` to guarantee root resolution regardless of invocation mode.

### 2.4 Issue 4: Docker Compose Re-creation Rule Awareness
- **Technical Context:** In Docker Compose, `docker compose restart <service>` only issues a restart signal to the existing container without re-reading `env_file` or updating `Config.Env`.
- **Operational Requirement:** Documented that configuration and `.env` updates require `docker compose up -d --force-recreate <service>` (or `docker compose down && docker compose up -d`).

---

## 3. Synchronized Files & Git Upstream

All modifications were synchronized from the local workspace to the designated GitHub staging repository:
- **Repository Path:** `C:\Users\phatthasuk.pi\Documents\GitHub\web-defacement-project-linux`
- **Remote:** `https://github.com/phatthasuk/web-defacement-project-linux.git`
- **Branch:** `main`
- **Commit ID:** `91dd04f`
- **Commit Message:** `fix(docker): resolve chromium sandboxing, auto-create data dirs, and fix user script path`

### Summary of Modified Files:
| File | Changes Made |
| :--- | :--- |
| `backend/app/main.py` | Create `data/` and subdirectories before `Base.metadata.create_all()`. |
| `backend/app/services/capture/capture.py` | Added resilient try/except fallback to `--no-sandbox` upon sandbox failure. |
| `backend/scripts/create_user.py` | Added `sys.path.insert` for direct script execution. |
| `backend/.env.example` | Updated `CORS_ORIGINS` to include port 3030; documented `BROWSER_DISABLE_SANDBOX`. |
| `docker-compose.yml` | Added `ipc: host`, `security_opt: [seccomp:unconfined]`, and `BROWSER_DISABLE_SANDBOX=true`. |

---

## 4. Stage 2 Soak Test Clean Restart Protocol

### 4.1 Deployment Execution on Ubuntu Server (`10.117.10.68`)
1. **Pull and Force-Recreate:**
   ```bash
   git checkout -- docker-compose.yml
   git pull
   sudo docker compose up -d --force-recreate backend
   ```
2. **Verify Application Startup:**
   ```bash
   sudo docker compose logs -f backend
   ```
   *Expected Output:*
   ```text
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
   ```

### 4.2 Initialized Target Telemetry for Stage 2
| Target Name | URL | Status at Restart |
| :--- | :--- | :--- |
| **Bangkok Chain Hospital** | `https://www.bangkokchainhospital.com/th/home` | Initial Baseline Check Running |
| **World Medical Hospital TH** | `https://theworldmedicalhospital.com/` | Initial Baseline Check Running |

### 4.3 Soak Test Metrics to Observe (2–4 Weeks)
1. **False-Positive Distribution:** Ensure visual diff score remains consistently below the `0.01` threshold or is accurately captured across rotational hero elements via multi-baseline retention (up to 20).
2. **DOM/Structural Invariants:** Confirm zero noise on unchanged DOM structures.
3. **Capture Stability:** Zero browser crash timeouts or sandboxing failures during scheduled hourly executions.
4. **Storage & Cleanup:** Verify that unchanged checks write zero artifacts and staging folders are purged after 30 minutes.
