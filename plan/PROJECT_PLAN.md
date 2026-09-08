# Website Defacement Monitoring System — Project Plan

**Status date:** 2026-09-07 (Stage 2 restarted; previous run cancelled)
**Supersedes:** every document in [`plan/archive/`](archive/). Those are kept for history only; where they disagree with this file, **this file wins**.

This is the single source of truth for what the system is, what is built, what was
deliberately rejected, and what happens next. It carries forward the material from
the archived plans that is still useful, and drops or corrects the rest.

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
| **Operators** | **One person** (the IT team is one person) | A noisy system gets muted within a week, and a muted system detects nothing. Alert volume is a hard design constraint, not a polish item. |
| **Check frequency** | **Hourly** | ~24 checks per target per day |
| **Targets** | **6+, expected to grow.** BCH group: bangkokchainhospital, kasemrad.co.th, kasemradari, kasemradinter, kasemradvientiane, theworldmedicalhospital, sustainability.bangkokchainhospital | 10 targets hourly = **240 checks/day** |
| **Deployment** | Single machine, localhost for now | Single uvicorn worker; scale-out infrastructure is not needed yet |
| **Authorisation** | All targets are owned by the organisation | Satisfies the "get written authorisation before monitoring" requirement |

### The arithmetic that shapes the roadmap

```
240 checks/day x ~2 MB per full-page snapshot        = ~480 MB/day = ~175 GB/year
240 checks/day x current visual false-positive rate  = ~240 alerts/day for one person
```

Both numbers are unacceptable. Storage was addressed in Stage 1.2 — an unchanged
check now writes nothing, so only baselines and real changes consume disk. Alert
volume is addressed in Stage 3.

---

## 3. Current status

**Verified 2026-09-03:** 112 pytest / 50 vitest passing; ruff, mypy, tsc and
eslint clean (one pre-existing eslint warning in `useAuth.tsx`); Alembic
migrations upgrade and downgrade cleanly; production build succeeds.

**Stage 1 is complete.** Checks now run unattended on a schedule, unchanged
captures cost no disk, and availability failures are distinguished from content
changes. See [`refinement/3-9-2026/Stage1-Implementation-3-9-2026.md`](../refinement/3-9-2026/Stage1-Implementation-3-9-2026.md),
[`refinement/3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md`](../refinement/3-9-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md)
and [`plan/archive/review stage 1 by opus 5.md`](archive/review%20stage%201%20by%20opus%205.md).

### 3.1 Built and working

| Area | What exists |
| :--- | :--- |
| **Capture** | Playwright/Chromium, SSRF-guarded, fixed 1440x900 viewport, full-page screenshot, visible text, post-JS HTML |
| **Page stabilisation** | Multi-phase: DOMContentLoaded, prescroll, adaptive network-quiet, freeze animations/transitions, force reveal-library elements visible, force lazy images to load and decode, wait for layout to settle, pin carousels through their own API, scroll to top, capture |
| **Overlay handling** | Clicks vendor consent buttons (CookieYes, OneTrust, Cookiebot) and Thai/English "accept" by role+name; closes promo modals. **Never hides anything** |
| **Detection** | Three detectors: text, visual (pixel), **structural** |
| **Baselines** | Multiple approved baselines per target (cap 20); a check is compared against all of them and judged by the closest match |
| **Review workflow** | Approve a snapshot as an additional baseline; acknowledge a change; list and demote baselines through a gallery modal. **The last baseline cannot be demoted** — with none left, the next check would adopt the live page as the baseline and report `OK` without review |
| **Operator tooling** | 3-panel visual diff (baseline / red heatmap / latest) rendered client-side on canvas with no server storage; click-to-zoom lightbox on every screenshot; all timestamps served as explicit UTC (`Z`) and rendered in local time |
| **Auth** | Local username/password, Argon2id, server-side sessions (hashed tokens), CSRF synchroniser token, per-account lockout, per-IP rate limit |
| **Scheduling** | In-process `CheckScheduler` on a per-target interval with jitter; skips targets already in flight and retries them in 60s; in-flight tasks are tracked, their exceptions logged, and drained on shutdown |
| **Artifact lifecycle** | Capture writes to `data/staging/{snapshot_id}/`; artifacts are promoted to permanent storage only for a baseline or a real change, and discarded on `OK`. Startup reconciliation removes expired staging directories and files no `Snapshot` row references, all confined to `DATA_DIR` |
| **Reliability** | Semaphore-limited concurrency (2 global, 1 per domain), per-check timeout, startup recovery of checks stranded by a crash |
| **Frontend** | React + TS + Vite + Tailwind + TanStack Query: login, target list, target detail, check detail |

