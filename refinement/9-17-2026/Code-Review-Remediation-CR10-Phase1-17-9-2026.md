# Refinement Record: Code Review Remediation CR10 — Phase 1

**Date:** September 17, 2026  
**Document Name:** `Code-Review-Remediation-CR10-Phase1-17-9-2026.md`  
**Authoritative Plan Reference:** [`plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md`](../../plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md)  
**Parent Plan:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Target Environment:** Ubuntu Server / Docker Compose Deployment (`10.117.10.68`)  
**Operational Status:** **Stage 2 (Hardening & Remediation / Soak Test Intact)**  

---

## 1. Scope and Operational Context

This record documents the successful implementation and verification of **Phase 1** of the CR10 remediation plan, targeting critical perimeter security and operational stability:

| Remediation Item | Severity | Focus Area | Status |
|---|---|---|---|
| **CR10-01** | P1 (High) | SSRF perimeter hardening for CGNAT (`100.64.0.0/10`) & benchmarking (`198.18.0.0/15`) | **Completed & Verified** |
| **CR10-02** | P1 (High) | Elimination of Uvicorn reload loops on active storage writes (`docker-compose.yml`) | **Completed & Verified** |
| **CR10-03** | P1 (High) | Path containment verification on snapshot artifact endpoints (`snapshots.py`) | **Completed & Verified** |
| **CR10-11** | P3 (Low)  | Explicit `charset=utf-8` header for snapshot text responses | **Completed & Verified** |

### Strict Invariants Maintained
- **Production Data & Target Preservation**: `backend/data/app.db` was not modified, reset, or cleared. Both active monitoring targets (*Bangkok Chain Hospital* and *World Medical Hospital TH*) remain intact in `Never Checked` state with all historical baseline and snapshot tables preserved.
- **Single API Worker Architecture**: Process-local concurrency caps and single-worker constraints were strictly maintained.
- **Fail-Closed Security**: No security checks were downgraded.

---

## 2. Technical Implementation Details

### 2.1 CR10-01: SSRF Boundary Hardening for Cloud & CGNAT Networks
- **Problem**: Python's `ipaddress.IPv4Address.is_private` only checks RFC 1918 subnets. RFC 6598 Shared Address Space (`100.64.0.0/10`) evaluates to `is_private=False` and `is_reserved=False`. Because major cloud platforms (AWS VPC CNI, Kubernetes cluster overlays, GCP private services, and Tailscale networks) utilize `100.64.0.0/10` for internal traffic, an attacker directing or redirecting a monitored target to `100.64.x.x` could connect to internal infrastructure.
- **Modifications**:
  - [`backend/app/core/ssrf_guard.py`](../../backend/app/core/ssrf_guard.py):
    - Added `BLOCKED_SPECIAL_NETWORKS` containing:
      - `ipaddress.ip_network("100.64.0.0/10")` (RFC 6598 Shared Address Space / CGNAT / Cloud Overlays)
      - `ipaddress.ip_network("198.18.0.0/15")` (RFC 2544 Benchmarking)
    - Updated `is_blocked_address(ip: IPAddress)` to test membership against `BLOCKED_SPECIAL_NETWORKS` after evaluating standard attributes.
    - Updated module docstring to remove stale notes regarding DNS rebinding gaps (resolved by `SsrfProxy`).
  - [`backend/tests/test_ssrf_guard.py`](../../backend/tests/test_ssrf_guard.py):
    - Added `100.64.0.1`, `100.127.255.254`, and `198.18.0.1` to `blocked_addresses` in `test_validate_url_blocks_private_and_non_public_ranges`.
- **Verification**: `pytest tests/test_ssrf_guard.py` passed with 7/7 assertions.

