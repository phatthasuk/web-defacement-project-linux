# Member Management and Website Assignments — Standalone Add-on Plan

**Original planning decision:** 2026-09-18.
**Updated:** 2026-10-12 — standalone scope aligned with the current repository;
self-registration requires explicit Admin approval.
**Status:** Member Management and website assignments are planned, not implemented.
Existing Tags functionality is implemented and will be reused.

This document owns the scope, implementation sequence and acceptance criteria of
the standalone Member Management add-on. It has no Stage number and no dependency
on the core roadmap's Notification or auth-hardening stages. Its implementation
start and release date are not yet set. This documentation update does not declare
the observation period complete or authorise implementation or deployment.

## Delivery boundary and existing foundations

- Initial delivery includes fixed roles, self-registration with Admin approval,
  member administration, individual website
  assignments, backend authorisation, password lifecycle, session revocation,
  administrative audit events and scoped access to existing Tags and filters.
- Reuse the existing local login, password hashing, session cookies, CSRF and
  lockout protections. Extend the existing user model and controlled account
  setup process rather than introducing a separate authentication system.
- Reuse existing Tags models, associations, APIs, pages and filters. Tag management
  permissions and Operator-visible tag options/counts belong to this delivery.
- Audit storage and password lifecycle changes needed by this add-on are prerequisites
  owned here. Implement them within this work if unavailable; reuse shared implementations
  if already present. Do not wait for a later core roadmap stage or duplicate them.
- Bulk operations and notification integration are subsequent increments and are
  not initial-release gates. Notification delivery requires a separately selected
  channel and recipient configuration; email addresses are not assumed to exist.
- The add-on is separate for planning and delivery. Once enabled, role and website
  scope checks must apply consistently across the existing application, including
  checks, review actions and artifact access.

## Current repository baseline

Inspected on 2026-10-12. These are source-code findings, not confirmation of the
database or application running on the Linux server. Proposed changes below are
not implemented by this planning update.

| Area | Current implementation | Required add-on change |
| :--- | :--- | :--- |
| Users | [User model](../backend/app/models/user.py) has integer IDs, unique username, password hash, `is_active`, free-text `role` defaulting to `authenticated-user`, and lockout fields | Constrain roles; add registration approval, member metadata and password-change state; keep existing IDs and hashes |
| Authentication | [Auth routes](../backend/app/api/routes/auth.py) provide login, logout and me; successful login creates a new session | Add registration with approval gate, password change/reset and successful-login timestamp; extend identity responses |
| Sessions | [Dependencies](../backend/app/api/deps.py) check cookie token, expiry, revocation, CSRF and active user on requests | Reuse this validation and add central role/target scope checks; suspension must revoke sessions permanently |
| Website access | Existing target/check/review/snapshot/tag routers require login but do not enforce roles or assignments | Apply the endpoint matrix below; add a separate user-target association |
| Websites | [Target API](../backend/app/api/routes/targets.py) has list/page, status/tag filtering, history, baselines and soft disable | Add server-side name/URL search and assignee summaries; preserve list/page response shapes and existing filters |
| Tags | Existing tags and target-tags tables, parent/sub-tags, any/all filters and `/tags` UI | Reuse schema and UI; scope options/counts and make all mutations Admin-only |
| Artifacts | [Snapshot API](../backend/app/api/routes/snapshots.py) serves metadata, screenshot, raw screenshot and text; HTML is stored but has no download endpoint | Authorise through `Snapshot.target_id` before reading files; preserve path containment and screenshot handling; no new HTML endpoint required |
| Config | [Config API](../backend/app/api/routes/config.py) exposes read-only detector thresholds and baseline cap used by target detail | Keep read access for both roles; no settings mutation API or settings editor is added here |
| Frontend | [App](../frontend/src/App.tsx) protects routes by login; auth context carries a string role; TanStack Query holds target, snapshot, check and tag caches | Add role-aware routes and controls, required-password-change flow, and cache cleanup on access loss |
| Background work | Scheduler and capture/check services run independently of interactive users | Continue monitoring every active target, including unassigned targets; assignments govern user access, not scheduling |
| Audit | Auth/review events currently use Python logging; no persistent administrative audit model | Add transactional audit storage for this add-on; a separate audit browsing page is outside initial delivery |

