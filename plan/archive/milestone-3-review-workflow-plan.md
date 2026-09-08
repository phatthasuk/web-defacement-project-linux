# Milestone 3 Development Plan — Review Workflow (Backend Core)

*Handoff document. Builds on the Milestone 1 (Capture Loop) and Milestone 2 (Baseline and Diff) backend core already implemented under `backend/app/`. Corresponds to Milestone 3 in [plan/prototype-plan.md](prototype-plan.md) §11.*

## 1. Goal

Give the system a formal status model and the two review actions the prototype needs to be usable end-to-end without touching the database directly:

- Approve the latest snapshot as the new baseline.
- Acknowledge a `Changed` check result.
- Make status transitions (including capture failure, which Milestone 2 does not yet handle) explicit and consistent instead of ad-hoc strings.

## 2. Scope

**In scope**
- Formal `Target.status` vocabulary and transition rules.
- Capture-failure handling in the check orchestration (`Checking` → `Failed`).
- Baseline approval service.
- Check-result acknowledgment service.
- Unit tests for all of the above.

**Out of scope (deferred)**
- HTTP/API route wiring (`POST /targets/{id}/baseline/approve`, `POST /checks/{id}/ack` from `plan/prototype-plan.md` §7). Milestones 1 and 2 were built as models + services + tests with no route layer; Milestone 3 stays consistent with that pattern. Route wiring for all three milestones' endpoints becomes its own follow-up milestone once this core is stable.
- Any `last_error`/failure-reason field on `Target`. Not part of the current data model in `plan/prototype-plan.md` §6; add it only when a screen actually needs to display it.
- Concurrency, retries, scheduling (Milestone 4).

## 3. Decisions locked for this milestone

These were open questions during design and are now resolved — implementers should not need to re-litigate them:

1. **Service-layer only, no routes this milestone.** Keeps parity with Milestones 1–2 and keeps API design as its own dedicated pass later.
2. **Approving a new baseline auto-acknowledges the `CheckResult` that flagged the change being approved.** Prevents a target sitting at `OK` while its most recent `CheckResult` still shows unacknowledged `Changed`.
3. **No `last_error` field on `Target` in this milestone.** Failure detail is a future dashboard concern, not a workflow concern; deferring keeps the schema change scoped to when it's actually needed.

## 4. Status model

### 4.1 Vocabulary

Add a single source of truth for `Target.status` values — new module `app/core/status.py` — instead of the string literals currently inline in `app/services/checks.py`:

| Status | Meaning |
|---|---|
| `Never Checked` | Target created, no check has run yet (existing `Target` default). |
| `Checking` | A check is currently in flight. New in this milestone. |
| `OK` | Latest check matched the baseline (or this is the first snapshot, auto-baselined). |
| `Changed` | Latest check diverged from baseline and has not been acknowledged. |
| `Failed` | Latest check could not complete (capture error, timeout, etc). New in this milestone. |
| `Acknowledged` | A `Changed` result has been acknowledged; overlays `Changed` until the next check runs. |

### 4.2 Transition table

Also defined in `app/core/status.py`, as data (a dict of allowed `{from: {to, ...}}`), not scattered conditionals — the prototype only has 6 states, so a lookup table is enough; no state-machine library needed.

```
Never Checked -> Checking
Checking      -> OK, Changed, Failed
OK            -> Checking
Changed       -> Checking, Acknowledged
Acknowledged  -> Checking          (overlay only; next check re-derives OK/Changed)
Failed        -> Checking
```

Add a small `is_valid_transition(current, target) -> bool` helper. Whether callers *enforce* it (raise on violation) or just use it in tests is an implementation-time call — recommend enforcing in `checks.py`/`review.py` so an invalid transition fails loudly instead of silently corrupting state.

## 5. Capture-failure handling (`app/services/checks.py`)

`run_target_check` currently has no failure path: if `capture_snapshot` raises, the exception propagates uncaught and nothing is persisted. Fix as part of this milestone, before baseline/ack logic is layered on top:

- Set `target.status = "Checking"` and commit **before** calling `capture_func`, so a check in progress (or one that hangs/fails) is visible to any concurrent reader immediately, not only after the fact.
- Wrap the `capture_func` call. On failure (`CaptureError`, Playwright `TimeoutError`, or any navigation/network exception):
  - Set `target.status = "Failed"` and commit.
  - Do **not** create a `Snapshot` row — there are no artifacts to reference, so a partial row just adds nullable-field complexity for no benefit.
  - Return a result variant that carries the failure (e.g. extend `TargetCheckResult` with an optional error field, or introduce a small `Failed` variant) rather than raising out of `run_target_check`.
