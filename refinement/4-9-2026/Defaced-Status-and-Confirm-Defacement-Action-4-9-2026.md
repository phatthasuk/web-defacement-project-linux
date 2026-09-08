# Refinement Record: Defaced Target Status & Confirm Defacement Action

**Date:** September 4, 2026  
**Document Name:** `Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test) Active on Ubuntu Server**  

| Work in this record | Plan mapping | Current operational context |
| :--- | :--- | :--- |
| `Defaced` status & `Confirm Defacement` action | Extends **Stage 3.4 / 4.3** (Review & Status Model) | Running **Stage 2** soak test on Ubuntu Server to observe live target site behavior. |

**Parent Records:**
- [`refinement/3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md`](../3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md)
- [`refinement/3-9-2026/Stage1-Implementation-3-9-2026.md`](../3-9-2026/Stage1-Implementation-3-9-2026.md)

---

## 1. Executive Summary & Operational Context

### Current Operational Context (Stage 2 on Ubuntu Server)
The system is currently undergoing **Stage 2: Observation Period (Soak Test)** on an **Ubuntu Server**, executing automated hourly checks with jitter across live production websites continuously for 2–4 weeks. This observation run captures empirical noise floors, structural shifts, and carousel drift prior to formalizing notification policies in Stage 3.

### Operator Ambiguity in Previous Workflow
When the detection engine flagged a page modification (`Changed`), operators previously had only two actions:
1. **Approve as Baseline (Green):** Accept that the modification represents a legitimate content update &rarr; promote as a new baseline &rarr; target status transitions back to `OK`.
2. **Acknowledge Change (Purple):** Mark the check as acknowledged &rarr; target status transitions to `Acknowledged`.

**The Defect:** The `Acknowledged` state was inherently ambiguous. It indicated only that an operator had reviewed the alert, without distinguishing whether:
- The site had suffered a genuine **malicious defacement incident**.
- The site was actively under security investigation.
- The shift was a benign or transient false positive (flapping carousel, ad tags).

Consequently, during genuine defacements, the dashboard failed to present a high-visibility critical security alert, making it impossible to distinguish hacked websites from routine acknowledged updates.

---

## 2. Implementation Details

### 2.1 Backend Core & Review Service
- **Status Model Definition ([`backend/app/core/status.py`](../../backend/app/core/status.py)):**
  - Added status constant: `STATUS_DEFACED: Final = "Defaced"`.
  - Included `STATUS_DEFACED` in `ALL_TARGET_STATUSES`.
  - Defined explicit state transitions in `ALLOWED_TARGET_STATUS_TRANSITIONS`:
    - `STATUS_CHANGED` &rarr; may transition to `STATUS_DEFACED`.
    - `STATUS_ACKNOWLEDGED` &rarr; may escalate to `STATUS_DEFACED`.
    - `STATUS_DEFACED` &rarr; may transition to `STATUS_CHECKING` (upon next check cycle) or `STATUS_OK` (upon remediation and baseline approval).
- **Review Service Function ([`backend/app/services/review.py`](../../backend/app/services/review.py)):**
  - Added `confirm_defacement(db: Session, check_result_id: str) -> CheckResult`:
    - Stamps `acknowledged_at = datetime.now(UTC)` if not previously set.
    - Transitions target status to `STATUS_DEFACED`.
    - Enforces idempotency and prevents stale checks from overwriting current target status.
- **API Endpoint ([`backend/app/api/routes/review.py`](../../backend/app/api/routes/review.py)):**
  - Added route: `POST /checks/{check_id}/confirm-defaced`, returning `CheckResultRead`.

### 2.2 Frontend UI & State Management
- **Type Definitions ([`frontend/src/types/target.ts`](../../frontend/src/types/target.ts)):**
  - Extended union type `TargetStatus` to include `'Defaced'`.
- **Target Status Badge ([`frontend/src/components/TargetStatusBadge.tsx`](../../frontend/src/components/TargetStatusBadge.tsx)):**
  - Added styling for `Defaced` status:
    - Frame and background: `bg-rose-950/80 border border-rose-600/70 text-rose-300 font-semibold shadow-[0_0_12px_rgba(244,63,94,0.35)]`.
    - Status indicator: Pulsing red beacon (`bg-rose-500 animate-pulse`).
- **API Client & React Query ([`frontend/src/api/checks.ts`](../../frontend/src/api/checks.ts), [`frontend/src/hooks/useTargetDetail.ts`](../../frontend/src/hooks/useTargetDetail.ts)):**
  - Added API client call `confirmDefacedCheck(checkId: string)`.
  - Added hook `useConfirmDefacedMutation()` with cache invalidation for target, checks, baselines, and snapshot queries.
- **Target Detail Action Buttons ([`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx)):**
  - Added **"Confirm Defacement"** button (rose gradient styling).
  - Rendering condition: `canConfirmDefacement = latestCheck && latestCheck.status === 'Changed' && target.status !== 'Defaced'`.
