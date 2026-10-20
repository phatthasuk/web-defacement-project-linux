# Run Check Progress Popover — 20-10-2026

## Issue

The target list showed only `Checking`, so operators could not tell whether a
manual or scheduled check was waiting for capacity, capturing the page, comparing
baselines, saving a result, or waiting for retry. The approved feature plan is
[Run Check Progress Popover](../../plan/archive/delivered-ui-20261020/Run_Check_Progress_Popover_Plan_20-10-2026.md).

## Implementation

- Added a bounded, process-local progress registry keyed by target and guarded
  by run ID and URL revision. It reports queue, navigation, page readiness,
  capture, comparison, result saving, retry wait and finished states without a
  schema migration or writes to `Target.updated_at`.
- Connected registry data to authorized target responses and the existing target
  polling. Added a portal popover for hover, keyboard focus and click/tap, with
  elapsed attempt time, step states, retry deadline, refresh failure and terminal
  result display.
- Added focused backend and frontend regression tests. No detector, baseline,
  capture budget, SSRF or production setting changed.

## Verification

- Date/time: 2026-10-20, Asia/Bangkok. OS: Windows development checkout.
- Source revision before edits: `31cf6b279f075b13d830ad658ba40825e0c6f127`.
- Passed: from `backend/`, `.venv/Scripts/ruff.exe check app/api/routes/targets.py app/api/routes/checks.py app/services/attempts.py app/services/checks.py app/services/capture/capture.py app/services/scheduler.py app/services/check_progress.py tests/test_check_progress.py` — all checks passed.
- Passed: from `backend/`, `.venv/Scripts/python.exe -m mypy app` — 62 source files, no issues.
- Passed: direct execution of all three functions in `tests/test_check_progress.py` using `runpy` — 3 progress assertions passed (scope, step/expiry and stale-run ownership).
- Not passed: `python -m pytest --basetemp=... tests/test_check_progress.py -q` collected both tests but pytest could not finish its temp-directory cleanup; Windows returned `PermissionError: [WinError 5] Access is denied` from `os.scandir` on the selected basetemp. The first attempt using the repository's configured `.pytest-tmp` also failed on the same access restriction. This is not a pytest pass.
- Not passed: full `ruff check app tests scripts alembic` reports six pre-existing findings in `alembic/versions/7e3a9c2f1b64_durable_check_retries.py` (UP035, I001, UP007 and E501); the changed source files pass targeted Ruff.
- Not run: `npm run test`, `npm run lint` and `npm run build`; `frontend/node_modules/.bin` has no executables and npm reports `vitest`, `eslint` and `tsc` are not recognized. Dependencies were not installed or upgraded.
- Not run: isolated frontend/browser verification and Linux Docker capture verification. Docker/runtime status was not changed and no production site or live database was used.
- Next action: run the backend pytest suite and frontend test/lint/build in an environment with accessible pytest temp directories and the repository's installed Node dependencies; then verify popover positioning and interactions using the isolated app configuration. Linux capture/runtime evidence remains separate.

### Follow-up review — 2026-10-20 (Asia/Bangkok)

Source: the same source revision plus the uncommitted feature changes. Review
scope: progress state transitions, attempt finalization, popover interaction and
comparison with the feature plan. Application source was not edited by this review.

Findings (open):

1. `skip_phase` appends a skipped step without completing the current running
   step. The following `set_phase` only examines the last step. An initial
   baseline capture therefore retains `capturing: running` after the check has
   finished. The same occurs for navigation when readiness is disabled.
2. A recovered attempt-finalization failure reaches the generic `finally` path
   and publishes `Failed / check_interrupted`, even though the actual result and
   recovered attempt preserve the successful candidate or comparison outcome.
3. Escape restores focus to the trigger, whose `onFocus` immediately opens the
   popover again if focus was previously elsewhere (including its close button).
4. Pointer leave does not cancel the pending hover-open timer. Entering and
   leaving before 300 ms can open the popover after the pointer has moved away.

Verification performed:

- Passed again: targeted Ruff; `python -m mypy app` (62 files).
- Passed outside the sandbox: `python -m pytest --basetemp=.pytest-popover-review-20261020 tests/test_check_progress.py -q` — 3 passed, 1 Argon2 deprecation warning. Running outside the sandbox resolved the earlier temporary-directory access restriction for this run; the historical failures above remain recorded.
- Reproduced finding 1 with direct in-memory calls: `begin_attempt`, `set_phase('capturing')`, `skip_phase('comparing')`, `set_phase('saving_result')`, `finish_progress('Awaiting Baseline')`. The capture step remains running.
- Reproduced finding 2 by running the existing `test_attempt_finalization_failure_recovers_target_and_attempt` and inspecting the process-local registry afterward: the test passes while the registry reports `('failure-run', 'Failed', 'check_interrupted')`. Its durable result is a baseline candidate.
- Frontend test/lint/build attempts still fail to start because `vitest`, `eslint` and `tsc` executables are absent, including test/build attempts outside the sandbox. Frontend findings are source-level review findings; no browser verification is claimed.
- Pipeline run outside the sandbox, from `backend/`: `.venv/Scripts/python.exe -m pytest --basetemp=.pytest-popover-pipeline-review-20261020 tests/test_attempts.py tests/test_checks.py tests/test_concurrency.py tests/test_scheduler.py tests/test_capture.py tests/test_capture_budgets.py tests/test_capture_failure_classification.py tests/test_check_progress.py -q` — 96 passed, 10 failed, 1 Argon2 deprecation warning, 144.04 seconds. The failures reported `FileNotFoundError` while writing screenshot paths under the long Windows basetemp.
- Reran only those 10 failures with a shorter disposable basetemp: 10 passed, 1 Argon2 deprecation warning, 32.25 seconds. This resolves the path-related failures for that retry; it is not a new single-run result of 106 passes. Exact PowerShell procedure:

  ```powershell
  $reviewTemp = Join-Path $env:TEMP 'wdm-pr-short-review'
  .venv/Scripts/python.exe -m pytest --basetemp=$reviewTemp tests/test_concurrency.py::test_run_checks_for_targets_isolates_expected_capture_failures tests/test_concurrency.py::test_run_checks_for_targets_with_pre_reserved tests/test_capture.py::test_capture_snapshot tests/test_capture.py::test_capture_snapshot_blocks_private_subresource tests/test_capture.py::test_capture_snapshot_allows_iframes_without_consuming_redirect_limit tests/test_capture.py::test_capture_snapshot_routes_all_requests_through_loopback_proxy tests/test_capture.py::test_capture_snapshot_sandbox_configuration tests/test_capture.py::test_capture_does_not_hide_overlay_content tests/test_capture.py::test_capture_snapshot_blocks_file_subresource_from_remote_target -q
  ```

The passing tests do not cover the four findings above. No source fix, production
capture or Linux Docker runtime verification was performed by this review.

Next action: fix these four defects with regressions, complete frontend checks
with the locked project dependencies, and verify the isolated browser workflow.
