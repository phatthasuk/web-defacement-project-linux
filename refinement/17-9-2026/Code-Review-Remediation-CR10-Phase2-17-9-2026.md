# Refinement Record: Code Review Remediation CR10 — Phase 2

**Date:** September 17, 2026  
**Document Name:** `Code-Review-Remediation-CR10-Phase2-17-9-2026.md`  
**Authoritative Plan Reference:** [`plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md`](../../plan/Code-Review-and-Remediation-Plan-CR10-17-9-2026.md)  
**Parent Plan:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Target Environment:** Ubuntu Server / Docker Compose Deployment (`10.117.10.68`)  
**Operational Status:** **Stage 2 (Hardening & Remediation / Soak Test Intact)**  

---

## 1. Scope and Operational Context

This record documents the implementation and verification of **Phase 2** of the CR10 remediation plan, targeting concurrency safety, resource lifecycle protection, database integrity, and parser reliability:

| Remediation Item | Severity | Focus Area | Status |
|---|---|---|---|
| **CR10-04** | P1 (High) | Synchronous check reservation to prevent concurrent double-trigger races | **Completed & Verified** |
| **CR10-05** | P2 (Medium) | Guaranteed staging artifact cleanup on `CancelledError` / process aborts | **Completed & Verified** |
| **CR10-06** | P2 (Medium) | Enforce SQLite foreign key constraints via `PRAGMA foreign_keys=ON` | **Completed & Verified** |
| **CR10-07** | P2 (Medium) | Buffer inline script chunks in `_StructureParser` to prevent false positive alerts | **Completed & Verified** |

### Strict Invariants Maintained
- **Production Data & Target Preservation**: `backend/data/app.db` was not modified, reset, or cleared. Both active monitoring targets (*Bangkok Chain Hospital* and *World Medical Hospital TH*) remain intact in `Never Checked` state with all historical baseline and snapshot tables preserved.
- **Single API Worker Architecture**: Process-local concurrency caps and single-worker constraints were strictly maintained.
- **Fail-Closed Security & Clean Disk Guarantees**: Zero temporary artifact leakage on cancel, failure, or unchanged checks.

---

## 2. Technical Implementation Details

### 2.1 CR10-04: Synchronous Reservation in Manual Check Route & Scheduler
- **Problem**: In `backend/app/api/routes/checks.py`, `trigger_target_check` previously checked `is_target_in_flight(target_id)` before calling `background_tasks.add_task(run_checks_for_targets, ...)`. However, `_in_flight_targets.add(target_id)` was only executed once the background worker coroutine actually started execution on the event loop. If an operator or automated client rapidly double-clicked "Check Now", both requests read `is_target_in_flight == False`, enqueued duplicate background tasks, and returned `accepted: True` to both. A similar race existed in `backend/app/services/scheduler.py` when dispatching due targets.
- **Modifications**:
  - [`backend/app/services/concurrency.py`](../../backend/app/services/concurrency.py):
    - Added atomic reservation helpers: `try_acquire_in_flight(target_id: str) -> bool` and `release_in_flight(target_id: str) -> None`.
    - Added `pre_reserved: bool = False` parameter to `run_checks_for_targets`. When `pre_reserved=True`, the worker assumes the reservation was pre-acquired synchronously by the caller and ensures it is safely released in the `finally:` block.
    - Wrapped `load_domain_keys` with exception handling to release `pre_reserved` target IDs if initialization fails.
  - [`backend/app/api/routes/checks.py`](../../backend/app/api/routes/checks.py):
    - Updated `trigger_target_check` to call `try_acquire_in_flight(target_id)` synchronously before `background_tasks.add_task`.
    - If the target is checking or reservation acquisition returns `False`, the endpoint immediately returns `CheckTriggerResponse(target_id=target_id, accepted=False)`.
    - Passes `pre_reserved=True` into `run_checks_for_targets`.
  - [`backend/app/services/scheduler.py`](../../backend/app/services/scheduler.py):
    - Updated `_tick` to check `if target.status == STATUS_CHECKING or not try_acquire_in_flight(target.id): continue`.
    - Passes `pre_reserved=True` to `run_checks_for_targets`.
- **Verification**:
  - In `backend/tests/test_api_routes.py`, `test_double_check_trigger_skips_in_flight_duplicate` verifies that concurrent trigger requests return 202, with exactly one receiving `accepted=True` and the other `accepted=False`, with only a single capture performed.
  - In `backend/tests/test_concurrency.py`, added `test_try_acquire_and_release_in_flight` and `test_run_checks_for_targets_with_pre_reserved`.

### 2.2 CR10-05: Staging Directory Cleanup Guard for CancelledError
- **Problem**: In `backend/app/services/checks.py`, `run_target_check` creates temporary capture artifacts in a staging directory. Artifact promotion (`_promote_staging_artifacts`) occurs after diffing. If the check is cancelled (e.g. timeout via `asyncio.wait_for`, task cancellation, or server shutdown), Python raises `asyncio.CancelledError`, which inherits from `BaseException` rather than `Exception`. The previous `except Exception:` block did not catch `CancelledError`, leaving staged images, text, and HTML files orphaned in `data/staging/`.
- **Modifications**:
  - [`backend/app/services/checks.py`](../../backend/app/services/checks.py):
    - Introduced an `artifacts_promoted = False` guard flag in `run_target_check`.
    - Flag is flipped to `True` only when staged artifacts are promoted to permanent storage.
    - Added a `finally:` block:
      ```python
      finally:
          if not artifacts_promoted:
              _discard_snapshot_files(capture)
      ```
    - This ensures that if `run_target_check` is aborted by `asyncio.CancelledError` or any unexpected exception during diffing or DB commits, all temporary staging directories and files are immediately purged.
