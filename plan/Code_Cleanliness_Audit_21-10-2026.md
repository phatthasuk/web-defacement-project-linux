# Code Cleanliness Audit

This audit identifies eight maintainability issues in the backend and frontend,
prioritized by their effect on behavior and future changes. The main cleanup
priority is Member Management: error propagation, overlapping requests, UTC
handling, response contracts and separation of responsibilities.

- Audit date: 2026-10-21, Asia/Bangkok.
- Source commit: `f8c58904a1d0d59d6ee483a4e75134fd4232b773`.
- Environment: Windows checkout, PowerShell, Python 3.13.7, Node v24.7.0.
- Scope: static review of backend application code, frontend source and related
  configuration, with targeted frontend tests and lint/type checks.
- Status: audit recorded; no remediation implemented by this audit. Existing
  finding IDs, roadmap stages and verification statuses remain unchanged.

P2 items affect behavior, contracts or query efficiency. P3 items concern
maintainability and consistency. These priorities do not assign new remediation
IDs or establish security severity. Behavioral risks below are inferred from
source unless explicitly covered by the verification results.

## Findings

### P2 Error propagation can hide failures and discard form input

**Source:** [MembersPage.tsx](../frontend/src/pages/MembersPage.tsx),
lines 69-81, 84-112, 115-130 and 146-173.

The loading functions catch errors and update a shared error state without
propagating failure to their caller. After awaiting them, `act()` clears that
state, so a failed refresh can lose its error message. Separately, `act()` also
catches mutation failures, while `addMember()` unconditionally resets the form
after awaiting it. A failed create request therefore discards the entered form.

**Suggested change:** separate mutation success from refresh results. Propagate
failure or return an explicit result, reset the form only after successful
creation, and preserve refresh errors in the relevant view.

### P2 Overlapping requests can overwrite newer results

**Source:** [MembersPage.tsx](../frontend/src/pages/MembersPage.tsx),
lines 69-144.

Search, filters, pagination and selected-member changes start asynchronous
requests that write directly to component state. There is no cancellation,
request identity check or effect cleanup preventing an older response from
overwriting newer results. The same issue can affect websites shown for the
selected member.

**Suggested change:** use TanStack Query hooks with keys containing the relevant
filters and member ID. Keep server state in the cache and preserve distinct
loading, failed and successfully empty states.

### P2 Member timestamps bypass the shared UTC utility

**Source:** [MembersPage.tsx](../frontend/src/pages/MembersPage.tsx),
lines 326 and 332; [members.py](../backend/app/api/routes/members.py),
lines 67-93; [date.ts](../frontend/src/utils/date.ts).

Member responses return datetime values through dictionaries without a dedicated
UTC response serializer. The page displays them with `new Date(...).toLocaleString()`
instead of the shared utility. When a timestamp has no offset, JavaScript treats
it as local time, creating a timezone-dependent display error.

**Suggested change:** normalize member API timestamps to explicit UTC and use
`formatDateTime()` consistently. Add a regression covering offset-free UTC input
and a browser timezone different from UTC.

### P2 List endpoints perform queries inside loops

**Source:** [members.py](../backend/app/api/routes/members.py),
lines 67-77, 137 and 543-554; [tags.py](../backend/app/api/routes/tags.py),
lines 24-39 and 74.

Member serialization counts assignments separately for each member. Assignment
listing loads assignees separately for each target. Tag listing calls a helper
that queries child IDs and counts targets for each tag. Database round trips
therefore grow with the number of returned items. This is a source-level query
pattern finding, not a measured production performance result.

**Suggested change:** batch assignment counts and assignee loading, and aggregate
tag counts while preserving operator scope, active-target rules and parent/child
tag semantics.

### P2 Member response contracts are weakly typed

**Source:** [members.py](../backend/app/api/routes/members.py),
lines 96 onward; [member.py](../backend/app/schemas/member.py);
[MembersPage.tsx](../frontend/src/pages/MembersPage.tsx), lines 5-28.

Member endpoints return dictionaries without explicit Pydantic response models.
The schema module defines request models, while frontend response types are
declared inside the page and use broad strings for role and status. This reduces
the ability of validation, OpenAPI and static checks to detect contract drift.

