# Stage 2 / Stage 3 planning update — 22 October 2026

## Issue

The Stage 2 exit gate did not specify reproducible coverage, independent labels
or treatment of configuration changes. The Stage 3 hypothesis could leave
visual-only incidents without a bounded review route, and confirmation lacked
finding identity, failure outcomes and restart acceptance. The register already
mentioned delivery persistence and health proposals, but their minimum release
obligations needed to be explicit in the core roadmap.

Source reviewed: `00ae0599f6b2859ffc1c8a1c80573e0714b93453`.
Date: 2026-10-22 (Asia/Bangkok). Environment: Windows / PowerShell, local checkout.
Scope: documentation only; no production or monitoring-data inspection this turn.

## Implementation

- Updated [PROJECT_PLAN.md](../../plan/PROJECT_PLAN.md) with a Stage 2 observation
  manifest and per-target evidence contract. Planning defaults are 14 monitored
  days, 95% scheduled terminal-run coverage, no unexplained gap above 3 hours,
  and at least two human-labelled samples/day/target. These are new planning
  criteria, not historic measurements, statistical guarantees or deployed settings.
- Distinguished successful comparisons from completed failures, scheduled runs
  from manual/network retries, and independent labels from detector status.
  Recorded OK-artifact disposal and historical zero-column limitations.
- Expanded Stage 3 policy, finding-specific confirmation, persistent delivery,
  recipient checks, visual review, availability and independent monitoring-health
  acceptance. Concrete channel/timer choices and named owners remain open.
- Corrected the source/document mismatch: missing baseline HTML yields
  unavailable in the diff helper, but `checks.py` raises CaptureError and fails
  the check, including in multi-baseline comparisons. No source behavior changed.
- Updated the [status register](../../plan/ROADMAP_STATUS_AND_BACKLOG.md) to align
  backlog ownership and distinguish minimum Stage 3 dependencies from broader
  proposed add-on UIs. Stage numbers, historical audit and all application
  Implemented/Tested/Runtime-verified statuses are preserved.

## Verification

Documentation checks executed on 2026-10-22 at approximately 10:53–10:55
Asia/Bangkok in Windows PowerShell:

- `git diff --check`: passed, exit 0. Git emitted a line-ending warning for
  ROADMAP_STATUS_AND_BACKLOG.md (LF will be replaced by CRLF on a later Git
  operation); no whitespace errors were reported.
- Local-link check via a Python script passed to `python -` using a PowerShell
  here-string: passed, 63 links checked, 0 missing. Procedure: read the three
  changed Markdown files as UTF-8, extract Markdown link targets with
  `\]\(([^)]+)\)`, skip schemes and fragment-only links, strip fragments,
  URL-decode paths, resolve relative to each document and require Path.exists().
  This checks file/directory existence, not heading anchors or external URLs.
- `git diff -- plan/PROJECT_PLAN.md plan/ROADMAP_STATUS_AND_BACKLOG.md`:
  reviewed the complete tracked diff; stage numbering and historical results
  are preserved. The new execution record was reviewed separately.
- `git status --short --untracked-files=all -- plan/PROJECT_PLAN.md plan/ROADMAP_STATUS_AND_BACKLOG.md refinement/10-22-2026`:
  final scope check covers the two edited plans and the new record only.

Application tests, migrations, browser checks, Linux/Docker runtime, provider
delivery and current production coverage were not run: this change edits plans
only. No secrets, application code, configuration, live data or historical audit
records were modified; no restart, capture, commit, branch or deployment occurred.

Next action: assign observation/policy owners, reconcile the deployed target
manifest through authorized read-only collection, and produce Stage 2 evidence
sheets before approving notification routing. This record does not close either
Stage or any security finding.
