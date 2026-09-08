# Frontend Milestone 3 Development Plan — Check Detail

*Handoff document. Builds on Frontend Milestone 2 (Target Detail — complete and verified) and the backend hardening pass since then (configurable thresholds, `last_error`, concurrency fixes — all verified: 46 backend tests, 20 frontend tests, ruff/mypy/eslint/tsc all clean). Scope is `plan/prototype-plan.md` §8's "Check Detail" screen — the last of the three dashboard screens the prototype plan defines.*

## 1. Goal

A dedicated, linkable page for a single historical `CheckResult`: its status, the metadata captured at that point, and the same text-diff/screenshot-comparison views built in Milestone 2 — anchored to that specific check's snapshot pair instead of "baseline vs. current latest."

## 2. Scope

**In scope**
- `/checks/:id` route + `CheckDetailPage`, reusing `TextDiffView` and `ScreenshotCompare` as-is.
- A link from Target Detail's "Latest Check Results" card into this page.

**Out of scope**
- **No action buttons on Check Detail** — `plan/prototype-plan.md` §8 lists exactly four things for this screen (check status, captured metadata, text diff, screenshot before/after, visual difference score) and, unlike Target Detail, does not mention approve/acknowledge here. This is a deliberate scope line, not an oversight: acknowledging a check from Check Detail would need its own product decision (does viewing an *old* check let you acknowledge it out of order, distinct from Milestone 2 decision #4's "acknowledge only applies to the latest for status purposes" reasoning?), and approving an old check's snapshot as baseline would effectively be a baseline rollback — a real feature, but not one either milestone plan or the prototype plan has asked for. If this is wanted later, it's a follow-up with its own decision, not smuggled into this milestone.
- No check-history/timeline list. Reachability into this page is deliberately narrow for now — see decision #1.

## 3. Decisions locked before/while building

1. **The only entry point into Check Detail is a link from Target Detail's latest-check card.** There is no check-history/timeline view in prototype scope (excluded explicitly in the Milestone 2 plan's own "out of scope" list, matching `plan/prototype-plan.md`'s production-only features). Without *some* link, Check Detail would be unreachable UI, so Target Detail's "Latest Check Results" card gets a small "View Full Details →" link to `/checks/{latestCheck.id}`. This makes the page a permalink for the current latest check, not a browsable archive — that's an intentionally narrow scope, not a placeholder for something bigger being half-built.
2. **`GET /checks/{id}` alone is sufficient data — no need to fetch the target's snapshot list.** Unlike Target Detail's single-check gap (Milestone 2 §2), every `CheckResult` row already carries non-nullable `baseline_snapshot_id`/`current_snapshot_id` (a `CheckResult` is never created for a target's first, baseline-establishing check — confirmed in `checks.py` — so any `CheckResult` that exists always has both ids). `ScreenshotCompare` and `TextDiffView` just need those two ids directly.
3. **Target context (name/url, for a breadcrumb) is fetched via the existing `useTargetQuery(check.target_id)`** — no new target-fetching code needed, same hook Target Detail already uses.
4. **No new backend endpoint needed.** `GET /checks/{id}` already returns everything this page needs; this is a frontend-only milestone.

## 4. New files

- `src/api/checks.ts` — add `getCheck(checkId)` (the file already has `listTargetChecks`/`acknowledgeCheck` from Milestone 2; `GET /checks/{id}` itself has existed since backend Milestone 6, just never had a frontend client function).
- `src/hooks/useTargetDetail.ts` (or split into `useCheckDetail.ts` if the file is getting crowded — implementer's call, no functional difference) — `useCheckQuery(checkId)` wrapping `getCheck`.
- `src/pages/CheckDetailPage.tsx` — composes: back link (to `/targets/{check.target_id}`, not `/`, so the breadcrumb goes to the relevant target, not the full list), status badge, captured-metadata block (`created_at`, scores, summary — same score/threshold display pattern as Target Detail's latest-check card, including the `/config`-fetched threshold labels), `ScreenshotCompare` (`baselineSnapshotId={check.baseline_snapshot_id}`, `currentSnapshotId={check.current_snapshot_id}`), `TextDiffView` (fetching both snapshots' text the same way `TargetDetailPage` does today).
- `src/App.tsx` — add route `/checks/:id` → `CheckDetailPage`.
- `src/pages/TargetDetailPage.tsx` — add the "View Full Details" link (decision #1) inside the latest-check card, only when `latestCheck` exists.

## 5. Sequencing

1. `getCheck` + `useCheckQuery`.
2. `CheckDetailPage` — this is almost entirely recombination of Milestone 2's existing components with different props; the bulk of the work is layout, not new data logic.
3. Route + the link from `TargetDetailPage`.

## 6. Test plan

- **`useCheckQuery`**: mocked-fetch test, same pattern as Milestone 2's hook tests.
- **`CheckDetailPage`**: mocked `useCheckQuery`/`useTargetQuery` — renders status, scores, summary, and passes the correct snapshot ids through to `ScreenshotCompare`/`TextDiffView` (assert via the same "correct ids in props" style Milestone 2's `ScreenshotCompare.test.tsx` already uses — no need to re-test those components' internals here). Back link points at the target, not the list.
- **`TargetDetailPage`**: one added assertion that the "View Full Details" link is present when a latest check exists and renders `href="/checks/{id}"` (or absent when there's no latest check yet — the single-check case from Milestone 2).
- **Manual verification**: from a target with at least one `Changed` check, click through from Target Detail to Check Detail and confirm the same diff/comparison renders correctly there.

## 7. Definition of done

- Tests above pass; `tsc -b`, `eslint`, and the full `vitest` suite stay clean (currently 20 tests — expect roughly +4).
- No backend changes required — confirms decision #4 held.
- Check Detail is reachable exactly one way (decision #1), not zero and not more than planned.

## 8. Handoff notes

- This closes out all three screens `plan/prototype-plan.md` §8 defines (Target List, Target Detail, Check Detail) — the prototype's dashboard scope is then feature-complete against the plan.
- If a future milestone wants check history/timeline browsing (a production-plan feature, not prototype scope), that's the natural point to revisit decision #1's "one entry point" restriction — nothing here blocks adding a list later, since `GET /targets/{id}/checks` already returns the full list, just unused for this purpose today.
