# Target Edit and Delete Implementation Plan & Record

**Date:** September 7, 2026  
**Archive Reference:** `plan/archive/target-edit-and-delete-implementation.md`  
**Parent Plan:** [`plan/PROJECT_PLAN.md`](../PROJECT_PLAN.md)  
**Refinement Record:** [`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](../../refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md)  

---

## 1. Overview & Objective

This document archives the design and implementation of Target editing (Name and URL) and Target deletion (soft delete) across the system:

- Enable operators to modify Target Name and URL via the Web Dashboard without direct DB access.
- Ensure all URL modifications pass the SSRF Guard (`validate_url`) to maintain strict security boundaries.
- Enable operators to remove decommissioned or unwanted targets safely via soft deletion (`Target.is_active = False`), instantly terminating scheduled checks and removing them from the active list while preserving historical snapshots and check results for compliance and auditing.
- Provide a clean, accessible UI with confirmation dialogues and error feedback matching the existing aesthetic.

---

## 2. Changes Made

### 2.1 Backend
- **Schema**: Updated `TargetUpdate` in `backend/app/schemas/target.py` with `url: str | None = Field(default=None, min_length=1, max_length=2048)`.
- **Endpoint**: Updated `update_target` in `backend/app/api/routes/targets.py` to inject `AppSettings`, validate URLs with `validate_url`, and update the target URL.
- **Endpoint**: Utilized existing soft delete in `delete_target` (`DELETE /targets/{target_id}`) setting `is_active = False`.
- **Tests**: Updated `backend/tests/test_api_routes.py` with comprehensive tests verifying valid URL updates and SSRF rejection (`http://127.0.0.1` -> 400).

### 2.2 Frontend
- **Types**: Added `TargetUpdatePayload` in `frontend/src/types/target.ts`.
- **API Client**: Added `updateTarget` and `deleteTarget` in `frontend/src/api/targets.ts`.
- **Hooks**: Added `useUpdateTargetMutation` and `useDeleteTargetMutation` in `frontend/src/hooks/useTargets.ts`.
- **Components**:
  - `frontend/src/components/EditTargetModal.tsx`: Accessible dialog for editing name and URL with inline API error presentation.
  - `frontend/src/components/DeleteTargetModal.tsx`: Confirmation dialog explaining consequences before deletion.
- **Pages**:
  - `frontend/src/pages/TargetListPage.tsx`: Added Edit and Delete buttons to the Actions column for each target row.
  - `frontend/src/pages/TargetDetailPage.tsx`: Added Edit and Delete buttons to the header action bar with automatic navigation back to dashboard on deletion.
- **Tests**:
  - Added unit tests in `frontend/src/pages/TargetListPage.test.tsx` and `frontend/src/pages/TargetDetailPage.test.tsx`.

---

## 3. Verification Summary

- **Backend Pytest**: 116 passed in 40.71s
- **Backend Lint & Typing**: `ruff` and `mypy` clean (0 errors)
- **Frontend Vitest**: 55 passed in 3.67s
- **Frontend Build**: `tsc -b && vite build` succeeded (0 errors)