Do not recreate existing Tags tables or add a new dashboard, notification channel,
per-target scheduling editor or role editor in this work. Public registration is
included, but never grants automatic approval or website access.

## Roles and access scope

Use exactly two fixed roles: **Admin** and **Operator**. Admins can access every
website. Operators can access only websites explicitly assigned to them. One
website can have multiple Operators, and one Operator can have multiple websites.
Tags organise websites and never grant or revoke access.

| Capability | Admin | Operator |
| :--- | :--- | :--- |
| View dashboard, websites, checks and related artifacts | All websites | Assigned websites only |
| Trigger checks and perform incident review actions | All websites | Assigned websites only |
| Receive incident alerts and notifications (future integration) | All websites | Assigned websites only |
| Create, edit or disable websites and monitoring settings | Yes | No |
| Create tags and change website tags | Yes | No |
| Search and filter websites by tags and status | All websites | Assigned websites only |
| Manage members and website assignments | Yes | No |
| Manage system-wide settings | Yes | No |

The settings row describes the role policy for any future management interface.
Current `GET /config` is read-only application metadata and remains available to
both roles so Operators can interpret detector scores and baseline limits.

Preserve existing review safeguards, including protection of the last baseline.
Map existing review endpoints to explicit permissions during implementation;
do not introduce additional roles or a custom role editor in this release.
Use `admin` and `operator` as database/API values, displayed as Admin and Operator.

## Backend permission matrix

Paths below are FastAPI paths. The existing frontend API client adds `/api` in
production; do not add a second `/api` prefix to backend routers.

| Existing endpoint | Admin | Operator |
| :--- | :--- | :--- |
| `GET /targets`, `GET /targets/page` | All targets with requested filters | Assigned targets; apply scope before filtering, totals and pagination |
| `GET /targets/{target_id}` | Any target | Assigned target only |
| `POST /targets`, `PATCH /targets/{target_id}`, `DELETE /targets/{target_id}` | Allowed | Denied, including tag-only and active-state changes |
| `DELETE /targets/{target_id}/tags/{tag_id}` | Allowed | Denied |
| `GET /targets/{target_id}/snapshots`, `/baseline`, `/baselines`, `/checks` | Any target | Assigned target only, including `include_history=true` |
| `POST /targets/{target_id}/check` | Any eligible target | Assigned eligible target; preserve existing inactive/in-flight checks |
| `POST /targets/{target_id}/baseline/approve` | Allowed | Assigned target; preserve snapshot-target/revision validation |
| `POST /targets/{target_id}/baselines/{snapshot_id}/demote` | Allowed | Assigned target; preserve last-baseline and in-flight safeguards |
| `GET /checks/{check_id}`, `POST /checks/{check_id}/ack`, `/confirm-defaced` | Allowed | Resolve check to its target and authorise before read/review |
| `GET /snapshots/{snapshot_id}`, `/screenshot`, `/screenshot/raw`, `/text` | Allowed | Resolve snapshot to its target and authorise before read/download |
| `GET /tags` | Full catalogue and counts | Accessible tags plus necessary parent metadata; scoped counts only |
| `POST /tags`, `PATCH /tags/{tag_id}`, `DELETE /tags/{tag_id}` | Allowed | Denied |
| `GET /config` | Read | Read |
| `GET /auth/me`, `POST /auth/logout` | Own session | Own session |

Use shared helpers in `app/api/deps.py` (or a dedicated authorisation module) for
Admin requirements, scoped target queries, and check/snapshot-to-target resolution.
Read current role and assignments from the database on each request; do not copy
website permissions into sessions. Unknown roles must fail closed.
Require `registration_status=approved` and `is_active=true` before accepting a
session, even if a stale session exists. Required password change is an additional
gate after approval, not a substitute for approval.

Return `401` for an invalid/revoked session or inactive account, `403` for an
authenticated user attempting an Admin-only operation, and `404` for an absent
or inaccessible target/check/snapshot. Validate all IDs in nested routes against
the same target. Denial must occur before capture reservation, file access or a
review mutation. Public login and health retain their existing access behaviour.

An accepted check may finish after an assignment is removed: access revocation
blocks subsequent user requests, while the system-owned background job completes.

## Navigation and page layout

