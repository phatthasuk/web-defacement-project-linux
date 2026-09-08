# Summary: Phase A Remediation — Code Review Remediation
**Execution Date:** September 2, 2026  
**Document Name:** `PhaseA-Remediation-2-9-2026.md`  
**Source Plan Reference:** [`plan/codereviewbygptsol.md`](../../plan/archive/codereviewbygptsol.md)  

---

## 1. Executive Summary

This document records the completion of **Phase A Remediation**, the first wave of fixes addressing the 8 findings identified in `plan/codereviewbygptsol.md`.

**Selection Criteria for Phase A:** High-impact, low-cost tasks that **do not touch `capture.py`** to avoid merge conflicts with Phase B, which refactors that file in a unified pass alongside `plan/capture-improvements.md` and Findings 6 and 7.

| Task | Finding | Severity | Status |
| :--- | :--- | :--- | :--- |
| Remove outdated comments & documentation | Minor | Low (misleading context) | ✅ Complete |
| Frontend renders artifact errors as distinct diff states | **F4** | **P2 / High correctness risk** | ✅ Complete |
| Target stuck in `Checking` status indefinitely | **F8** | P2 / High reliability risk | 🟡 Partially complete (see Section 5) |

### Combined Quality Verification Results

| Metric | Before Remediation | After Remediation |
| :--- | :--- | :--- |
| Backend tests (`pytest`) | 68 passed | **73 passed** (+5) |
| Frontend tests (`vitest`) | 23 passed | **33 passed** (+10) |
| Ruff linter | clean | clean |
| Mypy static analysis | clean | clean (42 source files) |
| TypeScript compilation (`tsc -b`) | clean | clean |
| ESLint | 0 errors, 1 warning | 0 errors, 1 warning *(pre-existing)* |
| Vite production build | Passed | Passed |

---

## 2. Minor Task — Removing Outdated Comments and Documentation

### Problem Statement
Project documentation and comments still stated that the repository **had no application code**, which had been untrue since the initial backend and frontend implementation landed. This misled new readers into believing the project was non-functional *(an observation noted in [`SummaryProject-22-7-2026.md`](../22-7-2026/SummaryProject-22-7-2026.md) item 3 but left unaddressed)*.

### Remediation Applied

**[`docker-compose.yml`](../../docker-compose.yml)** — Removed 3 misleading lines of comments (lines 4–6):
```yaml
# Application code (app/main.py, src bootstrap) is not written yet — see
# PROJECT_STRUCTURE.md. Until then these services will fail to start; this
# file exists so the dev environment is ready once that code lands.
```
Retained the first 2 instructions (instructing users to copy `.env.example` before execution) without touching any `services:` definitions.

**[`PROJECT_STRUCTURE.md`](../../PROJECT_STRUCTURE.md)** — Completely rewritten:
- Removed claims of *"No application code yet — folders only"* and the section *"Not yet added: Any application code"*.
- Updated the directory tree to reflect reality (added `alembic/`, `scripts/`, `tests/`, `api/deps.py`, `core/` modules, `services/{checks,concurrency,review}.py`, `main.py`, and Login views).
- Updated route mappings to cover auth groups, `User`/`Session` models, and `concurrency.py`.
- Added a **Planning Documents** section explaining distinctions between `plan/`, `plan/archive/`, `plan/future/`, and `refinement/`.
- Replaced *"Not yet added"* with **"Known Outstanding Work"** linking directly to `codereviewbygptsol.md`.

---

## 3. Finding 4 — Frontend Misrepresents Artifact Errors as "No Differences"

> **Severity:** P2 / High correctness risk  
> ⚠️ Logically the **most dangerous flaw** in a defacement monitoring tool because it produces **false negatives**.

### Problem & Root Cause

Queries fetching snapshot text defaulted to empty strings (`= ''`) and checked only `isLoading` without validating `isError` before rendering comparison views:

| Scenario | Previous Behavior | Actual Impact |
| :--- | :--- | :--- |
| **Both artifacts fail to load** | Both fall back to `''` → UI renders *"No textual differences detected"* | **System claims the website is unchanged when actual status is unknown** |
| **One artifact fails to load** | Fabricates a massive artificial diff between `''` and valid text | Erroneous alarm (false positive) |
| **Screenshot fails to load** | `<img>` lacked `onError` → Displays blank frame | Appears like a blank or unchanged page |

**Root Cause:** Code conflated *"not yet loaded"*, *"failed to load"*, and *"loaded successfully but content is empty"* — all three states collapsed into `''`.

### Remediation Applied

**New Component: [`frontend/src/components/ArtifactError.tsx`](../../frontend/src/components/ArtifactError.tsx)**
- Shared error display component used across `CheckDetailPage` and `TargetDetailPage`.
- Explicitly lists **failed artifact names** and provides a **Retry** action button.
- Displays explicit disclaimer: *"This comparison is unknown — it is **not** confirmation that the content is unchanged"*.
- Includes `role="alert"` for accessibility compliance.

