# Milestone 6 Development Plan — API & Routes Wiring (Backend Core)

*Handoff document. Exposes the service-layer logic built in Milestones 1–5 (`app/services/capture`, `app/services/checks.py`, `app/services/review.py`, `app/services/concurrency.py`, `app/core/ssrf_guard.py`) over HTTP, per the endpoint spec in [plan/prototype-plan.md](prototype-plan.md) §7. This is the last backend milestone before the frontend dashboard (§8) has anything to call.*

## 1. Goal

Every capability the backend has (capture, diff, baseline approval, acknowledgment, bounded concurrent checks, SSRF-safe fetching) currently exists only as Python functions exercised by tests. This milestone wires them behind FastAPI routes so a real client — the future dashboard, or `curl` in the meantime — can drive the whole loop: register a target, run a check, inspect the diff, approve a baseline, acknowledge a change.

## 2. Scope

**In scope**
- Full route set from §7: Targets, Checks, Snapshots, Baselines, Review.
- Pydantic request/response schemas in `app/schemas/`.
- Consistent error-to-HTTP-status mapping (today, service functions raise bare `ValueError`/`InvalidStatusTransitionError`, which would surface as opaque 500s if routed directly).
- Test-DB isolation infrastructure for route-level tests (new — prior milestones tested services directly, never through the HTTP layer).
- The smoke-test script deferred from Milestone 5 — now meaningful because there's an actual API to run it against.

**Out of scope (deferred)**
- Auth (`plan/prototype-plan.md` explicitly excludes multi-team/RBAC/SSO from the prototype).
- The frontend itself — this milestone only makes the backend callable.
- Real scheduling/cron for automatic checks (still manual-trigger only, per prototype scope).

## 3. Decisions to lock before/while building