### 2.2 CR10-02: Elimination of Uvicorn File Watcher Reload Loop
- **Problem**: In `docker-compose.yml`, the backend command was specified as `uvicorn app.main:app ... --reload`. Because `./backend` is mounted into the container at `/app`, `watchfiles` monitored the entire filesystem recursively—including `/app/data/screenshots`, `/app/data/html`, `/app/data/staging`, and SQLite WAL files (`app.db-wal`). Every check execution that wrote capture artifacts triggered a file change event, causing Uvicorn to restart in the middle of check execution and leaving targets stuck in `Checking` (`STALE_CHECK_ERROR`).
- **Modifications**:
  - [`docker-compose.yml`](../../docker-compose.yml):
    - Changed the backend start command to:
      ```bash
      uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --reload --reload-dir app
      ```
    - Restricting `--reload-dir app` ensures the file watcher strictly observes code changes under `/app/app` and completely ignores `/app/data`.
- **Verification**: File writes to `data/` do not trigger watchfile reload notifications.

### 2.3 CR10-03 & CR10-11: Strict Path Containment & UTF-8 Charset on Artifact Endpoints
- **Problem**: `get_snapshot_screenshot` and `get_snapshot_text` previously read directly from `Path(snapshot.screenshot_path)` and `Path(snapshot.text_path)`. If a database record or malicious injection manipulated those columns to point to `/etc/shadow`, `.env`, or outside files, the endpoints would serve arbitrary host files. Furthermore, `media_type="text/plain"` omitted `charset=utf-8`, risking character corruption for Thai language targets.
- **Modifications**:
  - [`backend/app/api/routes/snapshots.py`](../../backend/app/api/routes/snapshots.py):
    - Implemented `_resolve_contained_artifact(raw_path: str, data_dir: Path) -> Path`:
      - Resolves both `data_dir` and `raw_path`.
      - Enforces `resolved_file.is_relative_to(resolved_base)` and `resolved_file.is_file()`.
      - Raises `NotFoundError` (HTTP 404) if outside the authorized storage directory.
    - Updated `get_snapshot_screenshot` and `get_snapshot_text` to pass paths through `_resolve_contained_artifact`.
    - Injected `AppSettings = Annotated[Settings, Depends(get_settings)]` into both endpoints.
    - Updated `get_snapshot_text` to specify `media_type="text/plain; charset=utf-8"`.
  - [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py):
    - Added `test_snapshot_artifact_rejects_path_traversal` verifying that snapshot entries pointing to files outside `api_work_dir` return HTTP 404 for both screenshot and text endpoints.
    - Added assertion verifying that `text_response.headers["content-type"]` contains `charset=utf-8`.
- **Verification**: `pytest tests/test_api_routes.py` passed with 22/22 tests.

---

## 3. Verification Results

Environment: Windows, Python 3.13.7, pytest 9.1.1, Ruff 0.7.4, Mypy 1.13.0

| Check | Target | Result |
|---|---|---|
| **Targeted Pytest** | `tests/test_ssrf_guard.py` | `7 passed in 0.27s` |
| **Targeted Pytest** | `tests/test_api_routes.py` | `22 passed in 3.52s` |
| **Full Backend Suite** | `pytest` (All 12 test modules) | `138 passed, 1 warning in 41.29s` |
| **Ruff Linter** | `ruff check .` | `All checks passed!` |
| **Mypy Static Typing** | `mypy app` | `Success: no issues found in 47 source files` |

*(Note: The sole warning in Pytest is from passlib reading argon2's deprecated `__version__` attribute, unchanged from baseline).*

---

## 4. Files Modified in Phase 1

- `backend/app/core/ssrf_guard.py` (CR10-01)
- `backend/tests/test_ssrf_guard.py` (CR10-01)
- `docker-compose.yml` (CR10-02)
- `backend/app/api/routes/snapshots.py` (CR10-03, CR10-11)
- `backend/tests/test_api_routes.py` (CR10-03, CR10-11)

---

## 5. Next Phase Readiness

Phase 1 has been completed, tested, and recorded. The codebase is fully prepared for **Phase 2: Concurrency, Engine Precision & Database Integrity**:
- `CR10-04`: Atomic synchronous reservation for manual check triggers.
- `CR10-05`: `try...finally` staging directory cleanup on task cancellation.
- `CR10-06`: SQLite `PRAGMA foreign_keys = ON` activation.
- `CR10-07`: Inline script streaming chunk aggregation in AST structural diff parser.
