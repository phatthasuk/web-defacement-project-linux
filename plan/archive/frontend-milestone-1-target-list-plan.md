# Frontend Milestone 1 Development Plan — Target List (Bootstrap)

*Handoff document. First frontend milestone — the backend (Milestones 1–6) is complete and fully callable over HTTP; nothing here has a backend counterpart left to build. Scope is grounded in the actual current schemas (`backend/app/schemas/*`) and routes (`backend/app/api/routes/*`), not the heavier `plan/frontend-stack-recommendation.md`, which was written for the full production plan (recharts, shadcn/ui, React Hook Form + Zod) — `frontend/package.json` is already scoped to the lean prototype stack from `plan/prototype-plan.md` §3 (React + TS + Vite, TanStack Query, React Router, Tailwind), and this plan stays within that.*

## 1. Goal

Turn the six completed backend milestones into something visible: a page where a target can be added, listed, checked, and watched as its status updates — the smallest vertical slice of `plan/prototype-plan.md` §8's "Target List" screen.

## 2. Scope

**In scope**
- Typed API client + TS types for the endpoints this milestone needs.
- Frontend test tooling (currently nonexistent — see decision #3).
- Target List page: add-target form, list (name/url/status/last-activity/run-check button), status polling.

**Out of scope (deferred to Milestone 2 — Target Detail)**
- Latest text/visual change scores per target in the list — see decision #4 for why.
- The text-diff view and screenshot comparison (the diff-rendering approach — client-side diff of two fetched text blobs vs. a new backend endpoint — is exactly the open question flagged when this milestone was scoped; deferred to Milestone 2 since it's a Target Detail concern, not a list concern).
- Target edit/deactivate (`PATCH`/`DELETE /targets/{id}` exist on the backend and are trivial to wire, but aren't part of §8's Target List field list — adding them now is unnecessary scope for a first slice).
- Check Detail page, baseline approval UI, acknowledge UI (all Target Detail/Check Detail concerns, Milestone 2+).

## 3. Decisions locked before/while building

1. **Call the backend directly via `VITE_API_BASE_URL`, relying on CORS — not the `/api` proxy already sitting in `vite.config.ts`.** The backend's routes are unprefixed (`/targets`, `/checks/{id}`, `/health` — no `/api` prefix anywhere in `app/main.py`), so the existing `server.proxy['/api']` block in `vite.config.ts` doesn't correspond to any real backend path and would silently do nothing if used. The backend already has CORS configured for exactly `http://localhost:5173` (`Settings.CORS_ORIGINS` default, matching Vite's default port) and `frontend/.env.example` already defines `VITE_API_BASE_URL=http://localhost:8000` — that pairing is the one that actually works today. Remove the stale `/api` proxy block from `vite.config.ts` as part of this milestone's setup so it doesn't mislead the next person into routing through it.
2. **Hand-write the TypeScript types in `src/types/` rather than generating them from the OpenAPI schema.** FastAPI already serves `/openapi.json`, and a codegen tool (`openapi-typescript` or similar) would remove drift risk — but the type surface right now is five small, stable-shaped schemas. Hand-writing is less tooling for genuinely small value at this size; revisit codegen if the schema surface grows or drift becomes a recurring bug source.
3. **Add frontend test tooling in this milestone: Vitest + `@testing-library/react` + `jsdom`.** `frontend/package.json` currently has zero test infrastructure, unlike the backend where every milestone's definition of done includes `pytest`/`ruff`/`mypy`. It's far cheaper to establish this now, on one page, than to retrofit it once three pages and a router exist.
4. **Target List shows name/url/status/last-activity/run-check only — no latest text/visual change scores.** Per `plan/prototype-plan.md` §8 those scores come from a target's most recent `CheckResult`, but `GET /targets` returns only `TargetRead` (no embedded check data), and `CheckResult` isn't reachable from a target except via `GET /targets/{id}/checks` — fetching that per row for a whole list is an N+1 pattern with no backend support today. Rather than add a backend aggregation endpoint for a nice-to-have list column, defer the scores to Milestone 2 (Target Detail), where fetching one target's checks is naturally a single, cheap call. "Last activity" is approximated using `Target.updated_at` (bumped by any commit to the row — checks, approvals, acknowledgments alike), which is close enough for a prototype list view without new backend work.
5. **Status polling via TanStack Query's `refetchInterval` on the targets list query — not WebSockets.** Matches `plan/frontend-stack-recommendation.md`'s own reasoning (TanStack Query already handles polling/caching/refetch) and the backend's own design intent: Milestone 3 introduced the `Checking` status specifically so a polling client could observe it. A fixed interval (e.g. 4000ms) while the list page is mounted is enough at prototype scale; no need to special-case "poll faster only while something is `Checking`" yet.
6. **Parse backend errors as `{ detail: string }`, matching the exact shape FastAPI's exception handlers in `app/main.py` return** (`JSONResponse(status_code=..., content={"detail": str(exc)})` for every `NotFoundError`/`ValidationError`/`SsrfBlockedError`/`InvalidStatusTransitionError`). The add-target form's error display (e.g. an SSRF-rejected URL, or a 422 from a malformed request) should surface that `detail` string directly, not a generic "something went wrong."

## 4. New files

- `src/types/target.ts` — `Target` (mirrors `TargetRead`: `id, name, url, status, is_active, created_at, updated_at`), `TargetStatus` as a string union (`"Never Checked" | "Checking" | "OK" | "Changed" | "Failed" | "Acknowledged"`, matching `app/core/status.py` exactly).
- `src/types/checkResult.ts` — `CheckResult` (mirrors `CheckResultRead`) — added now even though the list doesn't render it yet, since `src/api/checks.ts` needs the type for Milestone 2 reuse; no harm defining it a milestone early.
- `src/api/client.ts` — a thin `fetch` wrapper reading `import.meta.env.VITE_API_BASE_URL`, parsing JSON, and throwing an `ApiError` carrying the parsed `detail` string on non-2xx responses (decision #6).
- `src/api/targets.ts` — `listTargets()`, `createTarget(payload)`, `triggerCheck(targetId)` — the three calls this milestone needs (`GET /targets`, `POST /targets`, `POST /targets/{id}/check`).
- `src/hooks/useTargets.ts` — `useTargetsQuery()` (TanStack `useQuery`, `refetchInterval` per decision #5), `useCreateTargetMutation()`, `useTriggerCheckMutation()` (both invalidate the targets query on success).
- `src/pages/TargetListPage.tsx` — the page itself: add-target form + table/list.
- `src/components/TargetStatusBadge.tsx` — small presentational component mapping `TargetStatus` to a color/label, reusable in Milestone 2.
- `src/App.tsx` / `src/main.tsx` — `QueryClientProvider` + `BrowserRouter` wiring, one route (`/`) rendering `TargetListPage`. Router is set up now (decision to use React Router was already made in `package.json`) even though there's only one real route yet, so Milestone 2 just adds a route rather than introducing routing from scratch.
- `vite.config.ts` — remove the stale `/api` proxy block (decision #1).
- `vitest.config.ts` (or a `test` block added to `vite.config.ts`) + `src/setupTests.ts` — Vitest/RTL wiring (decision #3).

## 5. Sequencing

1. `vite.config.ts` cleanup (decision #1) + `.env` created locally from `.env.example` — quick, unblocks everything else that needs to actually hit the backend.
2. Vitest/RTL setup (decision #3) — establish the test harness before writing components that need it.
3. `src/types/*` + `src/api/*` — data layer, no UI yet, testable in isolation (mock `fetch`, assert `ApiError.detail` parsing).
4. `src/hooks/useTargets.ts` — thin TanStack Query wrappers around the API layer.
5. `TargetStatusBadge` (small, standalone, easy first component test).
6. `TargetListPage` — add-target form + list, wired to the hooks.
7. `App.tsx`/`main.tsx` wiring + manual verification against the real running backend.

## 6. Test plan

- **API client**: `ApiError` correctly extracts `detail` from a mocked error response body; a successful response returns parsed JSON.
- **`useTargets` hooks**: with a mocked `fetch`, `useTargetsQuery` returns the list; `useCreateTargetMutation`/`useTriggerCheckMutation` call the right endpoint and invalidate the targets query on success (assert via a `QueryClient` spy or a refetch-count check).
- **`TargetStatusBadge`**: renders the expected label/style for each of the six status values.
- **`TargetListPage`**: renders targets from a mocked API layer; submitting the add-target form calls `createTarget` with the entered values and clears the form on success; clicking "Run Check" calls `triggerCheck` for the right target id; a backend error (e.g. simulated SSRF rejection) surfaces the `detail` message in the form.
- **Manual verification**: run the real backend (`uvicorn`) and `npm run dev`, add a real target (e.g. `https://example.com`), click "Run Check," and confirm the row's status visibly moves `Never Checked → Checking → OK` via polling without a page refresh.

## 7. Definition of done

- All tests above pass under `vitest`.
- `npm run lint` and `npm run typecheck` (both already defined in `package.json`) are clean.
- Manual verification against the real backend (§6) succeeds.
- No component reaches into `fetch`/`import.meta.env` directly outside `src/api/client.ts` — keeps the API layer swappable/mockable, consistent with how the hooks/tests above assume a single seam.

## 8. Handoff notes

- Milestone 2 (Target Detail) is where the deferred items land: latest scores (fetched per-target now that it's one target, not a list), the text-diff rendering decision (client-side diff of two `GET /snapshots/{id}/text` blobs vs. a new backend endpoint reusing `compare_text_files`), screenshot comparison (`GET /snapshots/{id}/screenshot` is already usable directly as an `<img src>`, no new backend work needed there), and baseline-approve/acknowledge actions (`POST /targets/{id}/baseline/approve`, `POST /checks/{id}/ack` — already fully implemented backend-side, purely a wiring task).
- `src/types/*` were hand-written against the schemas as they exist today (`app/schemas/target.py`, `check_result.py`, `snapshot.py`, `check_trigger.py`, `review.py`) — if those change, the frontend types need a manual pass; there's no codegen link between them (decision #2).
- The backend's own accepted tradeoffs (background-task response-vs-status race, `BackgroundTasks` non-durability) mean the list's "Run Check" click may not show `Checking` on the very next poll tick — this is expected, not a frontend bug, and resolves within one or two polling intervals.
