# Backend Fix Plan

Fix plans for all findings from the backend code review (2026-07-02), ordered by priority.
Each fix is scoped so it can be implemented and tested independently.

Review baseline: all 39 tests passing, ruff and mypy clean.

---

## Fix 1 — Make concurrency caps truly global

**Priority:** High
**Files:** `backend/app/services/concurrency.py`, `backend/app/api/routes/checks.py`

**Problem:** `run_checks_for_targets` creates fresh semaphores on every call, and the trigger
endpoint starts a new call per request. `MAX_CONCURRENT_CHECKS=2` only limits within one
request — ten rapid POSTs to `/targets/{id}/check` launch ten Chromium instances. The
per-domain cap doesn't hold across requests either, and the duplicate-check guard reads
`target.status` before acquiring semaphores while `Checking -> Checking` counts as a valid
transition, so two overlapping triggers for the same target can both run captures.

**Plan:**
1. Move the semaphores out of `run_checks_for_targets` into module-level state: a
   lazily-created `asyncio.Semaphore(settings.MAX_CONCURRENT_CHECKS)` plus a
   `dict[str, asyncio.Semaphore]` for per-domain limits, guarded by a helper like
   `get_global_semaphore(settings)` so they bind to the running event loop on first use
   (uvicorn creates the loop after import).
2. Keep a module-level `set[str]` of target IDs currently being checked, added/removed in
   the worker inside a `try/finally`. Skip (return `RESULT_SKIPPED`) when the ID is already
   in the set — closes the read-status-then-race window without relying on DB status.
3. In `trigger_target_check`, return `accepted=False` (or a 409) when the target's status is
   already `Checking`, so the UI gets immediate feedback instead of a silently skipped
   background task.
4. Since per-domain semaphores now persist, prune entries when their domain has no active
   checks to avoid unbounded growth.

**Tests:** simulate two overlapping `run_checks_for_targets` calls sharing one event loop and
assert combined max concurrency <= cap; assert a second trigger on an in-flight target skips.

---

## Fix 2 — Validate subresource requests in the SSRF guard

**Priority:** High
**Files:** `backend/app/services/capture/capture.py`, `backend/app/core/ssrf_guard.py`

**Problem:** Non-navigation requests are passed through unvalidated, so images, scripts, and
`fetch()` calls on the monitored page can reach private/internal addresses. A defaced
(attacker-controlled) page can make the monitoring server probe the internal network. Also,
`validate_url` resolves DNS separately from Chromium's own fetch (DNS-rebinding TOCTOU).

**Plan:**
1. In `guard_navigation`, remove the early `continue_()` for non-navigation requests: run
   `validate_url` on every routed request. For subresources, abort quietly on violation
   (don't set `blocked_error` — a defaced page pulling an internal URL shouldn't fail the
   capture; the abort itself is the protection). Only navigation requests keep the
   "set `blocked_error` and abort" behavior.
2. `validate_url` does blocking DNS; called per-request it would stall the loop. Wrap it as
   `await asyncio.to_thread(validate_url, ...)` inside the route handler, and add a small
   in-capture memo dict `{hostname: bool}` so each unique host resolves once per capture.
3. Allow `data:` and `blob:` URLs through without resolution (they have no host and the
   scheme check would reject them — verify and special-case).
4. Document DNS rebinding as a known limitation in a comment on `validate_url` (a real fix
   means pinning resolved IPs via a proxy, out of scope for the prototype).

**Tests:** unit test the route handler with a fake subresource request to a private IP and
assert it's aborted; assert `data:` images still load in the capture fixture.

---

## Fix 3 — Give checks a realistic timeout budget

**Priority:** High
**Files:** `backend/app/core/config.py`, `backend/app/services/concurrency.py`,
`backend/app/services/diff/diff.py`

**Problem:** The `wait_for` allowance is `PAGE_TIMEOUT_SECONDS + 5`, but inside it are
browser launch, navigation (which alone may use the full page timeout), a full-page
screenshot, artifact writes, and the diff. `SequenceMatcher` on large texts (up to 10 MB)
can take far longer than 5 seconds, so a slow-but-healthy target gets marked `Failed`
spuriously. `asyncio.to_thread` work also isn't cancellable, so after a timeout the diff
thread keeps running.

**Plan:**
1. Add `CHECK_TIMEOUT_SECONDS: int = 90` to `Settings` and use it as the `wait_for` default
   instead of `PAGE_TIMEOUT_SECONDS + 5`. Navigation stays bounded by
   `PAGE_TIMEOUT_SECONDS`; the outer budget covers launch + screenshot + writes + diff.
2. Cap the diff cost instead of hoping it's fast: switch `SequenceMatcher` to line-based
   comparison (`splitlines()`), which is orders of magnitude faster on big pages and still
   gives a stable 0-1 change ratio. Keep character-level only if both texts are small
   (e.g., < 100 KB).
3. Note in a comment that `to_thread` work survives cancellation — with the line-based diff
   its worst case is short, which makes the orphan-thread problem moot.

**Note:** changes score semantics — may need to re-tune `TEXT_CHANGE_THRESHOLD` after
switching to line-based scoring.

**Tests:** existing diff tests updated for line-based scores; add a test that two large texts
diff in well under a second.

---

## Fix 4 — Count only main-frame redirects

**Priority:** High
**Files:** `backend/app/services/capture/capture.py`

**Problem:** `navigation_request_count` increments for every navigation request in any frame,
so a page with more than `REDIRECT_LIMIT` iframes has its later iframes aborted. Because the
main navigation already succeeded, `blocked_error` is set but never raised — the capture
silently proceeds with missing iframes, making diffs noisy and nondeterministic.

