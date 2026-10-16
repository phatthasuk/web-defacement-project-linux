# Tags System Plan for Website Categorization

Planning Date: October 8, 2026  
Status: Planning Document (Archived Design Record)

This document planned the introduction of Tags to organize, filter, and categorize monitored websites. It specified a dedicated tag management view at `/tags`, navigation links in the application header, and visual tag badges displayed beneath URLs in the Target / URL column.

> Historical Note (October 12, 2026): The Tagging system has been implemented. This document is retained for architectural and design history. Development sequences and preliminary statuses reflect historical milestones. The standalone [Member Management](../MEMBER_MANAGEMENT_PLAN.md#tags-and-filtering) specification governs role-based access control (Admin/Operator) layered atop this tagging system.

This design establishes many-to-many tag associations per website without altering operational access permissions.

## 1. Scope

Initial deliverables include tag creation, editing, deletion, target-tag assignments, and tag-based filtering on the target dashboard. Operators can filter target subsets and trigger on-demand checks using existing execution workflows.

Batch-triggering entire tag groups, tag-driven scheduling intervals, and bulk tag assignments represent future roadmap items. Initial tag capabilities do not modify baseline approval logic or scheduled monitoring intervals.

## 2. Header Navigation

- Integrated into the global Header in `frontend/src/App.tsx`, adding `Websites` and `Tags` links to the right navigation cluster preceding user profile and Logout controls.
- `Websites` links to `/` and `Tags` links to `/tags`, with active route indicators.
- Persistent across Target List, Target Detail, Check Detail, and Tag Management views.
- Mobile viewports adapt via collapsible menus or stacked navigation bars without crowding system titles or session controls.
- Uses the application's Slate dark aesthetic; hidden on unauthenticated login views.

## 3. Tag Management Interface

A dedicated `Tags Management` view at `/tags` offering an inline creation form alongside an administrative list of configured tags, styled consistently with Add New Monitor and Monitored Targets cards.

| Component | Intended Behavior |
| :--- | :--- |
| Add Tag | Input tag name, select palette color, and display a live badge preview prior to submission. |
| Tag List | Display tag badge, name, associated website count, and Edit / Delete action triggers. |
| Search | Server-side name filtering with pagination. |
| Edit Tag | Modify name and color key; updates propagate instantly across all referencing targets. |
| Delete Tag | Confirmation dialog displaying name and count of affected associations; deletes tag and association records without modifying targets. |
| View States | Supports Loading, Empty, and Error states with retry triggers and notification banners. |

UI labels use English consistently, while tag names support UTF-8 (supporting Thai and English entries such as `Hospital`, `Production`, `Thai text`).

Usage counts display active targets, while deletion prompts report total associations (including inactive targets) to reflect complete impact.

## 4. Assigning Tags to Websites

1. Multi-select tag input added to the Add New Monitor form below the URL input.
2. Identical multi-select incorporated into the Edit Target Modal, pre-populated with current assignments.
3. Searchable dropdown for large tag volumes, supporting "Clear all" and a direct `Manage Tags` link.
4. Adding targets without tags remains valid; failed tag queries display inline retry actions without corrupting form state.
5. Updating tags submits `tag_ids` independently to allow categorization during active checks without re-submitting potentially stale URLs.

If an assigned tag is concurrently deleted by another session, the backend transaction rejects the payload; the frontend reloads available tags and prompts the user to re-verify.

## 5. Visual Tag Badge Placement

Within the Target / URL table cell, layout follows top-to-bottom:

```text
Kasemrad Inter Hospital TH
https://kasemradinter.com/
[ Hospital ] [ Production ] [ TH ]
```

- Badges appear beneath the URL separated by 6–8 px spacing, wrapping responsively via `flex-wrap`.
- Badges display in alphabetical order.
- Targets without tags render no extra vertical margin.
- Error messages and notices render below the badge cluster.
- Badges maintain high legibility against dark slate backgrounds; status badges remain segregated in the Status column.
- Long tag names truncate with ellipsis, accompanied by full-text accessible tooltips.
- Table rows dynamically scale to content height rather than forcing fixed dimensions or introducing separate columns.
- Reusable `TagBadge` component shared across Target List, Target Detail, and Tag Management.

## 6. Tag-Based Target Filtering

Filter controls positioned above the Monitored Targets table, defaulting to `Match any` with a toggleable `Match all` option and a `Clear filters` button.

| Mode | Behavior |
| :--- | :--- |
| No tags selected | Renders all targets accessible to the current session. |
| Match any | Renders targets matching at least one selected tag (OR). |
| Match all | Renders targets matching all selected tags (AND). |

Modifying filter selections resets the view to Page 1. Filtering executes server-side prior to pagination, ensuring `total` counts and showing metrics reflect the filtered subset rather than filtering client-side records.

Filter states persist in query parameters (e.g. `/?tag_ids=<id1>&tag_ids=<id2>&tag_match=any`) to support navigation back from detail views and direct URL sharing. Empty results display `No websites match the selected tags` with an action to clear filters.

If a filtered tag is deleted, the invalid ID is stripped, resetting pagination with an informative notification.

## 7. Data Integrity and Permissions

- Many-to-many relationship: targets can hold multiple tags; tags associate with multiple targets.
- Tag name length: 1–50 characters (trimmed); upper bound of 20 tags per target.
- Names normalized via Unicode NFKC, trimming, and casefolding (e.g., `Hospital` and ` hospital ` are treated as duplicates).
- Uniqueness enforced via database unique constraints, returning `409 Conflict` on collisions.
- Color palettes restricted to validated backend keys (`cyan`, `blue`, `violet`, `emerald`, `amber`, `rose`, `slate`), mapped to static CSS classes in the frontend.
- Submitted `tag_ids` arrays must contain unique, valid identifiers validated atomically.
- Omitting `tag_ids` on PATCH leaves existing tags unchanged; submitting `[]` strips all tags; submitting `null` returns `422 Unprocessable Entity`.
- Updating tag names or colors preserves tag IDs without requiring individual target updates.
- Deleting tags preserves target records, snapshots, and check histories.
- Tag updates modify `updated_at` timestamps without affecting `status`, `last_error`, `url_revision`, or active baselines.

Under Member Management, Admins create, edit, delete, and assign tags. Operators utilize tag filtering across assigned targets.

## 8. Data Model

| Table | Columns and Constraints |
| :--- | :--- |
| `tags` | `id` (UUID PK), `name`, `normalized_name` (Unique), `color_key`, `created_at`, `updated_at` |
| `target_tags` | `target_id`, `tag_id` (Composite PK, Foreign Keys to `targets` and `tags`) |

Indexes placed on `target_tags.tag_id` for accelerated lookup. Foreign key cascades remove relationship rows upon tag deletion. Soft-deleted targets maintain tag associations.

Database migrations applied sequentially via Alembic. Downgrades drop tag tables and association records cleanly.

## 9. Proposed API Endpoints

| Method | Endpoint | Functionality |
| :--- | :--- | :--- |
| GET | `/tags?search=...&limit=...&offset=...` | Paginated tag list with permission-scoped counts. |
| POST | `/tags` | Create tag with `name` and `color_key` (`201 Created`). |
| PATCH | `/tags/{tag_id}` | Update tag name or color. |
| DELETE | `/tags/{tag_id}` | Delete tag and cascades associations (`204 No Content`). |
| POST | `/targets` | Accepts optional `tag_ids` array (default `[]`). |
| PATCH | `/targets/{target_id}` | Replaces target tag set via `tag_ids`. |
| GET | `/targets` & `/targets/page` | Supports repeated `tag_ids` and `tag_match=any\|all`. |
| GET | `/targets/{target_id}` | Includes assigned `tags` in target read schema. |

Responses utilizing `TargetRead` output `tags: [{id, name, color_key}]`. Tag schemas are declared separately from target schemas to avoid circular dependencies.

Filter queries utilize `EXISTS` or subqueries to avoid duplicate row multiplication from joins. Relationships load eagerly via `selectinload` to prevent N+1 query overhead. Pagination preserves deterministic ordering (`created_at desc, id desc`).

## 10. Required Source Modifications

- Backend models: `models/tag.py`, `models/target_tag.py`, and relationships in `models/target.py`.
- Backend schemas: `schemas/tag.py` and extensions to `schemas/target.py`.
- Backend routes: `api/routes/tags.py`, updates to `api/routes/targets.py`, router registration in `main.py`.
- Database: Alembic migration establishing `tags` and `target_tags`.
- Frontend API & Types: `api/tags.ts`, `types/tag.ts`, updates to `api/targets.ts`, `types/target.ts`.
- Frontend Hooks: `hooks/useTags.ts`, updates to `hooks/useTargets.ts`.
- Frontend Components: `pages/TagsPage.tsx`, `components/TagBadge.tsx`, `components/TagMultiSelect.tsx`.
- Frontend Integration: `App.tsx`, `TargetListPage.tsx`, `EditTargetModal.tsx`, `TargetDetailPage.tsx`.

Query keys include sorted Tag IDs and match modes. Tag mutations invalidate tag lists, target lists, detail views, and counts.

## 11. Acceptance and Verification Criteria

- Tag Management accessible from Header; seamless navigation between Views.
- Adding and updating tag attributes updates referencing targets immediately.
- Multi-select operates smoothly in Add and Edit modals; tags can be completely cleared.
- Badges render responsively below URLs in table cells.
- Duplicate names, invalid color keys, missing IDs, and length violations are rejected cleanly.
- Filtering by `any` and `all` operates accurately across paginated boundaries.
- Modifying tags during background checks does not disrupt check execution.
- Tag deletion cleanly strips associations while preserving targets and snapshots.
- API enforces Admin authorization for mutation routes and validates CSRF tokens.
- Operators only see tags and counts within their assigned target scope.
