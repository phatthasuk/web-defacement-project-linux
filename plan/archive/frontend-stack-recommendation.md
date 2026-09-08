# Front-End Stack Recommendation — Website Defacement Monitoring System

*Based on `website-defacement-monitoring-plan-final-2.md`*

Based on the plan's frontend needs (target list, timeline view, visual-diff overlay slider, text/HTML diff viewer, alert ack workflow, baseline approval UI, config forms), here's a stack that stays simple now but scales cleanly as Phases 6–7 build out.

## Recommended Stack

| Layer | Pick | Why |
|---|---|---|
| **Framework** | React + TypeScript + Vite | No SSR needed — FastAPI already owns the API layer, so a plain Vite SPA avoids Next.js complexity (routing conventions, server components, deployment target lock-in) you don't need here. TS catches schema drift against the FastAPI/Pydantic models early. |
| **Server state** | TanStack Query | Handles polling for target status, caching, retries, and background refetch (needed for live "Verification Pending" → "Defacement Suspected" transitions) without hand-rolled `useEffect` fetch logic. Removes the need for Redux entirely — most of this app's state *is* server state. |
| **Client/UI state** | React `useState`/`useContext` only | With TanStack Query owning server data, local UI state (modal open, selected diff, filters) rarely needs more. Adding Redux/Zustand here would be premature complexity. |
| **Styling** | Tailwind CSS | Matches what the plan already proposes; fast to onboard new devs, no CSS-in-JS build overhead. |
| **Components** | shadcn/ui (Radix primitives) | Copy-in components, not a heavy dependency — new devs can read and modify the actual component code instead of fighting a black-box library. Good accessible primitives for the modals/tables/dropdowns a target-management UI needs. |
| **Routing** | React Router | Standard, well-documented, sufficient for a dashboard with a handful of top-level views (Targets, Diffs, Alerts, Baselines). |
| **Diff viewers** | `react-diff-viewer-continued` (text/HTML) + a small custom canvas/slider component (visual overlay) | Matches Section 10 of the plan directly; no need to build a text-diff renderer from scratch. |
| **Charts** | `recharts` | For the timeline/history view — simple API, good enough for check-history graphs without a heavyweight charting engine. |
| **Forms** | React Hook Form + Zod | Target config has real structure (ignore-selectors, thresholds, viewport, auth profile) — schema validation here catches bad config before it hits the SSRF-sensitive `POST /targets` endpoint. |

## Why Not the Plan's htmx Alternative

htmx is a fine call for CRUD-only admin panels, but this dashboard has genuinely stateful interactive pieces — the visual-diff overlay slider, live status polling, multi-step baseline approval — that are painful to build in htmx/Alpine without fighting the tool. React earns its complexity here.

## Scaling Path Without Added Complexity Later

- Route-based code-splitting (`React.lazy`) as pages grow — no architecture change needed.
- Feature-folder structure (`/features/targets`, `/features/diffs`, `/features/alerts`) rather than type-based folders — keeps future additions (e.g., Slack integration UI) isolated.
- If real-time push (vs. polling) becomes necessary later, add a WebSocket subscription that just invalidates the relevant TanStack Query cache key — no state-management rewrite required.

## Summary

This keeps the stack boring and mainstream on purpose: every piece here is something a mid-level dev can pick up from the official docs alone, which matters given the plan's own emphasis on operational maintainability over cleverness.