### 3.2 The three detectors

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

Design notes:

- Parses the HTML artifact **already stored** by capture, at diff time. `page.content()`
  serialises the DOM *after* scripts run, so JS-injected elements are included, and the
  detector works retroactively on snapshots taken before it existed.
- Uses stdlib `html.parser` — no new dependency in a component that handles hostile input.
- Inline scripts are stored as a **hash only** (bodies can contain secrets).
- Outbound links are recorded **per host**, so a 100-link spam farm is one finding.
- Relative URLs are resolved against the page URL, so `/app.js` and its absolute form match.

### 3.3 Configuration (current defaults)

| Setting | Value | Note |
| :--- | :--- | :--- |
| `TEXT_CHANGE_THRESHOLD` | 0.02 | |
| `VISUAL_CHANGE_THRESHOLD` | 0.01 | Currently exceeded by noise on carousel-heavy sites |
| `STRUCTURE_CHANGE_THRESHOLD` | **0.0** | Zero tolerance: one new external script is worth reporting regardless of size |
| `MAX_BASELINES_PER_TARGET` | 20 | |
| `MAX_CONCURRENT_CHECKS` / `PER_DOMAIN_CONCURRENCY` | 2 / 1 | Process-local; requires a single uvicorn worker |
| `PAGE_TIMEOUT_SECONDS` / `CHECK_TIMEOUT_SECONDS` | 25 / 90 | |
| `VIEWPORT_WIDTH` x `VIEWPORT_HEIGHT` | 1440 x 900 | Fixed for determinism |
| `BROWSER_DISABLE_SANDBOX` | false | Chromium sandbox **on** by default |
| `BLOCK_WEBSOCKETS` | true | |
| `MAX_ARTIFACT_SIZE_MB` | 10 | Enforced *after* materialisation — see 7, F3 |
| `REDIRECT_LIMIT` | 5 | |
| `SCHEDULER_ENABLED` | true | Set false to run without automatic checks |
| `CHECK_INTERVAL_SECONDS` | 3600 | Base interval per target |
| `CHECK_JITTER_MAX_SECONDS` | 180 | Random 0-180s added per run to avoid a thundering herd |
| `SCHEDULER_POLL_INTERVAL_SECONDS` | 15 | How often the scheduler loop wakes to check due times |
| `STAGING_CLEANUP_MAX_AGE_SECONDS` | 1800 | Staging directories older than this are removed at startup |

### 3.4 Status model (as built)

`Never Checked` · `Checking` · `OK` · `Changed` · `Failed` ·
`Availability Issue` · `Acknowledged`

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
- **Clicking is safe, hiding is not.** A dismiss click that fails leaves the overlay in
  the capture, which is honest.

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
Principle 4.3 keeps it away from the operator; Stage 4.2 reduces it further.

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
  reports `OK`, captured artifacts are discarded immediately to eliminate 480 MB/day
  disk accumulation. Baselines and changed snapshots remain fully preserved, but
  forensic visual records of quiet periods are traded off for storage sustainability.

---

## 6. Rejected approaches, and why

Recorded so they are not re-proposed.