- **Target List Layout & Table Spacing ([`frontend/src/pages/TargetListPage.tsx`](../../frontend/src/pages/TargetListPage.tsx)):**
  - Expanded container to `max-w-7xl` with responsive flex sizing (`lg:w-80 xl:w-96 shrink-0` for form, `flex-1 min-w-0` for table).
  - Protected the `Last Activity` column from line wrapping with `whitespace-nowrap min-w-[190px]`, resolving unwanted horizontal scrollbars.

---

## 3. Operator Actions Summary on Target Detail Page

| Action Button | Accent Color | Target Status Outcome | Operational Intent |
| :--- | :--- | :--- | :--- |
| **Approve as Baseline** | Emerald Green | `OK` | Valid change (legitimate content update); promotes current snapshot as a baseline template. |
| **Acknowledge Change** | Indigo Purple | `Acknowledged` | Acknowledged change under review or investigation without adopting it as a baseline. |
| **Confirm Defacement** | Rose Red | `Defaced` | Confirmed malicious defacement / active security incident requiring urgent intervention. |

---

## 4. Verification Results

### 4.1 Backend Test Suite (Pytest)
```text
tests/test_api_routes.py ...............
tests/test_auth.py ...................
tests/test_capture.py .....
tests/test_checks.py ............................
tests/test_concurrency.py ......
tests/test_diff.py .....
tests/test_review.py ............
tests/test_scheduler.py ....
tests/test_ssrf_guard.py .......
tests/test_status.py ..
tests/test_structure.py .............
======================= 116 passed in 41.87s =======================
```

### 4.2 Frontend Test Suite (Vitest)
```text
✓ src/components/TargetStatusBadge.test.tsx (8 tests)
✓ src/pages/TargetDetailPage.test.tsx (6 tests)
======================= 52 passed in 4.36s =======================
```

### 4.3 TypeScript & Production Build
```text
> tsc -b && vite build
✓ 1491 modules transformed.
✓ built in 3.10s (0 errors)
```

---

## 5. Stage 2 Execution & Deployment on Ubuntu Server

The system has entered **Stage 2 (Observation Period / Soak Test)** and was **deployed to the live Ubuntu Server**:

1. **Ubuntu Server Deployment Status:**
   - The updated release (including `Defaced` status, `Confirm Defacement` action, review API, and frontend UI) was **deployed to the Ubuntu Server**.
   - The SQLite database schema (`app.db`) models `status` as a generic `String`, accommodating the `Defaced` state seamlessly without requiring database migrations.
   - All backend and frontend container services operate normally on the target host.

2. **Continuous Stage 2 Monitoring:**
   - The background scheduler executes automated hourly checks with jitter on the server.
   - Operators can utilize **"Confirm Defacement"**, **"Approve as Baseline"**, and **"Acknowledge Change"** live during detection events.
   - Observation and empirical baseline collection continue over the planned 2–4 week period to prepare for Stage 3 notification policies.
