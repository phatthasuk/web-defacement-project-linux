# OK Target Scheduling Fix — 16-10-2026

## Issue

An unchanged target check could commit its `OK` result, then fail while the attempt wrapper read the expired, detached baseline snapshot ID. The attempt transaction consequently rolled back before closing the attempt or scheduling the next check. The target retained a `check_run_id` and no `next_check_at`, so the scheduler skipped it.

## Implementation

- Extended `TargetCheckResult` with optional primitive `snapshot_id` and `check_result_id` fields while retaining the existing ORM object fields for callers.
- Populated primitive IDs in the `Awaiting Baseline`, `Changed`, and `OK` result branches. For generated check-result IDs, the producing session flushes before copying the ID; the values are passed to attempt recording without reading ORM IDs across sessions.
- Updated attempt finalization to use the primitive IDs and added best-effort recovery after a finalization failure. Recovery closes the owned unfinished attempt with the actual bookkeeping error and schedules the target only if the same run and URL revision still own it and no deadline exists. A persisted retry deadline and newer run are preserved.
- Updated scheduler tests to assert persisted database deadlines rather than the removed `_next_due_times` state.
- Added attempt regression coverage for `OK`, `Changed`, `Awaiting Baseline`, injected finalization failure, retry-deadline preservation, ownership changes, startup recovery, and a subsequent scheduled `OK` check.

## Verification

Command run from `backend`:

```text
python -m pytest tests/test_attempts.py tests/test_scheduler.py tests/test_checks.py tests/test_review.py -q
```

Initial result: **71 passed**, with one existing `argon2` deprecation warning.

UI behavior was not manually checked. This code change does not modify production data or run deployment recovery; existing stuck rows should be released by the normal startup recovery after deploying and restarting the application.

## Follow-up: Refresh Failure Logging and Approval Schedule Preservation

- Captured `target_id` before the check's first commit and used the primitive value in logs and returned results after commits. The baseline refresh failure log now uses its previously captured `snapshot_id`.
- Added tests that force snapshot refresh to fail after commit in both `Awaiting Baseline` and `Changed` results, then verify the durable attempt still records its primitive IDs.
- Added parameterized approval tests for routine scheduling and pending retry state. Both verify that `next_check_at`, `check_run_id`, `check_run_source`, and `check_attempt_count` remain unchanged after reloading the target.

Updated verification command result: **73 passed**, with one existing `argon2` deprecation warning.