- On success, existing logic is unchanged (`OK`/`Changed` derived from the diff).

## 6. Baseline approval (`app/services/review.py`, new file)

`approve_baseline(db: Session, target_id: str, snapshot_id: str) -> Snapshot`

- Load the target and the snapshot; validate the snapshot's `target_id` matches (reject cross-target approval).
- Clear `is_baseline` on whatever snapshot currently holds it for this target (there should be at most one), then set it on the chosen snapshot. Enforced at the service layer, same as `run_target_check` already relies on `is_baseline` being unique per target.
- Set `target.status = "OK"`.
- Per decision #2: find the most recent `CheckResult` for this target with `acknowledged_at IS NULL` and set its `acknowledged_at = now()` as part of the same transaction.
- Commit once; return the updated snapshot.

## 7. Check-result acknowledgment (`app/services/review.py`)

`acknowledge_check_result(db: Session, check_result_id: str) -> CheckResult`

- Load the `CheckResult` and its target.
- Idempotent: if `acknowledged_at` is already set, return as-is without overwriting the timestamp.
- Set `acknowledged_at = now()`.
- Only transition `target.status` to `"Acknowledged"` if this `CheckResult` is the target's most recent one (compare by `created_at` or by id against a fresh query) — acknowledging stale history must not override a more recent `Changed`/`Failed` status.
- Commit; return the updated check result.

## 8. Reconciling `Acknowledged` on the next check

No special-casing needed in `run_target_check` — it already unconditionally derives `target.status` from the current diff (`OK` or `Changed`). `Acknowledged` is naturally overwritten the next time a check runs. Add a regression test asserting this explicitly (see below) so it can't silently regress if `checks.py` is refactored later.

## 9. Sequencing

1. `app/core/status.py` — vocabulary + transition table + `is_valid_transition()`.
2. Capture-failure handling in `checks.py` (depends on step 1 for the `Checking`/`Failed` constants).
3. `app/services/review.py::approve_baseline`.
4. `app/services/review.py::acknowledge_check_result`.
5. Tests (can be written alongside each step rather than batched at the end).

## 10. Test plan

- **Status module**: table-driven test asserting every legal transition passes and a representative set of illegal ones (e.g. `OK → Acknowledged`, `Never Checked → OK`) are rejected.
- **Failure path**: stub `capture_func` to raise → assert `target.status == "Failed"`, no `Snapshot` row created, no unhandled exception escapes `run_target_check`.
- **Checking status**: assert `target.status == "Checking"` is committed before capture completes (e.g. inspect via a second session mid-call, or assert the intermediate commit happened by mocking `capture_func` to check `target.status` inside it).
- **Baseline approval**: rebaselining swaps `is_baseline` from the old snapshot to the new one, resets `target.status` to `"OK"`, and auto-acknowledges the previously-unacknowledged `CheckResult`. Also test cross-target rejection.
- **Acknowledge**: sets `acknowledged_at`; idempotent on double-ack (timestamp unchanged on second call); only updates `target.status` when acknowledging the latest `CheckResult`, not stale history.
- **Post-acknowledgment check**: acknowledge → run another check with a diff → `target.status` moves to `"Changed"` again (not stuck on `"Acknowledged"`).

## 11. Definition of done

- All tests above pass under `pytest`.
- `ruff check .` and `mypy .` clean, consistent with Milestones 1–2.
- No new HTTP routes, no `last_error` field, no concurrency changes — confirms scope held to what's listed in §2.
- `plan/prototype-plan.md` §11 Milestone 3 checklist (approve baseline, acknowledge, simple status transitions) fully covered by the above.

## 12. Handoff notes

- Builds directly on `app/services/checks.py::run_target_check`, `app/models/target.py::Target.status`, `app/models/snapshot.py::Snapshot.is_baseline`, and `app/models/check_result.py::CheckResult.acknowledged_at` — no schema migrations needed for this milestone.
- Route wiring for Milestones 1–3's combined endpoint surface (`plan/prototype-plan.md` §7) is the natural next milestone after this one ships.
- Milestone 4 (Limited Concurrency) will need `"Checking"` to mean something under concurrent access (e.g. preventing two simultaneous checks on the same target) — this milestone only introduces the status value, not concurrency guards around it.