Add a public `/register` page linked from Login, with username, display name,
password and password confirmation. No role selector or website assignment fields.
After a successful submission show "Registration submitted. Awaiting Admin approval."
and a link back to Login; do not log the applicant in or display monitored data.

Use the existing header navigation with these destinations:

- **Websites:** website status, latest check results, search by name or URL,
  and tag/status filters. Show current assignees where appropriate. Admins manage
  website configuration and tags here; Operators see only their assigned scope.
- **Member Management (Admin only):** combine member administration and website
  assignment in one page with two tabs. Do not create a separate assignment page.
- **Tags Management (Admin only):** reuse the existing Tags page. Operators use
  scoped read-only tags and filters on Websites.

The **Members** tab shows display name, username, role, account status, last login
and assigned website count. Keep username as the existing login identifier; email
is not required. Add the missing display-name and last-login fields through migration,
and show an empty value for historical login times that cannot be recovered.
Support search, status filtering, adding Operators, editing basic details,
password reset, and disabling/re-enabling accounts. Opening a member shows their
assigned websites with actions to assign or remove websites directly.
Within this same tab, provide Pending / Active / Suspended / Rejected filters and
a Pending badge/count. Pending rows show registration time and Approve/Reject
actions; record the decision actor/time and optional rejection reason in member
details. Keep account approval inside Members, without adding a third tab.

The **Website Assignments** tab provides All / Unassigned / Assigned views with
counts, website name/URL search, and filters for Operator and tags. Its table shows
website name, URL, tags and current assignees. Both tabs use the same assignment
records and refresh affected counts after changes.

An **Unassigned** website has no active Operator assigned to it. Disabling the
only active assignee therefore places that website in this view. Retain assignment
records on account suspension; re-enabling restores those assignments and the UI
must make that effect clear. Admin access does not count as an Operator assignment.

Both tabs default to active websites and may opt into inactive websites through
the existing `include_inactive` convention. Member assigned-website counts use
active websites, including retained assignments on suspended members. Assignment
view counts use the same website/tag/search filters before the selected
All/Unassigned/Assigned view is applied. A temporary login lockout does not suspend
an account or make its websites Unassigned.
Only approved, active Operators count as active assignees.

Show full assignee details only to Admins. Operator website responses need not
expose other members' account details or assignment administration data.

## Account lifecycle and authorisation

- Applicants register themselves as pending Operators; only an active, approved
  Admin may approve or reject them. Admins may still directly create approved
  Operators for controlled onboarding; this explicit Admin action is audited.
- Provision Admin accounts through a separate controlled setup/recovery process,
  not the ordinary Add Member form. Protect the last active Admin.
- Prefer account suspension over permanent deletion to preserve history.
- Reuse the existing password/session/CSRF protections. Never display existing
  passwords. Use an Admin-supplied temporary password for initial Operator creation
  and reset, sent once over the existing authenticated/CSRF-protected API and stored
  only as a hash. The Admin delivers it through a controlled channel outside this
  application; no email service is required. Do not return the password from APIs.
  Reuse the setup script's minimum of 12 characters and the login schema's maximum
  of 200 for creation/reset/change. Reject choosing the temporary password again.
- Admin-created or reset Operators have `must_change_password=true`. Self-registered
  Operators choose their own password and start with this flag false; approval does
  not reset their password. Permit approved accounts with required change to login, me,
  logout and own password change, but block all normal data and administration APIs
  until the required change succeeds. Enforce this in backend dependencies as well
  as frontend routes. Keep recovery tooling usable for Admin accounts.
- Own password change verifies the current password, updates the hash and change
  timestamp, clears required-change state and revokes every session in one
  transaction. Clear the caller's cookie and require a fresh login. Admin reset
  also revokes every session and clears brute-force lockout counters/state.
- Suspension revokes all existing sessions in the same transaction as disabling
  the account and blocks subsequent requests. Re-enabling requires a fresh login;
  old sessions must not become valid again.
  Assignment removal takes effect on subsequent requests, including direct links
  and artifact downloads; it must not depend on logging in again.
- Enforce role permissions and website scope at the backend for list/detail APIs,
  mutations, checks, baselines, screenshots, HTML/text artifacts and aggregates.
  Frontend route/button visibility is supplementary.
- Calculate pagination totals, filter options and dashboard counts within the
  caller's authorised scope. An Operator with no assignments sees an empty state.
