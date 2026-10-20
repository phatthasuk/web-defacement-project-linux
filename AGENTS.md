# AGENTS.md — Rules for AI agents working on this repository

Read this whole file before doing any work. It applies to every AI coding agent
(Claude Code, Codex, Copilot, Cursor, etc.) and to every task: code, tests,
documentation, reviews, audits and operations.

If an instruction from the user conflicts with this file, follow the user and say
which rule you are departing from. If this file conflicts with
[plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md), the plan wins; report the conflict.

---

## 1. What this project is

**Web Defacement Monitoring System**: an internal security tool for Bangkok Chain
Hospital (BCH) group websites. It periodically captures each monitored site with
Playwright Chromium, compares the capture against operator-approved baselines with
three **deterministic** detectors (text, visual/pixel, structural DOM), and shows
results to operators in a React dashboard. There is no AI/ML in detection, by
design.

| Layer | Technology |
| :--- | :--- |
| Backend | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, SQLite |
| Capture | Playwright 1.63 (Chromium) behind an in-process SSRF proxy |
| Diff | Pillow (visual), `difflib` (text), stdlib `html.parser` (structural) |
| Frontend | React 18, TypeScript, Vite 5, TanStack Query v5, Tailwind, lucide-react |
| Tests / quality | pytest + pytest-asyncio, Ruff, mypy; Vitest + Testing Library, ESLint, `tsc -b` |
| Deployment | Single Linux host, Docker Compose, Nginx TLS reverse proxy, **one uvicorn worker** |

Development happens on Windows (this checkout); the target runtime is Linux
(Ubuntu) in Docker. Both must keep working.

### Repository map

```
backend/app/api/routes/     HTTP endpoints (auth, members, targets, checks, snapshots, review, tags, config, audit)
backend/app/api/deps.py     DB session, auth session, CSRF, current-user dependencies
backend/app/api/authorization.py  require_admin / accessible_targets / require_target_access
backend/app/core/           config (Settings), errors, security, ssrf_guard, status machine, time
backend/app/models/         SQLAlchemy models
backend/app/schemas/        Pydantic request/response models
backend/app/services/capture/  capture.py, page_ready.py, overlays.py, ssrf_proxy.py
backend/app/services/diff/  diff.py (text + visual), structure.py (structural)
backend/app/services/       checks.py (pipeline), review.py, audit.py, attempts.py, scheduler.py, concurrency.py
backend/alembic/versions/   migrations (linear chain; check current head with alembic heads)
backend/scripts/            create_user.py, cleanup_artifacts.py, smoke_test.py, probes
backend/tests/              pytest suite (conftest.py builds isolated temp DBs)
backend/data/               LIVE/LOCAL DATA: app.db and artifacts — never edit by hand
frontend/src/api/           fetch wrappers on apiFetch (client.ts)
frontend/src/hooks/         TanStack Query hooks, auth context
frontend/src/pages|components|types|utils/
plan/                       active plans + status register; plan/archive/ is history
refinement/<M-D-YYYY>/      dated implementation/remediation records
deploy/                     TLS cert location, Playwright seccomp profile
```

### Required reading by task type

| Task | Read first |
| :--- | :--- |
| Any change | This file, [plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md) sections 2, 4, 5, 6 |
| Picking up open work / claiming status | [plan/ROADMAP_STATUS_AND_BACKLOG.md](plan/ROADMAP_STATUS_AND_BACKLOG.md) |
| Security, SSRF, capture, container | [plan/Review Security 14-10-2026.md](plan/Review%20Security%2014-10-2026.md), [plan/Phase_5_Linux_Container_Runtime_Verification.md](plan/Phase_5_Linux_Container_Runtime_Verification.md) |
| Remediation IDs (B-xx, F-xx, SEC-xx, R2-xx) | [plan/Remediation_Plan_19-10-2026.md](plan/Remediation_Plan_19-10-2026.md), [Round 2 review](plan/Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md) |
| Members / roles / assignments | [plan/archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md](plan/archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md) |
| Deployment / setup | [README.md](README.md), [deploy/certs/README.md](deploy/certs/README.md) |

Files in `plan/archive/` are historical. Do not implement from them unless the
active plan points there; where they disagree with `PROJECT_PLAN.md`, the
active plan wins.

---

## 2. Non-negotiable design principles

