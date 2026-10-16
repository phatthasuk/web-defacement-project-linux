# Future Plan: Auto-rebaseline + Decision State Machine

**Status:** Future plan — Not yet started; pending security policy decisions.  
**Origin:** Prototype `python_project_website_checker/visual-checker` — `monitor.py` (`monitor_once`) + `monitor_helper/baseline_logic.py`.  
**Related to:** [plan/capture-improvements.md](../capture-improvements.md) (Prerequisites: items 1 and 2).

---

## Why Separated as a Future Plan

Originally item 4 in the consolidated list, this component was separated due to being **security-sensitive**, unlike items 1–3 which carry lower capture/diff risk:

- ⚠️ **Auto-rebaseline is a double-edged sword**: If an attacker defaces a webpage and the system automatically records the defaced page as a new baseline, the system effectively conceals the intrusion.
- ⚠️ **Conflicts with the existing human-approval workflow**: The current architecture is deliberately designed around human decision-making (`review.py`, `acknowledge`, `approve baseline`). Automated rebaselining contradicts this principle.
- ⚠️ **Requires multi-baseline support (Item 2)**: Database schema and baseline history capabilities must be established first.
- ⚠️ **Requires strict policy alignment prior to implementation**: What degree of automation should be permitted? Is human approval mandatory? How should audit logs be retained?

---

## Scope Implemented in Prototype (Reference)

### Three-Way Decision State Machine (`monitor_once`)
- `ratio ≤ threshold` → **Match** (Record `matched_baseline` without raising an alert).
- `ratio > threshold` **AND** an overlay was dismissed (`cookie_dismissed` / `promo_closed`) → **Rebaseline** (Without raising an alert).
- `ratio > threshold` solely → **Alert** + append new baseline (`_alert_and_append`).

### Distinguishing Overlay Changes from Defacement
- Leverages `cookie_dismissed` / `promo_closed` flags from capture improvements (Item 1).
- Controlled via environment flags: `REBASELINE_ON_COOKIE`, `REBASELINE_ON_OVERLAY` (toggleable).

### Conditional Auto-Rebaseline (`_rebaseline`)
- Stores current snapshot as new baseline + prunes stale baselines + logs rationale + references `closest_baseline`.
- Dispatches notifications indicating why the rebaseline occurred.

### Attaching Visual Diffs to Notifications (`_alert_and_append`)
- Attaches 3-panel comparison previews (from capture improvements Item 3) to Slack/webhook notifications upon alerting.

---

## Decision Checklist Prior to Implementation

- [ ] Is auto-rebaseline strictly restricted to **overlay-triggered cases only**? (Must never be applied to general diffs).
- [ ] Is **human approval** mandatory prior to rebaselining, or can it operate autonomously?
- [ ] How will **audit logging** be recorded for each rebaseline (actor/timestamp/reason/before-and-after artifacts)?
- [ ] Will this integrate directly into the existing review workflow (`review.py`) or follow a separate pipeline?
- [ ] Can thresholds and policies be customized per target (stricter enforcement for critical services)?
- [ ] Is there an automated rollback mechanism if an incorrect rebaseline occurs?

---

## Core Security Principles

1. **Auto-rebaseline must remain strictly bounded** — Confined solely to overlay-triggered events as demonstrated in the prototype, never extended to general visual diffs.
2. **Every rebaseline action requires an immutable audit trail**.
3. **Default to human-in-the-loop** — Automated behavior should be an explicit opt-in per target, not an application default.