**Suggested change:** add member and assignment response models, including UTC
serialization, and shared frontend types under `src/types/`. Use fixed unions
for roles and lifecycle states without changing authorization policy.

### P3 Member Management combines too many responsibilities

**Source:** [MembersPage.tsx](../frontend/src/pages/MembersPage.tsx),
686 lines; [members.py](../backend/app/api/routes/members.py), 572 lines.

The page combines response types, API calls, server state, mutations, account
forms and website-assignment UI. Backend routes also contain lifecycle rules,
assignment persistence and transaction orchestration. This makes behavior harder
to isolate and encourages duplicated loading and error handling.

**Suggested change:** extract member API wrappers, query/mutation hooks and
focused UI components. Move backend business operations into a member service,
keeping authorization and audit writes in the same transaction as the mutation.

### P3 Cache refresh logic is repeated across mutations

**Source:** [useTargetDetail.ts](../frontend/src/hooks/useTargetDetail.ts),
lines 73-153; [useTargets.ts](../frontend/src/hooks/useTargets.ts).

Mutation handlers repeat lists of literal query keys and similar invalidation
and refetch calls. Some invalidate both a prefix and its child key before
requesting another refetch. This increases maintenance cost and the risk that
future cache changes update only some handlers. Duplicate network requests were
not measured in this audit.

**Suggested change:** centralize query-key definitions and related refresh
operations. Review active-query refetch behavior before removing calls, and
preserve silent revalidation and existing cache regressions.

### P3 Check persistence is duplicated and baseline guidance is stale

**Source:** [checks.py](../backend/app/services/checks.py),
lines 218-531, especially Snapshot construction at lines 313 and 417;
[targets.py](../backend/app/api/routes/targets.py), lines 477-502.

The check pipeline repeats artifact promotion and Snapshot construction across
candidate and changed paths, while cleanup calls are distributed across outcome,
error and finalization branches. Small changes require care to keep these paths
consistent. The baseline-demotion comment and error text also describe automatic
baseline adoption when no baseline exists, but the current pipeline creates an
unapproved candidate and returns `Awaiting Baseline`.

**Suggested change:** extract small persistence helpers with explicit ownership
of artifacts and transaction boundaries. Update the stale guidance to describe
current behavior while retaining the last-baseline demotion guard and mandatory
human approval.

## Verification

The following commands were run during the audit on the source commit above.
Backend commands used `backend/`; frontend commands used `frontend/`.

| Command | Result |
| :--- | :--- |
| `.\.venv\Scripts\ruff.exe check app tests scripts alembic` | All checks passed |
| `.\.venv\Scripts\python.exe -m mypy app` | Success, no issues found in 64 source files |
| `npm run lint` | Passed, exit code 0; no diagnostics reported |
| `npm run typecheck` | Passed, exit code 0 |
| `npm run test -- src/pages/MembersPage.test.tsx src/pages/TargetDetailPage.cache.test.tsx src/utils/date.test.ts` | 3 files passed, 16 tests passed |

The initial combined backend invocation printed the Ruff pass but exited 1 after
invoking the mypy executable without diagnostics. The explicit Python module
invocation above subsequently completed successfully.

The first frontend test attempt could not load Vite configuration because child
process creation failed with `spawn EPERM` in the sandbox. Rerunning the same
targeted command outside the sandbox passed. The successful run reported
deprecation warnings for `esbuild` and `optimizeDeps.esbuildOptions` supplied by
`vite:react-babel`, plus a notice that oxc options take precedence. These warnings
are recorded without recommending a dependency upgrade as part of this cleanup.

The targeted tests do not establish coverage of every issue in this audit.
The full pytest/Vitest suites, production build, browser acceptance and Linux
Docker runtime verification were not run. Node 20 and Python 3.11 compatibility
were not established by this Windows environment. No production sites, live
database, capture artifacts, secrets or deployment settings were modified.

## Recommended next action

Address Member Management error handling and request ordering first, with
regression tests. Then align UTC serialization and response contracts, batch
queries, and perform the smaller structural cleanups. Any implementation should
retain detection sensitivity, SSRF controls, authorization scope, transactional
audit records and human baseline approval. Record implementation, testing and
runtime verification independently when remediation is performed.
