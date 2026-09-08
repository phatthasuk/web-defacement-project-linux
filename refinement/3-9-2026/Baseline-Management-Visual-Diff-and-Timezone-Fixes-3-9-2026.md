# Refinement Record: Full Baseline Management, 3-Panel Visual Diff & Timezone Normalization

**Date:** September 3, 2026  
**Document Name:** `Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)

| Work in this record | Plan mapping |
| :--- | :--- |
| 3-panel visual diff heatmap | **Stage 4.6**, pulled forward because Stage 2 review is unworkable without it |
| Baseline management (list / demote / gallery) | Extends **Stage 4.3**; the plan covered *adding* a baseline in one click, not removing one |
| Timezone normalization | **Unplanned bug fix** found during the first Stage 2 trial runs |
| Click-to-zoom lightbox | **Unplanned usability fix**, same trigger |

**Parent Record:** [`Stage1-Implementation-3-9-2026.md`](./Stage1-Implementation-3-9-2026.md)  

---

## 1. Executive Summary

This document captures the implementation, architectural rationale, and verification of three critical usability and operator-experience features delivered during initial Stage 2 trial runs:

1. **Timezone Normalization (Fixing 7-Hour Discrepancy):** Resolved UTC/local timezone translation bugs where naive ISO timestamps serialized from SQLite were interpreted by browsers as local time, causing a 7-hour delay in "Last Activity" timestamps.
2. **3-Panel Visual Diff Heatmap (Stage 4.6 Pulled Forward):** Introduced an offscreen HTML5 canvas pixel diff rendering a neon red (`rgba(239, 68, 68, 1)`) heatmap directly between the baseline and latest screenshots. Solves the operator blindspot where subtle visual shifts (e.g., 10px carousel translations on Bangkok Chain Hospital) were impossible to identify side-by-side. Zero backend disk footprint.
3. **Click-to-Zoom Lightbox Modal:** Added interactive full-screen modal overlays to all screenshot panels and baseline gallery cards to allow high-resolution inspection of long full-page captures (1440x8000px).
4. **Full Baseline Management (Level 3):** Fully exposed the underlying multi-baseline architecture (`MAX_BASELINES_PER_TARGET = 20`) via dedicated backend API endpoints (`GET /targets/{id}/baselines`, `POST /targets/{id}/baselines/{snapshot_id}/demote`) and a rich frontend gallery modal (`BaselineManagerModal.tsx`) with active counters, match indicators, and confirmation-guarded baseline removal.

---

## 2. Feature Breakdown & Implementation Details

### 2.1 Timezone Normalization (7-Hour Offset Fix)

#### Root Cause Analysis
- Backend models capture timestamps in UTC (`datetime.now(UTC)`).
- SQLite lacks native timezone-aware datetime types, storing timestamps as naive ISO strings (`2026-09-03 07:35:12.414864`).
- Pydantic serialized naive datetimes without timezone offset or `Z` suffix (`"2026-09-03T07:35:12.414864"`).
- In JavaScript, `new Date(isoString)` without a `Z` or timezone offset interprets the string in the browser's local timezone (UTC+7 Thailand time). Consequently, `07:35:12 UTC` was displayed as `7:35:12 AM` local time instead of converting to `14:35:12` (2:35 PM ICT).

#### Implementation
- **Backend Schema Serialization:** Added `@field_serializer` to `TargetRead`, `CheckResultRead`, and `SnapshotRead` (`target.py`, `check_result.py`, `snapshot.py`) ensuring all datetime fields are explicitly formatted in RFC 3339 / ISO 8601 with a `Z` suffix.
- **Frontend Normalization Helper:** Created [`frontend/src/utils/date.ts`](../../frontend/src/utils/date.ts) providing:
  - `parseDate(isoString: string)`: Enforces UTC parsing even if an ISO string is missing the `Z` suffix.
  - `formatDateTime(isoString, options)`: Standardizes localized display across `TargetListPage`, `TargetDetailPage`, and `CheckDetailPage`.
- **Unit Tests:** Added 5 unit tests in `frontend/src/utils/date.test.ts`.

---

### 2.2 3-Panel Visual Diff Heatmap & Zoom Lightbox

#### Problem Statement
On modern corporate sites (such as Bangkok Chain Hospital), carousels and dynamic banners shift slightly between checks. A visual change score of `0.039` triggered alerts, but human operators reviewing two side-by-side screenshots could not discern where the difference occurred.

#### Implementation Details
- **Component:** [`frontend/src/components/ScreenshotCompare.tsx`](../../frontend/src/components/ScreenshotCompare.tsx)
- **3-Panel Layout:**
  - **Panel 1 (Left):** `Baseline Screenshot` (Original full color)
  - **Panel 2 (Center):** `Visual Diff Highlight` (Neon red heatmap overlay)
  - **Panel 3 (Right):** `Latest Screenshot` (Original full color)
- **Client-Side Canvas Processing:**
  - Loads baseline and current screenshots into an offscreen HTML5 canvas using authenticated credentials (`credentials: 'include'`).
  - Unchanged pixels are desaturated and dimmed to 70% grayscale (`#333`).
  - Altered pixels exceeding color distance threshold are painted with vivid red (`cur[i] = 239; cur[i+1] = 68; cur[i+2] = 68; cur[i+3] = 255`).
  - **Zero Disk Footprint:** Pure in-memory canvas rendering. No server storage or database rows created.
