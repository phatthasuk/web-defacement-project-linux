# Website Defacement Monitoring System — Project Plan

**Documentation updated:** 2026-10-19 (source/evidence reconciliation; no new application test or runtime verification)
**Source baseline:** `ba1bbf2d8933293f115a2336df57b0d5430c30b7`
**Last recorded operational update:** 2026-09-07 (Stage 2 restarted; previous run cancelled; not reverified by this planning update)
**Supersedes:** every document in [`plan/archive/`](archive). Those are kept for history only; where they disagree with this file, **this file wins**.

This is the authoritative project roadmap for what the system is, what is built, what was
deliberately rejected, and what happens next. It carries forward the material from
the archived plans that is still useful, and drops or corrects the rest.
This roadmap owns core monitoring priorities, stage status and cross-feature
constraints. Standalone add-on plans own their scope, delivery sequence and
acceptance criteria independently of the numbered stages.

The [status and backlog register](ROADMAP_STATUS_AND_BACKLOG.md) separates
Implemented, Tested and Runtime verified, records evidence limitations and owns
the cross-plan open-work inventory. Historical reports remain dated evidence;
their test totals are not current-baseline verification.

---

## 1. What the system does

Periodically captures a website, compares the capture against approved
known-good baselines, and reports when something changed. Detection is
**deterministic** — no AI/ML — using text, pixel and structural comparison.

Similar in spirit to change-detection services (Visualping), but the purpose is
security monitoring of sites the organisation owns.

---

## 2. Operating constraints — read this first

These drive every priority decision below, and are the most important thing that
was missing from the archived plans.

| Constraint | Value | Consequence |
| :--- | :--- | :--- |
| **Operators** | Initially one person; Admin/Operator assignments now implemented | Keep alert volume manageable; verify full multi-user acceptance before claiming readiness. |
| **Check frequency** | **Hourly** | ~24 checks per target per day |
| **Targets** | **6+, expected to grow.** BCH group: bangkokchainhospital, kasemrad.co.th, kasemradari, kasemradinter, kasemradvientiane, theworldmedicalhospital, sustainability.bangkokchainhospital | 10 targets hourly = **240 checks/day** |
| **Deployment** | Single-machine Linux Docker target; HTTPS reverse-proxy configuration exists | Single uvicorn worker; actual server/container state remains unverified in this update |
| **Authorisation** | All targets are owned by the organisation | Satisfies the "get written authorisation before monitoring" requirement |

### The arithmetic that shapes the roadmap

```
240 checks/day x ~2 MB per full-page snapshot        = ~480 MB/day = ~175 GB/year
240 checks/day x current visual false-positive rate  = ~240 alerts/day for one person
```

These are original sizing assumptions, not current measurements or false-positive
labels. Stage 1.2 discards captured artifacts on OK, but Changed evidence still
accumulates. The [Stage 2 audit](../audit%20stage2.md) reports 3,587 Changed out of
3,620 local historical results and roughly 300 MB/day retained artifacts across
four active targets. Referenced-snapshot retention remains open; Stage 3 owns
selective notification. The audit does not establish live server state.

---

## 3. Current status

**Historical record, 2026-09-03:** 112 pytest / 50 vitest passing; ruff, mypy, tsc and
eslint clean (one pre-existing eslint warning in `useAuth.tsx`); Alembic
migrations upgrade and downgrade cleanly; production build succeeds.

**Stage 1 implementation was recorded complete on 2026-09-03.** Checks implement unattended scheduling, unchanged
captures retain no artifact files (database metadata still grows), and availability failures are distinguished from content
changes. Current deployment acceptance remains open. See [Stage 1 implementation](../refinement/9-3-2026/Stage1-Implementation-3-9-2026.md),
[baseline implementation](../refinement/9-3-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md)
and [`plan/archive/review stage 1 by opus 5.md`](archive/review%20stage%201%20by%20opus%205.md).

### 3.1 Implemented capabilities

