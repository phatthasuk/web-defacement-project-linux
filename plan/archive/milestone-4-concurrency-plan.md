# Milestone 4 Development Plan — Limited Concurrency (Backend Core)

*Handoff document. Builds on the Milestone 1–3 backend core (`app/services/capture`, `app/services/checks.py::run_target_check`, `app/core/status.py`, `app/services/review.py`). Corresponds to Milestone 4 in [plan/prototype-plan.md](prototype-plan.md) §11, using the concurrency model specified in §4.*

## 1. Goal

Today, `run_target_check()` only knows how to check one target at a time, called directly. Milestone 4 adds a bounded way to run checks across *multiple* targets at once — capped globally and per-domain — without changing what a single check does. Per §4: "the prototype should support limited concurrency from the beginning... but should not attempt production-scale crawling."

## 2. Scope

**In scope**
- A global concurrency cap on simultaneous checks (`Settings.MAX_CONCURRENT_CHECKS`, already `2` in config — just unused today).
- A per-domain concurrency cap (`Settings.PER_DOMAIN_CONCURRENCY`, already `1`).
- Defense-in-depth wall-clock timeout per check, on top of Playwright's own navigation timeout.
- A guard against double-checking the same target if it's already in flight.
- Tests proving the caps actually hold under concurrent load, using a fake/slow `capture_func` (no real Playwright/browser needed for the concurrency tests themselves).

**Out of scope (deferred)**
- Any HTTP route to trigger a batch run — same "core first, routes later" pattern as Milestones 1–3.
- Real periodic/cron scheduling ("Basic scheduled checks" is explicitly "if time allows" in §2, and separate from the concurrency mechanism itself). This milestone builds the bounded *runner*; wiring it to a timer is a later, optional step.
- Celery/Redis or any distributed queue — explicitly excluded from the prototype (§13: "Do not add Celery on day one").

## 3. Decisions to lock before/while building

1. **Each concurrent check must use its own DB session — not the caller's shared `Session`.** This isn't a style preference: SQLAlchemy's `Session` is not safe for concurrent use by multiple coroutines at once, and `run_target_check` commits mid-flow (`Checking` → then later `OK`/`Changed`/`Failed`). Running several targets concurrently against one shared session risks corrupted state or lost updates. The orchestrator must open a fresh `SessionLocal()` per target, load that target fresh in it, run the check, then close it — not receive `Target`/`Session` objects from a caller's outer session.
2. **Skip a target that's already `Checking` instead of double-running it.** Two overlapping checks on the same target (e.g. a manual "Run Check" click while a scheduled batch is already checking it) would race on the same row. Recommend the orchestrator loads each target's current status immediately before dispatching and silently skips (records as "skipped", not "failed") any target already `Checking`, rather than relying on `transition_target` to catch it — today `is_valid_transition` treats `Checking -> Checking` as a same-status no-op, so it would *not* raise, which means this race is currently invisible unless guarded explicitly here.
3. **Add a wall-clock timeout around the whole per-target check, not just Playwright's page-load timeout.** `Settings.PAGE_TIMEOUT_SECONDS` already bounds navigation inside `capture_snapshot`, but wrapping the entire `run_target_check` call in `asyncio.wait_for(..., timeout=settings.PAGE_TIMEOUT_SECONDS + buffer)` protects against a hang anywhere outside the page-load step (e.g. a stuck browser close). On timeout, treat it exactly like a capture failure: transition to `Failed`.

## 4. New module: `app/services/concurrency.py`

(Named to describe what it actually does — a bounded concurrent runner — rather than "scheduler," since no periodic triggering is in scope yet.)