These were decided after real failures. Do not reverse, weaken or "optimise"
them without the project owner's explicit approval, and re-read
`PROJECT_PLAN.md` section 4 and 6 before proposing anything nearby.

1. **Never blind the monitor.** A retrieval failure, hidden element or ignored
   region must never be reported as "unchanged".
   - Never inject `display:none` / hide-lists / masking CSS during capture. It
     removes content from both the screenshot and `inner_text`.
     `test_capture_does_not_hide_overlay_content` guards this; never delete or
     weaken it.
   - Never click consent/close/dismiss buttons on monitored pages, even when the
     legacy `DISMISS_OVERLAYS` setting is true. Page handlers are attacker-controlled.
   - The frontend must keep **loading**, **failed** and **successfully empty** as
     distinct states. A failed artifact load must never render as "no differences".
2. **Wait for the page; do not force it into a state.** Waiting for network
   quiet, fonts, lazy images, layout and freezing animations is fine. Hiding
   preloaders or overlays is not.
3. **Detect everything, notify selectively.** Do not lower detection sensitivity
   to reduce noise; noise is handled by notification policy (Stage 3), which is
   not built yet.
4. **A false positive beats a false negative.** When in doubt, report.
5. **Attackers hide below the fold.** Never reduce the monitored surface
   (full-page height is compared; horizontal overflow is clipped to the fixed
   1440 px viewport with the raw screenshot retained).
6. **Baselines require human approval.** First captures and captures after a URL
   change become candidates (`Awaiting Baseline`). Never auto-approve,
   auto-rebaseline, or absorb a detected change into a baseline.
7. **Determinism.** Fixed viewport (1440x900), no randomness in diff scoring, no
   ML. `STRUCTURE_CHANGE_THRESHOLD` stays 0.0. A check is `Changed` only when a
   score is strictly greater than its threshold.

### Rejected approaches — do not re-propose

`ignore_selectors` region masking · scoring only the first viewport · noise
masks in the visual diff (`MASK_LEVEL`) · more carousel-freezing hacks ·
auto-rebaseline on change · Celery/durable queue at current scale · skipping
visual diff when HTML is unchanged (HTML-only hash gate). Reasons are in
`PROJECT_PLAN.md` section 6.

---

## 3. Security invariants

This tool loads hostile web content and controls who can approve "normal".
Treat every change here as security-sensitive.

- **SSRF:** All capture traffic goes through `services/capture/ssrf_proxy.py`
  with DNS validated in `core/ssrf_guard.py` and sockets pinned to validated IPs.
  Never add a code path that fetches a target URL directly (requests/httpx/
  urllib/Playwright without the proxy). Keep private, loopback, link-local,
  IPv4-mapped IPv6 and rebinding protections. Validate URLs with `validate_url`
  on create/update.
- **SSRF blocks are security events.** `SsrfBlockedError` results in `Failed`, never
  `Availability Issue`, and is never retried.
- **Browser hardening:** keep `BROWSER_DISABLE_SANDBOX=false`,
  `BLOCK_WEBSOCKETS=true` and service workers blocked. Do not loosen
  `docker-compose.yml` hardening (non-root user, `read_only`, `cap_drop: ALL`,
  `no-new-privileges`, seccomp profile, resource limits, backend not published,
  fixed proxy-trust IP `172.30.0.2`). `docker-compose.dev.yml` is dev-only and
  must never be used for real monitoring.
- **Capture budgets:** keep the transfer, DOM node, screenshot height/pixel and
  artifact size limits enforced *before* the expensive step. Exceeding one fails
  the capture (`CaptureBudgetExceeded`) and does not retry.
- **Authentication:** cookie session (hashed token in DB, HttpOnly, SameSite),
  Argon2id passwords, lockout and rate limiting. Protected state-changing routes
  must go through `get_current_session` (directly or through an auth dependency)
  so CSRF (`X-CSRF-Token`) is enforced. Existing authentication-flow exceptions
  in `api/routes/auth.py` are limited to `/login`, which establishes a session
  after credential validation with rate limiting and lockout; `/logout`,
  which validates CSRF itself before revoking an existing non-revoked session
  and permits cookie clearing when no such session exists; and `/register`,
  which is rate limited to 5/minute, only creates an inactive `operator` with
  `registration_status="pending"` (no session, no access until an Admin
  approves), and records a `member.registration_submitted` audit event with
  no actor and source `self_registration` in the same transaction. Preserve
  these protections; do not extend these exceptions to other mutating endpoints.
