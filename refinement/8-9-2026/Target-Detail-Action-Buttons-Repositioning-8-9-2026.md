# Refinement Record: Target Detail Header Action Buttons Repositioning

**Date:** September 8, 2026  
**Document Name:** `Target-Detail-Action-Buttons-Repositioning-8-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test) — UI/UX Polish**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Target Detail Action Buttons Layout Refinement | Extends **Stage 4** (Operator Tooling & Target Management) | Repositioned Target Management action buttons (`Edit` and `Delete`) on `TargetDetailPage` from the right-hand header action bar to beneath the Target URL, separating entity configuration from operational defacement review actions. |

**Parent Records:**
- [`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](../7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md)
- [`refinement/8-9-2026/Linux-Code-Sync-and-Database-Reset-8-9-2026.md`](./Linux-Code-Sync-and-Database-Reset-8-9-2026.md)

---

## 1. Executive Summary & Operational Rationale

### 1.1 Problem Statement & Operator Feedback
In the initial implementation of the Target Edit and Delete feature ([`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](../7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md)), the **Edit** and **Delete** buttons were placed on the far right of the header bar alongside the primary defacement review actions:
- `Approve as Baseline`
- `Acknowledge Change`
- `Confirm Defacement`

This visual grouping caused semantic and operational confusion:
1. **Semantic Conflation:** Operational triage actions (approving baselines, acknowledging alerts, confirming defacements) were mixed with target administrative settings (editing monitor details, deleting monitors).
2. **Accidental Clicks & Visual Clutter:** Having the destructive `Delete` button immediately adjacent to frequently used operational buttons increased the risk of accidental misclicks during high-pressure defacement reviews.
3. **Information Hierarchy:** The target's identity (name and URL) sits on the left side of the header, but editing/deleting controls for that identity were situated across the screen on the far right.

### 1.2 Solution
The **Edit** and **Delete** buttons were relocated to the left column directly beneath the target URL:
- **Left Column:** Displays target identity (`target.name`), health status badge, target URL (`target.url`), and now the target management action buttons (`Edit` and `Delete`), followed by failure error callouts if applicable.
- **Right Column:** Exclusively dedicated to defacement investigation and triage action buttons (`Approve as Baseline`, `Acknowledge Change`, `Confirm Defacement`).
- **Header Alignment:** Changed container alignment from `md:items-center` to `md:items-start` to maintain a clean top baseline between the target name and the operational action buttons.

---

## 2. Technical Changes

### 2.1 File Modified
* **[`frontend/src/pages/TargetDetailPage.tsx`](../../frontend/src/pages/TargetDetailPage.tsx):**
  - Moved the `Edit` (`data-testid="detail-edit-target-btn"`) and `Delete` (`data-testid="detail-delete-target-btn"`) buttons from the right `flex flex-wrap items-center gap-3` action container to a dedicated `flex items-center gap-2 mt-3` container directly below the URL link.
  - Adjusted button padding to `px-3.5 py-2 rounded-lg text-xs` for optimal visual balance as sub-actions under the URL metadata.
  - Updated `<header>` layout class to `flex flex-col md:flex-row md:items-start md:justify-between gap-6`.

### 2.2 Preserved Functionality
- **Modals:** Modal trigger callbacks `onClick={() => setIsEditModalOpen(true)}` and `onClick={() => setIsDeleteModalOpen(true)}` remain fully wired to `EditTargetModal` and `DeleteTargetModal`.
- **Test IDs:** Maintained `detail-edit-target-btn` and `detail-delete-target-btn` attributes for automated test stability.
- **Responsive Behavior:** Gracefully wraps on mobile and aligns neatly with top baseline on medium and large viewports.

---

## 3. Verification & Quality Assurance

### 3.1 Static Typing & Compilation
- Verified frontend TypeScript compilation cleanly:
  ```bash
  node ./node_modules/typescript/bin/tsc -b
  # Exited with code 0 (0 errors)
  ```

### 3.2 Automated Test Compatibility
- Existing test suites in `frontend/src/pages/TargetDetailPage.test.tsx` and `TargetDetailPage.cache.test.tsx` verify the operational action buttons and cache invalidation behaviors without regression.
