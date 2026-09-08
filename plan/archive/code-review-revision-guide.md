# Code Review — Backend & Frontend Revision Guide

**Date:** 2026-07-03
**Scope:** Full manual review of `backend/` (FastAPI) and `frontend/` (React + TS + Vite). No git history existed at review time, so the whole codebase was reviewed rather than a diff.
**Overall:** Well-structured prototype. The SSRF guard, status state machine, off-loop diffing, and error handling are more careful than typical prototype code. Findings below are ordered by importance.

---

## Findings Summary

| # | Severity | Area | Finding |
|---|----------|------|---------|
| 1 | Security | `ssrf_guard.py`, `capture.py` | SSRF guard bypassable via DNS rebinding (TOCTOU between guard resolution and Chromium's own resolution) |
| 2 | Bug | `review.py` | Approving a baseline returns HTTP 409 when target status is `Failed` |
| 3 | Concurrency | `concurrency.py` | DB session held open while worker waits on concurrency semaphores |
| 4 | Concurrency | `concurrency.py` | In-flight de-dup and semaphores are process-local; break under multiple uvicorn workers |
| 5 | Minor | `concurrency.py` | `mark_target_failed` bypasses the status state machine |
| 6 | Minor | `db/session.py` | SQLite-specific engine config is unconditional |
| 7 | Minor | `schemas/target.py` | `TargetCreate` allows extra fields while `TargetUpdate` forbids them; no length bounds |
| 8 | Minor | `routes/targets.py`, `routes/checks.py` | No pagination on list endpoints |
| 9 | Minor UX | `TargetListPage.tsx` | One shared `isPending` disables every row's "Run Check" button |

**Things done well (not issues):** Captured HTML is stored but never served back to the browser (only screenshot as `image/png` and text as `text/plain`), and diff/text rendering goes through React escaping — no stored-XSS vector from defaced page content. The redirect limit is enforced twice (route-level and post-navigation), image diffing stays in Pillow's C paths off the event loop, and artifact size caps are checked before writing.

---

## #1 — SSRF DNS rebinding (mitigate + document)

**Files:** `backend/app/core/ssrf_guard.py:33`, `backend/app/services/capture/capture.py:49`

**Problem:** `validate_url` resolves the hostname with `socket.getaddrinfo` and checks the returned IPs, but Chromium does its *own* DNS resolution when it actually connects. Between the guard's lookup and the browser's fetch, an attacker-controlled domain can resolve to a public IP for the check and to `169.254.169.254` / `127.0.0.1` for the real connection. The per-request `page.route` guard re-validates by *hostname* (and caches the verdict per hostname), so it never binds the specific IP the browser connects to. For a tool whose purpose is fetching user-submitted URLs, this is the most significant gap.

**Revision:** You can't fully close this at the application layer, but you can pin the **main target host** to the IP you validated. In `capture.py`, resolve and validate before launch, then force Chromium to use that exact IP via `--host-resolver-rules`:

```python
from app.core.ssrf_guard import resolve_host_ips, validate_url

async def capture_snapshot(url: str, settings: Settings, out_dir: Path) -> CaptureResult:
    validate_url(url, settings)

    hostname = urlparse(url).hostname
    # Pin the browser to the address we just validated so a second DNS
    # lookup inside Chromium cannot be rebound to an internal address.
    pinned_ip = resolve_host_ips(hostname)[0]

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                f"--host-resolver-rules=MAP {hostname} {pinned_ip}",
            ]
        )
```

**Caveats to handle:**

- **Redirects and subresources on other hostnames** still get resolved by Chromium independently. The existing `page.route` guard validates those by hostname, which is still rebindable. That residual risk is acceptable for a prototype, but state it explicitly — add a "Known limitations" note (README or a module docstring in `ssrf_guard.py`): *"SSRF protection validates DNS at request time; hosts other than the primary target can theoretically rebind between validation and connection. Production deployments should run capture workers in an egress-restricted network segment."*
- The `hostname_cache` in `is_url_safe` (`capture.py:41`) actually *helps* here — one verdict per hostname per capture means no re-resolution window mid-capture. Keep it.

**Tests:** Assert the launch args contain a `--host-resolver-rules=MAP` entry for the target host (patch `chromium.launch` and inspect the call), plus keep the existing blocked-address tests.

---

## #2 — `approve_baseline` 409 on `Failed` targets (the one real bug)

**Files:** `backend/app/services/review.py:46`, `backend/app/core/status.py:25`, `frontend/src/pages/TargetDetailPage.tsx:134`

**Problem:** `approve_baseline` unconditionally calls `require_valid_transition(target.status, STATUS_OK)`, but the state machine only allows `Failed → Checking`. Reachable path: a target gets two successful checks (so the latest snapshot is not the baseline), then a later check fails (status `Failed`, no new snapshot). The frontend still shows "Approve as Baseline" because `latestSnapshot && !latestSnapshot.is_baseline`, the user clicks it, and gets a 409 instead of success.

**Revision:** The intent of approving a baseline is "this snapshot is now the trusted state" — a legitimate recovery action from `Failed`. Fix the state machine itself in `status.py`:

```python
STATUS_FAILED: {STATUS_CHECKING, STATUS_OK},
```

Then in `approve_baseline`, also clear the stale error since the target is explicitly healthy again:

```python
require_valid_transition(target.status, STATUS_OK)
target.status = STATUS_OK
target.last_error = None
db.commit()
```

Widening the state machine is preferred over switching to the non-raising `is_valid_transition` (as `acknowledge_check_result` does), because in the acknowledge case skipping is correct semantics (the ack still records even if the status can't move), whereas in the approve case the status change *is* the point — silently leaving the target `Failed` after a successful approve would be confusing.

**One more state to decide on:** `Checking → OK` via approve is currently allowed, meaning a user can approve a baseline while a check is mid-flight, and the check's completion transition (`Checking → OK/Changed/Failed`) will then be invalid and 409 inside `run_target_check`. Cheap fix — reject approvals during a check at the top of `approve_baseline`:

```python
if target.status == STATUS_CHECKING:
    raise ValidationError("Cannot approve a baseline while a check is in progress")
```

**Tests:**
- (a) Two-checks-then-failure scenario → approve succeeds, status becomes `OK`, `last_error` is `None`.
- (b) Approve while `Checking` → 400.

---

## #3 — DB session held across semaphore wait

**File:** `backend/app/services/concurrency.py:84`

**Problem:** The `with session_factory() as db:` opens *before* `async with global_semaphore` / `domain_semaphore`. With `MAX_CONCURRENT_CHECKS=2` and, say, 50 queued targets, ~48 workers each hold an idle DB connection while blocked on the semaphore. Low impact at current scale with SQLite+WAL, but a latent pool-exhaustion issue.

**Revision:** Restructure the worker so the pre-flight checks use a short-lived session that closes before queueing, and the real session opens only after both semaphores are acquired:

```python
try:
    # Pre-flight in a short-lived session so a queued worker does not
    # hold a DB connection while waiting for a semaphore slot.
    with session_factory() as db:
        target = db.get(Target, target_id)
        if target is None:
            return TargetCheckResult(status=RESULT_NOT_FOUND, ..., skipped=True)
        if not target.is_active:
            return TargetCheckResult(status=RESULT_SKIPPED, ..., skipped=True)
        if target.status == STATUS_CHECKING:
            return TargetCheckResult(status=RESULT_SKIPPED, ..., skipped=True)

    async with global_semaphore, domain_semaphore:
        with session_factory() as db:
            # Re-fetch: state may have changed while queued.
            target = db.get(Target, target_id)
            if target is None or not target.is_active or target.status == STATUS_CHECKING:
                return TargetCheckResult(status=RESULT_SKIPPED, ..., skipped=True)
            try:
                return await asyncio.wait_for(
                    run_target_check(db, target, settings, capture_func=capture_func),
                    timeout=timeout,
                )
            except TimeoutError:
                ...  # unchanged
            except Exception:
                ...  # unchanged
finally:
    ...  # unchanged
```

The re-fetch after acquiring the semaphore matters: with the session no longer pinned, the target could have been deactivated or picked up elsewhere while queued. The `_in_flight_targets` set still prevents duplicates within this process, so the re-check is cheap insurance, not the primary guard.

**Tests:** Existing concurrency tests should pass unchanged; add one asserting that a target deactivated *after* the batch is submitted but *before* its slot opens gets skipped (deactivate inside a stub capture func for the target ahead of it in the queue).

---

## #4 — Process-local concurrency guarantees (document, don't build)

**File:** `backend/app/services/concurrency.py:23`

**Problem:** `_in_flight_targets` and the semaphores are module globals, so duplicate-check suppression and concurrency caps only hold within a single process. Under multiple uvicorn workers the guarantees break.

**Revision:** Don't engineer a distributed lock for a prototype. Two small changes:

1. A comment on the module state:

```python
# NOTE: These caps and the in-flight de-dup set are process-local. Running
# uvicorn with multiple workers multiplies the effective concurrency limits
# and defeats duplicate-check suppression. Run a single worker, or move this
# state to the DB/Redis before scaling out.
```

2. Make the constraint operational: wherever the run command lives (README / docker-compose / launch script), pin `--workers 1` explicitly so nobody "fixes" throughput by bumping workers.

---

## #5 — `mark_target_failed` bypasses the state machine

**File:** `backend/app/services/concurrency.py:201`

**Problem:** Sets `status = STATUS_FAILED` directly rather than going through `transition_target`. Functionally fine today (failures come from `Checking`), but inconsistent with the rest of the code.

**Revision:** Here the *skip-if-invalid* pattern is the right one, because this runs in crash/timeout cleanup paths where the target might be in any status, and cleanup must never raise:

```python
target.last_error = error
if is_valid_transition(target.status, STATUS_FAILED):
    target.status = STATUS_FAILED
else:
    logger.warning(
        "Skipping status transition %r -> Failed for target %s", target.status, target_id
    )
db.commit()
```

---

## #6 — SQLite-only engine config is unconditional

**File:** `backend/app/db/session.py:10`

**Problem:** The `check_same_thread` connect arg and the `PRAGMA journal_mode=WAL` listener will break if `DATABASE_URL` is pointed at Postgres.

**Revision:** Gate on the URL dialect:

```python
is_sqlite = settings.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
)

if is_sqlite:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        ...
```

---

## #7 — Schema tightening

**File:** `backend/app/schemas/target.py`

**Problem:** `TargetCreate` allows extra fields while `TargetUpdate` forbids them — inconsistent. `url` is a plain `str` with no length validation and `name` has no max length. (The SSRF guard catches malformed URLs, so this is cosmetic.)

**Revision:** Make create/update symmetric and bound the inputs:

```python
class TargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)

class TargetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_active: bool | None = None
```

Stay with `str` + the SSRF guard rather than Pydantic's `HttpUrl` — `HttpUrl` normalizes URLs (trailing slashes, IDN encoding), and you want to store exactly what the guard validated.

---

## #8 — Pagination on list endpoints

**Files:** `backend/app/api/routes/targets.py:86`, `backend/app/api/routes/checks.py:59`

**Problem:** Unbounded result sets as snapshot/check history grows.

**Revision:** Add bounded `limit`/`offset` query params:

```python
from fastapi import Query

@router.get("/{target_id}/snapshots", response_model=list[SnapshotRead])
async def list_target_snapshots(
    target_id: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Snapshot]:
    ...
    .order_by(Snapshot.captured_at.desc(), Snapshot.id.desc())
    .limit(limit)
    .offset(offset)
```

Same shape for `/targets/{id}/checks` and `/targets`. The frontend needs no change since defaults apply.

**Frontend wrinkle to decide on:** the target-detail page assumes `snapshots[0]` is the latest and `find(is_baseline)` locates the baseline — with pagination the baseline could fall outside the first page once a target has 50+ snapshots. Either keep the baseline pinned in results (e.g. a separate `/targets/{id}/baseline` endpoint) or have the frontend request the baseline snapshot explicitly. Flagged now so pagination doesn't quietly break the compare view later.

---

## #9 — Per-row "Run Check" pending state

**File:** `frontend/src/pages/TargetListPage.tsx:240`

**Problem:** One shared `triggerCheckMutation.isPending` disables every row's "Run Check" button — clicking one target briefly disables all of them.

**Revision:** The mutation exposes its `variables` (the target id), so no extra state is needed:

```tsx
const isRowChecking = (targetId: string) =>
  triggerCheckMutation.isPending && triggerCheckMutation.variables === targetId;
...
disabled={target.status === 'Checking' || isRowChecking(target.id)}
```

---

## Suggested Order of Work

1. **#2 + its two tests** — user-facing bug, small diff.
2. **Minors (#5, #6, #7, #9)** — each is a few lines.
3. **#3** — mechanical restructure, verify the 5 concurrency tests still pass.
4. **#1 pinning + limitation note** — security posture.
5. **#8 pagination** — last, since it has the frontend baseline-visibility wrinkle to decide on.
6. **#4** — documentation-only, fold into whichever PR touches `concurrency.py`.

Everything above is designed to keep the existing test suites (46 pytest / 20 vitest) green except where new tests are called out.