- **Authorization:** fixed roles `admin` and `operator` only.
  - Admin-only actions call `require_admin(user)`.
  - Any query that returns targets, checks, snapshots or artifacts must be
    scoped through `accessible_targets(...)` or `require_target_access(...)`,
    including nested IDs (a check/snapshot ID must belong to an accessible target).
  - Out-of-scope resources return **404**, not 403, to avoid revealing existence.
  - Usernames are matched case-sensitively on purpose; do not add normalization
    without approval.
- **Audit:** review/baseline decisions use `services/audit.record_review_event`;
  member/website/tag changes add a `MemberAuditEvent`. Add the event in the
  **same DB session/transaction** as the change. Record IDs and states only —
  never URLs, page content, passwords or tokens. Follow the existing
  `<entity>.<verb>` action naming (`website.updated`, `baseline.approved`).
- **Structural detector parses hostile HTML.** Keep it on stdlib `html.parser`;
  do not add a new parsing dependency. Inline scripts are stored as hashes only.
- **Secrets:** never read, print, copy or commit `.env` files, `deploy/certs/*.pem`,
  `Bch@Web2026!.txt` or anything that looks like credentials. Use `.env.example`
  for documentation. Redact secrets and sensitive page content from logs,
  evidence and docs.

---

## 4. Backend conventions

- Python 3.11 target, Ruff line length 100, lint rules `E,F,I,UP,B`; code must
  pass `mypy app`. Use modern typing (`X | None`, `list[str]`, `Annotated`).
- Routes: `APIRouter(prefix=..., tags=..., dependencies=[Depends(get_current_user)])`,
  `Annotated` dependency aliases (`DbSession`, `AppSettings`), explicit
  `response_model`. The existing authentication-flow exceptions are described
  in section 3. Keep business logic in `services/`, not in routes.
- Raise domain errors from `core/errors.py` (`NotFoundError`, `ValidationError`,
  `ConflictError`, capture errors); `main.py` maps them to HTTP responses. Do not
  invent ad-hoc error shapes.
- Settings come only from `core/config.py` (`get_settings()`, `lru_cache`d). New
  settings need a typed field with a safe default, validation if it interacts
  with others, an entry in `backend/.env.example`, and a docs update.
- Time: use `core.time.utcnow()` (naive UTC) for anything stored or compared with
  DB timestamps. Never mix aware and naive datetimes. API serialization is UTC.
- Target status changes go through `core/status.py`
  (`require_valid_transition` / `transition_target`). Adding a status or
  transition means updating the transition table, tests and the frontend badge.
- Check pipeline (`services/checks.py`): capture writes to `data/staging/<snapshot_id>/`;
  artifacts are promoted only for baselines/candidates/real changes and discarded
  on `OK`. Keep all filesystem operations confined to `DATA_DIR`. After a commit,
  use primitive IDs captured earlier, not detached ORM attributes.
- Concurrency limits, duplicate suppression and stale-check recovery are
  **process-local**: keep `--workers 1`. Do not add multi-worker assumptions or
  a second scheduler.
- Retries: only transient network errors and HTTP 408/429/500/502/503/504 retry,
  with persisted deadlines (`CheckAttempt`). Budget, SSRF and other HTTP errors
  never retry. Network retries are not Stage 3 content-confirmation checks.
- Keep comments sparse and explanatory of *why*, matching existing code.

## 5. Database and migrations

- Every schema change needs an Alembic migration in `backend/alembic/versions/`
  that chains from the current head (check with `alembic heads`; keep one head),
  with a working `downgrade()`.
- Migrations must be safe for the **existing production SQLite database**: use
  batch operations for SQLite ALTERs, preserve data, and fail before changing the
  schema when a precondition is unmet (see the member-management migration and
  `MEMBER_ROLE_MAPPING`).
- Test migrations on a copy or temp DB, never on `backend/data/app.db`.
- Never edit an already-applied migration; add a new one.

## 6. Frontend conventions

- All HTTP goes through `src/api/*.ts` using `apiFetch` from `src/api/client.ts`.
  It adds `credentials: 'include'`, the in-memory CSRF header and the
  `api:access-denied` event. Do not call `fetch` directly or store the CSRF token
  in localStorage/cookies.