| Rejected | Reason |
| :--- | :--- |
| **`ignore_selectors` masking a page region** | Creates a blind spot exactly where an attacker would hide. The archived production plan section 3.4 recommends this via `display:none` before capture — **that guidance is withdrawn.** |
| **Scoring only the viewport instead of the full page** | Same reason. Below the fold is where SEO spam, injected scripts and hidden iframes live. |
| **Noise mask (`MASK_LEVEL=16`) in the visual diff** | Lowers sensitivity across the whole page, and measurement showed the residual is real carousel state, not compression noise. It also reverses a deliberate "any channel differs" test. |
| **Continuing to chase carousel freezing** | Four attempts, negligible gain; every fix is library-specific and will not generalise across a growing site list. |
| **Auto-rebaseline on detected change** | Can silently absorb a real defacement into the baseline. Only acceptable for overlay-triggered changes, with an audit trail and human-in-the-loop by default. Full analysis preserved in [`plan/archive/auto-rebaseline.md`](archive/auto-rebaseline.md). |
| **Celery / durable queue now** | Over-engineering at 10-20 targets on one machine. In-process scheduling plus the existing stale-check recovery is sufficient; revisit before scaling out. |
| **RBAC now** | The team is one person. Revisit when a second operator exists. |

---

## 7. Outstanding findings from the code review

From the archived `codereviewbygptsol.md`, verified against the code on 2026-09-02.

| # | Finding | Severity | Status |
| :--- | :--- | :--- | :--- |
| F1 | No auth/authz | P1 | auth done · **RBAC missing** (`User.role` has one value, never enforced) |
| F2 | SSRF DNS-rebinding window | P1 | main hostname pinned via `--host-resolver-rules` · **subresource hostnames still cached as a boolean, not pinned** |
| F3 | Resource limits applied after expensive work | P2 | **open** — no `Content-Length` check; the full-page screenshot is produced before its size is validated |
| F4 | Frontend showed artifact errors as valid diffs | P2 | text + screenshot done · **not applied to snapshot list / baseline / check history / config queries** |
| F5 | Failed checks leave orphan artifact files | P2 | **done** — staging directory pipeline, zero-disk discard on OK, and startup reconciliation job |
| F6 | WebSocket / service worker bypass the SSRF guard | P1 | **done** — `route_web_socket` blocks all, context created with `service_workers="block"` |
| F7 | Chromium runs without a sandbox | P2 | **done** — sandbox on by default; `BROWSER_DISABLE_SANDBOX` opt-out for containers that cannot support it |
| F8 | In-process background checks are not durable | P2 | startup recovery of stranded checks done · **no durable queue, lease, heartbeat or DB-level duplicate suppression** |
| — | Stale "no application code yet" comments | — | done |

Also outstanding, from the archived auth security plan:

- **Audit logging** — no `auth_audit_events` table; auth events go to Python logging only
- **`POST /auth/change-password`** — not implemented
- **User model fields** — missing `normalized_username`, `must_change_password`, `password_changed_at`, `created_at`/`updated_at`
- **MFA and OIDC migration** — documented intent only

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

### Stage 1 — Enable an unattended test run ✅ COMPLETE (2026-09-03)

| # | Work | Why it was needed | Status |
| :--- | :--- | :--- | :--- |
| **1.1** | **Scheduler** — automatic checks on a per-target interval, with jitter to avoid a thundering herd | Without it, 240 manual button presses per day. Nothing can be observed without it | ✅ `app/services/scheduler.py` |
| **1.2** | **Discard unchanged snapshots after diffing**, and clean up orphan artifacts left by failed checks (**this is F5**) | Must ship *with* 1.1, not after: an unattended hourly run across 6+ targets writes about 480 MB/day, so a multi-week observation period would fill the disk before it finished | ✅ staging pipeline + `reconcile_artifacts` |
| **1.3** | **Separate `Availability Issue` from `Changed`** — a timeout, DNS failure or 5xx is not a defacement | Transient failures will be frequent at 240 checks/day. Without this they are recorded as `Failed` and pollute the very measurements Stage 2 depends on | ✅ `is_availability_error` + status transitions |