- Record actor, time, affected account/website and relevant changes for member,
  assignment and tag administration in persistent audit storage delivered or reused
  by this add-on. Do not record passwords, session tokens or reset secrets.

## Self-registration and Admin approval

| Account state | Registration status | `is_active` | Login / access |
| :--- | :--- | :--- | :--- |
| Pending applicant | `pending` | false | No session or application access; awaiting Admin decision |
| Rejected applicant | `rejected` | false | No session or application access |
| Approved Operator | `approved` | true | May log in; websites require explicit assignments |
| Suspended member | `approved` | false | No access; existing sessions revoked and assignments retained |

- Backend fixes registration role to `operator`, status to `pending`, active state
  to false and assignments to empty. Reject client-supplied role, approval,
  active-state or assignment fields through strict schemas; do not silently trust them.
- Reuse trimmed, case-sensitive username rules, database uniqueness and password
  hashing. Apply the same 12–200 character password policy and validate confirmation
  before submission. Concurrent duplicate registrations must not create two users.
  Return a clear duplicate-username error without exposing any member data.
- Registration creates no session or auth cookie. Pending/rejected applicants
  cannot use `/auth/me`, password-change or any protected API. Login keeps the
  existing generic invalid-credentials response for unapproved/inactive accounts,
  and never creates a session for them. The registration confirmation explains the wait.
- Keep existing trusted-origin validation on the anonymous registration POST and
  add a separate IP rate limit using the existing limiter/client-IP policy. An
  anonymous applicant has no session CSRF token; do not require one or weaken CSRF
  requirements on authenticated approval/rejection/member mutations.
- Approve only a pending Operator: atomically set status to approved, active state
  to true, decision actor/time and audit event. Approval alone assigns no websites;
  the Admin may then assign websites through the existing assignment controls.
- Reject only a pending Operator: atomically set status to rejected, keep inactive,
  record the decision and optional reason, and revoke any sessions defensively.
  Record submission with a self-registration source and no authenticated actor.
- Pending and rejected accounts cannot receive assignments, be re-enabled through
  ordinary member PATCH, or receive incident notifications. Password reset must
  not approve them. Re-enable applies only to previously approved suspended members.
- Admin approval/rejection is enforced by the backend, including direct calls.
  Serialize competing approve/reject operations; return `409` for a decision on
  a non-pending account so one request cannot overwrite the other decision.
- Rejection retains the account and decision history and reserves its username.
  Reapplication, reopening rejected requests, email verification and approval
  emails are outside initial delivery. Pending count in Members supplies the queue;
  this flow does not depend on the notification integration.

## Data model and migration

Extend existing SQLAlchemy models and Alembic history; the inspected head is
`b7c8d9e0f1a2` (nested tags). Reconfirm the head at implementation time.

| Structure | Planned change |
| :--- | :--- |
| `users` | Reuse integer ID, username, hash, `is_active` and lockout fields; constrain role to `admin`/`operator`; add `display_name`, `registration_status` (`pending`/`approved`/`rejected`), `registration_reviewed_by`, `registration_reviewed_at`, optional `registration_rejection_reason`, `must_change_password`, `password_changed_at`, `last_login_at`, `created_at`, `updated_at` |
| New `user_target_assignments` | Composite primary key `(user_id, target_id)` with foreign keys to existing integer users and string target IDs; index by target for assignment views; record `assigned_at` |
| New `member_audit_events` | Actor ID (nullable for controlled setup), action, affected entity IDs, UTC time and sanitised before/after changes; record a source for setup/recovery events |
| `sessions` | Reuse existing `revoked_at` and `revocation_reason`; no duplicate session store or assignment snapshot |
| `tags` / `target_tags` | Reuse existing constraints and relationships; no replacement tables |

Assignment writes accept approved Operators only, including suspended Operators if the
Admin explicitly assigns them; make their inactive status visible. Suspension and
target soft disable retain associations. Assignment deletion removes only the
chosen relationship. Audit writes and their associated changes commit atomically;
the last-active-Admin check must also hold under concurrent requests.

