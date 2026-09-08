# Website Defacement Monitoring System — Project Plan

This is a legitimate and well-understood category of tool (change-detection / integrity monitoring), similar to Visualping.io.

## 1. Core Concept

A defacement monitor periodically snapshots a website (HTML, visual screenshot, or both), diffs it against a previous known-good snapshot, and alerts when changes exceed a threshold. Since AI analysis is excluded, detection relies on **deterministic diffing techniques**: DOM diffs, visual/pixel diffs, hash comparisons, and rule-based heuristics.

## 2. High-Level Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────────┐
│  Scheduler   │────▶│   Crawler/    │────▶│   Diff/       │────▶│  Alerting    │
│  (jobs queue)│     │   Snapshotter │     │   Comparator  │     │  Engine      │
│              │     │   (Playwright)│     │   Engine      │     │              │
└─────────────┘     └──────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                            ▼                     ▼
                     ┌──────────────┐     ┌──────────────┐
                     │  Storage      │     │  History/    │
                     │  (snapshots)  │     │  Audit DB    │
                     └──────────────┘     └──────────────┘
                            ▲
                            │
                     ┌──────────────┐
                     │  Dashboard/   │
                     │  Web UI       │
                     └──────────────┘
```

## 3. Key Components

### 3.1 Target Management
- Users register URLs to monitor
- Per-target config: check interval, diff sensitivity thresholds, which detection modes to use (DOM/visual/hash), auth/cookies if login-gated, viewport size, ignore-regions (for dynamic ad banners, timestamps, etc.)

### 3.2 Scheduler / Job Queue
- Decouples "when to check" from "how to check"
- Needs to handle thousands of targets on independent cadences without thundering-herd effects
- Should support retry-with-backoff for transient network failures (don't want a timeout to look like a defacement)

### 3.3 Snapshotter (Playwright)
This is the heart of the system. For each check:
- Launch headless browser, navigate to URL
- Wait for network idle / specific selector (configurable — SPAs need this)
- Capture multiple artifacts:
  - **Raw HTML** (post-render, since defacement often happens via injected JS)
  - **Rendered DOM text content** (strips tags, good for content diffs)
  - **Full-page screenshot** (PNG)
  - **Computed metadata**: page title, meta tags, response status, response headers, redirect chain, favicon hash
- Normalize HTML before storage (strip volatile attributes like CSRF tokens, timestamps, session IDs, ad-network iframes) — otherwise you get constant false positives

### 3.4 Diff/Comparator Engine
Multiple independent detectors, each producing a change score:

| Detector | Method | Good for |
|---|---|---|
| **Structural DOM diff** | Tree edit distance (e.g., `zss`, or custom tree diff) on normalized DOM | Detecting injected script tags, new hidden iframes, altered links |
| **Text content diff** | Line/word diff (`difflib`, or `diff-match-patch`) on visible text | Detecting defacement messages, propaganda text injection |
| **Visual/pixel diff** | Perceptual hashing (pHash) + SSIM/pixel diff (via `scikit-image` or `Pillow`) | Catching visual-only defacement (image replacement, CSS-based hiding) |
| **Hash/checksum** | SHA-256 of normalized content | Fast "did anything change at all" gate before running expensive diffs |
| **Link/resource diff** | Set diff of outgoing links, script `src`, external domains | Catching malicious redirect injection, added phishing links |
| **Security-signal checks** | New `<script src>` to unknown domain, new `<iframe>`, `eval()` patterns, base64 blobs, unusual meta-refresh | Rule-based defacement heuristics — this replaces the "AI" layer with explicit rules |

Each detector outputs a **change magnitude** (0–1) and a list of specific changes. A rules engine combines these into a severity score and decides whether to alert.

### 3.5 Alerting Severity Model (rule-based, no AI)

Weighted scoring config example:

- New external script domain → high severity (weight 0.9)
- >30% text content changed → medium-high
- Visual diff >15% of pixels changed → medium
- New iframe pointing to non-allowlisted domain → high
- Favicon changed → low-medium
- HTTP status code changed (200→403/500) → medium (site might be down, not defaced, but worth flagging)

This gives tunable, explainable "if X and Y then alert" logic without needing a model.

### 3.6 Storage
- **Snapshots**: raw HTML + screenshots — large binary/text blobs, don't belong in the relational DB
- **Metadata & diffs**: structured — belongs in relational DB
- **Time-series check results**: for building history graphs

### 3.7 Alerting Engine
- Email, Slack/Discord webhook, SMS (Twilio), generic webhook
- Include: diff summary, side-by-side/overlay screenshot, severity, direct link to dashboard for that check

### 3.8 Dashboard / Web UI
- List of monitored sites with current status (OK / Changed / Down)
- Timeline view per site
- Visual diff viewer (overlay slider between two screenshots)
- HTML diff viewer (side-by-side or unified)
- Alert history & acknowledgment workflow
- Config management (add/remove targets, adjust sensitivity)

## 4. Proposed Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Browser automation** | Playwright (Python, async API) | Multi-browser (Chromium/Firefox/WebKit), reliable auto-wait, screenshot + HTML extraction built in |
| **Backend framework** | FastAPI | Async-native (pairs well with Playwright's async API), auto OpenAPI docs, good for both API + background task triggers |
| **Task queue / scheduler** | Celery + Redis (or Celery + RabbitMQ), with `celery-beat` for periodic scheduling | Mature, handles retries/backoff, scales horizontally by adding workers |
| **Database (relational)** | PostgreSQL | Targets, users, check results, diff metadata, alert config |
| **Object storage** | S3-compatible (AWS S3 or self-hosted MinIO) | Screenshots and raw HTML snapshots — keeps DB lean |
| **Visual diffing** | Pillow + scikit-image (SSIM) or `imagehash` (pHash) | Pixel & perceptual diffing without deep learning |
| **HTML/DOM diffing** | `lxml` for parsing/normalizing + `difflib` or `diff-match-patch` for text diff; optionally `zss` for tree edit distance | Structural diffing |
| **Frontend** | React (or htmx if you want to keep it simpler/Python-heavy) + Tailwind | Dashboard, diff viewers |
| **Diff visualization** | `react-diff-viewer` (HTML/text) + custom canvas overlay slider (images) | Side-by-side comparison UX |
| **Auth** | FastAPI + JWT, or session-based with `fastapi-users` | Multi-user support |
| **Notifications** | SMTP (email), Slack/Discord webhooks, Twilio (SMS) | Standard integration set |
| **Containerization** | Docker + docker-compose (dev), Kubernetes (prod scale) | Playwright's browser binaries are heavy; containerize consistently |
| **Monitoring the monitor** | Prometheus + Grafana | Track job success rate, queue depth, Playwright crashes |
| **Logging** | structlog or standard logging → shipped to Loki/ELK | Debugging headless browser failures |

## 5. Data Model Sketch (conceptual, not code)

- **Target**: id, url, name, check_interval, viewport config, auth config, ignore_selectors, sensitivity_thresholds, active
- **Snapshot**: id, target_id, timestamp, html_hash, screenshot_object_key, html_object_key, http_status, response_time_ms
- **DiffResult**: id, target_id, snapshot_id_old, snapshot_id_new, detector_type, change_score, details (JSON), severity
- **Alert**: id, target_id, diff_result_id, sent_at, channel, acknowledged
- **User/Team/APIKey**: standard auth tables

## 6. Key Design Challenges to Discuss

1. **False-positive suppression** — dynamic content (ads, rotating banners, timestamps, A/B tests, CSRF tokens) will dominate naive diffs. You need a robust **normalization/ignore-region system** per target, possibly with an initial "learning period" that baselines normal variance before alerting.
2. **Scaling headless browsers** — Playwright browser contexts are memory-heavy. Need a worker pool with context reuse/recycling strategy, and concurrency limits per worker to avoid OOM.
3. **Auth-gated pages** — some sites need login; need secure storage of credentials/cookies/storage-state (Playwright supports `storage_state` for session persistence).
4. **JS-heavy SPAs** — need configurable wait conditions per target (networkidle vs. specific selector vs. fixed delay) since generic waits will be flaky.
5. **Distinguishing "down" from "defaced"** — a 500 error or timeout is not a defacement; needs separate status-code/availability handling from content-diff handling.
6. **Baseline drift** — should the "known good" snapshot auto-update after each check, or only after human approval? (Auto-update risks slow defacement creep going undetected; manual approval adds friction.) Recommendation: auto-update for low-severity diffs, require manual approval for medium/high.
7. **Rate limiting / politeness** — respecting robots.txt-style politeness and not hammering targets, especially for sites you don't own.

## 7. Suggested Build Phases

1. **Phase 1 — Core snapshot loop**: single target, Playwright capture (HTML+screenshot), store to disk, SHA-256 hash diff only (change/no-change)
2. **Phase 2 — Multi-detector diffing**: add text diff, visual diff (SSIM/pHash), link-diff
3. **Phase 3 — Scheduling & multi-target**: Celery+Redis, Postgres-backed targets, worker pool
4. **Phase 4 — Rules engine & severity scoring**: configurable weighted rules replacing simple thresholds
5. **Phase 5 — Alerting**: email/Slack/webhook integrations
6. **Phase 6 — Dashboard**: target management, diff viewers, history
7. **Phase 7 — Hardening**: normalization/ignore-regions, false-positive tuning, auth-gated targets, scaling workers