- **View Mode Switcher:** Header toggle allows operators to switch between `3-Panel Diff (Heatmap)` and classic `Side-by-side` modes.
- **Click-to-Zoom Lightbox Modal:**
  - Clicking any screenshot panel opens a full-resolution modal with independent scrolling.
  - Dismissible via close button (`✕`), background click, or keyboard `Escape`.
  - Blocks background page scrolling (`document.body.style.overflow = 'hidden'`) while active.

---

### 2.3 Full Baseline Management (Level 3)

#### Architectural Need
The system already supported multi-baseline matching against up to 20 baselines (`MAX_BASELINES_PER_TARGET = 20`), choosing the lowest diff score variant. However:
- The UI only showed a single baseline ID and gave operators no visibility into how many baselines were active.
- Operators could not see past approved baseline variants (e.g. seasonal promotional banners).
- Accidental approvals or outdated baselines could not be removed, potentially masking future defacements.

#### Backend Additions
- **Location:** [`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py)
- **Endpoints:**
  1. `GET /targets/{target_id}/baselines`:
     - Queries all snapshots where `target_id == target_id` and `is_baseline == True`, ordered by `captured_at.desc()`.
     - Returns `list[SnapshotRead]`.
  2. `POST /targets/{target_id}/baselines/{snapshot_id}/demote`:
     - Validates that the snapshot belongs to the specified target and is currently marked as a baseline.
     - Sets `snapshot.is_baseline = False`.
     - Preserves the physical snapshot files on disk for auditing.
- **Unit Tests:** Added `test_list_and_demote_target_baselines` in [`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py).

#### Frontend Components
- **API & Hooks:** Added `listTargetBaselines`, `demoteTargetBaseline` in `snapshots.ts` and `useTargetBaselinesQuery`, `useDemoteBaselineMutation` in `useTargetDetail.ts`.
- **Manager Modal:** Created [`frontend/src/components/BaselineManagerModal.tsx`](../../frontend/src/components/BaselineManagerModal.tsx):
  - Displays `X / 20 Active Baselines` counter.
  - Card grid showing thumbnail, capture time, snapshot ID, and page title for each active baseline.
  - Visual indicator: `🎯 Latest Match` badge highlighting which baseline matched the most recent check.
  - Full-resolution thumbnail zoom modal.
  - Inline confirmation dialogue for `Remove from Baselines` (demotion).