Preserve trimmed, case-sensitive username matching used by current login. Keep
usernames immutable in the initial UI; edit display name and active state instead.
Do not introduce casefold login matching or silently rename existing accounts.
Backfill display name from username, required-change state as false for existing
accounts, and unknown historical login/password-change timestamps as null. Record
migration time for new creation/update fields without claiming historical dates.
Backfill existing accounts as approved while preserving their current active state;
leave historical approval actor/time null. Controlled Admin setup and explicit
Admin creation produce approved accounts. Registration always supplies pending
explicitly; defaults alone must never enable a self-registered account. Add a
database constraint that pending/rejected accounts cannot have `is_active=true`.
Use UTC and the existing timestamp helpers/serialisation conventions.

Before upgrading an existing database:

1. Back up the database and record an explicit mapping identifying at least one
   active, accessible bootstrap Admin. Inspect actual role values; never infer
   Admin status from free-text role names or the first user ID.
2. Use a controlled pre-upgrade mapping step consumed by the role migration.
   Abort without it if legacy accounts cannot be mapped safely. Map remaining
   users to Operator with no assignments unless specific assignments are supplied.
   For a fresh database, use controlled Admin setup before serving application traffic.
3. Revoke existing sessions during conversion, preserve account IDs/password hashes,
   and apply the database role constraint after mapping. Validate with a fresh Admin
   login and verify an Operator with no assignments sees an empty scope.
4. Use SQLite-compatible Alembic batch changes where required. Existing startup
   and account creation call `Base.metadata.create_all`, which cannot migrate old
   tables; require migrations before either path and update the setup script.
   Docker currently runs `alembic upgrade head` before Uvicorn, so mapping must be
   prepared before container startup, without an interactive deployment prompt.

Update `scripts/create_user.py` to accept only the fixed role values, default new
ordinary users to Operator, and provide explicit controlled Admin setup/recovery.
Include script/deployment packaging changes as needed. Recovery actions require
audit events and session revocation. Do not downgrade to the old unrestricted
application while relying on assignment isolation; test recovery from backup.

## New API contracts

These routes are proposed additions, not existing functionality. Reuse integer
member IDs, string target IDs, `limit`/`offset` pagination and the existing error
and CSRF conventions. Pydantic request schemas reject unknown fields.

| Proposed endpoint | Behaviour |
| :--- | :--- |
| `POST /auth/register` | Public registration with username, display name and password; always pending/inactive Operator with no assignments; no session or secret in response |
| `GET /members` | Admin-only paginated search by username/display name, Pending/Active/Suspended/Rejected filter, pending count and assigned active-website count |
| `POST /members` | Admin-only approved Operator creation; username, display name and temporary password; role fixed by backend; audited explicit approval |
| `GET /members/{member_id}` | Admin-only member details, including suspended state |
| `POST /members/{member_id}/approve` | Admin-only atomic decision on pending Operator; activate without assigning websites |
| `POST /members/{member_id}/reject` | Admin-only atomic decision on pending Operator with optional reason; keep inactive and preserve history |
| `PATCH /members/{member_id}` | Admin-only display-name/active-state update; activation only for already approved accounts; no role, approval-status or username mutation; last-active-Admin protection |
| `POST /members/{member_id}/reset-password` | Admin-only approved Operator reset with temporary password; reset response contains no secret; Admin recovery uses controlled tooling |
| `GET /members/{member_id}/websites` | Admin-only paginated assigned websites with active-state filtering |
| `PUT /members/{member_id}/websites/{target_id}` | Admin-only idempotent individual assignment; preserve other assignees |
| `DELETE /members/{member_id}/websites/{target_id}` | Admin-only idempotent removal of this assignment only |
| `GET /member-assignments/websites` | Admin-only website list with All/Unassigned/Assigned counts, name/URL search, Operator/tag filters and pagination |
| `POST /auth/change-password` | Own password change using current/new passwords; CSRF required; revoke sessions and require login again |

Both assignment UI tabs call the same assignment mutation endpoints. Extend
`AuthResponse` and frontend auth types with fixed role values, display name and
`registration_status` and `must_change_password`; expose no password hash, review
reason or member list through auth/me. Only approved active users can reach auth/me.
Add server-side `search` to existing target list/page APIs, using the same scoped
query for items and totals and preserving current status, sort and tag parameters.
Register new routers/models in the existing application entry points.

## Tags and filtering

