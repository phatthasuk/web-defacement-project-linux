# Review Issue: OK Targets Stop Automatic Checks

> **Archived 2026-10-19 — code implemented:** Stored here because the scoped code changes exist. Tests and runtime acceptance remain open where recorded; track them in the [active status and backlog register](../../ROADMAP_STATUS_AND_BACKLOG.md). Historical Pending labels below describe the original report.

> October 19 source reconciliation: primitive result IDs, attempt-finalization recovery and schedule-preservation changes exist. The October 16 implementation record reports 73 passing tests; UI/deployment recovery remains unverified. Original investigation and remediation steps below are retained for traceability.
> See [current implementation, test/runtime status and open backlog](../../ROADMAP_STATUS_AND_BACKLOG.md).

**Date**: October 16, 2026  
**Original reviewer**: Argon (Gemini)  
**Edited by**: Sol  
**Document**: `plan/Review issue by Argon Edit by Sol.md`  
**Status**: Reviewed remediation plan; application changes are not implemented by this document update.

## 1. Problem Summary

An unchanged target check can successfully commit an `OK` result but fail while recording its durable attempt. The target remains with `next_check_at = None` and a non-null `check_run_id`, so the background scheduler skips it on subsequent ticks.

The target card consequently stops displaying `Next check`. Approval of a baseline can precede this symptom, but approval itself is not the cause: the next unchanged check encounters the session-boundary bug described below.

## 2. Evidence and Verification Scope

The analysis was compared with `checks.py`, `concurrency.py`, `attempts.py`, `scheduler.py`, `review.py`, the check trigger endpoint, and existing tests. `backend/requirements.txt` pins SQLAlchemy to `2.0.36`; `backend/app/db/session.py` creates `SessionLocal` without overriding the default `expire_on_commit=True`.

The supplied follow-up review reports reproducing `DetachedInstanceError` with SQLAlchemy 2.0.36. Sol verified the execution path against source code but did not independently run that reproduction or the test suite during this document revision. Source references below use function names because line numbers can change.

## 3. Root Cause and Consequences

### 3.1 Expired ORM instance crosses a closed session

In `backend/app/services/checks.py`, the unchanged branch of `run_target_check` loads `matched_baseline` before committing:

```python
matched_baseline = db.get(Snapshot, matched_baseline_id) or baseline
check_result = CheckResult(...)
transition_target(target, STATUS_OK)
db.add(check_result)
db.commit()
db.refresh(check_result)
return TargetCheckResult(
    status=STATUS_OK,
    snapshot=matched_baseline,
    check_result=check_result,
    target_id=target.id,
)
```

Commit expires loaded instances, including `matched_baseline`. The code refreshes `check_result`, but does not refresh the baseline. The worker in `backend/app/services/concurrency.py` then exits `with session_factory() as db:`, detaching the returned instances.

`run_check_attempt` in `backend/app/services/attempts.py` opens a different session and reads:

```python
attempt.check_result_id = result.check_result.id if result.check_result else None
attempt.snapshot_id = result.snapshot.id if result.snapshot else None
```

Reading the expired, detached snapshot's `.id` requires a reload that cannot occur through the closed session, raising `DetachedInstanceError`. Opening another session for the attempt does not attach the returned snapshot to that session.

The normal `Changed` branch refreshes both objects and therefore avoids this specific trigger when refresh succeeds. Its refresh calls are caught and logged, however, so refresh is not a reliable contract for passing identifiers across sessions. The initial `Awaiting Baseline` branch also returns an ORM snapshot and must be covered by the identifier fix.

### 3.2 Attempt finalization and scheduling are rolled back together

The exception occurs before the attempt-recording transaction commits. Although `finished_at` and status have already been assigned in memory, those changes are rolled back when the session exits. The persisted state remains:

- Target: `status = OK`, `next_check_at = None`, and `check_run_id` still set.
- CheckAttempt: `status = Checking` and `finished_at = None`.
- CheckResult: the successful `OK` result already committed by the worker remains persisted.

The later scheduling code never runs, so the run ownership fields are not cleared. The current `finally` block releases the in-memory reservation, but only attempts database scheduling recovery when `attempt_id is None`. It does not recover this failure because an attempt was already created.

### 3.3 Scheduler and UI reflect the incomplete finalization