- **Target Detail Integration:** Updated the `Baseline Info` card in [`TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx) with a live counter badge and a `Manage Baselines` launch button.
- **Unit Tests:** Added [`frontend/src/components/BaselineManagerModal.test.tsx`](../../frontend/src/components/BaselineManagerModal.test.tsx) with 5 test scenarios.

---

## 3. Complete Quality Gate Verification

All 6 quality gates were validated post-implementation with 100% pass rate and zero regressions:

| Quality Gate | Command | Previous Baseline | Result Post Implementation | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Backend Unit Tests** | `py -m pytest -q` | 109 passed | **110 passed, 1 warning** *(+1 test)* | ✅ Clean |
| **Backend Types** | `py -m mypy app` | Clean (46 source files) | **Clean** (46 source files) | ✅ Clean |
| **Backend Linter** | `py -m ruff check .` | Clean | **Clean** (0 errors) | ✅ Clean |
| **Frontend Unit Tests** | `npm test -- --run` | 34 passed (7 files) | **48 passed (9 files)** *(+14 tests)* | ✅ Clean |
| **Frontend Types & Build** | `npm run build` | Passed | **Passed** (0 errors, 3.20s bundle) | ✅ Clean |
| **Frontend Linter** | `npm run lint` | 0 errors, 1 warning | **0 errors, 1 warning** (`useAuth.tsx:91`) | ✅ Clean |

---

## 4. Modified & Added Files Summary

| File Path | Component | Type | Summary of Changes |
| :--- | :--- | :--- | :--- |
| `backend/app/api/routes/targets.py` | Backend API | Modified | Added `GET /{id}/baselines` and `POST /{id}/baselines/{snapshot_id}/demote`. |
| `backend/app/schemas/target.py` | Backend Schemas | Modified | Added `@field_serializer` with explicit UTC `Z` formatting. |
| `backend/app/schemas/check_result.py` | Backend Schemas | Modified | Added `@field_serializer` with explicit UTC `Z` formatting. |
| `backend/app/schemas/snapshot.py` | Backend Schemas | Modified | Added `@field_serializer` with explicit UTC `Z` formatting. |
| `backend/tests/test_api_routes.py` | Backend Tests | Modified | Added `test_list_and_demote_target_baselines`. |
| `frontend/src/utils/date.ts` | Frontend Utils | **New** | Added `parseDate` and `formatDateTime` for robust UTC/local conversion. |
| `frontend/src/utils/date.test.ts` | Frontend Tests | **New** | 5 unit tests for date parsing and formatting. |
| `frontend/src/api/snapshots.ts` | Frontend API | Modified | Added `listTargetBaselines` and `demoteTargetBaseline`. |
| `frontend/src/hooks/useTargetDetail.ts` | Frontend Hooks | Modified | Added `useTargetBaselinesQuery` and `useDemoteBaselineMutation`. |
| `frontend/src/components/ScreenshotCompare.tsx` | Frontend UI | Modified | Implemented 3-panel diff heatmap layout and zoom lightbox. |
| `frontend/src/components/ScreenshotCompare.test.tsx` | Frontend Tests | Modified | Added tests for 3-panel diff, mode switching, and zoom modal. |
| `frontend/src/components/BaselineManagerModal.tsx` | Frontend UI | **New** | Level 3 baseline gallery modal with demotion and match badges. |
| `frontend/src/components/BaselineManagerModal.test.tsx` | Frontend Tests | **New** | 5 unit tests covering rendering, confirmation, and demotion. |
| `frontend/src/pages/TargetDetailPage.tsx` | Frontend Page | Modified | Integrated baseline counter, manage baselines button, and modal. |
| `frontend/src/pages/TargetDetailPage.test.tsx` | Frontend Tests | Modified | Updated mock hooks and tests for baseline management. |
| `frontend/src/pages/TargetListPage.tsx` | Frontend Page | Modified | Updated to use `formatDateTime` utility. |
| `frontend/src/pages/CheckDetailPage.tsx` | Frontend Page | Modified | Updated to use `formatDateTime` utility. |
| `docker-compose.yml` | Infrastructure | Modified | Mapped frontend port to host as `"3000:5173"` to avoid Hyper-V reserved range `5141-5240`. |
| `backend/.env` | Configuration | Modified | Added `http://localhost:3000` to `CORS_ORIGINS`. |