The existing implementation provides a Tags page, badges below website URLs,
parent/sub-tags and any/all filters. Reuse these structures and extend their
authorisation. [Tags Management Plan](archive/TAGS_MANAGEMENT_PLAN.md) is historical
design context; current add-on access requirements are owned here.

- Allow multiple tags per website. Admins manage a shared tag catalogue with
  names and colours. Preserve Unicode NFKC, trimming and casefold normalisation:
  root names are unique among roots, and child names are unique within their parent.
  Sub-tags cannot have their own sub-tags.
- Support multi-tag filtering with **Match any** (default) and **Match all** modes.
  Preserve parent matching that includes websites carrying any of its sub-tags.
- Deleting a tag removes its website associations, never the websites themselves.
  A parent with sub-tags cannot be deleted until its children are moved or deleted.
- Operators can filter using tags present on accessible websites but cannot
  create, edit, delete or attach tags. Tag changes never change assignments.
  Include parent metadata required to render accessible sub-tags without exposing
  unrelated children or counts for inaccessible websites.

Preserve the existing limit of 20 tags per target and duplicate-ID validation.
Counts inside `TargetRead.tags` also need scoping; avoid leaking global tag counts
through nested schemas or eager-loaded parent/child relationships.

## Frontend integration

- Add `/members` with the two tabs and `/change-password` for the password flow,
  reusing React Router, Slate styling, current auth context and TanStack Query.
  Restrict `/members` and `/tags` to Admins even when entered through a direct URL.
- Add public `/register`, validation and submission/loading/error/success states.
  Pending approval is a submission result, not an authenticated application route.
  Add Approve/Reject controls and decision confirmation to the Members tab; refresh
  the pending badge, status lists and member details after decisions.
- Keep Operator access to target/check detail, Run Check, acknowledge, confirm
  defaced, approve baseline and demote baseline within their assigned scope.
  Hide Add/Edit/Disable Target and all tag/assignment administration controls.
  Preserve the existing review modals and baseline safety rules.
- Use the existing `/api` client, cookie credentials and in-memory CSRF token.
  Keep the required-change flag available from login and me across page reloads.
- On member/assignment mutations invalidate affected member lists/details,
  assignment counts, targets and tags. Existing logout already clears QueryClient;
  also clear auth/data caches on session loss and identity changes, and discard
  target/check/snapshot data and image blob URLs after access is denied.
- Existing target polling refreshes about every four seconds, while tags and
  some artifact queries do not poll. Refresh auth/scope on focus and handle
  `401`/`403`/`404` explicitly instead of retaining a formerly authorised page.
  Frontend refresh cannot revoke bytes already downloaded; backend scope controls
  every subsequent request regardless of frontend cache state.
- An unassigned Operator sees an explanatory empty state without an Add Target
  prompt. Keep loading/error/retry states and pagination consistent with existing pages.

## Implementation sequence

1. Inspect the existing authentication, user model, target routes and artifact
   serving paths against this repository baseline. Confirm the endpoint matrix,
   registration/approval and temporary-password flows, and explicit migration
   mapping for deployed accounts.
2. Add migrations for fixed user roles/account state as needed, unique user-target
   assignments, approval state/constraints, missing member fields and audit storage.
   Reuse existing tags and
   target-tag associations. Explicitly select the bootstrap Admin; map remaining
   accounts without silently granting Admin or all-website access. Restrict role
   values to Admin/Operator and update the controlled setup/recovery tooling.
3. Implement central backend role/scope checks, member lifecycle APIs, assignment
   APIs, public registration and Admin approval/rejection, password change/reset,
   session revocation and audit events. Apply scope to
   existing tag APIs and search/filter/count queries before building member UI.
4. Build Register and the combined Member Management page, approval queue and
   member detail assignment controls.
   Update Websites with name/URL search, assignees and role-appropriate actions;
   reuse existing tag/status filters and apply role-aware navigation.
5. Verify access boundaries and migration behaviour before release.
6. Follow up with bulk assignment/removal and bulk tag attachment/removal. Adding
   assignees must preserve existing assignees; removing must affect only the chosen
   members. Validate all selected items before committing each bulk operation.

Initial delivery includes registration with explicit Admin approval, individual
assignment from both tabs, members, backend
access controls, password/session lifecycle, audit events and scoped use of existing
website tags and filters. Bulk operations and notifications are subsequent increments,
not requirements for the initial release.

