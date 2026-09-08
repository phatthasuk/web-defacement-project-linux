# Prototype Plan - Website Defacement Monitoring System

This prototype plan intentionally cuts the full production roadmap down to the smallest useful system that can prove the core idea:

1. Can the system capture a rendered website reliably?
2. Can it compare the latest capture against a known-good baseline?
3. Can a user inspect the difference and decide whether to accept or investigate it?

The prototype is not a production monitoring platform yet. It is a working proof that the snapshot, diff, and review loop is worth expanding.

## 1. Prototype Goal

Build a small web application that can:

- Register a small number of target URLs.
- Capture rendered screenshots and visible text using Playwright.
- Store a baseline snapshot for each target.
- Run manual checks against the baseline.
- Show text and visual differences in a dashboard.
- Let the user approve the latest snapshot as the new baseline.
- Mark a detected change as acknowledged.

## 2. Scope

### In Scope

- Target URL management.
- Manual "Run Check" button.
- Basic scheduled checks, if time allows.
- Playwright-based snapshot capture.
- Screenshot capture.
- Visible text extraction.
- Basic HTML metadata capture, such as title, status code, and final URL.
- Baseline creation and approval.
- Basic text diff.
- Basic visual diff score.
- Dashboard with target list, latest status, latest check result, and diff view.
- Basic SSRF protection for submitted URLs.
- Local development using Docker Compose or direct local processes.

### Out of Scope

- Multi-team support.
- RBAC and SSO.
- Kubernetes deployment.
- Prometheus and Grafana.
- Multi-region verification.
- Slack, Discord, SMS, and escalation policies.
- Complex DOM tree diffing.
- Advanced rule engine.
- Learning window for normal page variance.
- Auto-baseline update policy by severity.
- Full audit log.
- Long-term object storage lifecycle policy.
- High-volume crawling.

## 3. Recommended Prototype Stack

| Layer | Prototype Choice | Notes |
|---|---|---|
| Backend API | FastAPI | Keeps the production path open while staying simple. |
| Database | SQLite first, PostgreSQL optional | SQLite is enough for prototype. Use PostgreSQL if Docker Compose is already preferred. |
| Snapshot engine | Playwright Python | Required for modern rendered pages. |
| Background execution | FastAPI BackgroundTasks or asyncio task queue | Avoid Celery for prototype unless scheduled/concurrent jobs become painful. |
| Frontend | React + TypeScript + Vite | Good for diff UI and dashboard interactions. Vue 3 + TypeScript + Vite is also acceptable if the team prefers Vue. |
| Styling | Tailwind CSS | Fast dashboard styling. |
| Server state | TanStack Query | Useful for polling check status. |
| Visual diff | Pillow + simple pixel/SSIM comparison | Keep it basic first. |
| Text diff | Python difflib or diff-match-patch | Enough for visible text comparison. |
| File storage | Local filesystem | Store screenshots and text/HTML artifacts under a local data directory. |

## 4. Should the Prototype Check Websites Concurrently?

Yes, but only with strict limits.

The prototype should support limited concurrency from the beginning because Playwright checks are slow and blocking if run one by one. However, it should not attempt production-scale crawling.

Recommended prototype setting:

- Default max concurrent checks: `2`
- Configurable upper limit: `3` to `5`
- Per-domain concurrency: `1`
- Page timeout: `20` to `30` seconds
- Redirect limit: `5`
- Maximum page size / artifact size: capped

This gives a realistic test of multiple targets without introducing the operational complexity of Celery, Redis queues, worker recycling, or distributed scheduling too early.

Concurrency should be implemented with an application-level semaphore around Playwright jobs:

```text
Run checks requested
        |
        v
Limited async worker pool
        |
        v
Playwright snapshot
        |
        v
Diff against baseline
        |
        v
Persist result
        |
        v
Dashboard updates by polling
```

Do not launch one browser per target without limits. Browser processes are heavy, and unrestricted concurrency will make the prototype unstable before it proves the product idea.

## 5. Prototype Architecture

```text
Frontend Dashboard
    |
    v
FastAPI API
    |
    +--> SQLite/PostgreSQL metadata
    |
    +--> Local artifact storage
    |
    +--> Limited async Playwright check runner
              |
              +--> Screenshot capture
              +--> Visible text extraction
              +--> Basic metadata capture
              +--> Diff against baseline
```