- `BASE_URL` is `VITE_API_BASE_URL` in development and same-origin `/api` in
  production. Never hard-code hosts or IPs.
- Server state lives in TanStack Query hooks under `src/hooks/`, with exported
  query-key constants (e.g. `TARGETS_QUERY_KEY`). Mutations invalidate the
  relevant keys. Preserve `placeholderData` and silent revalidation behavior so
  window focus does not flicker or remount pages.
- Types in `src/types/` mirror backend Pydantic schemas; update both sides
  together when an API changes.
- Role-dependent UI must mirror backend authorization, but the backend is the
  authority. Hiding a button is not access control.
- Timestamps from the API are UTC; display through `src/utils/date.ts`.
- Tests use `render` from `src/test-utils.tsx` (QueryClient + AuthContext,
  `role: 'admin' | 'operator'`). Co-locate tests as `*.test.ts(x)`.
- Styling: Tailwind utility classes in the existing slate dark theme, icons from
  `lucide-react`. Do not add a UI or state library without approval.

---

## 7. Testing and verification

Run the checks relevant to what you changed **before** saying work is done, and
report the actual command and result (pass counts, failures, warnings). Never
claim a pass you did not run.

Backend (from `backend/`, with the venv active —
`.\.venv\Scripts\Activate.ps1` on Windows, `source .venv/bin/activate` on Linux):

```bash
python -m pytest --basetemp=.pytest-tmp tests -q
ruff check app tests scripts alembic
mypy app
```

Frontend (from `frontend/`, Node 20 per `.nvmrc`):

```bash
npm run test
npm run lint
npm run build
```

Rules:

- Bug fixes come with a regression test that fails without the fix.
- Tests must never touch `backend/data/` or a real network target. `conftest.py`
  forces `DATABASE_URL=sqlite:///:memory:` and `SCHEDULER_ENABLED=false`; use its
  temp-DB fixtures and the injectable capture function (`get_capture_func`)
  instead of real browsing. Local fixtures belong in `backend/tests/fixtures/`.
- Authorization changes need tests for admin, assigned operator, unassigned
  operator (404) and unauthenticated (401), plus CSRF on mutations.
- Do not delete, skip or loosen existing tests to make a change pass. If a test
  is wrong, explain why and get agreement.
