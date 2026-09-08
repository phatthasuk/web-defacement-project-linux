# Website Defacement Monitoring System — Combined Project Plan

*This document merges the original project plan, the technical review feedback, and the revised plan into a single, complete template. It represents the current authoritative version.*

## 1. Executive Summary

This is a legitimate and well-understood category of tool — change-detection / integrity monitoring — similar in spirit to services like Visualping.io. It periodically snapshots a website (HTML, visual screenshot, or both), diffs it against a previous known-good baseline, and alerts when changes exceed a threshold.

Since AI analysis is explicitly excluded, detection relies entirely on **deterministic diffing techniques**: DOM diffs, visual/pixel diffs, hash comparisons, and rule-based heuristics.

The core approach is sound and production-appropriate, but the plan should front-load **false-positive control, baseline governance, retry verification, security threat modeling, and operational readiness** rather than treating them as late-stage hardening. These concerns determine whether the system is actually usable in production or degenerates into a high-noise alerting tool.

### Strengths of the original design
- Clean separation of concerns: Scheduler, Snapshotter, Diff Engine, Alerting, Storage, Dashboard
- Playwright for post-render snapshotting — correct choice for modern JS-heavy sites and SPAs
- Multiple independent detectors (DOM, text, visual, hash, link, security-signal rules) covering different defacement modes
- Correct separation of object storage (screenshots/HTML) from relational storage (metadata)
- Early awareness of baseline drift, dynamic content noise, and headless browser scaling issues

### Issues addressed in this revision
- Normalization, ignore-selectors, and visual masking are pulled forward from Phase 7 into Phase 2 — they are core requirements for false-positive suppression, not late hardening
- Added SSRF protection and sandboxing, since the system fetches URLs that may originate from user input
- Split target status into distinct states (`OK`, `Changed`, `Availability Issue`, `Unstable`, `Verification Pending`, `Defacement Suspected`, `Acknowledged`, `Resolved`) instead of a simple OK/Changed/Down model
- Added a double-check/retry verification step before high-severity alerts are sent
- Added explicit baseline update policy tied to severity, to prevent slow/malicious drift
- Added data retention, storage lifecycle, and operational metrics sections
- Added CSP-header monitoring and third-party script allowlisting to the security-signal rule set
- Reordered build phases so noise-control work happens immediately after the core snapshot loop

## 2. Revised High-Level Architecture

```text
Target Management
       |
       v
Scheduler / Job Queue
       |
       v
Crawler / Snapshotter (Playwright Workers)
       |
       +--> Snapshot Storage (S3 / MinIO)
       |
       +--> Metadata DB (PostgreSQL)
       |
       v
Normalization + Masking Layer
       |
       v
Diff / Comparator Engine
       |
       v
Rules Engine + Severity Scoring
       |
       v
Verification Queue / Retry Check
       |
       v
Alerting Engine + Dashboard
```

The key architectural principle: **Normalization/Masking and the Verification Queue are core pipeline stages**, not optional add-ons bolted on at the end of the project.

## 3. Core Components

### 3.1 Target Management

Users register URLs to monitor with per-target configuration:

- URL, name, owner/team
- Check interval
- Viewport size
- Detection modes to enable: hash, DOM, text, visual, link/resource, security rules
- Diff sensitivity thresholds
- Ignore-selectors and ignore-regions (for ads, timestamps, carousels, etc.)
- Allowlisted external domains
- Authentication profile (for login-gated pages)
- Baseline approval policy
- Alert channels

### 3.2 Scheduler / Job Queue

Decouples "when to check" from "how to check." Should support:

- Independent cadences per target without thundering-herd effects
- Jitter to spread load
- Retry-with-exponential-backoff for transient network failures (a timeout should not look like a defacement)
- Separate queues for normal checks, retry/verification, and high-priority incidents
- Per-domain concurrency limits to remain a polite crawler

### 3.3 Snapshotter (Playwright)

The heart of the system. For each check:

- Launch headless browser, navigate to URL
- Configurable wait strategy: network-idle, wait-for-selector, fixed delay, or custom per-target readiness condition (generic waits are flaky for SPAs)
- Capture multiple artifacts:
  - Raw rendered HTML (post-render — defacement often happens via injected JS)
  - Rendered DOM text content (tag-stripped, for content diffs)
  - Full-page screenshot (PNG)
  - Computed metadata: page title, meta tags, HTTP status, response headers, redirect chain, favicon hash
  - External script/link/iframe domains
  - Response time and browser timing data
