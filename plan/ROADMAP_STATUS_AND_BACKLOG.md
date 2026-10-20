# Roadmap status and open backlog

**Reconciled:** 2026-10-19 (Asia/Bangkok)  
**Source baseline:** `ba1bbf2d8933293f115a2336df57b0d5430c30b7`  
**Scope:** Documentation reconciliation against source and existing verification records. No new application test run, migration, cleanup, deployment or live-server verification was performed.

**Planning update, 2026-10-20 (Asia/Bangkok):** Added independent right Active
Checks and left Overview delivery plans against source
`06adbb6923713acf327da7798591da58462fe229` plus local changes. Archived only
the implemented four-defect popover remediation plan; remaining feature,
browser and Linux acceptance stays open. This update adds no application test
or runtime verification evidence.

The [core roadmap](PROJECT_PLAN.md) owns Stage priorities. This register owns the
cross-document evidence status and open-work inventory. Feature plans retain their
acceptance criteria. Existing finding IDs and Stage numbers remain unchanged;
descriptive names below are work labels, not a new numbering scheme.

## Status rules

| Dimension | Allowed states | Required evidence |
| :--- | :--- | :--- |
| Implemented | Not started / Partial / Implemented | Source paths and actual behavior, including required migration/API/UI components. |
| Tested | Not run / Partial / Passed / Failed / Evidence needs review | An execution record with command, date, environment, result and source revision. Test-file existence alone is not a pass. |
| Runtime verified | Not verified / Partial / Verified / N/A | Evidence from the intended Linux/container/browser environment matching the item's acceptance criteria. N/A needs an explicit reason. |

These dimensions are independent. Implemented does not imply Tested or Runtime
verified. Partial means only the named subset has evidence; it does not mean the
remaining requirements passed. An execution that cannot be linked reliably to
the source under review is Evidence needs review, not Passed or Failed.

Each future update must record the item/scope, source commit, command or manual
procedure, timestamp/timezone, environment/image digest/browser versions where
relevant, result, evidence location, exclusions, next action and closure criteria.
Redact secrets and sensitive page content from evidence.

Do not close a finding until all of its applicable acceptance criteria pass.
Documentation-only link/diff checks do not change application verification status.
Historical results stay dated and do not become current passes automatically.

## Evidence register

