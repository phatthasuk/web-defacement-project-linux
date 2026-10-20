# Run Check Progress Popover Remediation — 20-10-2026

## Issue

The 2026-10-20 follow-up review identified four defects: skipped phases could
leave earlier steps Running, recovered attempt finalization could publish a
synthetic Failed result, Escape dismissal could reopen the popover through focus
restoration, and a delayed hover timer could open the panel after pointer leave.
The source baseline was commit `31cf6b279f075b13d830ad658ba40825e0c6f127` plus
the uncommitted feature implementation. This remediation does not change
detector behavior, capture policy, durable retry deadlines or deployment.

## Implementation

- Phase transitions now close the actual running step before recording a skipped
  phase. Finishing and retry transitions also close the active step, so a
  terminal progress record cannot retain a Running step.
- Attempt finalization recovery returns whether it committed. A known check
  result remains the displayed outcome through recovery; unconfirmed finalization
  is marked with the safe diagnostic `attempt_finalization_unconfirmed` and an
  explicit UI message. Interrupted-check status is reserved for paths without a
  known result.
- Popover dismissal clears both timers. Pointer leave cancels pending hover-open;
  Escape restores focus only from inside the panel and suppresses the resulting
  focus event. Focus elsewhere is preserved. Re-entry clears delayed close.
- Added backend regressions for skipped readiness/comparison and recovered
  result consistency, plus frontend regressions for early pointer leave, Escape
  from the close control, focus preservation and later intentional focus.

## Verification

- Date/time: 2026-10-20, approximately 12:00 Asia/Bangkok. OS: Windows 11
  development checkout. Source revision: `31cf6b279f075b13d830ad658ba40825e0c6f127`
  plus the uncommitted implementation and remediation changes. No Linux image or
  browser runtime version applies because isolated browser/runtime verification
  was not run.
- Passed: from `backend/`,
  `$temp = Join-Path $env:TEMP 'wdm-popover-remediation-focused-final'; .venv/Scripts/python.exe -m pytest --basetemp=$temp tests/test_check_progress.py tests/test_attempts.py tests/test_checks.py -q`
  — 54 passed, 1 Argon2 deprecation warning, 7.38 seconds. The command used a
  disposable temp path; pytest was run outside the sandbox after Windows denied
  access to pytest temporary directories inside it.
- Full backend suite: from `backend/`,
  `$temp = Join-Path $env:TEMP 'wdm-popover-remediation-full2'; .venv/Scripts/python.exe -m pytest --basetemp=$temp tests -q`
  — 276 passed, 2 failed, 140 warnings, 131.42 seconds. Both failures are in
  `test_cleanup_artifacts.py`: Windows symlink creation requires a privilege and
  the POSIX `O_DIRECTORY`/`O_NOFOLLOW` directory operation is unsupported. No
  tests were skipped or weakened.
- Passed: from `backend/`,
  `.venv/Scripts/python.exe -m ruff check app/services/check_progress.py app/services/attempts.py tests/test_check_progress.py tests/test_attempts.py`
  — all checks passed.
- Passed: from `backend/`, `.venv/Scripts/python.exe -m mypy app` — 62 source
  files, no issues. Full `ruff check app tests scripts alembic` still reports
  six findings in the pre-existing applied migration
  `alembic/versions/7e3a9c2f1b64_durable_check_retries.py`; that migration was
  not edited.
- Passed: from `frontend/`, `npm run test -- --run` — 15 files, 100 tests
  passed. Vite emitted existing option deprecation warnings.
- Passed: from `frontend/`, `npm run lint` — exit 0, no warnings.
- Passed: from `frontend/`, `npm run build` — TypeScript build and Vite production
  build succeeded. Dependencies were restored with `npm ci` from the existing
  lockfile; no dependency or lockfile changes were made.
- Not run: isolated browser checks of popover position and interactions on both
  target pages, including narrow viewport and table-edge positioning. No
  isolated backend/frontend app session was launched for this remediation.
- Not run: Linux Docker capture/runtime checks. No production site, live database,
  or Stage 2 observation run was accessed or changed.
- Status: Implemented complete for the four reviewed defects; Tested Partial
  because the complete Windows backend suite retains two platform-specific
  failures; Runtime verified Not verified. Next action: run the isolated browser
  acceptance checks and the Linux runtime subset, then update the independent
  status fields with their actual results.