- Normalize HTML before storage (strip volatile attributes: CSRF tokens, nonces, session IDs, timestamps, tracking query params, ad-network iframes) — otherwise false positives dominate

**Memory management (from technical review):** Repeatedly opening/closing Playwright browser contexts thousands of times can leak memory at the OS level even though Playwright itself is stable.
- Configure `worker_max_tasks_per_child` in Celery to force a fresh process after N tasks
- Alternatively, keep a single browser instance open per worker and cycle contexts per task, restarting the browser every N jobs
- Set memory limits per container and ensure graceful shutdown so partial snapshots are never persisted

### 3.4 Normalization and Visual Masking

Should be implemented starting in the *first* phase that does real diffing — this is the primary lever for reducing false positives, not a Phase 7 afterthought.

**HTML normalization:**
- Remove volatile attributes (CSRF tokens, nonces, session IDs)
- Normalize timestamps
- Remove tracking query parameters
- Strip known ad widgets / dynamic containers
- Canonicalize whitespace and attribute ordering

**Visual masking:**
- Hide elements matched by `ignore_selectors` before taking the screenshot (inject CSS `display: none !important;`), or mask regions after capture with bounding boxes
- Needed for dynamic widgets: ad banners, carousels, timestamps, weather widgets, stock tickers, A/B-tested content

Raw pixel comparison alone is insufficient for SSIM/pHash — dynamic regions need to be explicitly masked before the perceptual-hash/pixel-diff stage runs, not just normalized in the DOM layer.

### 3.5 Diff / Comparator Engine

Multiple independent detectors, each producing a change score, evidence, and explanation:

| Detector | Method | Good for |
|---|---|---|
| **Hash/checksum** | SHA-256 of normalized content | Fast "did anything change at all" gate before running expensive diffs |
| **Structural DOM diff** | Tree edit distance (e.g. `zss`, or custom tree diff) on normalized DOM | Detecting injected script tags, new hidden iframes, altered links |
| **Text content diff** | Line/word diff (`difflib`, `diff-match-patch`) on visible text | Detecting defacement messages, propaganda text injection |
| **Visual/pixel diff** | Perceptual hashing (pHash) + SSIM/pixel diff (`scikit-image`, `Pillow`, `imagehash`) | Catching visual-only defacement (image replacement, CSS-based hiding) |
| **Link/resource diff** | Set diff of outgoing links, script `src`, external domains, forms | Catching malicious redirect injection, added phishing links |
| **Security-signal checks** | New `<script src>` to unknown domain, new `<iframe>`, `eval()`/`atob()` patterns, base64 blobs, unusual meta-refresh | Rule-based defacement heuristics — this replaces the "AI" layer with explicit rules |

Each detector outputs a **change magnitude** (0–1) with supporting evidence; a rules engine combines these into a severity score and decides whether to escalate to verification/alerting.

### 3.6 Security-Signal Rules

Extended rule set (incorporating review feedback):

- New external script domain outside the allowlist → **high severity**
- New iframe outside the allowlist → **high**
- **CSP (Content-Security-Policy) header removed or weakened** → high
- New inline script block → medium-high
- Subresource Integrity (SRI) attribute removed from an existing script/link tag → medium-high
- Suspicious `eval`, `atob`, long base64 blobs, or obfuscated JavaScript → high
- Unexpected `meta refresh` → medium
- Unexpected form `action` domain → high
- Redirect chain changed to an untrusted domain → high
- Favicon changed *together with* title/text change → medium (favicon alone → low-medium)
- >30% of visible text content changed → medium-high
- Visual diff >15% of pixels changed → medium
- HTTP 200 → 403/500/timeout → classified as an **availability issue first**, not treated as defacement until confirmed otherwise

This gives tunable, explainable "if X and Y then alert" logic without needing a model.

## 4. Status Model

Rather than a simple OK / Changed / Down model, targets should carry one of the following states:

- **`OK`** — no significant change detected
- **`Changed`** — a change was detected but does not meet defacement criteria
- **`Availability Issue`** — timeout, DNS error, 4xx/5xx, or asset load failure
- **`Unstable`** — retry produced an inconsistent result
- **`Verification Pending`** — a risk signal was found and is being re-checked
- **`Defacement Suspected`** — re-verification still shows the risk signal
- **`Acknowledged`** — a user has acknowledged the alert
- **`Resolved`** — the baseline or the site has been restored/corrected

This distinction matters because CMS slowness, CDN blips, or asset load failures are easy to mistake for defacement if "changed" is treated as a single bucket.

## 5. Baseline Policy

Baseline updates need explicit governance:

