# Refinement Record: Target Edit & Delete Implementation

**Date:** September 7, 2026  
**Document Name:** `Target-Edit-and-Delete-Implementation-7-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test)**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Target Name & URL Edit and Delete Functionality | Extends **Stage 4** (Operator Tooling & Target Management) | Enabled editing target details (name and URL) and deleting monitors that are no longer needed directly through the UI. |

**Parent Records:**
- [`refinement/4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md`](../4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md)
- [`refinement/3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md`](../3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md)
- [`refinement/3-9-2026/Stage1-Implementation-3-9-2026.md`](../3-9-2026/Stage1-Implementation-3-9-2026.md)

---

## 1. Executive Summary & Operational Context

### Background & Problem Statement
In the original prototype, operators could create new monitors (Add New Monitor) and trigger manual checks (Run Check), but lacked user interface (UI) controls and capabilities to:
1. **Edit Target Name or URL:** E.g., correcting typos in URLs, updating subpaths, or changing site display names.
2. **Delete Target Monitors:** When target sites were decommissioned or removed from active monitoring, they could not be deleted or removed from the dashboard via UI.

Furthermore, on the backend, the `TargetUpdate` schema previously disallowed updating the `url` field and did not pass `Settings` to validate URL security (SSRF prevention) on updates.

### Solution Overview
- **Backend:**
  - Added the `url` field to the `TargetUpdate` schema.
  - Added URL security validation via `validate_url(url, settings)` (SSRF Guard) in the `PATCH /targets/{target_id}` endpoint.
  - Leveraged existing soft-delete functionality (`DELETE /targets/{target_id}`), setting `is_active = False` to unregister targets from the scheduler and dashboard while preserving historical snapshots and check results for audit integrity.
- **Frontend:**
  - Added API client functions `updateTarget` and `deleteTarget`.
  - Added React Query mutation hooks for update and delete actions with cache invalidation.
  - Created `EditTargetModal` component for updating name and URL with inline error feedback.
  - Created `DeleteTargetModal` component for guarded confirmation before deleting a monitor.
  - Added **Edit** and **Delete** action buttons in the Actions column of the table on `TargetListPage` and in the header action bar on `TargetDetailPage`.

---

## 2. Implementation Details

### 2.1 Backend Core & API
1. **Target Schema ([`backend/app/schemas/target.py`](../../backend/app/schemas/target.py)):**
   - Added `url: str | None = Field(default=None, min_length=1, max_length=2048)` to the `TargetUpdate` schema.
2. **Targets Route ([`backend/app/api/routes/targets.py`](../../backend/app/api/routes/targets.py)):**
   - In `update_target`:
     - Added dependency `settings: AppSettings`.
     - When `url` is present in update data, invokes `validate_url(update_data["url"], settings)` to enforce SSRF guards and valid schemes prior to saving.
     - Persists `target.url = update_data["url"]`.
3. **Backend Test Suite ([`backend/tests/test_api_routes.py`](../../backend/tests/test_api_routes.py)):**
   - Updated `test_targets_crud_and_soft_delete` to verify valid URL updates (200 OK) and assert rejection of forbidden/SSRF loopback URLs like `http://127.0.0.1` (400 Bad Request).

### 2.2 Frontend Types, API & Components
1. **Type Definitions ([`frontend/src/types/target.ts`](../../frontend/src/types/target.ts)):**
   - Added interface `TargetUpdatePayload` supporting `name`, `url`, `is_active`, `allowed_domains`.
2. **API Client ([`frontend/src/api/targets.ts`](../../frontend/src/api/targets.ts)):**
   - Added `updateTarget(targetId: string, payload: TargetUpdatePayload): Promise<Target>`.
   - Added `deleteTarget(targetId: string): Promise<Target>`.
3. **Query Hooks ([`frontend/src/hooks/useTargets.ts`](../../frontend/src/hooks/useTargets.ts)):**
   - Added `useUpdateTargetMutation()`: Sends PATCH request and invalidates `['targets']` and `['targets', targetId]` caches.
   - Added `useDeleteTargetMutation()`: Sends DELETE request and invalidates `['targets']`.
4. **Edit Target Modal ([`frontend/src/components/EditTargetModal.tsx`](../../frontend/src/components/EditTargetModal.tsx)):**
   - Dark Slate dialog consistent with application design.
   - Input fields for Target Name and Target URL.
   - Supports Escape key to dismiss, closes on backdrop click.
   - Displays "Saving..." status during submission and shows red alert banners on API errors (such as blocked SSRF attempts).
5. **Delete Target Modal ([`frontend/src/components/DeleteTargetModal.tsx`](../../frontend/src/components/DeleteTargetModal.tsx)):**
   - Confirmation dialog with warning icon.
   - Explicitly displays the name and URL of the target slated for deletion.
   - Provides Cancel and Delete Target (rose accent) buttons with "Deleting..." state feedback.
6. **Target List Page ([`frontend/src/pages/TargetListPage.tsx`](../../frontend/src/pages/TargetListPage.tsx)):**
   - Added **Edit** (pencil icon) and **Delete** (trash icon) buttons in the table Actions column.
   - Connected modal state toggles and save/delete triggers.
7. **Target Detail Page ([`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx)):**
   - Added **Edit** and **Delete** buttons to header action area.
   - Automatically navigates back to Dashboard (`/`) upon confirming deletion.

---

## 3. Verification Results

### 3.1 Backend Test Suite (Pytest)
```text
tests/test_api_routes.py ...............                                 [ 12%]
tests/test_auth.py ...................                                   [ 29%]
tests/test_capture.py .....                                              [ 33%]
tests/test_checks.py ............................                        [ 57%]
tests/test_concurrency.py ......                                         [ 62%]
tests/test_diff.py .....                                                 [ 67%]
tests/test_review.py ............                                        [ 77%]
tests/test_scheduler.py ....                                             [ 81%]
tests/test_ssrf_guard.py .......                                         [ 87%]
tests/test_status.py ..                                                  [ 88%]
tests/test_structure.py .............                                    [100%]
======================= 116 passed, 1 warning in 40.71s =======================
```

### 3.2 Backend Code Quality (Ruff & Mypy)
- `ruff check .` : All checks passed!
- `mypy app` : Success: no issues found in 46 source files

### 3.3 Frontend Test Suite (Vitest)
```text
 Test Files  9 passed (9)
      Tests  55 passed (55)
   Duration  3.67s
```
- Verified rendering of Edit and Delete buttons.
- Verified opening Edit Modal, submitting form, and triggering update mutation.
- Verified opening Delete Modal and triggering delete mutation.
- Verified Edit and Delete functionality on Target Detail page.

### 3.4 TypeScript & Production Build
```text
> tsc -b && vite build
✓ 1493 modules transformed.
✓ built in 4.30s (0 errors)
```