This table describes inspected source only. The independent Tested and Runtime
verified statuses for every capability are in the
[verification matrix](ROADMAP_STATUS_AND_BACKLOG.md#implementation-and-verification-matrix).
Existing tests and reports cover subsets. The October 19 frontend transcript
names files absent from this source and needs provenance review before reuse.

| Area | What exists |
| :--- | :--- |
| **Capture** | Playwright/Chromium, SSRF proxy with validated upstream socket addresses, fixed 1440x900 viewport, full-height screenshot clipped horizontally to viewport for comparison, raw overflow screenshot retained, visible text and post-JS HTML |
| **Page stabilisation** | Multi-phase: DOMContentLoaded, prescroll, adaptive network-quiet, freeze animations/transitions, force reveal-library elements visible, force lazy images to load and decode, wait for layout to settle, pin carousels through their own API, scroll to top, capture |
| **Overlay handling** | Preserves overlays. No automatic consent/close clicks, even when legacy DISMISS_OVERLAYS=true; page handlers could remove evidence |
| **Detection** | Three detectors: text, visual (pixel), **structural** |
| **Baselines** | Multiple approved baselines per target (cap 20); a check is compared against all of them and judged by the closest match |
| **Review workflow** | First capture and captures after URL revision changes await human approval; scheduling holds pending candidates. Approval adds a baseline and acknowledges its matching check, resolving the latest matching change to OK. Gallery list/demote, confirm Defaced and actor-attributed transactional audit exist; last-baseline demotion guard remains |
| **Operator tooling** | Client-side 3-panel heatmap and screenshot zoom, target search/status/tag filters and Changed-first/structural-score sorting; UTC serialization exists for target/check artifacts, while member timestamp normalization remains B-11b |
| **Auth and members** | Local Argon2id auth, hashed sessions, CSRF/lockout/rate limits; fixed Admin/Operator roles, assignment-scoped APIs, pending registration/Admin approval, suspend/reset/change-password flows, session revocation and persistent member/review audit. Full acceptance is open in the member plan |
| **Scheduling** | In-process hourly scheduler with jitter and duplicate suppression; persisted retry deadlines/attempt history with up to 3 total attempts by default. Network retry delays default to 120/300 seconds plus jitter, with bounded Retry-After support. This is separate from future content-confirmation checks |
| **Artifact lifecycle** | Capture writes to `data/staging/{snapshot_id}/`; artifacts are promoted to permanent storage only for a baseline or a real change, and discarded on `OK`. Startup reconciliation removes expired staging directories and files no `Snapshot` row references, all confined to `DATA_DIR` |
| **Reliability** | Semaphore-limited concurrency (4 global, 1 per domain source defaults), timeout, startup recovery, proxy transfer and pre-render budgets; Compose CPU/memory/PID limits configured, effective Linux behavior unverified |
| **Frontend** | React + TS + Vite + Tailwind + TanStack Query: login/register/change-password, targets/checks, tags and members/assignments; silent auth revalidation and explicit artifact/query error states |

### 3.2 The three detectors

Noise measurements below are historical single-page observations, not a policy
validated across all current targets. Stage 2 remains open.

| Detector | Compares | Catches | Blind to | Measured noise on an unchanged real page |
| :--- | :--- | :--- | :--- | :--- |
| **Text** | visible text | defacement messages, content edits | anything hidden (`display:none` is excluded from `inner_text`), invisible injections | **0.000000** |
| **Visual** | full-page screenshot pixels | image/logo swap, layout change, CSS-based hiding | invisible injections | **0.028 - 0.054** (see 5.1) |
| **Structural** | set of facts parsed from the stored HTML | new `<script src>`, hidden `<iframe>`, repointed `<form action>`, `meta refresh`, changed inline script, new outbound link host | pure content edits with no structural change | **0.000000** |

The structural detector covers the threats that matter most for a compromised
CMS: SEO/pharma spam, injected skimmers, hidden iframes and redirects. Those are
placed **below the fold on purpose** and move no pixels.

**Structural facts extracted** (prefixed so a summary is human-readable):
`script:<url>` · `inline-script:<sha256[:16]>` · `iframe:<url>` · `form:<action>` ·
`stylesheet:<url>` · `meta-refresh:<content>` · `link-host:<host>`

Current extraction also covers event handlers, normalized JavaScript URLs,
formaction, base URLs, iframe srcdoc/sandbox and script execution classification.
Form owner association and explicit destination policy remain SEC-03 follow-ups.

Design notes:

- Parses the HTML artifact **already stored** by capture, at diff time. `page.content()`
  serialises the DOM *after* scripts run, so JS-injected elements are included, and the
  detector works retroactively on snapshots taken before it existed.
- Uses stdlib `html.parser` — no new dependency in a component that handles hostile input.
- Inline scripts are stored as a **hash only** (bodies can contain secrets).
- Outbound links are recorded **per host**, so a 100-link spam farm is one finding.
- Relative URLs are resolved against the page URL, so `/app.js` and its absolute form match.

### 3.3 Configuration (source defaults; effective deployment values unverified)

| Setting | Value | Note |
| :--- | :--- | :--- |
| `TEXT_CHANGE_THRESHOLD` | 0.02 | |
| `VISUAL_CHANGE_THRESHOLD` | 0.01 | Currently exceeded by noise on carousel-heavy sites |
| `STRUCTURE_CHANGE_THRESHOLD` | **0.0** | Zero tolerance: one new external script is worth reporting regardless of size |
| `MAX_BASELINES_PER_TARGET` | 20 | |
| `MAX_CONCURRENT_CHECKS` / `PER_DOMAIN_CONCURRENCY` | 4 / 1 | Process-local; requires a single uvicorn worker |
| `PAGE_TIMEOUT_SECONDS` / `CHECK_TIMEOUT_SECONDS` | 25 / 90 | |
| `VIEWPORT_WIDTH` x `VIEWPORT_HEIGHT` | 1440 x 900 | Fixed for determinism |
| `BROWSER_DISABLE_SANDBOX` | false | Chromium sandbox **on** by default |
| `BLOCK_WEBSOCKETS` | true | |
| `MAX_ARTIFACT_SIZE_MB` | 10 | Output file cap; complemented by early budgets below |
| `MAX_CAPTURE_TRANSFER_MB` | 100 | Aggregate proxy transfer budget |
| `MAX_SCREENSHOT_HEIGHT_PX` / `MAX_SCREENSHOT_PIXELS` | 30000 / 64000000 | Checked before screenshot; explicit width cap deferred under B-11c |
| `MAX_DOM_NODES` | 300000 | Checked before DOM serialization |
| `CHECK_RETRY_MAX_ATTEMPTS` / `CHECK_RETRY_DELAYS_SECONDS` | 3 / 120,300 | Total attempts include initial; settings validated at startup |
| `REDIRECT_LIMIT` | 5 | |
| `SCHEDULER_ENABLED` | true | Set false to run without automatic checks |
| `CHECK_INTERVAL_SECONDS` | 3600 | Base interval per target |
| `CHECK_JITTER_MAX_SECONDS` | 180 | Random 0-180s added per run to avoid a thundering herd |
| `SCHEDULER_POLL_INTERVAL_SECONDS` | 15 | How often the scheduler loop wakes to check due times |
| `STAGING_CLEANUP_MAX_AGE_SECONDS` | 1800 | Staging directories older than this are removed at startup |

### 3.4 Status model (as built)

`Never Checked` · `Checking` · `OK` · `Changed` · `Failed` ·
`Availability Issue` · `Acknowledged` · `Defaced` · `Awaiting Baseline`

`Availability Issue` was added in Stage 1.3. A timeout, DNS failure, connection
reset or HTTP 5xx now lands there instead of `Failed`, and the staged capture of
an error page is discarded so it cannot be diffed as a content change.
`SsrfBlockedError` is deliberately excluded: a blocked SSRF attempt is a security
event and stays `Failed`.

The archived production plan specifies four more (`Unstable`,
`Verification Pending`, `Defacement Suspected`, `Resolved`), which belong with the
rules engine in Stage 6.

---

## 4. Design principles

Decided during development, usually after being proven the hard way.
**Do not reverse these without re-reading the reasoning.**

### 4.1 Never blind the monitor to make the numbers look better

A retrieval failure, a hidden element or an ignored region must never be
reported as "unchanged". Concretely:

- **Nothing is hidden with `display:none` during capture.** It removes content from
  the screenshot *and* from `inner_text("body")`, so a defacement delivered as a
  `.modal` — or carrying any class name on a hide list — would vanish from both
  diffed artifacts. Capture once injected such CSS; it was removed, and
  `test_capture_does_not_hide_overlay_content` guards against it returning.
- **The frontend never renders a failed artifact load as "no differences".** Loading,
  failed, and successfully-empty are distinct states.
- **Do not dismiss page-controlled overlays.** Clicking can run attacker-controlled
  handlers and erase evidence. The earlier claim that dismissal was safe is withdrawn.

### 4.2 Wait for the page to finish; do not force it into a state

| Legitimate (does not change content) | Dangerous (fabricates a state) |
| :--- | :--- |
| wait for network quiet, lazy images, webfonts, layout to settle | hiding overlays or preloaders |
| freeze animations mid-flight so the shutter is deterministic | — |

Forcing reveal-library elements visible and pinning carousels sits between the
two: it cannot hide a defacement (it only makes content *more* visible), but the
captured page is then not exactly what a visitor sees. Kept, with that caveat
recorded — it is an open question, not a settled principle.

### 4.3 Detect everything; notify selectively

With one operator and 240 checks/day, a flood of alerts *is* a false negative,
because they get muted. The resolution is not to detect less, but to separate:

- **Detection:** full sensitivity, everything recorded to the database and dashboard.
- **Notification:** strict; only high-confidence signals reach a person.

### 4.4 A false positive beats a false negative — but alert fatigue is a false negative

Explicit decision by the project owner. Where a trade-off exists, prefer
over-reporting. This is why masking and sensitivity reductions were rejected
(section 6). Principle 4.3 is how that survives contact with 240 checks/day.

### 4.5 An attacker does not confine themselves to the visible area

Persistence-oriented attackers deliberately hide below the fold and outside the
rendered view. Any proposal that reduces monitored surface must be judged
against this.

---

## 5. Known limitations and accepted trade-offs

### 5.1 Visual false positives on carousel-heavy sites — accepted

On `bangkokchainhospital.com/th/home`, two captures of an **unchanged** page
differ by roughly **0.03-0.05** against a threshold of 0.01.

| Stage | Visual | Text |
| :--- | :--- | :--- |
| Before stabilisation | 0.211 - 0.294 | 0.0154 |
| After stabilisation | 0.039 | **0.000000** |
| After multi-baseline | 0.039 (closest baseline chosen, but none matched) | 0.000000 |
| After removing overlay hiding | 0.051 | 0.000000 |

**Root cause, confirmed:** `sd-hero-banner__swiper` — a Swiper carousel with
`loop: true`, 5 slides, `swiper-fade`, three instances on the page. Autoplay is
stopped and `realIndex` is pinned to 0 successfully, but the wrapper still lands
on a slightly different `translate` (-401 vs -417) between runs, shifting a whole
section by about 10px. Four fixes were attempted — CSS freeze, prescroll plus
forced reveal, `scrollLeft` reset, and Swiper API `update()` + `slideToLoop()` —
none brought it under threshold.

Evidence this is genuine carousel state rather than sub-pixel noise: two captures
that happen to land in the same state score **0.0026**, well under threshold,
while other pairs score about 0.043.

**Decision:** accept it. Freezing every carousel library is an unwinnable arms
race across a growing set of sites, and every alternative creates a blind spot.
Principle 4.3 is the intended notification policy; it is not implemented yet.
Stage 4.2 remains planned and must use reviewed observations.

### 5.2 Other limitations

- **Single worker required.** Concurrency limits and duplicate suppression are
  process-local, and startup stale-check recovery assumes no sibling worker is
  mid-check. Run `uvicorn --workers 1`.
- **Snapshots without an HTML artifact** make the structural detector report
  "Structural comparison unavailable" rather than failing the check.
- **Allowlist is API-only.** `Target.allowed_domains` can be set through
  POST/PATCH but has no UI field yet.
- **The captured page is not pixel-identical to a visitor's view** (see 4.2).
- **Quiet-period snapshots are discarded (Stage 1.2 trade-off).** When a check
  reports `OK`, captured artifacts are discarded immediately to reduce
  disk accumulation. Baselines and changed snapshots remain fully preserved, but
  forensic visual records of quiet periods are traded off for storage sustainability.

---

## 6. Rejected approaches, and why

Recorded so they are not re-proposed.

| Rejected | Reason |
| :--- | :--- |
| **`ignore_selectors` masking a page region** | Creates a blind spot exactly where an attacker would hide. The archived production plan section 3.4 recommends this via `display:none` before capture — **that guidance is withdrawn.** |
| **Scoring only the first viewport height instead of the full page** | Same reason. Below the fold is where SEO spam, injected scripts and hidden iframes live. Current comparison retains full height but clips horizontal overflow to the fixed viewport width, with raw overflow retained separately. |
| **Noise mask (`MASK_LEVEL=16`) in the visual diff** | Lowers sensitivity across the whole page, and measurement showed the residual is real carousel state, not compression noise. It also reverses a deliberate "any channel differs" test. |
| **Continuing to chase carousel freezing** | Four attempts, negligible gain; every fix is library-specific and will not generalise across a growing site list. |
| **Auto-rebaseline on detected change** | Can silently absorb a real defacement into the baseline. Human approval remains required; an overlay trigger does not establish trust. Historical analysis is preserved in [`plan/archive/auto-rebaseline.md`](archive/auto-rebaseline.md), not authorized as an exception to current approval rules. |
| **Celery / durable queue now** | Over-engineering at 10-20 targets on one machine. In-process scheduling plus the existing stale-check recovery is sufficient; revisit before scaling out. |
| **HTML-only hash gate for image diff** | Withdrawn Stage 4.5 proposal: images or CSS at unchanged URLs can change while HTML remains identical. Never skip visual comparison on HTML equality alone. |

The earlier deferral of RBAC is superseded by the implemented Member Management
add-on. Existing role and website scope checks must be preserved.

---

## 7. Review findings and remaining acceptance

Original IDs and severity below are historical review labels. Implementation is
reconciled to October 19 source; closure still requires the separate test/runtime
evidence in the [register](ROADMAP_STATUS_AND_BACKLOG.md).

| Finding | Implemented scope | Remaining work / owning plan |
| :--- | :--- | :--- |
| F1 (P1) | Auth and fixed Admin/Operator assignment authorization implemented | Full member permission matrix, fresh/legacy migration and deployed acceptance; Member Management plan |
| F2 (P1) | SSRF proxy validates DNS addresses and connects upstream sockets to validated IPs | Linux egress, redirect, WebSocket and WebRTC acceptance; Security review / Phase 5 |
| F3 (P2) | Proxy transfer budget, pre-screenshot pixel/height and pre-serialization DOM caps; Compose resource limits configured | Effective cgroups/seccomp, hostile-page acceptance, deferred B-11c width bound; SEC-06 / Phase 5 |
| F4 (P2) | Explicit artifact and target-detail query failures/retry handling implemented | Reconcile frontend test evidence and browser acceptance; F-04/F-05 and focus plan |
| F5 (P2) | Staging/promote/discard and startup reconciliation implemented | POSIX cleanup acceptance; referenced-snapshot retention is a separate open work item |
| F6 (P1) | WebSocket blocking and service_workers=block implemented | Deployment-equivalent bypass/egress acceptance; Phase 5 |
| F7 (P2) | Sandbox enabled by default and hardened Compose configuration present | Actual browser/sandbox/seccomp and image verification; SEC-01 / Phase 5 |
| F8 (P2) | Persisted retry deadlines/attempts and startup/finalization recovery implemented | Existing stuck-row deployment recovery; distributed queue/lease/DB duplicate suppression deferred to Stage 6 |

Persistent member/review audit, change-password and user lifecycle fields are
implemented. Complete auth-event audit coverage remains a scope review, not a
claim that all audit is absent. `normalized_username` is absent; the member plan
deliberately preserves case-sensitive username matching. MFA/OIDC remain deferred.
SEC-01–SEC-07 and B/F remediation IDs keep their own acceptance criteria; source
fixes alone do not close them. B-04 remains refuted/excluded.

---

## 8. Roadmap

Ordered by *what makes the system usable by one person monitoring 6+ sites
hourly*, not by code-review severity. The reasoning is in section 2.

**Sequencing decision (2026-09-02):** notification is deliberately *not* built
first. Its policy — which detector on which target justifies interrupting a
person — should be derived from measured behaviour across all targets, not from
a single test site. Stage 1 makes an unattended test run possible, Stage 2 is
that run, and Stage 3 designs notification from what it produces.

**Accepted consequence:** until Stage 3 ships, the system does not protect
anything on its own. Findings are recorded but nobody is told, so someone has to
open the dashboard. That is acceptable for a supervised test period and is not
acceptable afterwards.

### Stage 1 — Enable an unattended test run (historical implementation complete)

Implemented: Implemented. Tested: Partial (historical records; no current rerun).
Runtime verified: Not verified for the current deployment. Checkmarks below refer
only to the historical implementation milestone.

| # | Work | Why it was needed | Status |
| :--- | :--- | :--- | :--- |
| **1.1** | **Scheduler** — automatic checks on a per-target interval, with jitter to avoid a thundering herd | Without it, 240 manual button presses per day. Nothing can be observed without it | ✅ `app/services/scheduler.py` |
| **1.2** | **Discard unchanged snapshots after diffing**, and clean up orphan artifacts left by failed checks (**this is F5**) | Must ship *with* 1.1, not after: an unattended hourly run across 6+ targets writes about 480 MB/day, so a multi-week observation period would fill the disk before it finished | ✅ staging pipeline + `reconcile_artifacts` |
| **1.3** | **Separate `Availability Issue` from `Changed`** — a timeout, DNS failure or 5xx is not a defacement | Transient failures will be frequent at 240 checks/day. Without this they are recorded as `Failed` and pollute the very measurements Stage 2 depends on | ✅ `is_availability_error` + status transitions |

**Carried into Stage 2 as a known nit:** `_on_task_done` in the scheduler calls
`logger.exception()` outside an `except` block, so a failed check logs its message
outside the original exception context. Traceback presentation remains unverified;
review this logging behavior when diagnosing scheduler failures.

### Stage 2 — Observation period (no new features)

Implemented: Partial (scheduler/data collection exist; measurement acceptance open).
Tested: Partial (historical local-data audit). Runtime verified: Not verified for
current all-target coverage. The [audit](../audit%20stage2.md) did not establish exit
criteria. The September restart below is historical, not an instruction to reset
the current run. Stage 2 has no new feature delivery; proposed reporting tools
remain separate add-ons.

> [!NOTE]
> **Operational Status Update (2026-09-07):** The previous Stage 2 soak test initiated on 2026-09-03/04 was cancelled and reset. A fresh Stage 2 observation period officially restarts today, **2026-09-07**, on the Ubuntu server (running hourly checks across all targets for 2–4 weeks to collect clean baseline metrics following the recent Target management, Defaced status, and UI fixes).

Run every target hourly for **2-4 weeks** and collect evidence. This is the soak
test the archived production plan called for, and it is the input to Stage 3.

| # | What to measure | Feeds |
| :--- | :--- | :--- |
| 2.1 | How often each detector (text / visual / structural) fires, **per target** | Stage 3.2 notification policy |
| 2.2 | Distribution of visual scores on unchanged pages, **per target** — each site's own noise floor | Stage 4.2 per-target thresholds |
| 2.3 | Check failure rate and cause (timeout, DNS, 5xx) | Stage 3.2, and whether `PAGE_TIMEOUT_SECONDS` needs raising |
| 2.4 | Actual storage growth after 1.2 | Retention policy in 9.3 |
| 2.5 | Check duration per target, and whether hourly rounds overlap | Concurrency settings |

**Exit criteria before designing notification:** every target has run for at
least two weeks, and for each target it is known which detectors are quiet
(0.000000 on an unchanged page) and which are not. Only quiet detectors are
candidates for immediate notification.

### Stage 3 — Notification, designed from Stage 2 data

Implemented: Not started. Tested: Not run. Runtime verified: Not verified.
Persisted network retries do not implement Stage 3.3 content verification.
Recipient routing must respect active Admin/Operator assignment scope at delivery.

| # | Work |
| :--- | :--- |
| 3.1 | **Choose the channel** — email or webhook (Line / Teams / Slack). **Deferred question, still open.** One channel only |
| 3.2 | **Tiered policy.** Working hypothesis from BCH data, to be confirmed or replaced by Stage 2: notify on structural and text changes (both measured 0.000000 on an unchanged page), do not notify on visual-only changes (measured 0.028-0.054). Every notification names the detector that fired and includes the structural summary |
| 3.3 | **Verification retry before notifying** — re-check after 1-2 minutes and notify only if the finding persists. Removes transient false positives before they reach the one operator |
| 3.4 | **Escalation alert for sustained `Availability Issue`** — an attacker taking a site down or triggering 500 errors must not stay silent indefinitely. A target remaining in `Availability Issue` across several consecutive checks (e.g. 2-3 hours) must escalate as an availability incident |

### Stage 4 — Make it comfortable for one person

Implemented: Partial. Tested: Evidence needs review for current frontend claims;
historical baseline/scheduling tests cover subsets. Runtime verified: Not verified.

| # | Work |
| :--- | :--- |
| 4.1 | **Partial:** target search, status/tag filters and Changed-first/structural-score sorting exist. Comprehensive severity/detector triage remains open |
| 4.2 | **Planned:** reviewed per-target visual calibration based on labelled unchanged samples. Do not automatically learn unreviewed changes or silently lower text/structural sensitivity; preserve raw scores/evidence |
| 4.3 | **Implemented behavior; acceptance open:** baseline approval acknowledges the matching check and can resolve the latest matching change to OK. Gallery/list/demote exists. Verify UI semantics rather than implement a duplicate combined mutation |
| 4.4 | **Partial:** per-target allowed_domains API exists and currently filters expected-host facts. System-wide defaults, UI and the decision to retain/label raw findings remain open; preserve security-sensitive form/script evidence |
| 4.5 | **Withdrawn:** HTML-only hash equality must not bypass image diff; unchanged HTML can reference changed resources |
| 4.6 | Diff heatmap: a `baseline / current / highlighted` preview so a human sees *where* it changed. Take the 3-panel composite from the prototype, **not** its mask threshold. ✅ **Done 2026-09-03** — implemented client-side on canvas (images fetched as blobs so the canvas is same-origin and never tainted), so it adds no disk or database footprint |

### Stage 5 — Close the remaining review findings

Implemented: Partial. Tested: Partial (subset records; October 19 provenance review
open). Runtime verified: Partial (October 15 Linux subsets reported; full container
acceptance open). This core Stage 5 is distinct from remediation **Phase 5**.

| # | Work |
| :--- | :--- |
| 5.1 | **F3 source controls implemented:** transfer, DOM, height/pixel and Compose resource limits; complete SEC-06/Phase 5 acceptance and B-11c follow-up. Do not claim every historical suggested control (e.g. request/frame/host caps) exists |
| 5.2 | **F2 proxy pinning implemented:** complete Linux redirect/egress acceptance rather than rebuilding hostname pinning |
| 5.3 | **Auth lifecycle/member-review audit implemented:** complete member acceptance; review broader auth-event audit scope and defer MFA/OIDC |
| 5.4 | **F4 source error-state fixes implemented:** reconcile test provenance and verify browser/query failures |
| 5.5 | **Partial:** existing fixtures, regressions and probes cover subsets; consolidate reproducible end-to-end synthetic scenarios, including image and header changes |

### Stage 6 — Later / larger

Implemented: Not started for the listed future architecture. Tested: Not run.
Runtime verified: Not verified. Existing retry persistence is tracked in Stage 1,
not counted as delivery of a distributed queue.

Durable job queue with leases and heartbeats (**F8 remainder**) · full status
model and rules-engine severity scoring · MFA and OIDC migration · object
storage with lifecycle policies · Prometheus metrics · auto-rebaseline (see
archive).

---

## 9. Reference material carried forward

### 9.1 Security-signal rules worth adding to the structural detector

From the archived production plan section 3.6. Those already covered are marked.

| Signal | Severity | Covered? |
| :--- | :--- | :--- |
| New external script domain outside the allowlist | high | yes |
| New iframe outside the allowlist | high | yes |
| New inline script block | medium-high | yes (content hash) |
| Unexpected form `action` domain | high | yes |
| Unexpected `meta refresh` | medium | yes |
| Redirect chain changed to an untrusted domain | high | no — the redirect chain is not stored |
| **CSP header removed or weakened** | high | no — response headers are not captured |
| Subresource Integrity attribute removed | medium-high | no |
| Suspicious `eval`, `atob`, long base64 blobs, obfuscated JS | high | no — only the hash of inline scripts is kept |
| Favicon changed together with a title/text change | medium | no |
| More than 30% of visible text changed | medium-high | partial (text score) |
| Visual diff over 15% of pixels | medium | partial (visual score) |
| HTTP 200 becomes 403/500/timeout | availability first | HTTP/network failure classification exists; sustained notification escalation is Stage 3.4 |

Capturing **response headers** and the **redirect chain** would unlock three of
these cheaply, and is worth folding into Stage 5.

### 9.2 SSRF requirements (still binding)

`http`/`https` only · block private ranges (`127/8`, `10/8`, `172.16/12`,
`192.168/16`), link-local and cloud metadata (`169.254.169.254`) · validate DNS
before fetch and on every redirect hop · cap redirects, response size and page
timeout · treat any uncertain resolution or interception failure as blocked ·
egress firewall rules as defence in depth, because browser-level interception
cannot close every race.

### 9.3 Retention policy (target state)

Full screenshots and raw HTML: 30-90 days · metadata and alert history: 1-2 years ·
**confirmed-incident snapshots: retain indefinitely** · compress text/HTML
artifacts. Stage 1.2 adds the missing piece: unchanged snapshots need not be kept
at all.

This retention policy is not implemented for Snapshot-referenced artifacts.
`scripts/cleanup_artifacts.py` inventories/applies expired orphans only; it retains
all referenced snapshots. Coordinated DB/artifact backup, restore, reference
protection and partial-deletion recovery are separate acceptance requirements.

Cleanup must verify that every path resolves beneath `DATA_DIR` before deleting,
and must never delete a path merely because it came from the database.

### 9.4 Operational metrics worth tracking

Checks per minute · queue depth · average render time · browser crash count ·
timeout rate · diff processing latency · alert count by detector · retry
confirmation rate · storage growth · per-domain failure rate.

### 9.5 Target onboarding checklist

Adding a target needs human judgement that no schema captures. Before enabling a
new site, record: does it have ads, carousels or rotating banners? · is it an
SPA? · does it need authentication? · which third-party hosts are expected
(allowlist)? · what check interval? · who is notified?

### 9.6 Frontend stack notes

React + TS + Vite + Tailwind + TanStack Query + React Router are in use and
working. The archived recommendation also suggested shadcn/ui,
react-diff-viewer, recharts and React Hook Form + Zod; none are used. Zod is
worth revisiting when Stage 4.4 adds target configuration forms.

---

## 10. Naming

Earlier work used four overlapping numbering schemes (code-review findings 1-8,
Phases A-D, capture-improvement items 1-5, and ad-hoc option letters), which
caused real confusion. Going forward:

- **Findings** keep their `codereviewbygptsol` numbers, `F1`-`F8`, listed in section 7.
- **Stage work** is referenced by its Stage number from section 8, e.g. "Stage 1.2".
- **Standalone add-ons** use their feature names and their own plan documents;
  they do not receive Stage numbers or belong to the numbered roadmap in section 8.
- Do not introduce competing numbering schemes.

---

## 11. Document map

| Location | Contents |
| :--- | :--- |
| `plan/PROJECT_PLAN.md` | **Active core monitoring roadmap** |
| [Status and backlog register](ROADMAP_STATUS_AND_BACKLOG.md) | Three-dimensional capability status, evidence register, open acceptance/remediation and proposed add-ons |
| [Member Management](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md) | Standalone member scope and acceptance; implementation exists |
| [Remediation plan](Remediation_Plan_19-10-2026.md) | Audit finding ownership and historical execution reports; section 6 provenance review open |
| [Linux remediation Phase 5](Phase_5_Linux_Container_Runtime_Verification.md) | Container runtime acceptance and execution evidence |
| `plan/archive/TAGS_MANAGEMENT_PLAN.md` | (Completed) Detailed plan for Tags management, website tag assignment, header navigation and filters |
| `plan/archive/` | All previous plans and review documents, kept for history |
| `refinement/<date>/` | Dated point-in-time records of completed work |
| `PROJECT_STRUCTURE.md` | Repository layout |

Archive policy clarified on 2026-10-19: archive a plan/review when its scoped code
changes are implemented, even if test or runtime acceptance remains open. Keep
those verification obligations in the active status register and link to the
archived acceptance contract. Archiving is not finding closure. Roadmap, register
and plans with unfinished code remain active; see the [planning index](README.md).

### Plan archive review — 2026-10-16

Historical review retained below. Current source and evidence status is reconciled
in the October 19 [register](ROADMAP_STATUS_AND_BACKLOG.md); older missing-control
and test-environment statements below must not override it.

All eight Markdown documents at the top level of `plan/` were reviewed against
the available source, tests and implementation records. Existing historical
documents under `archive/` remain archived. A source implementation alone does
not close a plan whose acceptance criteria still require verification. Some older
plan headers describe their original planning state; the evidence below records
why those documents remain active without claiming a new deployment or test pass.

| Document | Decision | Evidence or remaining work |
| :--- | :--- | :--- |
| `PROJECT_PLAN.md` | Keep active | Core roadmap still contains unfinished stages and operational work. |
| [Member Management](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md) | Keep active | Member routes, UI and tests exist, superseding the original not-implemented description. The complete acceptance matrix and fresh/legacy Alembic migration verification are not recorded as complete. |
| [Page flicker on focus](archive/implemented-20261019/Page-Flicker-On-Window-Focus-Fix%20By%20Argon.md) | Keep active | Silent revalidation, cooldown and regression tests exist. Browser acceptance is not recorded; the Windows test rerun could not start because the installed dependencies lack the Rolldown Windows native binding. |
| [OK target scheduling](archive/implemented-20261019/Review%20issue%20by%20Argon%20Edit%20by%20Sol.md) | Keep active | [Implementation record](../refinement/10-16-2026/OK-Target-Scheduling-Fix-16-10-2026.md) records 73 passing tests, but explicitly leaves UI verification and deployment recovery unverified. |
| [Review by GPT 6.1 Sol](archive/implemented-20261019/Review%20By%20GPT%206.1%20Sol%2014-10-2026.md) | Keep active | The later Round 2 report records source fixes and passing checks. Required live Linux deployment acceptance remains unverified. |
| [Review Round 2](Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md) | Keep active | The Security report records detector remediations, but still tracks form destination policy/owner association and deployment verification. Do not infer full closure from source changes. |
| [Security review](Review%20Security%2014-10-2026.md) | Keep active | Explicitly has no fully closed findings; container, sandbox, resource limits and other verification/follow-up items remain. |
| [Artifact Cleanup](archive/artifact-cleanup-20261016/Artifact%20Cleanup%20Plan.md) | Archived: dry-run scope closed | Zero eligible orphan files and zero reclaimable bytes. The plan and all three CSV inventories are preserved together; no apply or production acceptance is claimed. |

Before reusing cleanup apply mode, address the review follow-ups: reject database
locations within artifact directories, explicitly protect database/sidecar paths
from deletion, and document partial-deletion recovery. A database backup does not
restore deleted artifact files. These follow-ups do not reopen the completed
zero-candidate inventory run.
