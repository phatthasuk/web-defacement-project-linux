# Code Cleanliness Audit Remediation

- Date: 2026-10-21, Asia/Bangkok
- Plan: [plan/Code_Cleanliness_Audit_21-10-2026.md](../../plan/Code_Cleanliness_Audit_21-10-2026.md)
- Environment: Windows checkout, PowerShell, Python 3.13.7, Node v24.7.0
- Scope: Backend services, schemas, and routes (`members`, `tags`, `checks`, `targets`); Frontend pages, API wrappers, types, and hooks (`MembersPage`, `useMembers`, `useTargetDetail`, `date`).

---

## 1. Issue

The Code Cleanliness Audit (2026-10-21) identified eight maintainability and behavioral issues:
1. **P2 Error propagation can hide failures and discard form input (`MembersPage.tsx`)**: loading functions caught errors without propagating them to callers, `act()` cleared shared errors on completion, and `addMember()` unconditionally reset the form even after mutation failure.
2. **P2 Overlapping requests can overwrite newer results (`MembersPage.tsx`)**: search, filters, pagination, and selected-member state changes started unmanaged asynchronous fetches that wrote directly to local state without request identity or cancellation.
3. **P2 Member timestamps bypass the shared UTC utility (`MembersPage.tsx`, `members.py`, `date.ts`)**: naive timestamps returned in raw dictionaries were formatted via raw `new Date(...).toLocaleString()`, producing timezone-dependent display errors for naive UTC inputs.
4. **P2 List endpoints perform queries inside loops (`members.py`, `tags.py`)**: `/members` ran queries in a loop to count target assignments per user; `/member-assignments/websites` queried operator assignees per website in a loop; `/tags` ran queries in a loop to resolve child tags and count active targets per tag.
5. **P2 Member response contracts are weakly typed (`members.py`, `member.py`, `MembersPage.tsx`)**: member endpoints returned untyped dictionaries; request models existed but response models were missing; frontend types used broad strings for roles and statuses.
6. **P3 Member Management combines too many responsibilities (`MembersPage.tsx`, `members.py`)**: `MembersPage.tsx` bundled server state, API fetching, mutation orchestration, and UI components; `members.py` mixed route definitions with business logic, audit recording, and password hashing orchestration.
7. **P3 Cache refresh logic is repeated across mutations (`useTargetDetail.ts`, `useTargets.ts`)**: target detail mutation hooks repeated lists of query keys and refetch operations.
8. **P3 Check persistence is duplicated and baseline guidance is stale (`checks.py`, `targets.py`)**: candidate and changed snapshot creation duplicated artifact promotion and `Snapshot` construction; `targets.py` baseline demotion comments and error text referenced obsolete auto-rebaseline behavior instead of the current candidate / `Awaiting Baseline` workflow.

---

## 2. Implementation

### Backend

1. **Member Schemas (`backend/app/schemas/member.py`, `__init__.py`)**:
   - Added typed response models: `MemberRead`, `PaginatedMembersRead`, `TargetAssigneeRead`, `MemberWebsiteTagRead`, `MemberWebsiteRead`, `MemberWebsitesCountsRead`, `PaginatedMemberWebsitesRead`, `MemberWebsitesListRead`.
   - Added field serializers ensuring naive UTC datetimes (`created_at`, `registration_at`, `registration_reviewed_at`, `last_login_at`) are serialized in explicit ISO 8601 UTC format with trailing `'Z'`.
   - Re-exported member schemas in `backend/app/schemas/__init__.py`.

2. **Member Service (`backend/app/services/members.py`)**:
   - Extracted member business logic, lifecycle rules, assignment persistence, and transactional audit event recording (`MemberAuditEvent`) from the route module into a dedicated service.
   - Implemented `get_member_assigned_counts` to batch-fetch active target assignment counts for all listed users in a single grouped query.
   - Implemented batched assignee querying in `list_assignment_websites` to load all operator assignees for target websites in a single query instead of per-target queries.

3. **Member Route Cleanliness (`backend/app/api/routes/members.py`)**:
   - Refactored routes to delegate business logic to `member_service`, reducing the file from 572 lines to 148 lines.
   - Bound explicit `response_model` definitions to all endpoints.

4. **Tag Hierarchy & Target Count Batching (`backend/app/api/routes/tags.py`)**:
   - Added `batch_active_target_counts` to resolve child tag IDs and query active targets in two batched queries across the page, preserving operator scoping, active target filtering, and parent/child aggregation semantics.

5. **Check Persistence Unification & Demotion Guidance (`backend/app/services/checks.py`, `backend/app/api/routes/targets.py`)**:
   - Extracted `_persist_promoted_snapshot` in `checks.py` to unify artifact promotion and `Snapshot` creation across both initial candidate (`baseline is None`) and genuine change (`has_changes`) paths.
   - Updated baseline demotion comments and `ValidationError` message in `targets.py` to accurately state that removing the only baseline leaves the target without an approved reference, transitioning it to `Awaiting Baseline` on the next check.