**Carried into Stage 2 as a known nit:** `_on_task_done` in the scheduler calls
`logger.exception()` outside an `except` block, so a failed check logs its message
without a traceback. Harmless, but it removes exactly the detail wanted when
diagnosing a check that failed during the soak.

### Stage 2 — Observation period (no new features)

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

| # | Work |
| :--- | :--- |
| 3.1 | **Choose the channel** — email or webhook (Line / Teams / Slack). **Deferred question, still open.** One channel only |
| 3.2 | **Tiered policy.** Working hypothesis from BCH data, to be confirmed or replaced by Stage 2: notify on structural and text changes (both measured 0.000000 on an unchanged page), do not notify on visual-only changes (measured 0.028-0.054). Every notification names the detector that fired and includes the structural summary |
| 3.3 | **Verification retry before notifying** — re-check after 1-2 minutes and notify only if the finding persists. Removes transient false positives before they reach the one operator |
| 3.4 | **Escalation alert for sustained `Availability Issue`** — an attacker taking a site down or triggering 500 errors must not stay silent indefinitely. A target remaining in `Availability Issue` across several consecutive checks (e.g. 2-3 hours) must escalate as an availability incident |

### Stage 4 — Make it comfortable for one person

| # | Work |
| :--- | :--- |
| 4.1 | Dashboard sorted by severity/status, showing which detector fired. **Worth pulling into Stage 1 if reviewing the observation period by hand proves painful** |
| 4.2 | **Per-target thresholds with an automatic noise-floor warm-up** — measure a new target's own variance over its first N checks and set its visual threshold above it. This is calibration, not masking: the whole page is still compared, and text/structural sensitivity is untouched |
| 4.3 | One click to acknowledge *and* add the snapshot as an additional baseline (400 separate approvals is not viable). 🟡 **Partly done 2026-09-03** — a baseline gallery with list/demote shipped; the single-click acknowledge-and-approve action is still outstanding |
| 4.4 | Allowlist: system-wide default plus per-target override, and a UI field. **Decide first whether an allowlisted host is filtered out (blind spot) or merely labelled "expected" (no blind spot)** — principle 4.1 argues for labelling |
| 4.5 | Hash gate — skip the expensive image diff when the HTML hash is unchanged |
| 4.6 | Diff heatmap: a `baseline / current / highlighted` preview so a human sees *where* it changed. Take the 3-panel composite from the prototype, **not** its mask threshold. ✅ **Done 2026-09-03** — implemented client-side on canvas (images fetched as blobs so the canvas is same-origin and never tainted), so it adds no disk or database footprint |

### Stage 5 — Close the remaining review findings

| # | Work |
| :--- | :--- |
| 5.1 | **F3** — enforce limits before expensive work: reject on `Content-Length`, count response bytes, cap request/frame/host counts, check document dimensions before screenshotting |
| 5.2 | **F2** — resolve and pin every hostname (store the validated IP set and the pinned IP), not just the main one |
| 5.3 | Auth: audit log table, `change-password`, missing user columns |
| 5.4 | **F4 remainder** — apply the error-state discipline to the remaining queries |
| 5.5 | Synthetic defacement test harness (text injection, image swap, script injection, hidden iframe, CSP removal) against a local fixture site |

### Stage 6 — Later / larger

Durable job queue with leases and heartbeats (**F8 remainder**) · full status
model and rules-engine severity scoring · RBAC · MFA and OIDC migration · object
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
| HTTP 200 becomes 403/500/timeout | availability first | no — Stage 1.3 |

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
- **Everything else** is referenced by its Stage number from section 8, e.g. "Stage 1.2".
- No other numbering.

---

## 11. Document map

| Location | Contents |
| :--- | :--- |
| `plan/PROJECT_PLAN.md` | **This file — the only active plan** |
| `plan/archive/` | All previous plans and review documents, kept for history |
| `refinement/<date>/` | Dated point-in-time records of completed work |
| `PROJECT_STRUCTURE.md` | Repository layout |

Review documents may sit alongside the plan while their findings are still being
acted on; once closed they move to `archive/`.
