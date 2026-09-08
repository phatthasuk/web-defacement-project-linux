# Frontend–Backend Integration Fix Plan

To-dos from the frontend-vs-backend contract review (2026-07-02), ordered by priority.

Review baseline: all 9 endpoints the frontend calls exist on the backend with matching
paths, payloads, and response shapes. Status strings and CORS defaults match. Frontend:
`tsc` clean, 19/19 tests pass. Backend: 45/45 tests pass. Nothing is broken — these
items close the gaps left because the frontend was built against the pre-fix backend
contract.

---

## To-do 1 — Surface `last_error` in the UI

**Priority:** High · **Side:** Frontend
**Files:** `frontend/src/types/target.ts`, `frontend/src/pages/TargetListPage.tsx`,
`frontend/src/pages/TargetDetailPage.tsx`

**Problem:** The backend returns `last_error: string | null` on every target (added so
the UI can explain failures), but the `Target` interface doesn't declare it and no
component displays it. A failed check shows a red "Failed" badge with no reason.

**Plan:**
1. Add `last_error: string | null` to the `Target` interface.
2. List page: show the error as a tooltip (`title` attribute) on the Failed badge, or a
   small muted line under the URL when status is `Failed`.
3. Detail page: show the error prominently near the status badge in the header when
   status is `Failed`.

**Tests:** component test — target with `status: 'Failed'` and `last_error` set renders
the error text; target with `last_error: null` renders nothing extra.

---

## To-do 2 — Handle `accepted: false` and trigger errors

**Priority:** High · **Side:** Frontend
**Files:** `frontend/src/pages/TargetListPage.tsx`, `frontend/src/hooks/useTargets.ts`

**Problem:** The backend returns `202 {accepted: false}` when a check is already in
flight and `400` for inactive targets. `handleRunCheck` awaits the trigger and swallows
everything via `console.error` — a rejected trigger looks identical to a successful one.

**Plan:**
1. In `handleRunCheck`, inspect the returned `CheckTriggerResponse`; when
   `accepted === false`, show an inline notice ("Check already in progress").
2. On `ApiError`, display `err.detail` to the user (inline row message or a simple
   toast/banner state) instead of only logging.
3. Keep the button disabled while status is `Checking` (already done) — the notice covers
   the race where two tabs/users trigger simultaneously.

**Tests:** mock `triggerCheck` returning `{accepted: false}` → notice rendered; mock a
400 ApiError → detail text rendered.

---

## To-do 3 — Expose diff thresholds via API instead of hardcoding in UI

**Priority:** Medium · **Side:** Backend + Frontend
**Files:** backend — new route (e.g. `backend/app/api/routes/config.py`), schema, `main.py`;
frontend — `frontend/src/api/` (new module), `frontend/src/pages/TargetDetailPage.tsx`

**Problem:** The detail page displays "Threshold: 2.0%" and "1.0%" as string literals,
but `TEXT_CHANGE_THRESHOLD` and `VISUAL_CHANGE_THRESHOLD` are env-configurable. If ops
tune them, the UI lies.

**Plan (backend):**
1. Add `GET /config` returning
   `{"text_change_threshold": float, "visual_change_threshold": float}` from `Settings`
   via the existing `get_settings` dependency.
2. Add a `ConfigRead` Pydantic schema and register the router in `main.py`.
3. API test: `GET /config` returns the overridden test settings values.

**Plan (frontend):**
4. Add `getConfig()` API function and a `useConfigQuery` hook (long `staleTime`; the
   values change only on server restart).
5. Replace the hardcoded "Threshold: 2.0%" / "1.0%" strings with the fetched values,
   with a sensible fallback while loading.

**Tests:** backend route test; frontend component test with mocked config.

---

## To-do 4 — Poll target detail while a check is running

**Priority:** Medium · **Side:** Frontend
**Files:** `frontend/src/hooks/useTargetDetail.ts`, `frontend/src/pages/TargetDetailPage.tsx`

**Problem:** The list page polls every 4 s, but the detail queries have no
`refetchInterval`. A check triggered while viewing the detail page leaves the page stale
until manual refresh.

**Plan:**
1. In `useTargetQuery`, set a conditional interval:
   `refetchInterval: (query) => query.state.data?.status === 'Checking' ? 3000 : false`.
2. While status is `Checking`, also poll (or invalidate on status change) the snapshots
   and checks queries so scores/screenshots appear as soon as the check finishes —
   simplest: when a poll observes the status leaving `Checking`, invalidate
   `['snapshots', id]` and `['checks', id]`.

**Tests:** hook/component test — status transitions `Checking -> OK` cause snapshots and
checks queries to refetch.

---

## To-do 5 — Format FastAPI 422 validation errors in apiFetch

**Priority:** Low · **Side:** Frontend
**Files:** `frontend/src/api/client.ts`

**Problem:** FastAPI returns `detail` as an *array* of objects for request-validation
failures (422). `String(detail)` renders "[object Object]".

**Plan:** In the error branch, when `detail` is an array, map entries to their `msg`
(fall back to `JSON.stringify`) and join with "; " before constructing `ApiError`.

**Tests:** unit test `apiFetch` against a mocked 422 response with an array detail.

---

## To-do 6 — Document `CHECK_TIMEOUT_SECONDS` in backend .env.example

**Priority:** Low · **Side:** Backend
**Files:** `backend/.env.example`

**Problem:** The setting was added to `Settings` during the fix round but never
documented in `.env.example`.

**Plan:** Add under the concurrency block:
`CHECK_TIMEOUT_SECONDS=90` with a comment that it is the overall per-check budget
(browser launch + navigation + screenshot + diff), and must exceed
`PAGE_TIMEOUT_SECONDS`.

**Tests:** none (docs only).

---

## Known unused backend surface (no action now)

`PATCH /targets/{id}` (rename / activate–deactivate) and `DELETE /targets/{id}`
(soft delete) have no frontend UI yet. This is a missing feature to schedule, not a
contract mismatch.

---

## Suggested implementation order

1. **To-do 6** — one line.
2. **To-do 3 (backend half)** — small, unblocks the frontend half.
3. **To-dos 1, 2** — highest user-visible value; both touch the same pages, do together.
4. **To-do 4** — polling behavior.
5. **To-dos 3 (frontend half), 5** — finish up.

Verification after each group: backend `pytest`, `ruff check .`, `mypy app`;
frontend `npm run typecheck`, `npm test`.
