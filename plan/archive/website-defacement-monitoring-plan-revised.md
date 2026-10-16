# Website Defacement Monitoring System - Revised Project Plan

## 1. Executive Summary

The Website Defacement Monitoring System detects unexpected website alterations using deterministic, non-AI diffing methods. The system captures comprehensive snapshots of web pages (including rendered HTML, extracted text, full-page screenshots, and metadata) and compares them against approved baselines representing a known-good state.

The primary architectural direction is sound and well-suited for production. However, planning must emphasize false-positive controls, baseline governance, retry verification, security threat modeling, and operational readiness from the earliest phases. These factors dictate whether the system operates as a reliable alerting pipeline or degrades into an unmanageable source of false alarms.

## 2. Review Summary

### Strengths of Initial Architecture

- Clean component separation across Scheduler, Snapshotter, Diff Engine, Alerting, Storage, and Dashboard layers.
- Selection of Playwright for post-rendering captures, ideal for modern Single Page Applications (SPAs).
- Comprehensive multi-vector detection combining DOM, text, visual, hash, and security-signal rules.
- Proper segregation of object storage (for screenshots and raw artifacts) from relational databases.
- Early recognition of baseline drift, dynamic content challenges, and headless browser scaling.

### Identified Areas for Improvement

- Address file encoding anomalies affecting diagrams and structural symbols.
- Accelerate normalization, ignore selectors, and visual masking into early phases rather than deferring them to Phase 7, as they are essential for noise suppression.
- Implement robust SSRF protection and container sandboxing for user-submitted URLs.
- Delineate distinct operational states: `OK`, `Changed`, `Availability Issue`, `Unstable`, and `Defacement Suspected`.
- Enforce secondary retry verification before dispatching high-severity alerts.
- Establish strict baseline governance to guard against incremental, malicious drift.
- Incorporate data retention schedules, artifact lifecycle policies, and operational metrics.

## 3. Revised High-Level Architecture

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

The core tenet of this revised architecture is embedding Normalization/Masking and the Verification Queue as first-class pipeline stages rather than supplementary add-ons.

## 4. Core Components

### 4.1 Target Management

Enables target URL registration with granular per-target configurations:

- URL, name, owner/team.
- Check interval.
- Viewport dimensions.
- Sensitivity thresholds.
- Detection modes: hash, DOM, text, visual, link/resource, and security rules.
- Ignore selectors and visual ignore regions.
- Allowed external domain lists.
- Authentication profiles for login-gated targets.
- Baseline approval policies.
- Notification routing channels.

### 4.2 Scheduler / Job Queue

Utilizes Celery + Redis or Celery + RabbitMQ with capabilities:

- Distinct scheduling intervals per target.
- Jitter injection to eliminate thundering-herd spikes.
- Exponential backoff retries.
- Dedicated queues separating routine checks, retry verification, and high-priority incident triage.
- Per-domain concurrency limits to prevent denial-of-service against monitored hosts.

### 4.3 Snapshotter

Leverages Playwright to capture post-render artifacts:

- Raw rendered HTML.
- Visible text content.
- Full-page screenshots.
- Page title and meta tags.
- HTTP status codes and response headers.
- Redirect chains.
- Favicon hashes.
- External script, stylesheet, and iframe domains.
- Page load and browser performance timings.

Configurable wait strategies:
- Network idle.
- Selector presence.
- Fixed delays.
- Target-specific custom readiness selectors.

### 4.4 Normalization and Visual Masking

Integrated early in the diffing lifecycle to suppress false positives:

HTML normalization:
- Strip volatile attributes (CSRF tokens, nonces, session identifiers).
- Normalize dynamic timestamps.
- Strip tracking query parameters.
- Exclude known advertisement containers and dynamic widgets.
- Canonicalize whitespace and attribute ordering.

Visual masking:
- Hide elements via `ignore_selectors` prior to screenshot capture.
- Apply post-capture bounding box masks.
- Support masks for dynamic banners, carousels, weather widgets, and financial tickers.