| Evidence | What is recorded | Reconciliation decision |
| :--- | :--- | :--- |
| [Stage 1 record](../refinement/9-3-2026/Stage1-Implementation-3-9-2026.md) and [baseline record](../refinement/9-3-2026/Baseline-Management-Visual-Diff-and-Timezone-Fixes-3-9-2026.md) | Historical Stage 1 implementation and verification. | Preserve as historical evidence; not a current deployment acceptance. |
| [Scheduling fix](../refinement/10-16-2026/OK-Target-Scheduling-Fix-16-10-2026.md) | 73 tests reported passing for attempts/scheduler/checks/review; UI and deployment recovery explicitly not checked. | Tested: Partial for the current scheduling feature; confirm revision applicability before release. Runtime: Not verified for deployment recovery. |
| [Remediation record, section 6](Remediation_Plan_19-10-2026.md#6-verified-test-execution-record) | 264 main pytest passes; cleanup 7 passed/2 failed on Windows; frontend 94 tests in 14 files; static checks reported passing. | Evidence needs review before current-baseline claims. Frontend excerpt names absent files such as SettingsPage, AlertsPage, UsersPage and HtmlDiffViewer. The current 14-file inventory has different names. Preserve the original report; obtain original logs/revision or rerun. Backend/static results remain reported historical results, not newly verified here. |
| [Security review, section 7.6](Review%20Security%2014-10-2026.md#76-verification-update-oct-15-2026-asiabangkok) | Linux SSRF, Range and budget tests reported passing; Docker acceptance unavailable. | Partial historical Linux test evidence; not full container/runtime acceptance. |
| [Phase 5 execution record](Phase_5_Linux_Container_Runtime_Verification.md#execution-record) | Compose syntax validation recorded; runtime tests not run. | Container runtime remains Not verified. |
| [Stage 2 audit](../audit%20stage2.md) | Local historical data: 3,587 Changed / 3,620 results; approximately 300 MB/day retained artifacts across four active targets; expected sites missing. | Stage 2 exit not established. This is neither a current server measurement nor proof all Changed results are false positives. |

The current source contains 14 frontend test files under components, hooks, pages,
api and utils. A matching file count alone cannot authenticate a test transcript.
The two reported Windows cleanup failures remain recorded failures; do not rewrite
them as skips or passes because POSIX behavior is expected to differ.

## Implementation and verification matrix

| Capability | Implemented | Tested | Runtime verified | Source / remaining evidence |
| :--- | :--- | :--- | :--- | :--- |
| Run Check progress popover | Partial | Partial | Not verified | Four defects from the 2026-10-20 follow-up review are fixed with regressions. Focused backend suites: 54 passed; frontend: 100 tests passed, lint and build passed; targeted Ruff and mypy passed. Full backend suite: 276 passed, 2 Windows-specific cleanup-artifact failures (symlink privilege and POSIX directory operations). Full Ruff has six existing findings in an applied migration. Isolated browser and Linux runtime verification remain open. See [feature record](../refinement/10-20-2026/Run-Check-Progress-Popover-20-10-2026.md) and [remediation record](../refinement/10-20-2026/Run-Check-Progress-Popover-Remediation-20-10-2026.md). |
| Capture, stabilization and overlay preservation | Implemented | Partial | Not verified | `capture.py`, `page_ready.py`, `overlays.py`; capture tests exist and historical reports cover subsets. Validate actual browser/image and unchanged/changed fixtures. No automatic dismiss clicks, even with legacy DISMISS_OVERLAYS=true. |
| SSRF socket pinning, WebSocket/service-worker blocking | Implemented | Partial | Partial | `ssrf_proxy.py`, `capture.py`; historical Linux subset reported. Full production-equivalent egress, redirects and WebRTC remain under Phase 5. |
| Capture budgets and container hardening | Implemented | Partial | Not verified | Proxy transfer cap, pre-screenshot dimensions/pixels, pre-serialization DOM cap, Compose CPU/memory/PID limits. B-11c width cap deferred; effective cgroups/seccomp need runtime evidence. |
| Text, visual and structural detectors | Implemented | Partial | Not verified | `services/diff/`; existing regression/probe records. SEC-03 policy/form-owner work remains Partial in scope; missing HTML returns structural unavailable, not a validated zero-change detector. |
| Baseline approval, URL revisions and triage audit | Implemented | Partial | Not verified | `checks.py`, `review.py`, `services/audit.py`; candidates require approval, and approval acknowledges the matching check. Audit records actor/IDs/states transactionally. |
| Scheduler, durable retry deadlines and restart recovery | Implemented | Partial | Not verified | `scheduler.py`, `attempts.py`, `CheckAttempt`; October 16 record covers a subset. Durable retry state is not a distributed queue/lease. Validate existing stuck-run recovery. |
| Local auth, Member Management and assignments | Implemented | Partial | Not verified | `authorization.py`, auth/member routes, user/member models, member migration, Members/Register/ChangePassword UI. Full permission and migration acceptance remains open. |
| UI comparison, error handling and focus revalidation | Implemented | Evidence needs review | Not verified | ScreenshotCompare, TargetDetailPage, useAuth and tests. Resolve October 19 transcript mismatch; manually verify focus/network/access changes. |
| Tags, target search and sorting | Implemented | Evidence needs review | Not verified | Target/tag routes and TargetListPage; no evidence of a comprehensive incident severity queue. |
| Orphan inventory/apply tooling | Implemented | Partial | Not verified | `scripts/cleanup_artifacts.py`; 7/9 Windows result reported, Linux cases open. Archived zero-candidate dry-run remains closed only for that inventory scope. |
| Retention of referenced snapshots and coordinated restore | Not started | Not run | Not verified | Orphan cleanup deliberately preserves all Snapshot-referenced artifacts. Separate retention and DB/artifact recovery work required. |
| Notification delivery and incident lifecycle | Not started | Not run | Not verified | No outbox/delivery or separate incident entity found in the reviewed source. Stage 3 and proposed add-ons below own future scope. |
| Monitoring readiness and overdue-check reporting | Partial | Not run | Not verified | `/health` is static API liveness; scheduler/DB/artifact health and independent external monitoring are not established. |

## Open verification and remediation backlog

Priority describes execution order, not a new severity rating. Owner identifies the
authoritative plan; named human assignees remain to be allocated when work starts.

| Priority / reference | Owner / dependency | Next action and closure criteria |
| :--- | :--- | :--- |
| First — verification evidence reconciliation | Remediation section 6; source baseline above | Obtain logs and revisions behind reported frontend/backend/static results or rerun against this baseline in an isolated environment. Close when test inventory, commands, revision and results agree; retain Windows failures and exclusions. |
| First — Phase 5 / B-01, B-07, B-09b, B-10, F-08a/b, F-09c | [Phase 5](Phase_5_Linux_Container_Runtime_Verification.md); Linux Docker test host | Run controlled egress tests, all 9 cleanup cases, cgroup/seccomp checks and production Nginx/routing checks. Close each item with the parent's required evidence; Compose syntax alone is insufficient. Keep current seccomp baseline until experiments justify changes. |
| First — SEC-01/SEC-02 and deployment acceptance | [Security review](Review%20Security%2014-10-2026.md); Phase 5 | Record installed package/image/browser versions and image digest; inspect dependency/OS/image advisories and Range behavior (normal/single/multiple/malformed). Confirm sandbox, non-root/read-only/capabilities, redirects/private IP/WebSocket and CDP restrictions under the deployment configuration. Close only against original acceptance criteria; no production load/security test is implied. |
| Next — SEC-03 / R2-01 form destination semantics | Security and Round 2 reports | Review current allowed-domain filtering versus an explicit form-destination policy; associate submitters with owning forms. Add cases for same-host path changes, cross-host destinations, external form= ownership, allowed hosts and added/removed overrides. Close when unauthorized effective destinations are detected without visual/text changes. API allowed_domains already exists; do not rebuild it as missing. |
| Next — SEC-04/SEC-05 acceptance | Security report; detector regressions exist | Validate URL normalization and inert/executable script transitions against original probe/acceptance scope on intended platform. Source fixes alone do not close report-wide acceptance. |
| Next — Member Management acceptance | [Member plan](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md); isolated DBs | Exercise its full permission matrix with real sessions/CSRF, suspension/session revocation, pending/rejected users, disjoint/shared/no assignments, last-Admin concurrency and artifact/nested-ID access. Run fresh and legacy Alembic upgrades, mapping rejection cases, identity/hash preservation and restore. No broad completion claim from the two member backend tests alone. |
| Next — OK scheduling deployment recovery | [Scheduling issue](archive/implemented-20261019/Review%20issue%20by%20Argon%20Edit%20by%20Sol.md) and October 16 record | Verify next-check/retry UI, restart recovery of old unfinished rows and a subsequent scheduled OK check. Preserve valid retry deadlines and run ownership. Close with browser and isolated deployment evidence. |
| Next — scheduler exception diagnostics | Core roadmap Stage 1 carry-over; scheduler.py | Inspect `_on_task_done` traceback logging outside the original exception context. Close after an injected task failure yields the originating traceback with the correct target/task context; do not infer correctness from logger.exception alone. |
| Next — focus revalidation acceptance | [Focus plan](archive/implemented-20261019/Page-Flicker-On-Window-Focus-Fix%20By%20Argon.md) | Resolve test evidence, then verify focus/visibility bursts, transient network failures, logout, role/access change and required password change in browser. Close without losing session enforcement or remounting the full page unnecessarily. |
| Next — Stage 2.1–2.5 | Core roadmap; target list and effective settings verified | Confirm expected targets, hourly coverage for at least two weeks per target, legitimate-change labels, detector distributions, failure causes, durations and storage. Audit local historical data is insufficient; do not restart the soak automatically or assume all Changed results are noise. |
| After Stage 2 policy evidence — Stage 3.1–3.4 | Core roadmap; selected channel and recipient configuration | Select one channel; implement selective policy, separate content-confirmation checks from network retries, persist delivery/retry/dedup state and availability escalation. Re-evaluate active recipient/assignment rights before delivery; unassigned sites route to active Admins. Close after simulation and controlled end-to-end delivery. |
| Planned — Stage 4.1–4.4 | Core roadmap; observed behavior | Complete detector/severity triage beyond current Changed-first sorting, reviewed per-target calibration, baseline-approval UX acceptance and expected-domain policy/UI. Approval already acknowledges related checks; do not add a redundant acknowledge endpoint. No unattended learning from unreviewed changes or removal of raw evidence. |
| Planned — Stage 5.5 | Core roadmap; controlled fixture network | Consolidate existing tests/probes into reproducible text/image/script/hidden-iframe/form/header regression scenarios, including benign changes. Close with expected detector behavior and evidence, without targeting production. |
| Planned — retention / backup / recovery | Core roadmap section 9.3; protected references and backups | Design coordinated DB/artifact retention, incident holds, dry-run manifest, protected database/sidecar paths and resumable partial-deletion recovery. Close with failure-injection and restore evidence. Existing orphan-tool protections need Linux acceptance, not a duplicate implementation claim. |
| Deferred — B-11a | Remediation section 4; agreed URL-port policy | Decide allowed custom ports and convert invalid port parsing to domain-specific failure; test malformed/out-of-policy ports. |
| Deferred — B-11b | Remediation section 4 | Make member timestamps explicitly UTC; assert serialization. The suggested test_members.py does not exist here; extend test_member_management.py or a deliberately created focused test. |
| Deferred — B-11c | Remediation section 4 | Add/test explicit maximum width alongside existing pixel/height/file limits. |
| Deferred — F8 / Stage 6 / SEC-01/SEC-06 worker isolation | Core roadmap; revisit before multiple workers/hosts or when isolation requirements demand it | Durable queue/leases, DB duplicate suppression and browser/API separation remain architectural work; persisted retries do not satisfy them. Preserve the single-worker constraint until verified replacement exists. |
| Deferred — auth audit scope / MFA / OIDC | Core roadmap Stage 5.3/6 and member scope | Review whether auth failure/login/logout coverage and username canonicalization are required beyond current member/review audit. Record exact gaps; normalized_username is absent but case-sensitive matching is intentional in the member plan. Do not silently change identity semantics. |

## Proposed add-ons awaiting feature scope

These are proposals, not confirmed defects or authorization to implement them.
They do not receive Stage numbers. Scope and acceptance must be agreed in their
own plans before implementation.

| Proposal | Dependency / intended outcome |
| :--- | :--- |
| [Active Checks inline card progress](Active_Checks_Inline_Card_Progress_Plan_20-10-2026.md) | Partial: one-card inline expansion, collapse/switch, terminal retention, run/revision matching and 404 cleanup implemented. Frontend 107 tests passed; lint/build passed; Chromium 153 mocked UI check at 1920×1080 passed. Width/accessibility matrix and production acceptance remain open; Popover hold is unchanged. See [execution record](../refinement/10-20-2026/Active-Checks-Inline-Card-Progress-20-10-2026.md). |
| [Right Active Checks panel](Dashboard_Right_Active_Checks_Plan_20-10-2026.md) | Partial: scoped/paginated active-check endpoint and wide-screen activity panel implemented. Backend 279 passed/2 Windows cleanup failures; frontend 104 passed, lint/build passed; targeted Ruff/mypy passed. Browser launch failed (`spawn EPERM`); Linux and production acceptance not run. Popover replacement/deduplication is explicitly paused by the user until production testing passes. See [execution record](../refinement/10-20-2026/Dashboard-Right-Active-Checks-20-10-2026.md). |
| [Left Overview panel](Dashboard_Left_Overview_Plan_20-10-2026.md) | Separate later delivery after the shared right-panel layout: authorization-scoped full-population status counts and matching table-filter shortcuts. Never derive global counts from paginated rows. Implemented Not started; Tested Not run; Runtime verified Not verified. |
| [Existing Run Check progress popover](Run_Check_Progress_Popover_Plan_20-10-2026.md) | Four reviewed defects fixed with focused regressions; their [remediation plan is archived](archive/implemented-20261020/Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md). Feature remains Implemented Partial; Tested Partial; Runtime verified Not verified. Remaining feature/lifecycle/authorization acceptance and isolated browser/Linux checks stay open; wide-screen layout replacement is owned by the new right-panel plan. |
| Monitoring health and Stage 2 report | Report overdue/stuck checks, detector availability, attempt causes and per-target growth; separate liveness/readiness and external monitor failure paths. Supports Stage 2. |
| Structured findings | Persist detector facts, availability and policy/version context to explain and group changes without parsing summary text. Review storage/privacy requirements. |
| Incident Inbox | Group recurring findings, assign owners and track resolution independently of transient target status. New dangerous findings must not be swallowed by deduplication. |
| Notification outbox integration | Supports Stage 3 delivery reliability; define idempotency, retries/cooldowns, recipient rechecks and delivery history. |
| Audit Viewer and evidence export | Reuse Admin-only audit API; define access, retention, checksum/export and secret-handling scope. SEC-07 remains open for the report's UI/retention follow-ups. |
| Target settings and security metadata | Expected-domain UI/onboarding plus redirect-chain/CSP/SRI evidence; no HTML-only hash bypass of image comparison. |

## Excluded and historical scope

### Archive decisions on 2026-10-19

The user requested archiving plans whose code changes are implemented, rather
than archiving every document edited during reconciliation. The earlier bulk move
was reversed. Core roadmap, this register, remediation, Linux Phase 5, Round 2 and
Security review stay active. Four implementation-complete documents are now in
`archive/implemented-20261019/`; their acceptance requirements remain authoritative
and their open verification is tracked above.

| Archived plan | Implementation evidence | Remaining obligations |
| :--- | :--- | :--- |
| [Member Management](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md) | Fixed-role models/migration, auth/member/assignment APIs and UI exist | Full permission/session/migration matrix and Linux/browser acceptance |
| [Focus flicker](archive/implemented-20261019/Page-Flicker-On-Window-Focus-Fix%20By%20Argon.md) | Silent revalidation, cooldown/deduplication, auth epoch and cache handling exist | Test provenance review and browser acceptance |
| [OK scheduling](archive/implemented-20261019/Review%20issue%20by%20Argon%20Edit%20by%20Sol.md) | Primitive result IDs, finalization recovery and persisted scheduling changes exist; October 16 record | Deployment recovery and next-check/retry UI acceptance |
| [First review](archive/implemented-20261019/Review%20By%20GPT%206.1%20Sol%2014-10-2026.md) | RV-01–RV-08 source remediations are recorded in Round 2 and present in inspected source | Current-source test evidence and Linux deployment acceptance; later Round 2 gaps stay active |

Archiving these files declares implementation storage status only. It does not
change any Tested or Runtime verified value or close an unresolved finding.

### Exclusions retained

- B-04 remains refuted/excluded by the remediation record; no new evidence reopens it.
- B-05 script-type whitespace behavior must follow HTML/Chromium semantics, not arbitrary trimming.
- Stage 4.5 HTML-only image-diff hash gate is withdrawn: resources at unchanged URLs can change independently of HTML.
- Archived orphan inventory found zero candidates; do not reopen it as an unfinished deletion run.
- Older report statements that cgroup limits, RBAC, password change or actor-attributed review audit are absent are superseded by inspected source. Runtime/acceptance remains separate.

## Next execution order and documentation acceptance

1. Reconcile source/evidence and publish the three-dimension matrix (this update).
2. Resolve test provenance and run applicable acceptance in an isolated environment.
3. Complete Linux Phase 5, member migration/authorization, scheduling and browser acceptance; update individual rows only with actual results.
4. Establish Stage 2 coverage and labels. Design Stage 3 policy from that evidence; proposed health/incident work needs its own scoped plan.
5. Deliver Stage 3 and later operator/retention capabilities according to dependencies above.

Documentation acceptance: every reviewed active plan links to this register;
implemented capabilities are no longer described as absent in current summaries;
historical claims remain dated; open items have an owner plan, next action and
closure criterion; local links resolve; application source and monitored data are
unchanged. Passing documentation checks does not close application findings.

### Documentation verification record

On 2026-10-19, checked the 9 edited Markdown documents and this new register:
63 relative local-file links resolved, all edited plans linked to this register,
and the frontend source inventory contained 14 test files. `git diff --check`
passed. A final scope check confirmed only planning Markdown changed. These are
documentation checks; no pytest, Vitest, migration or live runtime result is claimed.