- **Low severity** → auto-update baseline allowed, if it passes defined rules
- **Medium severity** → requires human review before the baseline updates
- **High severity** → freeze the baseline; alert immediately after verification
- **Repeated low-risk changes** → use a learning window to characterize normal variance
- **Manual override** → an admin can mark any snapshot as known-good

Rationale: auto-updating the baseline too aggressively risks missing slow, incremental defacement or a malicious change inserted gradually over many checks.

## 6. Retry and Verification Policy

Before sending a high-severity alert, run a verification step:

- Retry after a 1–2 minute delay
- Use a different worker/browser instance than the one that produced the original result
- Where possible, use a different network path or region
- Only confirm the alert if the diff still exceeds threshold on retry
- If the retry produces a different result, mark the target `Unstable` rather than `Defacement Suspected`

This directly reduces false positives caused by CDN edge inconsistency, asset loading races, transient network issues, and CMS slowness — and reduces alert fatigue for whoever is on the receiving end.

## 7. Security and Threat Model

Because this system fetches URLs that may originate from user input, it must defend against SSRF and browser abuse:

- Allow only `http` and `https` schemes
- Block private IP ranges: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`
- Block link-local and cloud metadata addresses (e.g. `169.254.169.254`)
- Validate DNS resolution before fetch *and* on every redirect hop (DNS rebinding protection)
- Cap redirect count
- Cap response size
- Cap page load timeout
- Run browser workers in sandboxed containers with no unnecessary access to the internal network
- Encrypt stored credentials, cookies, and Playwright `storage_state`
- Audit-log access to snapshots, credentials, and baseline approvals
- Respect `robots.txt`-style politeness and rate limits, especially for sites you don't own

## 8. Storage and Retention

### Storage split
- **PostgreSQL**: targets, users, configs, check results, diff metadata, alert state
- **S3 / MinIO**: screenshots, raw HTML, rendered text, large diff artifacts (keeps the relational DB lean)
- **Time-series store or PostgreSQL partitioning**: metrics and check-history for graphing

### Retention policy
- Full screenshot/raw HTML: retain 30–90 days
- Metadata and alert history: retain longer, e.g. 1–2 years
- Incident snapshots (confirmed defacement): retain permanently or until explicitly archived
- Use S3 lifecycle policies to control storage cost over time
- Apply compression to HTML/text artifacts

## 9. Data Model Sketch (conceptual)

- **Target**: id, url, name, owner/team, check_interval, viewport config, auth config, ignore_selectors, allowlisted domains, sensitivity_thresholds, baseline approval policy, active
- **Snapshot**: id, target_id, timestamp, html_hash, screenshot_object_key, html_object_key, http_status, response_time_ms
- **DiffResult**: id, target_id, snapshot_id_old, snapshot_id_new, detector_type, change_score, evidence (JSON), severity
- **Alert**: id, target_id, diff_result_id, sent_at, channel, acknowledged, status
- **VerificationAttempt**: id, target_id, diff_result_id, retry_timestamp, worker_id, result, outcome_status
- **User / Team / APIKey**: standard auth tables

## 10. Proposed Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| **Browser automation** | Playwright (Python, async API) | Multi-browser, reliable auto-wait, screenshot + HTML extraction built in |
| **Backend framework** | FastAPI | Async-native (pairs well with Playwright's async API), auto OpenAPI docs |
| **Task queue / scheduler** | Celery + Redis (or RabbitMQ), with `celery-beat` for periodic scheduling | Mature, handles retries/backoff, scales horizontally |
| **Database (relational)** | PostgreSQL | Targets, users, check results, diff metadata, alert config |
| **Object storage** | S3-compatible (AWS S3 or self-hosted MinIO) | Screenshots and raw HTML snapshots, keeps DB lean |
| **Visual diffing** | Pillow + scikit-image (SSIM), `imagehash` (pHash) | Pixel and perceptual diffing without deep learning |
| **HTML/DOM diffing** | `lxml` for parsing/normalizing + `difflib`/`diff-match-patch` for text diff; optionally `zss` for tree edit distance | Structural diffing |
| **Frontend** | React (or htmx for a simpler, Python-heavy stack) + Tailwind | Dashboard, diff viewers |
| **Diff visualization** | `react-diff-viewer` (HTML/text) + custom canvas overlay slider (images) | Side-by-side comparison UX |
| **Auth** | FastAPI + JWT, or session-based with `fastapi-users` | Multi-user support |
| **Notifications** | SMTP (email), Slack/Discord webhooks, Twilio (SMS) | Standard integration set |
| **Containerization** | Docker + docker-compose (dev), Kubernetes (prod scale) | Playwright's browser binaries are heavy; containerize consistently |
| **Monitoring the monitor** | Prometheus + Grafana | Track job success rate, queue depth, Playwright crashes |
| **Logging** | structlog or standard logging → Loki/ELK | Debugging headless browser failures |

## 11. Operational Metrics

Track at minimum:

- Checks per minute
- Queue depth
- Average render time
- Browser crash count
- Timeout rate
- Diff processing latency
- Alert count by severity
- Retry confirmation rate
- False positive rate
- Storage growth rate
- Per-domain failure rate
- Worker memory usage

For Playwright workers specifically, configure:

- `worker_max_tasks_per_child`
- Max browser contexts per worker
- Scheduled browser restart every N jobs
- Memory limit per container
- Graceful shutdown to avoid partial snapshots

## 12. Build Phases

### Phase 1 — Core Snapshot Loop
- Single target
- Playwright capture: HTML, text, screenshot, metadata
- Store artifacts to disk or object storage
- Simple SHA-256 hash diff (change / no-change gate)
- Basic status: `OK`, `Changed`, `Availability Issue`

### Phase 2 — Normalization and Noise Control
*(moved forward from the original Phase 7, per review feedback — this must happen before multi-detector diffing or false positives will dominate testing)*
- HTML normalization
- Ignore-selectors
- Visual masking
- Viewport config
- Basic external-domain allowlist
- Initial baseline policy

### Phase 3 — Multi-Detector Diffing
- Text diff
- DOM diff
- Visual diff (pHash/SSIM)
- Link/resource diff
- Structured diff-result JSON output

### Phase 4 — Scheduler and Multi-Target Support
- Celery + Redis/RabbitMQ
- Postgres-backed targets
- Worker pool with context reuse/recycling
- Retries with backoff
- Per-domain concurrency limits

### Phase 5 — Rules Engine and Verification Queue
- Weighted severity scoring
- Full security-signal rule set (including CSP/SRI checks)
- Double-check/retry verification before high-severity alerts
- Status model refinement (`Unstable`, `Verification Pending`, etc.)
- Baseline approval workflow

### Phase 6 — Alerting
- Email / webhook / Slack / Discord / SMS integrations
- Alert deduplication
- Escalation policy
- Include diff summary, evidence, severity, and direct dashboard link in every alert

### Phase 7 — Dashboard
- Target list with current status
- Timeline view per site
- Visual diff viewer (overlay slider)
- HTML/text diff viewer (side-by-side or unified)
- Alert history and acknowledgment workflow
- Baseline approval UI
- Target/config management

### Phase 8 — Hardening and Scale
- SSRF protection and sandboxing
- Credential/cookie/storage-state encryption
- Container sandboxing for browser workers
- Object storage lifecycle policies
- Full observability dashboards (Prometheus/Grafana/Loki)
- Load testing
- Worker memory recycling tuning

## 13. Key Design Challenges (cross-reference)

1. **False-positive suppression** — dynamic content (ads, rotating banners, timestamps, A/B tests, CSRF tokens) will dominate naive diffs without a robust normalization/masking system and an initial learning period to baseline normal variance.
2. **Scaling headless browsers** — Playwright contexts are memory-heavy; use a worker pool with context reuse/recycling and per-worker concurrency limits to avoid OOM.
3. **Auth-gated pages** — some targets need login; store credentials/cookies/`storage_state` securely and encrypted.
4. **JS-heavy SPAs** — generic wait strategies are flaky; need configurable wait conditions per target.
5. **Distinguishing "down" from "defaced"** — a 500 or timeout is an availability issue, not a defacement, and must be routed through separate handling from content-diff logic.
6. **Baseline drift** — auto-update only for low-severity diffs; require manual approval for medium/high (see Section 5).
7. **Rate limiting / politeness** — respect `robots.txt`-style politeness, especially on third-party sites you don't own.
8. **Race conditions between "down" and "defaced"** — transient slowness or partial asset loads can mimic defacement; mitigate with the retry/verification queue (Section 6) rather than alerting on the first observation.

## 14. Final Recommendation

The project has a solid foundation and should move forward. The key adjustment from the original plan is to treat **false-positive suppression, verification retry, baseline governance, and SSRF protection as core requirements from the start**, not as end-of-project hardening work.

The recommended build order is: get the snapshot loop working first, immediately follow with normalization/masking, then layer in the multi-detector diffing and rules engine. Following this order keeps testing tractable, keeps alert noise low, and gives the system credibility once it's pointed at real, live websites.
