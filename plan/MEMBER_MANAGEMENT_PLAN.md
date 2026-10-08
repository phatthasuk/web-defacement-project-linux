# Member Management, Website Assignments and Tags — Implementation Plan

**Parent roadmap:** [Project Plan — Planned Features](PROJECT_PLAN.md#planned-features)

This is the authoritative detailed specification for the Member Management feature. The parent
project plan owns overall priorities, stage status and cross-feature constraints.
Maintain feature requirements here and keep only a summary in the parent plan.

**Planning decision: 2026-09-18. Status: planned, not implemented.**
This document defines the agreed feature scope. It does not declare the observation
period complete or authorise implementation or deployment. Implementation of this
feature is scheduled to begin in Stage 3 (Notification).

## Roles and access scope

Use exactly two fixed roles: **Admin** and **Operator**. Admins can access every
website. Operators can access only websites explicitly assigned to them. One
website can have multiple Operators, and one Operator can have multiple websites.
Tags organise websites and never grant or revoke access.

| Capability | Admin | Operator |
| :--- | :--- | :--- |
| View dashboard, websites, checks and related artifacts | All websites | Assigned websites only |
| Trigger checks and perform incident review actions | All websites | Assigned websites only |
| Receive incident alerts and notifications (Stage 3) | All websites | Assigned websites only |
| Create, edit or disable websites and monitoring settings | Yes | No |
| Create tags and change website tags | Yes | No |
| Search and filter websites by tags and status | All websites | Assigned websites only |
| Manage members and website assignments | Yes | No |
| Manage system-wide settings | Yes | No |

Preserve existing review safeguards, including protection of the last baseline.
Map existing review endpoints to explicit permissions during implementation;
do not introduce additional roles or a custom role editor in this release.

## Navigation and page layout

Keep two relevant navigation destinations:

- **Websites:** website status, latest check results, search by name or URL,
  and tag/status filters. Show current assignees where appropriate. Admins manage
  website configuration and tags here; Operators see only their assigned scope.
- **Member Management (Admin only):** combine member administration and website
  assignment in one page with two tabs. Do not create a separate assignment page.

The **Members** tab shows name, login identifier/email as supported by the existing
account model, role, account status, last login and assigned website count.
Support search, status filtering, adding Operators, editing basic details,
password reset, and disabling/re-enabling accounts. Opening a member shows their
assigned websites with actions to assign or remove websites directly.

The **Website Assignments** tab provides All / Unassigned / Assigned views with
counts, website name/URL search, and filters for Operator and tags. Its table shows
website name, URL, tags and current assignees. Both tabs use the same assignment
records and refresh affected counts after changes.

An **Unassigned** website has no active Operator assigned to it. Disabling the
only active assignee therefore places that website in this view. Retain assignment
records on account suspension; re-enabling restores those assignments and the UI
must make that effect clear. Admin access does not count as an Operator assignment.

## Account lifecycle and authorisation

- Admins create Operators; public self-registration is out of scope.
- Provision Admin accounts through a separate controlled setup/recovery process,
  not the ordinary Add Member form. Protect the last active Admin.
- Prefer account suspension over permanent deletion to preserve history.
- Reuse the existing password/session/CSRF protections. Never display existing
  passwords. Select the reset mechanism after inspecting the current auth flow;
  email delivery is not assumed to exist.
- Suspension invalidates existing sessions and blocks subsequent requests.
  Assignment removal takes effect on subsequent requests, including direct links
  and artifact downloads; it must not depend on logging in again.
- Enforce role permissions and website scope at the backend for list/detail APIs,
  mutations, checks, baselines, screenshots, HTML/text artifacts and aggregates.
  Frontend route/button visibility is supplementary.
- **Incident alert and notification routing (scheduled for Stage 3):**
  - **Admins** receive incident alerts for **all websites** without exception.
  - **Operators** receive incident alerts **only for their assigned websites**.
  - Incident alerts for **unassigned websites** route directly to Admins.
  - Apply the same scoping rules to periodic reports when implemented.
- Calculate pagination totals, filter options and dashboard counts within the
  caller's authorised scope. An Operator with no assignments sees an empty state.
- Record actor, time, affected account/website and relevant changes for member,
  assignment and tag administration in the audit log, reusing Stage 5.3 work.

## Tags and filtering

Detailed Tags UI, API and migration design is in [Tags Management Plan](TAGS_MANAGEMENT_PLAN.md).
Provide a separate Tags Management page, reachable from the top-right header
navigation. Show assigned tag badges below each website URL on the Websites list.

- Allow multiple tags per website. Admins manage a shared tag catalogue with
  names and colours; reject duplicate names after trimming and case normalisation.
- Support multi-tag filtering with **Match any** (default) and **Match all** modes.
- Deleting a tag removes its website associations, never the websites themselves.
- Operators can filter using tags present on accessible websites but cannot
  create, edit, delete or attach tags. Tag changes never change assignments.

## Implementation sequence

1. Inspect the existing authentication, user model, target routes and artifact
   serving paths. Finalise the endpoint permission matrix and reset mechanism.
2. Add migrations for fixed user roles/account state as needed, unique user-target
   assignments, tags and target-tag associations. Reuse existing structures where
   possible. Define an explicit migration/bootstrap mapping for existing accounts:
   preserve a working Admin and never grant every Operator every target implicitly.
3. Implement central backend role/scope checks, member lifecycle APIs, assignment
   APIs, tag APIs and scoped search/filter/count queries with audit events.
4. Build the combined Member Management page and member detail assignment controls.
   Update Websites with tags, filters and role-appropriate actions.
5. Verify access boundaries and migration behaviour before release.
6. Follow up with bulk assignment/removal and bulk tag attachment/removal. Adding
   assignees must preserve existing assignees; removing must affect only the chosen
   members. Validate all selected items before committing each bulk operation.

Initial delivery includes individual assignment from both tabs, members, backend
access controls, website tags and filters. Bulk operations are the subsequent
increment, not a requirement for the initial release.

## Acceptance criteria

- Admins manage accounts and assignments from one Member Management page with
  two tabs; Operators cannot access its routes or APIs.
- Two Operators assigned different websites cannot retrieve or modify each
  other's website data through IDs, direct links, artifacts or aggregates.
- A shared website is accessible to each assigned active Operator; an unassigned
  Operator has no website access. Admins retain visibility of all websites.
- Suspension invalidates sessions; assignment removal blocks subsequent access;
  the Unassigned view correctly includes websites with only inactive assignees.
- Tags support any/all filtering without changing authorisation. Tag deletion
  leaves websites and assignments intact.
- Incident alerts and notification recipient routing (Stage 3) delivers alerts for
  all websites to Admins, alerts for assigned websites to Operators, and falls back
  to Admins for unassigned websites.
- Member details and the assignment tab show consistent assignments and counts.
- Backend tests cover allowed and denied access, session revocation, duplicate
  relationships, last-Admin protection and migration/bootstrap behaviour.
  Frontend checks cover both roles, filters and loading/empty/error states.
- Run the relevant backend/frontend checks and migration validation; record
  actual results when implemented. This planning update claims no test results.
