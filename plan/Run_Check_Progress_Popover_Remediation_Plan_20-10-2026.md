# Run Check Progress Popover — Remediation Plan

**Created:** 2026-10-20 (Asia/Bangkok)

**Source baseline:** `31cf6b279f075b13d830ad658ba40825e0c6f127` plus the uncommitted progress feature.

**Parent:** [Feature plan](Run_Check_Progress_Popover_Plan_20-10-2026.md)

**Evidence:** [Follow-up review](../refinement/10-20-2026/Run-Check-Progress-Popover-20-10-2026.md#follow-up-review--2026-10-20-asiabangkok)

**Remediation status:** Implemented: Complete for the four reviewed defects. Tested: Partial. Runtime verified: Not verified.

The parent feature remains Partial. Existing test passes cover other behavior;
they do not close these findings. This document plans fixes only and does not
authorize deployment or changes to the active Stage 2 observation run.

## 1. Scope and intended result

Resolve the four findings from the follow-up review without adding new finding
IDs or changing the numbered roadmap Stages:

| Review item | Problem | Required result |
| :--- | :--- | :--- |
| 1 — skipped steps | A skipped phase leaves the previous phase running. | Earlier completed operations stop running, skipped operations remain explicitly skipped, and terminal records contain no running steps. |
| 2 — recovered finalization | Generic cleanup publishes Failed after the actual check result was preserved. | Progress agrees with the authoritative check outcome and distinguishes incomplete finalization telemetry from a check failure. |
| 3 — Escape dismissal | Restoring focus invokes the trigger's open-on-focus handler. | Escape closes the panel and restores focus without reopening it. |
| 4 — delayed hover | The pending open timer survives pointer leave. | Moving away before the hover delay expires never opens the panel afterward. |

Primary files: `backend/app/services/check_progress.py`,
`backend/app/services/attempts.py`,
`frontend/src/components/CheckProgressPopover.tsx`, and their regression tests.
Inspect `services/checks.py`, `services/capture/capture.py`, target response
serialization and both target pages where necessary to verify the complete path.

Preserve the single-worker architecture, retry policy, persisted deadlines,
result/attempt ownership, detector scores, baseline approval and artifact lifecycle.
No migration, new dependency, capture behavior change, production capture or
deployment configuration change is expected. Any necessary API field addition
must update the backend schema and frontend types together.

## 2. Fix phase completion around skipped steps

### Cause and approach

`skip_phase()` currently appends a skipped step. Both `set_phase()` and
`finish_progress()` examine only the last step, so an earlier running step can
remain open indefinitely.

Introduce one internal operation that closes the actual active step at a real
phase boundary. Use it consistently when advancing, skipping and finishing.
Skipping a phase must close the preceding successful operation before recording
the skipped phase; it must not mark the skipped phase completed.

Retain idempotent reporting for repeated phase announcements. On a terminal
error, mark only the operation that failed as failed, without completing pending
operations or changing the check outcome. Retain run/revision/attempt ownership
protections so stale reporters cannot mutate a newer run's visible state.

### Regressions and acceptance

- Reproduce `capturing -> skip comparing -> saving_result -> Awaiting Baseline`.
  Capture and saving finish, comparison is skipped, and no step is running.
- Reproduce `opening_page -> skip waiting_page_ready -> capturing` with readiness
  disabled. Navigation completes, readiness is skipped, and capture alone runs.
- Cover ordinary progression, repeated announcements, error termination and
  stale-run reports. Verify ordered start/end timestamps and terminal states.
- Extend pipeline coverage using injected captures and existing capture mocks;
  assertions must inspect progress as well as the durable result.

## 3. Preserve outcomes through attempt-finalization recovery

### Cause and approach

The generic `finally` block treats any remaining running/queued telemetry as an
interrupted failed check, even when `run_target_check()` already returned a real
result and recovery persisted that same outcome.

Track the known check result separately from attempt finalization and actual
cancellation. Make recovery report whether finalization was recovered; do not
infer recovery success from a best-effort helper returning normally after it
has logged an exception.

- Publish completed finalization only after its transaction commits.
- When a real result is known, retain its outcome (`OK`, `Changed`,
  `Awaiting Baseline`, or the real failure) even if finalization recovery fails.
- Surface finalization as unavailable/failed telemetry with a safe diagnostic
  code when its completion cannot be confirmed. Do not present all save steps
  as completed or replace the result with a synthetic check failure.
- Reserve interrupted-check handling for genuinely cancelled/interrupted work
  without a completed result. Preserve existing durable startup recovery.
- Perform identity-guarded cleanup and reset the reporter context exactly once.
  Telemetry failure must not trigger extra capture retries or change a deadline.

If the current response cannot represent the distinction, add a small typed
finalization/telemetry field or make progress explicitly unavailable. Keep the
target's durable status authoritative and use an explicit UI message. Record
the selected representation in the implementation evidence.

### Regressions and acceptance

- Extend `test_attempt_finalization_failure_recovers_target_and_attempt` to
  inspect progress and compare its outcome with the durable target/attempt.
- Cover recovered finalization for `OK`, `Changed` and `Awaiting Baseline`.
- Inject a recovery failure: preserve a known result, display incomplete
  finalization honestly, and do not fabricate a successful save or failed check.
- Cover actual cancellation, capture failure, retry wait, retry exhaustion and
  a newer run/revision taking ownership. Old cleanup must not replace new state.
- Assert that persisted deadlines, artifact references and result IDs retain
  their existing behavior.

## 4. Coordinate popover focus and timers

Implement the two frontend fixes together because dismissal, focus restoration
and delayed pointer events share the same open state.

### Escape and focus restoration

Use a single dismissal path that cancels pending open/close timers and clears
pinned state. Restore focus only when it was inside the panel and the trigger
still exists; do not steal focus from another control during hover dismissal.
Suppress the single focus event caused by that restoration using a synchronous
ref/explicit restoration guard. Later intentional focus must open normally.

Acceptance cases:

- Escape from the trigger and the panel's close button leaves the panel closed.
- Restoring focus does not schedule or immediately reopen the panel.
- Hover-opened Escape preserves focus on an unrelated control.
- A later intentional keyboard focus or click opens normally; tab navigation
  remains usable and no focus trap is introduced.

### Hover-open cancellation

Cancel the pending open timer immediately on pointer leave. Cancel both timers
on explicit dismissal, outside click and unmount. On re-entry, cancel a pending
close before applying the intended hover delay. Timer callbacks must respect
current pointer/focus/pinned state rather than a stale render's closure.

Acceptance cases:

- Enter, leave before 300 ms, and advance timers past both delays: panel stays closed.
- Sustained hover opens after the delay; moving into the panel keeps it open.
- Rapid enter/leave/re-enter produces only the expected current interaction.
- Escape, outside click, click/tap pinning and unmount remain correct even with
  a pending timer. Dismissal never causes a delayed reopening.

Use fake timers with React `act`, assert visible behavior and focus, and restore
real timers in test cleanup even when an assertion fails. Cover the shared
component and its use on target list/detail pages without weakening existing tests.

## 5. Execution order

1. Confirm the four reproductions against the current uncommitted source. Add
   regression assertions that fail before each fix.
2. Repair skipped-phase transitions and run their focused backend tests.
3. Repair finalization/recovery reporting and verify durable outcome consistency.
4. Coordinate focus dismissal and hover timers; run focused interaction tests.
5. Run the relevant complete checks and the isolated browser scenarios below.
6. Add a dated refinement record and update this plan, the parent and status
   register using actual evidence. Keep unresolved criteria open.

## 6. Verification procedures

### Environment preparation

Use the repository backend venv and Node version. Inspect the frontend install
before checks; the review found missing `vitest`, `eslint` and `tsc` executables.
Restore dependencies with the existing lockfile using `npm ci` if needed and
available. Do not upgrade versions or rewrite the lockfile. If installation is
blocked, report the actual reason and leave frontend/browser acceptance open.

Run pytest in disposable directories only. On Windows use a short basetemp:
the review's long workspace path caused ten screenshot-write failures, and all
ten passed when rerun under a shorter temp path. Record sandbox permissions and
the actual resolved temp path; do not treat a failed runner as a pass.

### Backend checks

From `backend/`, first run the focused suites, then the full suite and quality checks:

```powershell
$remediationTemp = Join-Path $env:TEMP 'wdm-popover-remediation'
python -m pytest --basetemp=$remediationTemp tests/test_check_progress.py tests/test_attempts.py -q
python -m pytest --basetemp=$remediationTemp tests -q
ruff check app tests scripts alembic
mypy app
```

Record all failures and warnings. Full Ruff previously reported six findings in
`alembic/versions/7e3a9c2f1b64_durable_check_retries.py`; do not edit an applied
migration to make this feature's quality check green. Report unrelated findings
and targeted changed-file results separately. Windows results do not establish
Linux capture/container verification.

### Frontend and browser checks

From `frontend/`:

```text
npm run test
npm run lint
npm run build
```

Run the app with `backend-isolated` / `scripts/run_isolated_dev.py`, disposable
test users and local mocked responses or controlled fixtures. Do not use the
plain backend with live data or trigger real monitored sites.

Verify hover, early pointer departure, panel entry, Escape from the trigger and
close button, tab navigation, click/tap pinning and outside click. Also inspect
skipped steps, recovered outcomes, retry transitions and completion while open.
Check both target pages, table/viewport edges and a narrow viewport. Record the
browser version and screenshots of material states. No browser pass is implied
by component-test success.

## 7. Completion and evidence

Close each review item only when its regressions fail without the fix and pass
with it, and applicable acceptance criteria have recorded evidence. Keep
Implemented, Tested and Runtime verified independent. Add a record under
`refinement/<M-D-YYYY>/Run-Check-Progress-Popover-Remediation-<D-M-YYYY>.md` with
**Issue**, **Implementation** and **Verification**, including source revision,
exact commands, date/time/timezone, OS/browser versions, results, exclusions
and next action. Preserve the historical review's failed runs.

Implementation and verification evidence: [Remediation record](../refinement/10-20-2026/Run-Check-Progress-Popover-Remediation-20-10-2026.md).

The four code defects have regression coverage and pass the focused suites.
Frontend test, lint and build checks pass. The full backend suite has two
Windows-specific cleanup-artifact failures; browser and Linux runtime acceptance
remain open. Keep Tested Partial and Runtime verified Not verified until those
remaining checks are recorded.