- Historical Windows result, reported 2026-10-19: `test_cleanup_artifacts.py`
  recorded 7 passed / 2 failed (symlink privilege and POSIX directory operations).
  See [the execution record](plan/Remediation_Plan_19-10-2026.md#61-test-and-tool-results)
  and [the evidence register](plan/ROADMAP_STATUS_AND_BACKLOG.md#evidence-register)
  for provenance limitations. Rerun for the source under review before claiming
  a current result; this history is not an exemption for new failures. Report
  actual failures; do not mark them skipped or passed.
- Capture/SSRF/container behavior can only be truly verified on Linux in Docker.
  Windows results for those areas are partial evidence; say so.
- For visible UI changes, run the app (`.claude/launch.json` defines `backend`
  on :8000 and `frontend` on :5173) and check it in a browser. Use the
  `backend-isolated` configuration (`backend/scripts/run_isolated_dev.py`), not
  `backend`: it points `DATABASE_URL` and `DATA_DIR` at a disposable directory
  outside `backend/data/` (system temp, or `WDM_ISOLATED_DIR`), sets
  `SCHEDULER_ENABLED=false`, and migrates that database. Create its first Admin
  with `python scripts/run_isolated_dev.py --create-user <name> --role admin`.
  The plain `backend` configuration uses live data, and pytest's `conftest.py`
  does not apply to a standalone app. Use only local fixtures or mocked API/capture responses;
  do not trigger captures against real monitored sites. Any required capture
  must use the existing SSRF protections in an isolated test environment.
  Test accounts may be created only in the disposable test database. If browser
  verification cannot be isolated, report it as not run with the reason.

---

## 8. Documentation and evidence rules

This project tracks **Implemented**, **Tested** and **Runtime verified** as
independent states (see the status rules in
[ROADMAP_STATUS_AND_BACKLOG.md](plan/ROADMAP_STATUS_AND_BACKLOG.md)).

- Implemented does not mean Tested; Tested does not mean Runtime verified.
  Test-file existence is not a pass. Windows results are not Linux runtime proof.
- Never close a finding (F-, B-, SEC-, R2-, RV-, Stage items) until **all** of its
  acceptance criteria have evidence. Do not renumber findings or Stages.
- Evidence must record: scope, source commit, exact command or procedure, date
  and timezone (Asia/Bangkok), environment (OS, image digest, browser versions
  where relevant), result, exclusions and next action.
- Historical results stay dated; never rewrite them as current passes or change
  recorded failures.
- After a meaningful implementation or remediation, add a record under
  `refinement/<M-D-YYYY>/<Topic>-<D-M-YYYY>.md` with sections **Issue**,
  **Implementation**, **Verification** (commands and results, and what was *not*
  checked). Update the status register and plan rows only with actual results.
- When docs and source disagree, inspect the source and report the mismatch;
  do not silently "fix" either side to match assumptions.
- Archive a plan to `plan/archive/` only when the user asks; archiving does not
  change Tested or Runtime-verified status.
- Write new docs in English (consistent with the repo). Reply to the user in the
  language they use (often Thai).

---

## 9. Operational safety

- `backend/data/` holds the database and evidence artifacts that may be the only
  record of a defacement. Never delete, reset, rewrite or bulk-modify it, and
  never run `cleanup_artifacts.py --apply-orphans` without the user's explicit
  approval of a reviewed dry-run manifest and confirmation that writers are stopped.
- The Stage 2 observation run may be active on the server. Do not restart, reset
  or re-seed it, change targets, or trigger checks against production sites
  unless the user asks.
- The production host (e.g. `10.117.10.68`) and the monitored hospital websites
  are real. No load tests, security probes, SSRF tests or bulk captures against
  production without written authorization; use local fixtures or an isolated
  test environment.
- Do not run `docker compose down -v`, prune volumes, or change deployment
  config, TLS certs, AppArmor/seccomp or host settings unless asked.
- Never create accounts or set passwords on the user's behalf beyond local test
  databases; `scripts/create_user.py` is interactive for a reason.
- Do not upgrade dependencies, the Playwright image (`v1.63.0-noble` must match
  `playwright==1.63.0`) or Node version as a side effect. Version changes are their
  own task with a changelog and verification.

## 10. Git conventions

- Do not commit, push, create branches or open PRs unless the user asks.
- Commit messages follow Conventional Commits as in history:
  `type(scope): summary` — e.g. `fix(scheduler): ...`, `feat(frontend): ...`,
  `docs(plan): ...`. Types: feat, fix, refactor, style, docs, test, chore.
- Keep commits focused; do not mix unrelated refactors with fixes.
- Never commit `.env`, certificates, `backend/data/app.db*`, captured artifacts,
  `node_modules`, `.venv`, `.pytest-tmp`, caches or build output.
- Exception: `backend/data/raw_screenshots/` is tracked **on purpose** so the
  Linux deployment receives it through git. Do not untrack it, add it to
  `.gitignore` or delete its files. Commit changes there only when the user asks.
- Never rewrite published history or force-push.

---

## 11. Working process and definition of done

1. **Understand:** read the relevant plan and source; confirm current behavior in
   code, not from docs alone.
2. **Scope:** do what was asked. Note other problems you find instead of fixing
   them silently. Ask when a choice affects security, detection sensitivity,
   data or deployment.
3. **Change:** match the surrounding code style; keep backend and frontend
   contracts in sync; add migrations, settings and docs as needed.
4. **Verify:** run section 7 checks for the touched areas.
5. **Report:** state what changed, what was verified (commands and results), what
   was not verified (e.g. Linux runtime, browser), and any follow-up.

A task is done only when:

- [ ] No principle in section 2 or invariant in section 3 was weakened.
- [ ] Relevant tests, Ruff, mypy / Vitest, ESLint, build pass, or failures are reported verbatim.
- [ ] New behavior has tests; schema changes have a reversible migration.
- [ ] `.env.example`, README and plan/register are updated if behavior, settings or status changed.
- [ ] No secrets or live data were modified or committed. Artifact changes are
  limited to disposable test outputs or the explicit user-requested
  `backend/data/raw_screenshots/` exception in section 10; this does not permit
  deletion or modification of live evidence under section 9. No commit was made
  unless the user requested it.
