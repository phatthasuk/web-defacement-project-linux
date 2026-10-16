# Refinement Record: Stage 2 Soak Test Reset & Restart

**Date:** September 7, 2026  
**Document Name:** `Stage2-Reset-and-Restart-7-9-2026.md`  
**Authoritative Plan Reference:** [`plan/PROJECT_PLAN.md`](../../plan/PROJECT_PLAN.md)  
**Operational Status:** **Stage 2 (Observation Period / Soak Test) — Restarted**  

| Work in this record | Plan mapping | Operational context |
| :--- | :--- | :--- |
| Stage 2 Soak Test Reset & Restart | **Stage 2** (Observation Period / Soak Test) | Cancelled the initial observation run started on Sept 3–4 and restarted a clean soak test run on Sept 7, 2026 to ensure clean telemetry following major system updates. |

**Parent Records:**
- [`refinement/7-9-2026/Check-Result-Summary-Text-Overflow-Fix-7-9-2026.md`](./Check-Result-Summary-Text-Overflow-Fix-7-9-2026.md)
- [`refinement/7-9-2026/Target-Edit-and-Delete-Implementation-7-9-2026.md`](./Target-Edit-and-Delete-Implementation-7-9-2026.md)
- [`refinement/4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md`](../4-9-2026/Defaced-Status-and-Confirm-Defacement-Action-4-9-2026.md)

---

## 1. Executive Summary & Operational Decision

### Background & Decision
The long-term observation soak test (**Stage 2: Observation Period / Soak Test**), which originally began on the Ubuntu Server on September 3–4, 2026, was **cancelled and reset** to officially begin a fresh observation period on **September 7, 2026**.

### Rationale
Between September 4 and September 7, 2026, several critical functional enhancements and architectural fixes were introduced:
1. Addition of the `Defaced` target status and the `Confirm Defacement` operator action (Sept 4, 2026).
2. Addition of Target Name/URL modification and soft-delete capabilities (Sept 7, 2026).
3. CSS text overflow fix in the Result Summary display card (Sept 7, 2026).

Resetting and restarting the observation period on this date ensures that:
- Telemetry and statistical data (detector firing rates, noise floors, failure rates) accumulated over the subsequent 2–4 weeks originate exclusively from the stable, hardened release.
- Score variability and change metrics remain clean and uncontaminated by pre-update artifacts and experimental configurations.

---

## 2. New Timeline & Objectives

- **Start Date:** September 7, 2026
- **Observation Duration:** 2–4 weeks (targeted through approximately September 21 – October 5, 2026).
- **Runtime Environment:** Ubuntu Server (automated hourly checks with jitter).
- **Exit Criteria:** All target sites must run continuously for at least 2 weeks, with verified baseline noise floors and zero unexplained flappings, prior to synthesizing data for Notification Policy design in Stage 3.
