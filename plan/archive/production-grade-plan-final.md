# Website Defacement Monitoring System — Combined Project Plan

*This document merges the original project plan, the technical review feedback, the revised plan, and the MVP/API/test/deployment additions into a single, complete template. It represents the current authoritative version.*

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

### Phase 1 — Core Snapshot Loop + Baseline Security
*(security guardrails moved forward from the original Phase 8, per Section 17 — see rationale there)*
- Single target
- Playwright capture: HTML, text, screenshot, metadata
- Store artifacts to disk or object storage
- Simple SHA-256 hash diff (change / no-change gate)
- Basic status: `OK`, `Changed`, `Availability Issue`
- SSRF protection: scheme allowlist, private-IP/link-local/cloud-metadata blocking, DNS rebinding checks on every redirect hop, redirect/size/timeout caps
- Browser workers run in sandboxed containers with no route to the internal network from the first image build
- Credential/cookie/`storage_state` encryption at rest, even for the single-target MVP

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

### Phase 8 — Scale and Observability Polish
*(security-critical items — SSRF protection, sandboxing, credential encryption — moved to Phase 1; this phase is now scale/ops only, per Section 17)*
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

## 14. MVP Definition

The MVP proves the core detection loop is trustworthy — low noise, no missed obvious defacement, no SSRF exposure — before investing in scale, multi-tenancy, or polish.

### In scope for MVP
- A handful of targets (5–20), single tenant/team
- Scheduler with jitter and backoff (no multi-queue priority yet — one queue is fine)
- Playwright snapshotting: HTML, text, screenshot, metadata
- **Normalization + visual masking** (moved up from the original Phase 7 — this is non-negotiable for MVP, not a nice-to-have)
- Detectors: hash gate, text diff, visual diff (pHash/SSIM). DOM tree-edit-distance and full link/resource diff can wait.
- Security-signal rules: the highest-signal subset only — new external script domain, new iframe, CSP removed, suspicious `eval`/`atob`/base64 blobs, redirect-to-untrusted-domain
- Status model in full (`OK`, `Changed`, `Availability Issue`, `Unstable`, `Verification Pending`, `Defacement Suspected`, `Acknowledged`, `Resolved`) — this is cheap to build now and expensive to retrofit
- Retry/verification queue before any high-severity alert
- **SSRF protection, IP/scheme allowlisting, sandboxed browser containers, encrypted credential storage** — included from day one (see Section 17)
- One alert channel (email or a generic webhook — pick one, not both)
- Minimal dashboard: target list with status, one diff viewer (text or visual), acknowledge button
- Manual baseline approval only (no auto-update, no learning window yet)

### Explicitly out of scope for MVP
- Multi-team/RBAC, SSO
- SMS/Twilio, Slack/Discord integrations beyond the one chosen channel
- Kubernetes autoscaling, multi-region checks
- Full Prometheus/Grafana/Loki stack (basic structured logs + a handful of metrics are enough)
- Baseline auto-update / learning window for low-severity drift
- SRI checks, meta-refresh detection, favicon-hash correlation
- DOM tree-edit-distance diffing