### 4.5 Diff / Comparator Engine

Detectors emit scores, supporting evidence, and diagnostic explanations:

| Detector | Method | Purpose |
|---|---|---|
| Hash diff | Normalized content SHA-256 | High-speed change detection |
| DOM diff | Normalized DOM tree comparison | Injected elements, scripts, iframes |
| Text diff | Line/word diff algorithms | Textual defacement messages |
| Visual diff | pHash, SSIM, pixel comparison | Image, CSS, and styling defacements |
| Link/resource diff | Set diff of links/scripts/iframes | Open redirects, phishing, injected hosts |
| Security-signal rules | Rule-based heuristics | Explainable threat detection |

### 4.6 Security-Signal Rules

High-priority evaluation rules:

- Newly introduced external script domains outside allowlists.
- Injected iframes outside allowlists.
- Removal or weakening of Content Security Policy (CSP) headers.
- Insertion of new inline script blocks.
- Stripping of Subresource Integrity (SRI) attributes.
- Detection of `eval`, `atob`, large base64 blobs, or obfuscated JavaScript.
- Unexpected `<meta http-equiv="refresh">` tags.
- Modified `<form action>` domains.
- Redirect chains terminating on untrusted domains.
- Simultaneous changes to favicon and title/text.
- HTTP 200 transitioning to 403/500/timeout classified initially as an Availability Issue rather than defacement.

## 5. Status Model

Clear differentiation of target states:

- `OK`: No significant changes detected.
- `Changed`: Detected changes below defacement severity thresholds.
- `Availability Issue`: Timeouts, DNS resolution errors, 4xx/5xx responses, or asset failures.
- `Unstable`: Inconsistent check results across consecutive retries.
- `Verification Pending`: Elevated change score awaiting secondary verification.
- `Defacement Suspected`: Confirmed change exceeding thresholds upon re-check.
- `Acknowledged`: Operator triaged and acknowledged.
- `Resolved`: Baseline updated or site restored to known-good state.

## 6. Baseline Policy

Structured governance rules:

- Low severity: Automated baseline updates permitted under strict allowlists.
- Medium severity: Mandatory operator review before baseline adoption.
- High severity: Baselines locked immediately; instant alert dispatch.
- Repeated low-risk changes: Learning windows to capture normal content variance.
- Manual override: Administrators can designate any snapshot as known-good.

Unrestricted auto-rebaselining risks absorbing stealthy, incremental defacements into trusted baselines.

## 7. Retry and Verification Policy

Secondary verification prior to high-severity alerts:

- Re-check scheduled within 1–2 minutes.
- Evaluated via an independent browser instance or separate worker process.
- Executed across alternate network paths or egress IPs where feasible.
- Confirm alerts only if diff scores consistently breach thresholds across runs.
- Discrepancies mark the target as `Unstable` rather than `Defacement Suspected`.

This prevents spurious alerts triggered by CDN propagation lags, transient network errors, or temporary CMS rendering delays.

## 8. Security and Threat Model

Safeguards for fetching arbitrary, user-specified URLs:

