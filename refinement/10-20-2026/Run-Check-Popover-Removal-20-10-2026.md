# Run Check Popover Removal — 20-10-2026

## Issue

The target list and target detail pages wrapped status badges in the Run Check
Progress Popover. The user asked to execute
[`../../plan/Run_Check_Popover_Removal_Plan_20-10-2026.md`](../../plan/Run_Check_Popover_Removal_Plan_20-10-2026.md),
which calls for plain status badges, an inline progress section on target detail,
and a narrow-screen route to that section. The Popover interaction and its
component tests were specific to that retired surface; progress lifecycle
coverage needed replacement ownership before removal.

## Implementation

- Added `CheckProgressDetails` as the shared phase and outcome presenter used by
  Active Checks and target detail. It retains attempt number, retry deadline,
  skipped/failed steps, finished outcome and unconfirmed-finalization messages.
- Added the target detail `#check-progress` disclosure. Active details open by
  default; direct anchor entry opens and focuses the heading. Elapsed time updates
  only while active details are open. Existing target data and refetch state supply
  its content and refresh warning.
- Replaced list/detail wrappers with plain badges and queue/retry text. The list
  shows “View progress” below the existing 1680 px panel breakpoint for active
  runs.
- Removed the Popover component and its interaction tests. Added presenter, detail
  anchor/focus and narrow-layout navigation regressions. Active Checks selection
  and retention code remains in place.
- A source scan found no remaining `CheckProgressPopover` references in
  `frontend/src/`.

## Verification

- **Scope:** frontend only. No backend, migration, deployment, production session,
  monitored site or live check was used.
- **Source revision:** `6b260c407548ccae0b12042c24db70435d22dc52` plus the local
  changes from this implementation; no commit was created.
- **When:** 2026-10-20, Asia/Bangkok.
- **Environment:** Windows NT 10.0.26300.0; Node.js 24.7.0; npm 11.5.1. The
  repository `.nvmrc` specifies Node 20, so this is not the requested Node runtime.
- **`cd frontend; npm run test -- --run`:** Passed, 16 test files and 107 tests.
  Vitest emitted existing Vite configuration deprecation warnings about `esbuild`
  and `optimizeDeps.esbuildOptions`.
- **`cd frontend; npm run lint`:** Passed, no ESLint findings.
- **`cd frontend; npm run build`:** Passed; TypeScript project build and Vite
  production build completed.
- **`git diff --check`:** Passed. `rg -n 'CheckProgressPopover' frontend/src`
  returned no references.
- **Not checked:** isolated browser acceptance at widths 1920, 1680, 1600, 1440,
  1280, 768 and 390 px; 200% zoom; keyboard/touch and resize; screenshot evidence;
  Node 20 execution; Linux/container runtime; broader access/session behavior in
  a browser. The frontend has no installed Playwright, `@playwright/test` or
  Puppeteer package, and no mocked API browser session was provisioned. These
  remain required before marking runtime acceptance verified.
- **Next action:** rerun the frontend commands under Node 20 and complete the
  isolated, mocked-API browser matrix from the plan. Preserve the current
  Implemented status as scoped implementation only, Tested as Partial and Runtime
  verified as Not verified until that evidence exists.