### Frontend

1. **Member Types (`frontend/src/types/member.ts`)**:
   - Created shared TypeScript definitions matching backend Pydantic models: `MemberRole` (`'admin' | 'operator'`), `MemberStatus` (`'pending' | 'active' | 'suspended' | 'rejected'`), `Member`, `PaginatedMembers`, `MemberWebsite`, `PaginatedMemberWebsites`, `MemberCreatePayload`, `MemberUpdatePayload`, etc.

2. **Member API Wrapper (`frontend/src/api/members.ts`)**:
   - Created centralized typed fetch functions built on `apiFetch`: `listMembers`, `getMember`, `createMember`, `approveMember`, `rejectMember`, `updateMember`, `resetMemberPassword`, `listMemberWebsites`, `assignMemberWebsite`, `removeMemberWebsiteAssignment`, `listAssignmentWebsites`.

3. **Member Query & Mutation Hooks (`frontend/src/hooks/useMembers.ts`)**:
   - Created TanStack Query hooks with constant keys (`MEMBERS_QUERY_KEY`, `MEMBER_ASSIGNMENTS_QUERY_KEY`, `MEMBER_WEBSITES_QUERY_KEY`).
   - Implemented `invalidateMemberCaches` to ensure coordinated cache invalidation for members, websites, and tags across mutations.

4. **Members Page Modernization (`frontend/src/pages/MembersPage.tsx`)**:
   - Converted to TanStack Query hooks, eliminating unmanaged asynchronous state mutations and race conditions from overlapping filter/search inputs.
   - Preserved form inputs on creation failure: `memberForm` is only reset on mutation success (`onSuccess`); submission errors are displayed via `formError`.
   - Formatted all timestamps (`registration_at`, `last_login_at`) via `formatDateTime` from `src/utils/date.ts`.
   - Maintained distinct loading, error, and empty states for both tabs.

5. **Target Detail Cache Helper (`frontend/src/hooks/useTargetDetail.ts`)**:
   - Centralized `TARGET_DETAIL_QUERY_KEYS` and created `refreshTargetDetailQueries` to eliminate repeated lists of query key invalidations across baseline approval, demotion, acknowledgment, and defacement confirmation mutations.

---

## 3. Verification

### Verification Commands & Results

1. **Targeted Frontend Vitest Suite**:
   ```bash
   cd frontend
   npm run test -- src/pages/MembersPage.test.tsx src/pages/TargetDetailPage.cache.test.tsx src/utils/date.test.ts
   ```
   - Result: 3 passed test files, 20 passed tests.
   - Includes regressions for member creation form retention on failure, timestamp formatting via `formatDateTime`, and target detail cache refresh.

2. **Frontend Linter & Typecheck**:
   ```bash
   cd frontend
   npm run lint
   npm run typecheck
   ```
   - Result: `eslint .` passed with 0 errors and 0 warnings; `tsc -b` passed with 0 diagnostics.

3. **Frontend Production Build**:
   ```bash
   cd frontend
   npm run build
   ```
   - Result: `tsc -b && vite build` succeeded (exit code 0). Built assets generated in `dist/`.

4. **Full Frontend Vitest Suite**:
   ```bash
   cd frontend
   npm run test
   ```
   - Result: 16 passed test files, 111 passed tests.

5. **Backend Code Quality (Ruff & Mypy)**:
   ```bash
   cd backend
   .\.venv\Scripts\ruff.exe check app tests scripts alembic
   .\.venv\Scripts\python.exe -m mypy app
   ```
   - Result: All Ruff checks passed. Mypy reported "Success: no issues found in 65 source files".

6. **Targeted Backend Pytest Suite**:
   ```bash
   cd backend
   .\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp tests/test_member_management.py tests/test_tags.py tests/test_checks.py tests/test_review.py -q
   ```
   - Result: 74 passed tests.
   - Verified UTC `'Z'` serialization, batched assignment queries, batched tag hierarchy counts, and snapshot persistence helpers.

7. **Full Backend Pytest Suite**:
   ```bash
   cd backend
   .\.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp tests -q
   ```
   - Result: 281 passed, 2 failed (the 2 historical Windows environment failures in `test_cleanup_artifacts.py`), 152 warnings in 304.36s.

### Exclusions & Provenance Limitations

- **Full Pytest Suite on Windows**: `test_cleanup_artifacts.py` has 2 expected failures on Windows due to symlink creation privileges (`[WinError 1314]`) and POSIX directory descriptor handling (`O_DIRECTORY`), matching the historical execution record. All other 281 tests pass.
- **Runtime Environment**: Executed on Windows development host. Docker Linux container runtime verification and multi-browser manual verification were not run as part of this code cleanliness task. Node 20 and Python 3.11 runtime compatibility were not verified on Linux.
- **Production Safety**: No production websites, live database (`backend/data/app.db`), or capture artifacts were accessed or altered.