- **Verification**:
  - Added `test_run_target_check_cleans_staging_on_cancellation` in `backend/tests/test_checks.py`. A monkeypatched cancellation during check execution verified that the staging directory is completely deleted upon cancellation.

### 2.3 CR10-06: Foreign Key Enforcement in SQLite Connections
- **Problem**: By default, SQLite engine instances in Python do not enforce foreign key constraints unless explicitly enabled per connection via `PRAGMA foreign_keys=ON`. Without this, invalid foreign key relationships (e.g., child records referencing deleted targets) could be committed without database-level integrity rejection.
- **Modifications**:
  - [`backend/app/db/session.py`](../../backend/app/db/session.py):
    - In `set_sqlite_pragma(dbapi_connection, connection_record)` event listener, added:
      ```python
      cursor.execute("PRAGMA foreign_keys=ON")
      ```
- **Verification**:
  - Added `test_sqlite_foreign_keys_pragma` in `backend/tests/test_checks.py`, verifying that connections created by `engine` return `PRAGMA foreign_keys == 1`.

### 2.4 CR10-07: Inline Script Buffering Across Multiple Chunks in `_StructureParser`
- **Problem**: In `backend/app/services/diff/structure.py`, `_StructureParser.handle_data` previously appended each chunk directly to `self._inline_script_parts`. In HTML parsing, `handle_data` is invoked repeatedly for a single `<script>` tag whenever chunks contain newlines, entity references (`&amp;`), or streaming chunk boundaries. This resulted in hashing fragments of scripts instead of the complete script body, leading to false-positive defacement alerts.
- **Modifications**:
  - [`backend/app/services/diff/structure.py`](../../backend/app/services/diff/structure.py):
    - Added `self._current_inline_chunks: list[str] = []` and `_flush_inline_script()` method.
    - In `handle_data`, chunks are accumulated in `self._current_inline_chunks`.
    - In `handle_endtag("script")`, `_flush_inline_script()` joins all accumulated chunks, strips whitespace, and appends the single coalesced script body to `self.inline_scripts`.
    - In `close()`, `super().close()` is executed first to flush any pending CDATA, followed by `_flush_inline_script()` to safely capture unclosed script tags without data loss.
- **Verification**:
  - Added `test_inline_script_multiline_and_chunked_is_buffered_into_single_digest` in `backend/tests/test_structure.py` covering multi-line scripts, HTML entities, and unclosed script tags. All 14 tests in `test_structure.py` passed.

---

## 3. Comprehensive Verification Summary

### 3.1 Automated Test Execution
- **Backend Tests (pytest)**: `143 passed, 1 warning in 39.75s` (up from 138 in Phase 1).
  - `tests/test_api_routes.py`: 22 passed
  - `tests/test_auth.py`: 19 passed
  - `tests/test_capture.py`: 12 passed
  - `tests/test_checks.py`: 33 passed (+2 new tests for cancellation cleanup and foreign keys pragma)
  - `tests/test_concurrency.py`: 8 passed (+2 new tests for reservation acquire/release and pre-reserved checks)
  - `tests/test_diff.py`: 5 passed
  - `tests/test_review.py`: 16 passed
  - `tests/test_scheduler.py`: 4 passed
  - `tests/test_ssrf_guard.py`: 7 passed
  - `tests/test_ssrf_proxy.py`: 1 passed
  - `tests/test_status.py`: 2 passed
  - `tests/test_structure.py`: 14 passed (+1 new test for inline script chunk buffering)
- **Static Analysis & Linting**:
  - `ruff check .`: `All checks passed!`
  - `mypy app`: `Success: no issues found in 47 source files`
- **Frontend Test Suite & Build**:
  - Vitest: `67 passed (11 test files)`
  - TypeScript: `tsc --noEmit` exited 0 (no errors)
  - Vite Build: `dist/index.html`, `dist/assets/index-*.js` built in 2.20s

### 3.2 Target Database Integrity Check
Verified that `backend/data/app.db` was preserved without mutation:
- Target `84300ac1-1f23-42cb-af6f-b39d6f0d892e`: `Bangkok Chain Hospital` (`Never Checked`, active)
- Target `441a36ef-6b4e-41b2-b3a1-eff7c0dc389c`: `World Medical Hospital TH` (`Never Checked`, active)

---

## 4. Files Modified in Phase 2

1. [`backend/app/services/concurrency.py`](../../backend/app/services/concurrency.py) (CR10-04)
2. [`backend/app/api/routes/checks.py`](../../backend/app/api/routes/checks.py) (CR10-04)
3. [`backend/app/services/scheduler.py`](../../backend/app/services/scheduler.py) (CR10-04)
4. [`backend/app/services/checks.py`](../../backend/app/services/checks.py) (CR10-05)
5. [`backend/app/db/session.py`](../../backend/app/db/session.py) (CR10-06)
6. [`backend/app/services/diff/structure.py`](../../backend/app/services/diff/structure.py) (CR10-07)
7. [`backend/tests/test_concurrency.py`](../../backend/tests/test_concurrency.py) (CR10-04 tests)
8. [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py) (CR10-04 assertion)
9. [`backend/tests/test_checks.py`](../../backend/tests/test_checks.py) (CR10-05 and CR10-06 tests)
10. [`backend/tests/test_structure.py`](../../backend/tests/test_structure.py) (CR10-07 tests)

---

## 5. Next Phase Readiness

Phase 2 is complete and verified. The codebase is prepared for:
- **Phase 3**: Frontend Resiliency & Observability (`CR10-08`, `CR10-09`, `CR10-10`, `CR10-12`).