**Plan:**
1. In `guard_navigation`, only increment `navigation_request_count` when
   `request.frame == page.main_frame`. Iframe navigations still go through SSRF validation
   (per Fix 2) but never consume redirect budget.
2. Keep the post-navigation `redirected_from` walk as the authoritative count; the in-flight
   counter is just the early-abort guard against redirect loops.

**Tests:** capture a fixture page containing several iframes with `REDIRECT_LIMIT=2` and
assert the capture succeeds with `redirect_count == 0`.

---

## Fix 5 — Block checks on inactive targets

**Priority:** Medium
**Files:** `backend/app/api/routes/checks.py`, `backend/app/services/concurrency.py`

**Problem:** `trigger_target_check` verifies existence but not `is_active`, so a
soft-deleted target keeps consuming capture capacity if anything still triggers it.

**Plan:**
1. In `trigger_target_check`, raise `ValidationError("Target is inactive")` (-> 400) when
   `target.is_active` is false.
2. Add the same guard in the worker (return a skipped result) so batch/scheduled callers
   can't bypass it either.

**Tests:** API test — delete a target, trigger a check, expect 400 and no capture call
recorded.

---

## Fix 6 — SQLite busy timeout + WAL in production engine

**Priority:** Medium
**Files:** `backend/app/db/session.py`

**Problem:** Test engines pass `timeout: 30` but the production engine doesn't, so
concurrent background commits can raise `database is locked`.

**Plan:**
1. Add `"timeout": 30` to `connect_args` (matches what the tests already use).
2. Enable WAL once via an `event.listens_for(engine, "connect")` hook executing
   `PRAGMA journal_mode=WAL` — readers stop blocking the background writer.

**Tests:** covered indirectly by the concurrency tests; no dedicated test needed.

---

## Fix 7 — Persist and log check failures

**Priority:** Medium
**Files:** `backend/app/services/checks.py`, `backend/app/services/concurrency.py`,
`backend/app/models/target.py`, `backend/app/schemas/target.py`

**Problem:** A failed background check stores `Failed` on the target but the error string in
`TargetCheckResult.error` is discarded (nobody consumes the background task's return value).
An unexpected exception in `asyncio.gather` (no `return_exceptions`) kills the sibling
results. There is no logging anywhere — when a check fails in production there's no way to
find out why.

**Plan:**
1. Add module-level loggers; log at `warning` on capture failure/timeout (with target ID and
   error) and `exception` for unexpected errors.
2. Store the failure reason: add a nullable `last_error: Mapped[str | None]` column to
   `Target` (set on failure, cleared on success). The prototype uses `create_all` with no
   migrations — existing dev DBs need deleting or a manual `ALTER TABLE`; flag this in the
   commit message.
3. Change `asyncio.gather(...)` to `return_exceptions=True`, convert exception entries into
   `STATUS_FAILED` results with the stringified error, and log them — one crashed worker no
   longer discards its siblings' results or blows up the background task silently.
4. Expose `last_error` in `TargetRead` so the frontend can show why a check failed.

**Tests:** trigger with a capture func that raises; assert target ends `Failed` with
`last_error` set, and a sibling target in the same batch still completes.

---

## Fix 8 — Allow acknowledging a check while target is Failed

**Priority:** Medium
**Files:** `backend/app/services/review.py` (or `backend/app/core/status.py`)

**Problem:** If the latest capture failed (target status `Failed`), acknowledging the most
recent `Changed` check raises `InvalidStatusTransitionError` (409) because
`Failed -> Acknowledged` isn't allowed.

**Plan:** In `acknowledge_check_result`, only transition the target when
`is_valid_transition(target.status, STATUS_ACKNOWLEDGED)` holds; otherwise still mark the
check row acknowledged and leave target status alone. The ack itself should never 409.

**Tests:** target in `Failed` with an unacked `Changed` check -> ack succeeds, check has
`acknowledged_at`, target stays `Failed`.

---

## Fix 9 — Test artifacts to tmp_path

**Priority:** Low
**Files:** `backend/tests/conftest.py`, `backend/tests/test_concurrency.py`,
`backend/tests/test_capture.py`, plus test_checks/test_diff if they share the helper

**Problem:** Tests write artifacts into the repo at `data/test-artifacts/` with no cleanup.

**Plan:**
1. Replace `Path("data") / "test-artifacts" / ...` with pytest's `tmp_path` fixture (thread
   the fixture into `make_session_factory` as a parameter).
2. Delete any existing `data/test-artifacts` directory from the working tree.

**Tests:** the suite itself; verify `data/` stays clean after a run.

---

## Fix 10 — Silence the pytest-asyncio deprecation

**Priority:** Low
**Files:** `backend/pyproject.toml`

**Plan:** Add `asyncio_default_fixture_loop_scope = "function"` under
`[tool.pytest.ini_options]`. One line, no behavior change.

---

## Suggested implementation order

1. **Fix 10, Fix 9** — trivial, clean test output first.
2. **Fix 6, Fix 5, Fix 8** — small and independent.
3. **Fix 1 + Fix 7** — touch the same files (concurrency.py); do together.
4. **Fix 2 + Fix 4** — same function in capture.py; do together.
5. **Fix 3** — last, since the diff change affects score semantics and
   `TEXT_CHANGE_THRESHOLD` may need re-tuning afterwards.

Fixes 3 and 7 change observable behavior the frontend will care about (`last_error` field,
score scale), so land them before starting frontend work. Run the full test suite
(`pytest`), `ruff check .`, and `mypy app` after each group.