### MVP exit criteria
Define these numerically before writing code, not after:
- False-positive rate on a 2-week soak test across all MVP targets (suggested target: **<5%** of checks producing a non-`OK` status that isn't a real change)
- 100% detection rate against a synthetic defacement test harness (see Section 16) covering text injection, image swap, and malicious script injection
- Zero SSRF findings in the security test suite
- No memory growth over a 48-hour soak run of the worker pool

If these aren't met, that's a go/no-go gate before Phase 3 multi-detector work begins — not something to patch later.

## 15. API and Schema

### 15.1 Database schema (expanded from Section 9)

```
Target
  id                    UUID PK
  url                   TEXT NOT NULL
  name                  TEXT
  owner_team_id         UUID FK -> Team.id
  check_interval_sec    INT NOT NULL
  viewport_width        INT
  viewport_height       INT
  wait_strategy         ENUM(network_idle, selector, fixed_delay, custom)
  wait_config           JSONB
  detectors_enabled     JSONB          -- {"hash":true,"dom":false,...}
  sensitivity_thresholds JSONB
  ignore_selectors      JSONB
  ignore_regions        JSONB
  allowlisted_domains   JSONB
  auth_profile_id       UUID FK -> AuthProfile.id, NULLABLE
  baseline_policy       JSONB
  active                BOOLEAN DEFAULT true
  created_at, updated_at TIMESTAMPTZ

Snapshot
  id                    UUID PK
  target_id             UUID FK -> Target.id
  taken_at              TIMESTAMPTZ
  html_object_key       TEXT
  screenshot_object_key TEXT
  html_hash             TEXT (SHA-256)
  http_status           INT
  response_time_ms      INT
  redirect_chain        JSONB
  external_domains      JSONB
  worker_id             TEXT

DiffResult
  id                    UUID PK
  target_id             UUID FK
  snapshot_id_old       UUID FK -> Snapshot.id
  snapshot_id_new       UUID FK -> Snapshot.id
  detector_type         ENUM(hash, dom, text, visual, link, security_rule)
  change_score          FLOAT (0-1)
  evidence              JSONB
  severity              ENUM(low, medium, medium_high, high)
  created_at            TIMESTAMPTZ

VerificationAttempt
  id                    UUID PK
  diff_result_id        UUID FK
  retry_at              TIMESTAMPTZ
  worker_id             TEXT
  network_path          TEXT NULLABLE
  outcome_status        ENUM(confirmed, unstable, resolved)
  new_snapshot_id       UUID FK -> Snapshot.id

Alert
  id                    UUID PK
  target_id             UUID FK
  diff_result_id        UUID FK
  channel               ENUM(email, webhook, slack, sms)
  sent_at               TIMESTAMPTZ
  acknowledged_by       UUID FK -> User.id, NULLABLE
  acknowledged_at       TIMESTAMPTZ
  status                ENUM(open, acknowledged, resolved)

User / Team / APIKey / AuthProfile
  standard auth + credential tables; AuthProfile.storage_state is
  stored encrypted (see Section 17), never in plaintext columns
```

Indexing notes: index `Snapshot(target_id, taken_at)` and `DiffResult(target_id, created_at)` for the dashboard's timeline queries; partition `Snapshot` and `DiffResult` by month once volume grows.

### 15.2 REST API (FastAPI)

```
Targets
  POST   /targets                    Create target
  GET    /targets                    List targets (filter by team, status)
  GET    /targets/{id}                Get target detail
  PATCH  /targets/{id}                Update config (ignore_selectors, thresholds, etc.)
  DELETE /targets/{id}                Deactivate (soft delete)
  POST   /targets/{id}/check          Trigger an immediate manual check

Snapshots
  GET    /targets/{id}/snapshots      List snapshots for a target
  GET    /snapshots/{id}              Snapshot detail + presigned artifact URLs

Diffs
  GET    /diffs?target_id=&severity=  List/filter diff results
  GET    /diffs/{id}                  Diff detail with evidence
  POST   /diffs/{id}/verify           Manually force a verification retry

Alerts
  GET    /alerts?status=open
  POST   /alerts/{id}/ack
  POST   /alerts/{id}/resolve

Baselines
  POST   /targets/{id}/baseline/approve   Approve current snapshot as new baseline
  POST   /targets/{id}/baseline/reject

Auth
  POST   /auth/login
  POST   /auth/apikeys
  DELETE /auth/apikeys/{id}

Webhooks / channel config
  POST   /targets/{id}/alert-channels
  DELETE /targets/{id}/alert-channels/{id}
```

Design notes:
- `POST /targets` should validate the URL against the SSRF blocklist (Section 17) synchronously and reject invalid targets at creation time, not just at check time — fail fast, don't let a bad target sit in the queue.
- Every mutating endpoint writes to an audit log (who, when, what changed) — this matters for baseline approvals and credential access.
- Presigned S3 URLs for artifacts should be short-lived and scoped per-request, not permanent public links.

## 16. Test Plan

### Unit tests
- Normalization functions: volatile-attribute stripping, timestamp/token normalization, whitespace canonicalization — assert idempotency (normalizing twice = normalizing once)
- Each detector in isolation, with fixed input pairs and expected `change_score`
- Rules engine severity scoring: table-driven tests covering every rule in Section 3.6
- SSRF validator: private-IP ranges, link-local, cloud metadata IP, decimal/hex/octal IP obfuscation, IPv6-mapped-IPv4, redirect-hop re-validation, DNS-rebinding simulation (mock DNS returning a public IP on first resolve, private IP on second)
- Retry/verification state machine transitions

### Integration tests
- Full pipeline against a local, controllable fixture site (a small Flask/static app you can mutate) — run snapshot → normalize → diff → rules → verification → alert end to end
- Synthetic defacement scenarios to inject into the fixture site:
  - Text-based defacement message injected into body
  - Image/logo swap
  - New `<script src>` pointing to an unlisted domain
  - Injected inline `<script>` with `atob()`/base64 payload
  - Redirect chain changed to point off-domain
  - CSP header stripped from the response
- Each scenario should produce the expected severity and expected status transition (`OK` → `Verification Pending` → `Defacement Suspected`)

### False-positive regression suite
- A curated set of "noisy but benign" real-world pages (rotating ad banners, live timestamps, A/B-tested hero sections, stock tickers) captured as fixtures
- Assert these never cross the alerting threshold after normalization/masking is applied
- Run this suite on every PR that touches normalization, masking, or detector thresholds — this is the guardrail against silent noise regressions

### Availability vs. defacement tests
- Simulate 500s, timeouts, DNS failures, partial asset loads — assert these route to `Availability Issue`, never directly to `Defacement Suspected`
- Simulate a flaky retry (first check fails, second succeeds with no diff) — assert `Unstable`, not a confirmed alert

### Load / soak tests
- Sustained run of the worker pool for 48+ hours at target concurrency — track memory growth per worker (this is the test that actually catches the Playwright context-leak issue noted in Section 3.3)
- Queue depth under burst load (many targets due at once) — verify jitter prevents thundering herd
- Per-domain concurrency limit enforcement against a single fast-changing target

### Security tests
- SSRF bypass attempts as above, run as an actual test suite, not just code review
- Verify `storage_state`/credentials are encrypted at rest (attempt to read the raw DB/disk value and confirm it's ciphertext)
- Container sandbox escape checks for the browser worker (network namespace isolation — worker should not reach internal services)
- Redirect-count and response-size caps enforced against a deliberately malicious test target

### End-to-end / UI tests
- Baseline approval workflow
- Alert acknowledgment and resolution flow
- Diff viewer rendering for both text and visual diffs

## 17. Security Guardrails — Moved to Phase 1

The original ordering placed SSRF protection, sandboxing, and credential encryption in **Phase 8 (Hardening and Scale)**. Since the system fetches and renders arbitrary user-supplied URLs from the very first working prototype, these are attack-surface-defining decisions, not late polish — retrofitting sandboxing after the architecture is already built around unrestricted browser workers is significantly more expensive than building it in from the start.

**Moved into Phase 1 (Core Snapshot Loop):**
- Scheme allowlist (`http`/`https` only)
- Private-IP, link-local, and cloud-metadata-address blocking, applied at target-creation time *and* at fetch time
- DNS resolution validated before fetch and re-validated on every redirect hop (DNS rebinding protection)
- Redirect count cap, response size cap, page load timeout cap
- Browser workers run in sandboxed containers with no route to internal network services, from the first container image — not added later
- Any credential/cookie/`storage_state` field encrypted at rest before it's ever written, even in the single-target MVP

**Left in a later phase (genuinely scale-related, not security-defining):**
- Full observability stack (Prometheus/Grafana/Loki)
- Object storage lifecycle policies for cost optimization
- Load testing at production scale
- Fine-tuning worker memory recycling thresholds under real traffic

This changes Phase 1's exit criteria: a working snapshot loop is not "done" until it also can't be pointed at `169.254.169.254` or `10.0.0.5` and doesn't store a plaintext password anywhere.

## 18. Deployment Plan

### Environments
- **Dev**: docker-compose, single replica of each service, local MinIO instead of S3
- **Staging**: mirrors prod topology at small scale, includes the synthetic defacement fixture site from Section 16 so every deploy can be smoke-tested against known scenarios
- **Prod**: Kubernetes; worker pool as its own Deployment, scaled independently from the API

### CI/CD pipeline
1. Lint + type-check
2. Unit tests
3. Integration tests against ephemeral fixture site (spun up in the CI job)
4. Build container images
5. Image security scan (base image CVEs, no baked-in secrets)
6. Deploy to staging
7. Automated smoke test: run the synthetic defacement scenarios against staging targets, confirm expected alerts fire
8. Manual approval gate
9. Canary rollout to a subset of prod worker replicas
10. Full rollout

### Infrastructure specifics
- Worker containers get **egress firewall rules** enforcing the SSRF blocklist at the network layer as well as the application layer — defense in depth in case app-layer validation has a bug
- Secrets (DB credentials, S3 keys, encryption keys for `storage_state`) come from a secrets manager (Vault, AWS Secrets Manager, or equivalent) — never baked into images or plaintext env files
- Autoscale worker replicas on queue depth (Celery/Redis queue length), not CPU alone — queue depth is the real signal for this workload
- Postgres: managed instance with automated backups and point-in-time recovery; S3/MinIO: versioning enabled on the bucket holding incident snapshots specifically, since those may need to be preserved as evidence

### Rollback plan
- All DB migrations written to be reversible
- Container images tagged by commit SHA; rollback = redeploy previous tag
- New detectors or rule changes ship behind a config flag per target, so a bad rule can be disabled for one target without a full rollback

### Day-one observability (not deferred to Phase 8)
Even in the MVP, ship:
- Structured logs (worker crashes, timeout rate, per-target check success/failure)
- A handful of Prometheus metrics: checks/min, queue depth, alert count by severity, false-positive rate (once you have a way to mark alerts as false positives)
The full Grafana/Loki dashboard build-out can wait; having *no* visibility into worker health until Phase 8 would make the Phase 1–7 soak tests hard to debug.

## 19. Additional Recommendations

- **Get written authorization before monitoring any site you don't own.** Automated fetching and headless rendering of third-party sites, especially at short intervals, can look like scraping or probing from the target's side. This should be a target-onboarding requirement, not an afterthought — add an `authorized_by`/attestation field to `Target` at creation.
- **Treat the threat model as a living document.** Section 7's SSRF/sandboxing list is a snapshot of known risks; revisit it every time a new detector or integration is added (e.g., adding a Slack webhook introduces a new place where sensitive diff evidence could leak if the webhook URL is wrong).
- **Add a per-target circuit breaker.** If a target repeatedly fails verification (flips between `Unstable` and `Verification Pending` across many cycles), that's a signal of a genuinely flaky site, not a monitoring bug — auto-throttle checks and surface it to an operator instead of continuing to hammer it or spamming alerts.
- **Make incident evidence tamper-resistant.** For confirmed-defacement snapshots that may later be used as evidence (e.g., for a takedown request or incident report), consider object-lock/WORM storage and an export function that preserves a chain of custody (hash + timestamp of retrieval).
- **Sign or authenticate outbound webhooks.** If alerts go to a webhook, sign the payload (HMAC) so the receiving system can verify it actually came from your system — otherwise the alert channel itself becomes a spoofable notification vector.
- **Define SLOs before scaling.** A concrete target like "high-severity defacement alerted within 10 minutes of occurrence, 95th percentile" gives the scheduler, retry-delay, and queue-priority decisions in Sections 3.2 and 6 a number to design against, instead of tuning them by feel.
- **Build a target-onboarding checklist**, not just a config schema. Ignore-selectors, viewport size, and wait strategy all currently require someone to look at the target site and make judgment calls — a short checklist (does this page have ads/carousels? is it an SPA? does it require auth?) turns that into a repeatable process instead of tribal knowledge.

These aren't required for MVP viability, but each one is cheap to design for now and expensive to bolt on after targets and incident history already exist in the system.

## 20. Final Recommendation

The project has a solid foundation and should move forward. The key adjustment from the original plan is to treat **false-positive suppression, verification retry, baseline governance, and SSRF protection as core requirements from the start**, not as end-of-project hardening work.

The recommended build order is: get the snapshot loop working first — with SSRF protection, sandboxing, and credential encryption already in place — immediately follow with normalization/masking, then layer in the multi-detector diffing and rules engine. Following this order keeps testing tractable, keeps alert noise low, and gives the system credibility once it's pointed at real, live websites.