`CheckScheduler._tick` skips a target with both a null deadline and a non-null run ID, assuming that an active run will persist its deadline.

`frontend/src/pages/TargetListPage.tsx` displays `Next check` only when `!target.check_run_id && target.next_check_at`. The missing label is therefore consistent with the database state; it is not evidence that `OK` targets are intentionally excluded from scheduling.

### 3.4 Restart provides temporary recovery

`recover_stale_checks`, called during application startup, selects targets where `check_run_id IS NOT NULL AND next_check_at IS NULL`, as well as targets still in `Checking`. It closes unfinished attempts with `process_interrupted` and schedules a retry or a routine check according to the configured policy.

This restores scheduling temporarily, but the next unchanged check can encounter the same bug. The target is not permanently unrecoverable: startup recovery can release it, and the manual check endpoint can reserve a new run when no check is active. The precise symptom is that automatic scheduling stalls again after an affected `OK` result.

Startup recovery also misattributes this attempt-finalization failure to process interruption, obscuring the original cause in attempt history.

## 4. Approve Baseline Is Not a Separate Root Cause

`approve_baseline` in `backend/app/services/review.py` updates baseline and review state without changing the scheduling fields. A normal `Changed` check whose attempt finalized successfully already has a routine deadline; approval preserves it. The subsequent unchanged check can then trigger the bug in section 3.1.

A non-null `check_run_id` is not sufficient evidence of a stale run. It also identifies a valid retry waiting for `next_check_at`:

- Clearing the run ID while retaining its deadline causes the next scheduled check to start a new run, losing the existing retry sequence and count.
- Clearing the run ID and replacing the deadline with the routine interval additionally postpones the intended retry.

If both `next_check_at` and `check_run_id` are null, the scheduler already assigns an initial deadline.

**Remove the original Step 3 that resets scheduling in `approve_baseline`.** It is unnecessary for this root-cause fix and can interfere with valid retry state. Keep approval scheduling behavior unchanged; add preservation tests where useful.

## 5. Revised Remediation Plan

### Step 1: Pass primitive result identifiers across sessions

Extend `TargetCheckResult` with primitive `snapshot_id` and `check_result_id` fields. Obtain these values while the producing session is usable, before returning across the session boundary.

For newly inserted records whose IDs are assigned during insertion, explicitly call `db.flush()`, then copy their `.id` values into primitive local variables before `db.commit()`. Return a successful result only after the commit succeeds. This sequence both obtains generated primary keys and avoids depending on an attribute reload after commit expiration. Snapshots constructed with `id=capture.id` already have their identifier, but still require a successful commit before being reported as persisted. If identifiers are read after commit instead, the session must still be usable and any reload failure must be handled; prefer the flush-and-copy sequence.

Update all result-producing branches and constructors consistently, including `OK`, `Changed`, `Awaiting Baseline`, failures, and skipped results. Missing records should have null identifiers.

Change attempt recording to consume the primitive fields directly:

```python
attempt.check_result_id = result.check_result_id
attempt.snapshot_id = result.snapshot_id
```

Preserve the existing `snapshot` and `check_result` attributes for backward compatibility with other callers. Append the new optional ID fields after the existing dataclass fields, defaulting each to `None`, so existing positional and keyword construction remains compatible. Audit result consumers and constructors to ensure every persisted result populates its primitive identifiers explicitly. Retaining the object fields does not make their expired attributes safe to read after session closure.

Attempt finalization must use the primitive fields directly, without falling back to `result.snapshot.id` or `result.check_result.id` when an identifier is missing; that fallback would reintroduce the original failure path. Handle missing required identifiers as an explicit result-contract error.

Adding `refresh(matched_baseline)` is only a local mitigation. Catching refresh exceptions and returning potentially expired objects does not remove the cross-session failure path.

### Step 2: Recover incomplete attempt finalization

Expand the attempt wrapper's recovery path to cover failures after durable attempt creation, using a fresh session after the failed transaction has exited or rolled back.