## Future notification integration

When a notification channel and recipient configuration are available, connect
them to the same active-account and website-assignment rules:

- Approved, active Admins receive incident alerts for all websites without exception.
- Approved, active Operators receive alerts only for their assigned websites.
- Alerts for websites with no active Operator route to active Admins.
- Re-evaluate recipients at dispatch, including retries, so suspension or assignment
  removal does not leave a stale recipient list. Deduplicate shared assignments.
- Apply the same scope to periodic reports when implemented.

This section defines the integration contract; delivering a notification channel
or report system is outside the initial Member Management release.

## Acceptance criteria

- Public registration produces only a pending, inactive Operator with no assignments
  or session. Submitted role/status/active/assignment overrides are rejected.
- Pending/rejected accounts cannot log in, access protected APIs or artifacts, or
  bypass approval through re-enable, password reset or direct assignment endpoints.
- Only an approved active Admin can approve/reject; decisions persist actor/time
  and audit events. Competing decisions cannot overwrite each other.
- Approved applicants use their own password and initially see an empty website
  scope until assigned. Admin-created/reset Operators retain required-password-change.
- Members shows pending count, registration time, status filters and approval/rejection
  actions without a third tab. Register shows confirmation and login navigation.
- Registration tests cover duplicate/concurrent usernames, password/schema validation,
  anonymous rate limiting and origin validation; existing authenticated CSRF remains enforced.
- Admins manage accounts and assignments from one Member Management page with
  two tabs; Operators cannot access its routes or APIs.
- Two Operators assigned different websites cannot retrieve or modify each
  other's website data through IDs, direct links, artifacts or aggregates.
- A shared website is accessible to each assigned active Operator; an unassigned
  Operator has no website access. Admins retain visibility of all websites.
- Suspension invalidates sessions; assignment removal blocks subsequent access;
  the Unassigned view correctly includes websites with only inactive assignees.
  Re-enabling restores assignments but does not restore revoked sessions.
- Password reset revokes existing sessions, and the selected reset/change flow is
  usable without email. Temporary-password accounts cannot bypass required change.
- Administrative audit events persist with actor, time and affected records,
  without password or token contents.
- Tags support any/all filtering without changing authorisation. Tag deletion
  leaves websites and assignments intact.
- Member details and the assignment tab show consistent assignments and counts.
- Backend tests cover allowed and denied access, session revocation, duplicate
  relationships, last-Admin protection and migration/bootstrap behaviour.
  Frontend checks cover both roles, filters and loading/empty/error states.
- Exercise the permission matrix with real cookie sessions and CSRF tokens:
  two Operators with disjoint targets, a shared target, a suspended Operator,
  an Operator without assignments, an Admin and an account requiring password change.
  Include pending and rejected applicants and attempts to bypass the approval gate.
  Check raw/normalised screenshots, text, historical snapshots/checks and nested IDs.
- Existing API test fixtures currently seed `authenticated-user`. Update privileged
  regression fixtures to an explicit Admin and add separate scoped Operator fixtures;
  do not bypass authorisation dependencies to make existing tests pass.
- Verify `/config` still supports Operator target detail, scoped parent/sub-tag
  filtering/counts, idempotent assignment writes, retained inactive assignments,
  concurrent last-Admin protection and continued scheduling of unassigned targets.
- Validate a fresh database and an upgrade copy of a legacy database through Alembic,
  not only `create_all`; include missing/invalid bootstrap mapping, existing arbitrary
  roles, preserved hashes/IDs, session revocation and preserved tag associations.
  Existing active/inactive accounts migrate to approved without changing active state.
- Run the relevant backend/frontend checks and migration validation; record
  actual results when implemented. This planning update claims no test results.

Implementation verification uses the repository's existing commands: backend
`pytest`, `ruff check .` and `mypy app` from `backend`; frontend `npm test`,
`npm run lint`, `npm run typecheck` and `npm run build` from `frontend`. Perform
`alembic upgrade head` only against isolated migration-test databases or the
explicitly authorised deployment database. Record results and migration/recovery
evidence with the release; source inspection is not evidence of passing tests.

For the later notification increment, verify all-website routing to active Admins,
assignment-scoped routing to active Operators, Admin routing for unassigned sites
and recipient re-evaluation after suspension or assignment removal.
