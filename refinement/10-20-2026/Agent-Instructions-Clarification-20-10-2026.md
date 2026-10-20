# Agent instructions clarification

## Issue

The repository instructions had four ambiguities: an absolute session-dependency
rule that did not describe the existing login/logout flows; browser verification
without explicit data isolation; mutable migration/test facts presented as current;
and an artifact checklist that did not acknowledge the tracked screenshot exception.

## Implementation

- Clarified the existing `/login` and `/logout` exceptions after reading
  `backend/app/api/routes/auth.py`. Protected mutations still require session/CSRF
  enforcement; the exceptions cannot be extended to other mutating endpoints.
  The backend route convention now points to the same exceptions.
- Required disposable database/artifact directories, a disabled scheduler, local
  fixtures or mocked responses, and existing SSRF protections for browser checks.
  Inspection of `.claude/launch.json`, `backend/app/core/config.py`, and
  `backend/tests/conftest.py` confirmed that the launch configuration does not
  provide pytest's isolation.
- Replaced the hard-coded migration head with the instruction to check
  `alembic heads`. Dated the reported Windows cleanup result to 2026-10-19,
  linked its execution record and the register's provenance limitations, and
  required a new run before claiming a current result.
- Aligned the completion checklist with disposable test artifacts and the
  existing explicitly requested `backend/data/raw_screenshots/` exception.
  Live evidence and secrets remain protected; committing still requires a request.

Only instructions and this record changed. No application behavior, settings,
finding status, or roadmap acceptance changed, so application README, environment
examples, plan rows, and status register were not updated.

## Verification

- Date: 2026-10-20, Asia/Bangkok (UTC+07:00).
- Environment: Windows, PowerShell, local checkout; no container or browser used.
- Source commit: `eed4637c8d9c664b07e3f545dc673da7d66ec2f5` plus these uncommitted
  documentation changes.
- Read `PROJECT_PLAN.md` sections 2, 4, 5, and 6 and compared the edited rules
  with source and historical evidence. No conflict with those plan sections found.
- `git diff --check`: passed (exit 0). Git warned that LF in `AGENTS.md` will be
  replaced by CRLF the next time Git touches it.
- `git diff -- AGENTS.md`: reviewed the changes for scope and preservation of
  existing security/detection requirements.
- Local-link check procedure: read `AGENTS.md`, extract Markdown link targets,
  strip fragments, URI-decode paths, and call PowerShell `Test-Path -LiteralPath`
  on each target. Passed: all 13 local file targets exist. The two newly added
  fragment targets were also checked against their source headings.
- Auxiliary command from `backend/`: `.\.venv\Scripts\alembic.exe heads`
  exited 1 with no output. No migration-head verification is claimed; diagnosing
  the local executable is outside this documentation task. No migration ran.
- Initial `git status --short` reported no changes but warned:
  `warning: could not open directory 'backend/.audit-tmp-review/': Permission denied`.
  The unreadable directory was not inspected or modified.
- Not run: pytest, Ruff, mypy, frontend tests/lint/build, browser checks, Linux
  runtime verification, or production checks. These edits do not change executable
  code or visible UI. Historical test results were not promoted to current passes.
- Next action: apply the clarified rules during future implementation work and
  collect fresh application/runtime evidence for the scope actually changed.