## 6. Data Model

### Target

- `id`
- `name`
- `url`
- `status`
- `created_at`
- `updated_at`
- `is_active`

### Snapshot

- `id`
- `target_id`
- `captured_at`
- `final_url`
- `http_status`
- `title`
- `screenshot_path`
- `text_path`
- `html_path`
- `is_baseline`

### CheckResult

- `id`
- `target_id`
- `baseline_snapshot_id`
- `current_snapshot_id`
- `created_at`
- `status`
- `text_change_score`
- `visual_change_score`
- `summary`
- `acknowledged_at`

## 7. API Endpoints

```text
Targets
  POST   /targets
  GET    /targets
  GET    /targets/{id}
  PATCH  /targets/{id}
  DELETE /targets/{id}

Checks
  POST   /targets/{id}/check
  GET    /checks/{id}
  GET    /targets/{id}/checks

Snapshots
  GET    /snapshots/{id}
  GET    /snapshots/{id}/screenshot
  GET    /snapshots/{id}/text

Baselines
  POST   /targets/{id}/baseline/approve

Review
  POST   /checks/{id}/ack
```

## 8. Dashboard Screens

### Target List

- Target name.
- URL.
- Current status.
- Last checked time.
- Latest text change score.
- Latest visual change score.
- Run check button.

### Target Detail

- Baseline snapshot.
- Latest snapshot.
- Latest check result.
- Screenshot comparison.
- Text diff.
- Approve baseline button.
- Acknowledge change button.

### Check Detail

- Check status.
- Captured metadata.
- Text diff.
- Screenshot before/after.
- Basic visual difference score.

## 9. Status Model

Keep the prototype status model small:

- `Never Checked`
- `Checking`
- `OK`
- `Changed`
- `Failed`
- `Acknowledged`

The full production statuses such as `Verification Pending`, `Defacement Suspected`, `Unstable`, and `Resolved` can be introduced after retry verification exists.

## 10. Basic Security Requirements

Even the prototype must include basic URL safety because it fetches user-provided URLs.

Required:

- Allow only `http` and `https`.
- Block localhost and private IP ranges.
- Block cloud metadata IPs such as `169.254.169.254`.
- Re-check DNS after redirects.
- Cap redirect count.
- Cap timeout.
- Cap response/artifact size.

Not required for prototype:

- Full network sandboxing.
- Encrypted credential profiles.
- Authenticated target login flows.
- Full audit log.

## 11. Milestones

### Milestone 1 - Capture Loop

- Add target.
- Run Playwright snapshot.
- Save screenshot and visible text.
- Show latest snapshot in dashboard.

### Milestone 2 - Baseline and Diff

- Mark first snapshot as baseline.
- Run second check.
- Compare text and screenshot.
- Store check result.
- Show diff in dashboard.

### Milestone 3 - Review Workflow

- Approve latest snapshot as baseline.
- Acknowledge changed result.
- Add simple status transitions.

### Milestone 4 - Limited Concurrency

- Add semaphore-limited concurrent checks.
- Add per-domain concurrency limit.
- Add check timeout and failure status.

### Milestone 5 - Prototype Hardening

- Add SSRF guard.
- Add basic error handling.
- Add fixture test pages.
- Add a small smoke test script.

## 12. Go/No-Go Criteria

Move from prototype to MVP only if:

- The system can check at least 5 targets reliably.
- Limited concurrency does not crash Playwright.
- False positives are understandable from the diff view.
- A user can approve a new baseline without touching the database.
- Failed checks are clearly separated from changed content.
- Basic SSRF protection is in place.

## 13. Key Decision

The prototype should include concurrent checking, but only as bounded concurrency.

Do:

- Use `asyncio.Semaphore`.
- Start with 2 concurrent checks.
- Keep per-domain concurrency at 1.
- Make the limit configurable.

Do not:

- Add Celery on day one.
- Run unlimited Playwright jobs.
- Build production scheduling before the manual check flow works.
- Optimize for hundreds of targets before the baseline and diff UX is validated.