- Restrict schemes strictly to `http` and `https`.
- Block private IP ranges (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`).
- Block link-local and cloud metadata addresses (`169.254.169.254`).
- Validate DNS resolution at socket connection to eliminate rebinding gaps.
- Enforce maximum redirect hop limits.
- Enforce upper bounds on response transfer size.
- Impose strict page navigation timeouts.
- Execute browser instances within unprivileged, sandboxed containers.
- Encrypt stored credentials, cookies, and session states.
- Maintain tamper-evident audit logs for baseline approvals and administrative actions.

## 9. Storage and Retention

### Storage Partitioning
- PostgreSQL: Targets, user accounts, configurations, check results, diff metadata, alert states.
- S3 / MinIO: PNG screenshots, raw rendered HTML, text dumps, visual diff masks.
- Partitioned storage / time-series metrics: Historical check records and latency metrics.

### Retention Policy
- Retain full screenshots and raw HTML for 30–90 days.
- Retain metadata and alert history long-term (1–2 years).
- Archive incident-related snapshots indefinitely.
- Apply object storage lifecycle rules to minimize ongoing storage overhead.
- Enable gzip/brotli compression on HTML and text artifacts.

## 10. Proposed Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Browser Automation | Playwright Python async | High-fidelity rendering, screenshotting, DOM access |
| Backend API | FastAPI | Asynchronous performance, native OpenAPI documentation |
| Distributed Queue | Celery + Redis / RabbitMQ | Scheduling, retries, worker scaling |
| Database | PostgreSQL | Structured relational integrity and JSON querying |
| Object Storage | S3 or MinIO | Efficient storage for heavy image and HTML artifacts |
| Visual Diffing | Pillow, imagehash, scikit-image | pHash, SSIM, and masked pixel comparison |
| DOM / Text Diffing | lxml, difflib, diff-match-patch | Deterministic tree and textual diffing |
| Web Dashboard | React or htmx | Responsive UI and side-by-side artifact comparison |
| Notifications | SMTP, Slack, Discord, Webhooks, SMS | Multi-channel alerting |
| Observability | Prometheus, Grafana, Loki / ELK | Operational telemetry |
| Containerization | Docker Compose / Kubernetes | Reproducible Playwright execution environments |

## 11. Operational Metrics

Key monitored indicators:

- Checks executed per minute.
- Queue depth and worker latency.
- Mean render and capture duration.
- Browser crash and unhandled exception rates.
- Navigation timeout frequency.
- Diff processing latency.
- Alert volume categorized by severity.
- Retry confirmation vs. instability rates.
- Measured false-positive rates.
- Artifact storage consumption growth.
- Per-domain availability failure rates.
- Worker container memory and CPU utilization.

Playwright worker hygiene:
- Periodic worker process recycling (`worker_max_tasks_per_child`).
- Bounded browser context limits.
- Container memory caps to mitigate memory leaks.
- Graceful shutdown handling preventing partial artifact writes.

## 12. Revised Build Phases

### Phase 1: Core Snapshot Loop
- Single target monitoring.
- Playwright capture of HTML, text, screenshots, and metadata.
- Storage of artifacts to local filesystem / object storage.
- Basic hash comparison.
- Baseline status classifications: `OK`, `Changed`, `Availability Issue`.

### Phase 2: Normalization and Noise Control
- HTML normalization pipeline.
- Ignore selectors and visual masking.
- Viewport standardization.
- External domain allowlists.
- Baseline approval governance.

### Phase 3: Multi-Detector Diffing
- Text and DOM diff engines.
- Visual diffing with pHash and SSIM.
- Link and external resource diffing.
- Structured diff result schemas.

### Phase 4: Scheduler and Multi-Target Support
- Celery / distributed task workers.
- PostgreSQL target management.
- Dynamic check intervals with jitter.
- Per-domain concurrency limits.

### Phase 5: Rules Engine and Verification Queue
- Weighted severity scoring.
- Security-signal rule evaluations.
- Automated retry verification pipeline.
- Comprehensive status model.
- Baseline approval workflow.

### Phase 6: Alerting
- Notification dispatch (Email, Slack, Webhooks).
- Alert deduplication and throttling.
- Rich payloads with embedded diffs and evidence summaries.

### Phase 7: Web Dashboard
- Target list and real-time status indicators.
- Historical check timelines.
- Side-by-side visual and text diff viewers.
- Incident acknowledgment and baseline approval UI.
- Target configuration management.

### Phase 8: Hardening and Scale
- SSRF guard and DNS validation.
- Credential encryption at rest.
- Container isolation and sandboxing.
- Storage retention lifecycle rules.
- Production load testing and worker recycling.

## 13. Final Recommendation

The architectural foundations are solid. By establishing noise reduction, verification retries, baseline governance, and SSRF prevention as core requirements from Phase 1 rather than late-stage enhancements, the project will achieve high alerting fidelity, low operational noise, and enterprise-grade reliability in production.