1. **`POST /targets/{id}/check` triggers the check as a background task, not synchronously in the request.** A single check can take up to `PAGE_TIMEOUT_SECONDS` (+ buffer) to complete; blocking the HTTP response for that long is poor UX for a "Run Check" button. Schedule it via FastAPI's `BackgroundTasks`, return immediately, and let the client poll `GET /targets/{id}` to watch `status` move `Checking → OK/Changed/Failed` — this is exactly why Milestone 3 introduced the `Checking` status in the first place. **Explicitly document that `BackgroundTasks` is an in-process mechanism tied to the API server's lifecycle** — it is not a durable job queue: a server restart or crash mid-check loses the in-flight task with no retry or persistence. That's an acceptable prototype tradeoff (matches "avoid Celery on day one" from `plan/prototype-plan.md` §13), but it must be written down here so it isn't mistaken for a queue later.
2. **Reuse `run_checks_for_targets([target_id], settings)` for the single-target route, not `run_target_check` directly.** It already gives us, for free, everything a route handler would otherwise have to reimplement: its own DB session per call (never share the request's session with a background task), and the "skip if already `Checking`" guard (Milestone 4 decision #2) — which now doubles as protection against a user double-clicking "Run Check." **The route must still confirm the target exists synchronously, before scheduling the background task** — `run_checks_for_targets`'s own missing-target handling only runs *inside* the background task, so without this check a request for a nonexistent target would get a `202`-style accepted response and fail invisibly in the background. Do `db.get(Target, id)` in the route handler and raise `NotFoundError` (404) immediately if it's missing, before touching `BackgroundTasks` at all.
3. **`POST /targets/{id}/check` returns a lightweight acceptance response, not `TargetRead`.** Since the status transition to `Checking` happens once the background task actually starts — after the response has already been sent — returning `TargetRead` would imply a current-state snapshot that isn't actually current, and invites callers (and tests) to wrongly assume `status == "Checking"` in the response body. Return a dedicated `CheckTriggerResponse {target_id: str, accepted: bool}` instead, and assert the eventual status only via a follow-up `GET /targets/{id}` (after awaiting/flushing the background task in tests — see §8).
4. **Replace bare `ValueError` in `review.py`/`checks.py` with a small typed exception hierarchy**, so routes can map errors to correct HTTP status codes instead of everything falling through as a 500. Add to the existing `app/core/errors.py` (which already holds `CaptureError`/`SsrfBlockedError`): a `NotFoundError` (→ 404) and a `ValidationError` (→ 400) base, plus reuse the existing `InvalidStatusTransitionError` from `app/core/status.py` (→ 409 Conflict — it's a legitimate state conflict, not a generic bad request). `review.py`'s current "target not found" / "snapshot not found" / "cross-target mismatch" `ValueError`s get reclassified into these, and a single FastAPI exception handler in `main.py` maps each type to its status code — no route needs its own try/except for this. See the full mapping table in §5.1.
5. **Make check-triggering testable without a real browser, without letting the background task re-enter FastAPI's DI system.** Declare `capture_func: CaptureFunc = Depends(get_capture_func)` as a parameter directly on the `POST /targets/{id}/check` route function — FastAPI resolves it once, synchronously, within the request (before the response is sent). The route handler then passes that **already-resolved value** as a plain argument into `background_tasks.add_task(run_checks_for_targets, [target_id], settings, capture_func=capture_func)`. The background task itself must never call `get_capture_func()` (or any `Depends`-wrapped provider) on its own after the response has gone out — `BackgroundTasks` just invokes a plain callable with plain arguments, it does not run FastAPI's dependency resolution again, so anything the task needs must be captured as a value at request time. Tests override `get_capture_func` via `app.dependency_overrides`, which affects the value resolved during the request, exactly as with `get_db`/`get_settings`.
6. **`PATCH /targets/{id}` allows updating `name` and `is_active` only — not `url` — and rejects the request outright if `url` is present, rather than silently ignoring it.** Changing a target's URL after it has snapshots/baseline conceptually means monitoring a different page; rather than defining reset semantics for baseline/status on a URL change, keep `url` immutable after creation. Silently dropping an unrecognized field would mislead a client into thinking the update applied. Enforce this at the schema level: `TargetUpdate` sets `model_config = ConfigDict(extra="forbid")`, so a payload containing `url` (or any other unknown field) fails Pydantic validation and FastAPI returns `422` automatically — no manual check needed in the route body. If a target's URL needs to change, delete and recreate it. Flagging this as the one schema-level product call in this milestone — revisit if the dashboard workflow needs otherwise.
7. **`DELETE /targets/{id}` is a soft delete** (`is_active = False`), not a row delete. `Snapshot`/`CheckResult` reference `target_id` by FK with no cascade configured, and SQLite doesn't enforce FKs by default anyway (`PRAGMA foreign_keys` isn't currently turned on in `app/db/session.py`) — hard-deleting would either silently orphan history or need cascade semantics nobody has designed yet. `is_active` already exists on `Target` for exactly this purpose; reuse it rather than introducing delete semantics now.

## 4. New modules

- `app/schemas/target.py` — `TargetCreate` (`name`, `url`), `TargetUpdate` (`name`, `is_active`, both optional, `model_config = ConfigDict(extra="forbid")` per decision #6), `TargetRead` (mirrors the ORM model).
- `app/schemas/check_result.py` — `CheckResultRead` (status, scores, summary, snapshot ids, `acknowledged_at`).
- `app/schemas/snapshot.py` — `SnapshotRead` (metadata only — `screenshot_path`/`text_path`/`html_path` are server-internal; expose them only indirectly via the download routes below, not as raw filesystem paths in the JSON body).
- `app/schemas/review.py` — `BaselineApproveRequest` (`snapshot_id`).
- `app/schemas/check_trigger.py` — `CheckTriggerResponse` (`target_id: str`, `accepted: bool`) — decision #3.
- **Every `*Read` schema (`TargetRead`, `CheckResultRead`, `SnapshotRead`) sets `model_config = ConfigDict(from_attributes=True)`** (Pydantic v2's replacement for v1's `orm_mode`) — routes return SQLAlchemy ORM instances directly (e.g. `db.get(Target, id)`), and without `from_attributes=True` Pydantic v2 can't validate/serialize a response model from an arbitrary object's attributes.
- `app/api/deps.py` — `get_capture_func()` (decision #5); re-exports `get_db`/`get_settings` for route modules to import from one place.
- `app/api/routes/targets.py`, `checks.py`, `snapshots.py`, `review.py` — one `APIRouter` per resource, each `include_router()`-ed in `app/main.py`.
- `app/core/errors.py` — extended with `NotFoundError`/`ValidationError` (decision #4).

## 5. Endpoint-to-service mapping

### 5.1 Exception → HTTP status mapping (single handler in `app/main.py`)

| Exception (`app/core/errors.py` unless noted) | HTTP status |
|---|---|
| `NotFoundError` | 404 |
| `ValidationError` | 400 |
| `SsrfBlockedError` | 400 |
| `InvalidStatusTransitionError` (`app/core/status.py`) | 409 |

Registered once via `@app.exception_handler(...)` per type (or one handler keyed on a common base if the hierarchy supports it) — no route should need its own try/except for these.

### 5.2 Routes

| Endpoint | Service call | Notes |
|---|---|---|
| `POST /targets` | `db.add(Target(...))` | Calls `ssrf_guard.validate_url(payload.url, settings)` before insert — reject unsafe URLs at creation time, per the reuse this function was explicitly designed for in Milestone 5. `SsrfBlockedError` → 400 per §5.1. |
| `GET /targets` | plain query, filtered by `is_active` unless overridden | Takes `include_inactive: bool = False` query param — required, not optional, since it's the only way to verify a soft-delete (decision #7) actually happened without querying the DB directly. Low cost to add. |
| `GET /targets/{id}` | `db.get(Target, id)` | 404 via `NotFoundError` if missing. |
| `PATCH /targets/{id}` | update `name`/`is_active` | See decision #6 — `url` in the payload → `422` via `extra="forbid"`, not silently ignored. |
| `DELETE /targets/{id}` | set `is_active = False` | See decision #7. |
| `POST /targets/{id}/check` | `db.get(Target, id)` existence check, then `run_checks_for_targets([id], settings, capture_func=...)` via `BackgroundTasks` | See decisions #1–2, #3, #5. Returns `CheckTriggerResponse {target_id, accepted}` — not `TargetRead`. Missing target → `404` before any background task is scheduled (decision #2). |
| `GET /checks/{id}` | `db.get(CheckResult, id)` | 404 if missing. |
| `GET /targets/{id}/checks` | `db.get(Target, id)` existence check, then query `CheckResult` by `target_id`, ordered by `created_at desc` | Checking target existence first matters: a real target with zero checks yet must return `200` with `[]`, while a nonexistent target must return `404` — an empty list alone can't distinguish the two. |
| `GET /snapshots/{id}` | `db.get(Snapshot, id)` | Metadata only, per `SnapshotRead` above. |
| `GET /snapshots/{id}/screenshot` | `FileResponse(snapshot.screenshot_path)` | Explicitly check `Path(snapshot.screenshot_path).is_file()` (covers both "doesn't exist" and "exists but isn't a regular file") before constructing the `FileResponse`, raising `NotFoundError` (404) otherwise — defends against DB/filesystem drift (e.g. artifact manually deleted, disk cleanup, row corruption) rather than trusting the stored path blindly. |
| `GET /snapshots/{id}/text` | read `snapshot.text_path`, return as `text/plain` | Same `is_file()` check as the screenshot route before reading. |
| `POST /targets/{id}/baseline/approve` | `review.approve_baseline(db, target_id, snapshot_id)` | `snapshot_id` from `BaselineApproveRequest` body. |
| `POST /checks/{id}/ack` | `review.acknowledge_check_result(db, check_result_id)` | |

## 6. Test-DB isolation (new infrastructure)

Prior milestones tested services directly against transient sessions; testing through HTTP needs the app itself wired to a test database. Add a `tests/conftest.py`:

- A fixture creating a fresh SQLite file (or in-memory DB with `StaticPool` so it survives across connections within a test) per test function, running `Base.metadata.create_all()` against it.
- Overrides `app.dependency_overrides[get_db]` to yield sessions bound to that test engine, and `app.dependency_overrides[get_capture_func]` to a stub by default (decision #5) — individual tests can override further as needed.
- A shared `client` fixture (`httpx.AsyncClient` with `ASGITransport(app=app)`, matching the async stack already in use) for route tests to call against.
- **Do not rely on the app's `lifespan` startup hook to create tables for tests.** Depending on the installed `httpx` version, `ASGITransport` may not trigger `lifespan` startup/shutdown at all; since the fixture above already calls `Base.metadata.create_all()` directly against the test engine, table creation for tests is independent of whether `lifespan` fires. If a later `httpx` upgrade changes this behavior, nothing here needs to change.

## 7. Sequencing

1. `app/core/errors.py` additions + the `main.py` exception handler (decision #4) — do this before writing routes, so every route from the start returns correct status codes instead of retrofitting later.
2. `app/schemas/*` — data contracts, no behavior, quick to write and review.
3. `app/api/deps.py` (decision #5) and `tests/conftest.py` (test-DB isolation) — build the testability scaffolding before the routes that need it.
4. Routes in dependency order: Targets first (nothing else works without a target), then Checks, then Snapshots, then Review/Baselines.
5. Smoke-test script (deferred from Milestone 5) — a short script exercising the full loop end-to-end against a running server: create target → trigger check → poll until not `Checking` → fetch snapshot/screenshot → approve baseline → run another check → acknowledge. **Lives at `backend/scripts/smoke_test.py`, outside `tests/`, so pytest never collects it.** It needs a real running `uvicorn` instance, a real Playwright browser, and network access to a real target — the same combination that already requires elevated privileges on this Windows environment (per the Milestone 4 handoff notes on sandboxed named-pipe subprocess creation). It is a manual verification step, never part of the `pytest` suite or any CI gate that must run headless/offline.

## 8. Test plan

- **Targets CRUD**: create (including SSRF-rejected URL → 400), list (default excludes inactive; `include_inactive=true` includes them), get (404 for unknown id), patch (`url` in the payload → `422`, confirm decision #6 holds), soft-delete (`is_active` becomes `False`, target still fetchable by id and by `GET /targets?include_inactive=true`, no longer in the default list).
- **Check trigger**: `POST /targets/{id}/check` with the stubbed `capture_func` returns `202`-style `CheckTriggerResponse {target_id, accepted: true}` promptly — the test must **not** assert `status == "Checking"` on this response (decision #3). Follow up with `GET /targets/{id}` after the background task has actually run (await it directly rather than sleeping/polling, since `TestClient`/`httpx` triggers `BackgroundTasks` inline within the test's event loop) and assert the expected terminal status there instead. A nonexistent target id returns `404` immediately, with no background task scheduled (assert the stub `capture_func` was never called).
- **Double-trigger**: firing the check route twice quickly — second call's underlying `run_checks_for_targets` skip-guard (Milestone 4) prevents a double-run; assert only one check actually executed against the stub.
- **Checks/Snapshots read paths**: 404 handling for unknown ids; `GET /targets/{id}/checks` returns `404` for a nonexistent target versus `200` + `[]` for a real target with no checks yet (the two cases the plain-empty-list approach couldn't distinguish); screenshot/text download routes return the right content type and body bytes/text, and return `404` (not a 500) when the DB row exists but the artifact file has been deleted from disk.
- **Review flow end-to-end**: create target → run check (stub produces a diff) → `GET /targets/{id}/checks` shows it as `Changed` and unacknowledged → `POST /checks/{id}/ack` → status `Acknowledged` → `POST /targets/{id}/baseline/approve` with the new snapshot → status `OK`, previous `CheckResult` auto-acknowledged (Milestone 3 behavior, now verified through the API instead of only at the service layer).
- **Error mapping**: one representative case per new exception type (`NotFoundError` → 404, `ValidationError` → 400, `InvalidStatusTransitionError` → 409) to confirm the handler in `main.py` is actually wired, not just defined.

## 9. Definition of done

- All tests above pass under `pytest`, run through the HTTP layer via the `conftest.py` test client — not just at the service layer. The `pytest` run is fully offline/stub-driven; it has no dependency on `backend/scripts/smoke_test.py`, network access, or a real Playwright browser.
- `ruff check .` and `mypy .` clean.
- The smoke-test script (`backend/scripts/smoke_test.py`) is run manually at least once against a locally running `uvicorn` instance, covering the full create → check → review loop with a real (non-stubbed) target — the first true end-to-end verification of Milestones 1–6 together. Its success is a manual sign-off step, not an automated gate.
- No route bypasses `ssrf_guard.validate_url` at target-creation time.

## 10. Handoff notes

- This is the last item on the backend side of `plan/prototype-plan.md`'s milestone list (§11) before frontend work (§8) has an API to call.
- `app/schemas/*` should mirror ORM field names closely so the future frontend's `src/types/` can be generated or hand-mapped from the OpenAPI schema FastAPI already produces automatically — no extra doc work needed there.
- The background-task response-vs-status race (decision #3) and `BackgroundTasks`' lack of durability (decision #1) are both accepted, explicitly documented prototype-scope tradeoffs, not bugs to chase — revisit only if a durable queue or stricter response-consistency guarantee becomes an actual requirement later.
