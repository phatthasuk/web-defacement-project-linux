# Dashboard Right Active Checks — 20-10-2026

## Issue

The dashboard had no authorization-scoped activity feed across filtered or
off-page monitors. Progress was available only through per-row state and the
existing progress popover. The user requested implementation of the right-side
Active Checks plan and explicitly paused further Popover work until production
testing passes.

## Implementation

Added `GET /targets/check-activity` with bounded pagination and
`accessible_targets(...)` scoping. It lists active targets with durable run IDs,
matches optional in-process progress only when target, run and URL revision
agree, and excludes raw URLs and exception text. Added typed response schemas,
frontend API/types/query hooks, four-second polling only at the wide layout,
selection/pagination and explicit loading, empty, missing-progress and refresh
failure states. Added API and UI regressions. The right panel currently appears
at 1680 CSS px; this threshold is provisional pending browser measurement.

The popover was left unchanged as explicitly requested. It therefore remains
alongside the new panel on wide screens, and the planned single detailed surface
and popover replacement are not complete. This also leaves original 1600 px
breakpoint and responsive browser acceptance open.

## Verification

**Date/time:** 2026-10-20, Asia/Bangkok (execution date; exact wall-clock time
not retained in the command transcript).

**Source revision:** `06adbb6923713acf327da7798591da58462fe229` plus the local
uncommitted changes in this checkout.

**Environment:** Windows checkout, Python project venv, installed frontend
Node dependencies, isolated SQLite database at the system temp path. No Linux
container or production host was used.

- Backend focused endpoint tests:
  `.venv/Scripts/python.exe -m pytest --basetemp=<temp>/wdm-active-checks-api-final tests/test_api_routes.py -q -k 'check_activity'`
  — **3 passed, 28 deselected**, 7 warnings.
- Backend full suite:
  `.venv/Scripts/python.exe -m pytest --basetemp=<temp>/wdm-active-checks-full tests -q`
  — **279 passed, 2 failed**, 146 warnings. The two failures are the existing
  Windows cleanup-artifact cases: symlink creation (`WinError 1314`) and POSIX
  directory flags (`PermissionError`). No tests were skipped or altered.
- Targeted Ruff:
  `.venv/Scripts/python.exe -m ruff check app/api/routes/targets.py app/schemas/check_activity.py app/schemas/__init__.py app/services/check_activity.py tests/test_api_routes.py`
  — **passed**.
- Full Ruff:
  `.venv/Scripts/python.exe -m ruff check app tests scripts alembic`
  — **failed with 6 existing findings**, all in the applied migration
  `alembic/versions/7e3a9c2f1b64_durable_check_retries.py` (import style,
  modern typing and one long line). The migration was not edited.
- Mypy: `.venv/Scripts/python.exe -m mypy app` — **64 source files, no issues**.
- Frontend: `npm run test -- --run` — **16 files, 104 tests passed**;
  `npm run lint` — **passed**; `npm run build` — **passed** (TypeScript and Vite).
- Attempted isolated browser launch using `backend/scripts/run_isolated_dev.py`
  and `npm run dev`. The backend started against disposable SQLite and a local
  test Admin was created. Vite failed to start with `Error: spawn EPERM` while
  launching esbuild, so no browser UI was inspected. Isolated server was stopped
  afterward. No target was added and no capture was triggered.
- Not run: full Ruff; Linux/container tests; browser-width, keyboard, touch,
  zoom, authorization-session and resize acceptance; production testing or
  deployment. No production monitor or live evidence was accessed or modified.

**Next action:** resolve the local browser launch limitation and complete the
planned browser/authorization matrix in an isolated environment. Keep the
Popover paused until production acceptance is performed by an explicitly
authorized production procedure; then resume its replacement/deduplication
work and record evidence independently.
