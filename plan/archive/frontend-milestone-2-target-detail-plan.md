# Frontend Milestone 2 Development Plan — Target Detail

*Handoff document. Builds on Frontend Milestone 1 (Target List — complete and verified) and the full backend API (Milestones 1–6 — complete and verified). Scope is `plan/prototype-plan.md` §8's "Target Detail" screen: baseline snapshot, latest snapshot, latest check result, screenshot comparison, text diff, approve baseline, acknowledge change. Check Detail (the separate §8 screen) is explicitly deferred to Milestone 3 — building Target Detail first establishes the diff-rendering and image-comparison components Check Detail will reuse.*

## 1. Goal

Give each target a detail page reachable from the list, showing what changed (or didn't) between its baseline and latest snapshot, with the two review actions (approve baseline, acknowledge) wired to the already-complete backend endpoints.

## 2. A gap found while grounding this plan — needs a small backend addition

`GET /targets/{id}/checks` returns `CheckResult` rows, and each one references a `baseline_snapshot_id`/`current_snapshot_id` — but **a target's very first check never creates a `CheckResult`**. Per `app/services/checks.py::run_target_check`, when no baseline exists yet, the first captured snapshot is marked `is_baseline=True` and the function returns early with `check_result=None` — no `CheckResult` row is written. That means for any target that has been checked exactly once (a common, ordinary state — every target passes through it), `GET /targets/{id}/checks` returns `[]`, and there is currently **no endpoint that can return that target's baseline snapshot** at all. `GET /snapshots/{id}` exists, but only if you already know the snapshot's id — and nothing exposes it.

**Fix**: add `GET /targets/{id}/snapshots` to `backend/app/api/routes/snapshots.py` (or `targets.py` — either is reasonable; `snapshots.py` mirrors how `checks.py` hosts `GET /targets/{id}/checks` next to the checks-by-id routes), returning `list[SnapshotRead]` ordered by `captured_at desc`, with the same existence-check pattern already used by `list_target_check_results` (404 if the target doesn't exist, `200 + []` if it exists with no snapshots yet — same reasoning as the Milestone 6 decision for the checks-list route). This is small, additive, and doesn't touch any existing route — but it is new backend surface, so flagging it plainly rather than quietly writing it: **Milestone 2 has one backend sub-step before the frontend work.**

With this endpoint, the detail page can always find "the baseline snapshot" (`is_baseline: true` in the list) and "the latest snapshot" (first item, since the list is newest-first) regardless of how many checks have run — including the single-check case the current API can't serve at all.

## 3. Scope

**In scope**
- Backend: `GET /targets/{id}/snapshots` (§2).
- `/targets/:id` route + `TargetDetailPage`.
- Baseline vs. latest screenshot comparison (side by side).
- Text diff view.
- Latest check result summary (status, scores, summary sentence).
- Approve-baseline and acknowledge actions.
- Linking from `TargetListPage` into the detail page.

**Out of scope (deferred)**
- Check Detail page (§8's separate screen, Milestone 3) — a per-`CheckResult` drill-down that will reuse this milestone's diff/comparison components.
- Check history/timeline view beyond "latest" (not in prototype scope per `plan/prototype-plan.md` — production-only feature).
- Editing target config (`PATCH`/`DELETE` exist backend-side per Milestone 6 but weren't in Milestone 1's scope either; still not needed here).

## 4. Decisions locked before/while building

1. **Text diff is rendered client-side, not via a new backend diff endpoint.** The backend's `compare_text_files` (in `app/services/diff/diff.py`) only ever produces a float score, never the actual diff — extending it to return diff chunks would mean a new response schema and reworking `difflib` usage to expose match/replace opcodes instead of a ratio. Cheaper path: fetch both snapshots' raw text via the already-existing `GET /snapshots/{id}/text` and diff them in the browser with a small, well-known library (`diff` npm package — `diffWords`/`diffLines`). Zero backend change, proportionate to what §8 actually asks for ("text diff," not a sophisticated diff UI). Revisit only if a future milestone needs the diff server-side for some other reason (e.g. an alerting summary).
2. **One new frontend dependency: the `diff` npm package.** First non-bootstrap dependency added since Milestone 1's lean stack — worth naming explicitly rather than adding it silently. It's small (~20KB), has no transitive dependencies of consequence, and is the standard choice for this (used under the hood by most React diff-viewer libraries anyway).
3. **Screenshot comparison is two `<img>` tags side by side, not an overlay/slider.** `plan/frontend-stack-recommendation.md` proposed a canvas overlay slider, but that doc targets the full production plan; `plan/prototype-plan.md` §8 just says "screenshot comparison." `GET /snapshots/{id}/screenshot` already serves the PNG directly and works as an `<img src>` with no backend change — an overlay slider is a nice-to-have that can be layered on later without changing this milestone's data flow.
4. **"Approve as Baseline" targets the latest snapshot, always.** The backend's `approve_baseline(db, target_id, snapshot_id)` accepts any snapshot id for that target, but the UI only exposes approving the *current latest* snapshot — approving an arbitrary older snapshot isn't a workflow §8 describes, and isn't needed yet.
5. **Action button visibility**: "Approve as Baseline" is hidden when the latest snapshot is already the baseline (nothing to approve); "Acknowledge Change" is shown only when the latest `CheckResult`'s `status === "Changed"` and `acknowledged_at` is `null` — matching the backend's own idempotency/latest-only rules from Milestone 3 (`review.py::acknowledge_check_result`), so the UI never offers an action the backend would no-op or reject.

## 5. New files

**Backend**
- `backend/app/api/routes/snapshots.py` — add `list_target_snapshots` (§2). `backend/tests/test_api_routes.py` gets a matching test (existence check, ordering, empty-list case).

**Frontend**
- `src/types/snapshot.ts` — `Snapshot` (mirrors `SnapshotRead`: `id, target_id, captured_at, final_url, http_status, title, is_baseline`).
- `src/api/snapshots.ts` — `listTargetSnapshots(targetId)`, `getSnapshotText(snapshotId)` (plain-text fetch — `apiFetch`'s existing content-type branching already handles non-JSON responses, no change needed there), plus screenshot URL is just a string built from `VITE_API_BASE_URL` (no fetch needed — used directly as an `<img src>`).
- `src/api/checks.ts` — `listTargetChecks(targetId)`, `acknowledgeCheck(checkId)`.
- `src/api/review.ts` — `approveBaseline(targetId, snapshotId)`.
- `src/api/targets.ts` — add `getTarget(targetId)` (single-target fetch, not currently exposed).
- `src/hooks/useTargetDetail.ts` — `useTargetQuery(id)`, `useTargetSnapshotsQuery(id)`, `useTargetChecksQuery(id)`, `useApproveBaselineMutation()`, `useAcknowledgeCheckMutation()`. Mutations invalidate/refetch all three (`target`, `snapshots`, `checks`) queries for that target id on success — same pattern as Milestone 1's fix (`invalidateQueries` + `refetchQueries`), applied from the start this time rather than discovered as a bug.
- `src/components/TextDiffView.tsx` — takes baseline/current text strings, renders a highlighted diff using the `diff` package.
- `src/components/ScreenshotCompare.tsx` — baseline/current snapshot ids in, two `<img>`s out.
- `src/pages/TargetDetailPage.tsx` — composes the above: header (name/url/status/back-link), screenshot comparison, text diff, latest check summary, action buttons.
- `src/App.tsx` — add route `/targets/:id` → `TargetDetailPage`.
- `src/pages/TargetListPage.tsx` — wrap each target's name in a `<Link to={`/targets/${target.id}`}>`.

## 6. Sequencing

1. Backend: `GET /targets/{id}/snapshots` + test (§2) — unblocks everything else; without it the detail page can't reliably find the baseline for a once-checked target.
2. `diff` dependency + `src/types/snapshot.ts` + the three new `src/api/*` modules — data layer first, as in Milestone 1.
3. `useTargetDetail.ts` hooks.
4. `TextDiffView` and `ScreenshotCompare` — standalone, testable components before wiring them into the page.
5. `TargetDetailPage` — compose everything, wire actions.
6. Route + `TargetListPage` link.

## 7. Test plan

- **Backend**: `GET /targets/{id}/snapshots` — 404 for unknown target, `200 + []` for a target with no snapshots, correct ordering and `is_baseline` flag for a target with multiple snapshots.
- **`TextDiffView`**: identical text renders as unchanged; a text change renders the expected added/removed segments.
- **`ScreenshotCompare`**: renders two images pointing at the correct snapshot ids' screenshot URLs.
- **Hooks**: mocked-fetch tests for each new query/mutation, mirroring Milestone 1's pattern; mutation success invalidates all three related queries.
- **`TargetDetailPage`** integration: renders baseline vs. latest correctly for (a) a target with only one snapshot ever (no `CheckResult` — the gap from §2, now handled), and (b) a target with a `Changed`, unacknowledged latest check; clicking "Acknowledge Change" calls the right endpoint and the button disappears/updates after refetch; clicking "Approve as Baseline" calls the right endpoint with the latest snapshot's id.
- **Manual verification**: against the real backend, create a target, run one check (confirm the detail page renders the single-snapshot case correctly — this is the exact scenario §2 exists to fix), then run a second check and confirm the diff view and action buttons behave correctly for both the no-change and changed cases.

## 8. Definition of done

- All tests above pass (`pytest` for the backend addition, `vitest` for the frontend).
- `ruff`/`mypy` clean on the backend addition; `eslint`/`tsc -b` clean on the frontend.
- The single-check target case (§2) renders correctly — this is the concrete proof the backend gap is actually fixed, not just documented.
- No component reaches into `fetch`/`import.meta.env` outside `src/api/*`, consistent with Milestone 1's rule.

## 9. Handoff notes

- Milestone 3 (Check Detail) reuses `TextDiffView` and `ScreenshotCompare` as-is — it's the same comparison, just anchored to a specific historical `CheckResult`'s snapshot pair instead of "baseline vs. latest."
- If a future milestone wants the overlay-slider screenshot comparison from `plan/frontend-stack-recommendation.md` instead of side-by-side, that's a `ScreenshotCompare` internals change only — nothing else in this milestone's data flow depends on how the comparison is rendered.