- `async def run_checks_for_targets(target_ids: list[str], settings: Settings, capture_func: CaptureFunc = capture_snapshot) -> list[TargetCheckResult]`
  - Creates one global `asyncio.Semaphore(settings.MAX_CONCURRENT_CHECKS)`.
  - Creates one `asyncio.Semaphore(settings.PER_DOMAIN_CONCURRENCY)` per distinct hostname among `target_ids` (hostname via `urllib.parse.urlparse(target.url).hostname`), stored in a `dict[str, asyncio.Semaphore]` built up front from a single query for all targets.
  - For each target id, a worker coroutine that:
    1. Opens its own `SessionLocal()`.
    2. Loads the `Target`; if not found or `status == STATUS_CHECKING`, closes the session and returns a "skipped" result (decision #2) — do not acquire any semaphore for a skipped target.
    3. Acquires the global semaphore, then the per-domain semaphore for that target's hostname (in that order, consistently, to avoid deadlock).
    4. Runs `run_target_check` wrapped in `asyncio.wait_for(...)` (decision #3); a `TimeoutError` is handled the same way `run_target_check` handles a capture exception (transition to `Failed`, commit, release semaphores in `finally`).
    5. Releases both semaphores (via `async with`, not manual acquire/release) and closes the session.
  - Runs all worker coroutines with `asyncio.gather(..., return_exceptions=False)` — an unexpected bug in one worker should surface, not be silently swallowed; expected failures (capture errors, timeouts) are already converted to a normal `TargetCheckResult` inside the worker, not raised.
  - Returns the list of results (including skips) in the same order as the input `target_ids`, so callers can match results back to targets.

## 5. Sequencing

1. Hostname-grouping helper + semaphore-map construction (small, testable in isolation).
2. Per-target worker coroutine (session-per-task, status guard, semaphore acquisition order).
3. Timeout wrapping around `run_target_check` inside the worker.
4. `run_checks_for_targets` orchestrator wiring workers together with `asyncio.gather`.
5. Tests (concurrency limits are the part most worth testing early — write the fake slow `capture_func` first, since steps 2–4 are hard to verify without it).

## 6. Test plan

- **Global cap holds**: N targets (distinct domains) with a `capture_func` stub that increments a shared counter, sleeps briefly, decrements — assert the observed max concurrent count never exceeds `MAX_CONCURRENT_CHECKS`.
- **Per-domain cap holds**: several targets on the *same* hostname — assert max concurrent count for that hostname never exceeds `PER_DOMAIN_CONCURRENCY`, while targets on other hostnames still proceed in parallel up to the global cap.
- **Already-checking target is skipped, not double-run**: pre-set a target's status to `Checking`, include it in the batch, assert the stub `capture_func` is never invoked for it and the result reports "skipped".
- **Timeout produces `Failed`, not a hang**: a `capture_func` stub that sleeps longer than the wrapped timeout — assert the target ends in `Failed` and the overall batch still completes (doesn't hang waiting on it).
- **Isolation**: one target's `capture_func` raises — assert other targets in the same batch still complete normally (`asyncio.gather` config from step 4 matters here).
- **Session isolation**: assert each worker's DB writes are visible after `run_checks_for_targets` returns (i.e. results are actually committed, not lost because a per-task session wasn't properly closed/committed).

## 7. Definition of done

- All tests above pass under `pytest`.
- `ruff check .` and `mypy .` clean.
- No new HTTP routes, no scheduling/cron, no Celery — confirms scope held to §2.
- Running a batch of targets with a real (non-stubbed) `capture_snapshot` against a small local fixture set stays within the configured global/per-domain caps (a manual sanity check, not necessarily an automated test, since it involves real Playwright timing).

## 8. Handoff notes

- Depends on nothing new in the data model — `Settings.MAX_CONCURRENT_CHECKS` and `Settings.PER_DOMAIN_CONCURRENCY` already exist in `app/core/config.py` and `.env.example`, just unused until now.
- `run_target_check`'s existing signature (`db: Session, target: Target, settings: Settings`) stays as-is for the single-target case; `run_checks_for_targets` is an additive orchestration layer on top, not a replacement.
- Once this lands, the natural following milestone is the API-wiring pass deferred since Milestone 1 (`POST /targets/{id}/check` for a single target, plus something like `POST /checks/run` for a batch backed by `run_checks_for_targets`) — see `plan/prototype-plan.md` §7. Milestone 5 (Prototype Hardening: SSRF guard, fixture tests, smoke test script) can proceed independently of that route-wiring pass.