**[`frontend/src/pages/CheckDetailPage.tsx`](../../frontend/src/pages/CheckDetailPage.tsx) & [`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx)**
- **Removed `= ''` defaults** — fixes the root cause, distinguishing `undefined` (unloaded) from `''` (empty string).
- Wired `isError` and `refetch` from React Query hooks.
- Extracted `isSameSnapshot` variable — when baseline equals current snapshot, only a single network fetch is dispatched.
- Retry button triggers `refetch()` **strictly for the failed query**, avoiding redundant network re-requests for succeeded artifacts.
- `TargetDetailPage`: Re-ordered `isOnceChecked` guard to the top since that branch makes no comparison claims.

**Explicit 5-State Render Sequence:**
```
loading       → Spinner
error         → ArtifactError + Retry button
success       → TextDiffView (including legitimately empty text)
not-requested → Neutral note: "Text artifacts are not available for this comparison"
```

**[`frontend/src/components/ScreenshotCompare.tsx`](../../frontend/src/components/ScreenshotCompare.tsx)**
- Extracted sub-component `ScreenshotPanel` so each image maintains independent error boundaries.
- Added `onError` to `<img>` tags — failed captures render an explicit red alert: *"Screenshot failed to load / This image is unavailable — not evidence that the page is unchanged"*.
- Keyed panels by `snapshotId` for automatic remounting upon snapshot updates without requiring manual effect cleanup.
- Failure on one side never blocks or corrupts the other side.

### New Unit Tests (+10 Tests)

| Test Case | Test File |
| :--- | :--- |
| Baseline text failure renders error rather than "no differences" | `CheckDetailPage.test.tsx`, `TargetDetailPage.test.tsx` |
| Current text failure renders error | `CheckDetailPage.test.tsx` |
| Both text artifacts fail → Combined message *"baseline text and current text"* | `CheckDetailPage.test.tsx` |
| **Empty content (`''`) distinguished from load failure** | `CheckDetailPage.test.tsx`, `TargetDetailPage.test.tsx` |
| Retry refetches strictly the failed query | `CheckDetailPage.test.tsx` |
| Unrequested artifacts display neutral notice | `CheckDetailPage.test.tsx` |
| Screenshot load failure renders explicit error without affecting other panel | `ScreenshotCompare.test.tsx` |
| Snapshot transition clears prior failure state | `ScreenshotCompare.test.tsx` |

> Every error test asserts that **"No textual differences detected" is NOT present in the document**, satisfying strict review guidelines.

---

## 4. Finding 8 — Target Stuck in `Checking` Status Indefinitely

> **Severity:** P2 / High operational reliability risk  
> **Status:** Completed startup recovery portion (durable job queue deferred per architectural agreement).

### Problem & Root Cause

`run_target_check` committed `Checking` status to the database **before** dispatching capture logic ([`checks.py:43-45`](../../backend/app/services/checks.py)). Tasks ran in-process via FastAPI `BackgroundTasks` without a persistent queue.

**Failure Sequence:**
1. Database commits target status to `Checking`.
2. Process, container, or server terminates unexpectedly (OOM, restart, host reboot).
3. Background task vanishes with the killed process, but **database row remains frozen as `Checking`**.
4. Future invocations of `trigger_target_check` reject the target because it appears in-progress.
5. → **Target becomes permanently uncheckable until an operator manually patches the database.**

The original `main.py` lifespan only verified cookie policy, executed `create_all()`, and provisioned directories — **no recovery logic existed**.

### Remediation Applied

**[`backend/app/services/checks.py`](../../backend/app/services/checks.py)** — Added `recover_stale_checks(db)` function and constant `STALE_CHECK_ERROR`:
- Scans for targets stuck in `Checking` → sets `last_error` → transitions status to `Failed` → commits transaction → logs warning with target ID.
- Returns list of released target IDs.

**Safety Invariant Without Timestamps:**
> Because checks execute in-process, at application boot time **no background tasks have been scheduled yet**. Therefore, any target found in `Checking` status **must** be an orphan from a previously terminated process — eliminating the need for timestamp heuristics.

- Reuses `transition_target()`, enforcing valid state transitions (`Checking → Failed` is explicitly permitted).
- Because `Failed → Checking` is also valid, released targets can be immediately checked again.

**[`backend/app/main.py`](../../backend/app/main.py)** — Injected `recover_stale_checks()` into the lifespan sequence immediately following data directory creation.

### New Unit Tests (+5 Tests) — `backend/tests/test_checks.py`

| Test Case | Scope Covered |
| :--- | :--- |
| `test_recover_stale_checks_releases_targets_stuck_in_checking` | Transitions `Checking` → `Failed` and sets `last_error` |
| `test_recover_stale_checks_leaves_other_statuses_untouched` | **Leaves intact** OK / Changed / Never Checked statuses |
| `test_recover_stale_checks_releases_every_stuck_target` | Releases all stuck records without collateral side effects |
| `test_recover_stale_checks_is_idempotent` | Re-running recovery produces identical safe state |
| `test_released_target_can_be_checked_again` | **Released targets can resume checks immediately** (core F8 objective) |

---

## 5. Unresolved Items & Known Limitations

### 5.1 F8 — Architectural Queue Portions Remaining
| Item | Status |
| :--- | :--- |
| Migrate to durable queue (Celery / Dramatiq / RQ) | ❌ Deferred |
| Job metadata + lease / heartbeat protocol | ❌ Currently relies solely on `Checking` column |
| Idempotent task execution + bounded retry + dead-letter queue | ❌ Deferred |
| Database-level duplicate suppression | ❌ Relies on process-local `_in_flight_targets` set |

**⚠️ Single-Worker Constraint:** `recover_stale_checks` assumes a **single Uvicorn worker** (enforced by `concurrency.py` and `docker-compose.yml` with `--workers 1`). If scaled horizontally to multiple workers in the future, boot recovery could inadvertently fail checks running in another active worker. Must migrate to lease/heartbeat protocols before multi-worker scaling.

### 5.2 F4 — Additional Queries Pending
- Guidelines recommend applying uniform error boundaries across other queries (`snapshot list`, `baseline`, `check history`, `config`). Phase A focused strictly on **text + screenshot**, the two primary paths generating false negative claims.
- Remaining queries fail open as "no data available" rather than claiming the page is unchanged (lower correctness risk).

### 5.3 ESLint Warning
`frontend/src/hooks/useAuth.tsx:91` — `react-refresh/only-export-components` warning remains pre-existing and is located in untouched auth files.

---

## 6. Status of All Findings in `codereviewbygptsol.md`

| # | Finding | Severity | Status |
| :--- | :--- | :--- | :--- |
| 1 | Backend lacks auth/authz | P1 | ✅ Local auth complete / ❌ **RBAC pending** (`User.role` unenforced) |
| 2 | SSRF DNS-rebinding vulnerability | P1 | 🟡 Primary hostname pinned / ❌ Subresources still cache boolean |
| 3 | Resource limits checked post-workload | P2 | ❌ Deferred |
| 4 | Frontend artifact error handling | P2 | ✅ **Complete in Phase A** (minor queries pending) |
| 5 | Orphan artifact files on disk | P2 | ❌ Deferred to Phase C (staging/reconciliation) |
| 6 | WebSocket + service worker SSRF bypass | P1 | ❌ Scheduled for Phase B |
| 7 | Chromium lacks process sandbox | P2 | ❌ Scheduled for Phase B |
| 8 | Background job durability | P2 | 🟡 **Startup recovery complete** / durable queue deferred |
| — | Minor: Outdated comments | — | ✅ **Complete in Phase A** |

---

## 7. Recommended Next Steps (Phase B)

**Execute `plan/capture-improvements.md` items 1–3 in conjunction with Findings 6 and 7 in a single pass.**

*Rationale:* All four tasks modify [`backend/app/services/capture/capture.py`](../../backend/app/services/capture/capture.py). Finding 6 (`route_web_socket`) must register listeners **before navigation**, exactly where `capture-improvements` injects its page stabilization pipeline. Consolidating these changes prevents redundant rework.

**Phase B Sequencing:**
1. Establish page-stabilization pipeline (cookie/dialog dismissal and wait strategies).
2. Wire Finding 6 — `route_web_socket` + disable service workers pre-navigation.
3. Wire Finding 7 — Enable browser sandbox and configure container capabilities.
4. Multi-baseline matching and diff heatmap algorithms in `diff.py`.

---

## 8. Summary of Modified Files

### Backend (3 Files)
| File | Changes Made |
| :--- | :--- |
| `backend/app/services/checks.py` | Added `recover_stale_checks()` and `STALE_CHECK_ERROR` |
| `backend/app/main.py` | Wired recovery into startup lifespan; imported `SessionLocal` |
| `backend/tests/test_checks.py` | Added 5 recovery unit tests; imported `STATUS_NEVER_CHECKED` |

### Frontend (7 Files)
| File | Changes Made |
| :--- | :--- |
| `frontend/src/components/ArtifactError.tsx` | **New component** for explicit artifact error display |
| `frontend/src/components/ScreenshotCompare.tsx` | Refactored with `ScreenshotPanel` and `onError` image handlers |
| `frontend/src/pages/CheckDetailPage.tsx` | Replaced `= ''` defaults with explicit 5-state error sequences |
| `frontend/src/pages/TargetDetailPage.tsx` | Replaced `= ''` defaults with explicit 5-state error sequences |
| `frontend/src/components/ScreenshotCompare.test.tsx` | Added 2 tests for error isolation and key remounting |
| `frontend/src/pages/CheckDetailPage.test.tsx` | Added 6 tests and `mockTextQueries()` helper |
| `frontend/src/pages/TargetDetailPage.test.tsx` | Added 2 tests and `mockTextQueries()` helper |

### Documentation (5 Files)
| File | Changes Made |
| :--- | :--- |
| `docker-compose.yml` | Removed obsolete "no application code" comment |
| `PROJECT_STRUCTURE.md` | Rewritten to reflect actual codebase architecture and status |
| `plan/capture-improvements.md` | **New file** defining Phase B scope |
| `plan/future/auto-rebaseline.md` | **New file** defining future auto-baseline requirements |
| `plan/local-authentication-implementation-review.md` | **Archived** to `plan/archive/` |