- Close the specific unfinished attempt owned by this invocation, recording its completion time and the actual finalization error.
- Distinguish a successfully committed website check from failure to persist attempt bookkeeping. Preserve known result status and primitive links where possible; do not falsely report a website failure or process interruption.
- Before changing target scheduling, verify both `target.check_run_id == run_id` and `target.url_revision == url_revision`, and require that no deadline has already been persisted.
- Preserve valid retry deadlines and never overwrite a newer run or URL revision.
- When recovering the current abandoned run to the routine schedule, set the configured interval plus jitter and consistently clear `check_run_id`, `check_run_source`, and `check_attempt_count`.
- Handle failures before attempt creation separately; do not create synthetic completion records for invocations that never started an attempt.
- Log recovery failures without masking the original exception. A database outage can prevent recovery from committing, so this fallback is best effort rather than an absolute guarantee.

Do not rely on `finally` for process termination recovery; retain startup recovery for that case.

### Step 3: Add regression coverage and update scheduler tests

No tests currently call `run_check_attempt` directly. API tests do exercise the check endpoint indirectly, so the accurate gap is missing direct regression coverage of attempt finalization and scheduling across separate sessions.

Use a real SQLAlchemy session factory with `expire_on_commit=True`, separate worker and recording sessions, and a stub capture function. Exercise the actual check/worker path rather than replacing it with already-loaded ORM objects.

Required cases:

1. `OK`: no detached-instance error; completed attempt with correct result and snapshot IDs; routine deadline within the configured interval/jitter range; all run ownership fields reset.
2. `Changed`: completed attempt and correct links, with routine scheduling preserved.
3. `Awaiting Baseline`: completed attempt with its snapshot ID and null check-result ID.
4. Injected finalization failure: the attempt is closed, the error is recorded accurately, and the abandoned current run receives a deadline.
5. Ownership changes: recovery does not overwrite a newer run or URL revision.
6. Retry behavior: an ordinary retry keeps its run identity, count, and persisted retry deadline; fallback does not replace them.
7. Approval behavior: approving a baseline preserves existing valid scheduling fields, including a pending retry where approval is permitted.
8. Startup recovery: a target already in `OK` with an unfinished attempt, a run ID, and no deadline becomes schedulable again.
9. Scheduler progression: after an `OK` check, advance the persisted deadline and verify that a subsequent scheduler tick actually starts another check.

Existing `backend/tests/test_scheduler.py` still refers to `_next_due_times`, which the current scheduler no longer defines. Update these tests to inspect persisted `Target.next_check_at` and the current scheduling behavior before relying on the scheduler suite as validation.

### Step 4: Verify the end-to-end behavior

Run the focused attempt, scheduler, review, and affected API tests. Verify in the UI that completed `OK` and `Changed` checks display the next routine deadline and that a later scheduled check executes. Approve a baseline and confirm that its existing schedule remains intact through the next unchanged check. Verify retry scheduling separately.

## 6. Implementation Order and Acceptance Criteria

Implement primitive IDs first, then guarded finalization recovery, then the regression coverage and scheduler-test updates. Make no scheduling-reset change in `approve_baseline` for this issue.

The fix is accepted when successful checks finalize their attempts and retain automatic scheduling across repeated `OK` results; valid retries and newer runs retain ownership; injected finalization failures are recoverable without misleading history; and affected tests and UI verification pass.

## 7. Deployment and Recovery of Existing Stuck Targets

The code fix prevents new occurrences, but existing database rows may still contain an abandoned `check_run_id` and a null `next_check_at`. Deploy the corrected code and allow the existing startup recovery to run during the normal application restart. It should close unfinished attempts and restore a retry or routine deadline according to the configured policy; no separate database cleanup is normally necessary.

For attempts left by the old bug, the current startup recovery records `process_interrupted`. This is an existing attribution limitation, not proof that a process interruption caused the original failed finalization. The new runtime fallback should record the actual failure as described in Step 2.

If a separate one-time repair is necessary, first establish that no check worker is still executing for the affected targets. Select only confirmed abandoned runs, close the corresponding unfinished attempts, and update scheduling and ownership fields together in a transaction. Do not clear every non-null `check_run_id`: a run with a valid retry deadline must retain its retry state. Avoid issuing an unguarded bulk reset or rerunning startup recovery against live checks.

After deployment recovery, verify that affected targets have persisted deadlines, their attempts are closed, and subsequent scheduled `OK` checks complete without becoming stuck again. This document describes the recovery procedure; updating it does not modify the current database or deploy application code.
