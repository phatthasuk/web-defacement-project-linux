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
- Follow-up review found `/register` was also a session-less mutating route and
  was missing from the list. Added it with its source behavior: 5/minute rate
  limit, creation of an inactive `operator` with `registration_status="pending"`
  and no session, and a `member.registration_submitted` audit event (no actor,
  source `self_registration`) in the same transaction.
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
- Source commit: reviewed against `eed4637c8d9c664b07e3f545dc673da7d66ec2f5`; the
  instruction changes, including the `/register` follow-up, were committed as
  `d35a7f32423e43db6c1f2bc2f47ccbcd062ab48a`.
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

## Follow-up: Isolated Backend Launch Configuration

### Issue

The browser-verification rule required a disposable database, artifact directory
and disabled scheduler, but `.claude/launch.json` only offered `backend`, which
uses `backend/data/app.db` with the scheduler enabled. Setting environment
variables alone is not enough: startup requires a migrated schema and an active
Admin, so a fresh disposable database fails to start.

### Implementation

- Added `backend/scripts/run_isolated_dev.py`. It sets `DATABASE_URL` and
  `DATA_DIR` to a directory outside `backend/data/` (system temp
  `wdm-isolated-dev`, or `WDM_ISOLATED_DIR`), sets `SCHEDULER_ENABLED=false` and
  `ENVIRONMENT=development`, runs `alembic upgrade head` in-process, then starts
  uvicorn on 127.0.0.1:8000 with one worker. It refuses a directory inside
  `backend/data/`. `--create-user ...` runs `scripts/create_user.py` against the
  same disposable database instead of starting the server.
- Added a `backend-isolated` entry to `.claude/launch.json` and pointed
  `AGENTS.md` section 7 at it.
- "Check Now" still performs a real capture through the SSRF proxy; the script
  does not stub capture. The AGENTS.md rule to use only local fixture targets
  still applies.

### Verification

- Date: 2026-10-20, Asia/Bangkok. Environment: Windows, Git Bash, backend venv.
- `WDM_ISOLATED_DIR` set inside `backend/data/`: exited 1 with the refusal
  message; no directory was created.
- `run_isolated_dev.py --create-user isoadmin --role admin` against a scratch
  directory, with a generated password on stdin: migrated the scratch database
  and created the user (exit 0).
- `run_isolated_dev.py` against the same directory: startup completed and
  `GET /health` returned 200 with `{"status":"ok"}`; the scratch directory held
  `app.db` and the artifact subdirectories.
- SHA-256 of `backend/data/app.db` was identical before and after.
- `python -m ruff check scripts/run_isolated_dev.py`: passed.
- `.\.venv\Scripts\alembic.exe` is broken in this venv (exits 1 with no output),
  while `python -m alembic --version` reports 1.13.1. The launcher uses the
  Alembic API, so it is unaffected.
- Not run: starting the `backend-isolated` entry through the preview tool, a
  browser login, pytest, mypy, or Linux runtime.
