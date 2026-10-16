# Artifact Cleanup Plan

**Status:** inventory and dry run complete; no artifacts or database rows were deleted.

**Scope:** local workspace data in `backend/data`; the Linux deployment host was not inspected.

## Inventory

Filesystem sizes and modification times were inspected on October 16, 2026. Times below are UTC.

| Directory | Files | Size | Modification date range |
|---|---:|---:|---|
| `screenshots` | 3,594 | 9.64 GB | Sep 8–Oct 16, 2026 |
| `html` | 3,594 | 1.59 GB | Sep 8–Oct 16, 2026 |
| `text` | 3,594 | 60 MB | Sep 8–Oct 16, 2026 |
| `raw_screenshots` | 815 | 1.93 GB | Oct 8–Oct 16, 2026 |

The local SQLite database contains 3,594 snapshot rows and 14 active baseline snapshots. There are 3,624 check results. Each screenshot, HTML, and text artifact has a matching snapshot ID; all 815 raw screenshots have a database reference. The inventory found **zero unreferenced files**.

## Fourteen-day retention assessment

The dry run used a rolling 14-day cutoff. It listed 6,654 older artifact files:

- 6,642 files from 2,214 snapshots referenced by check history.
- 12 files from four older active baselines, which must be retained.
- Zero expired, unreferenced orphan files eligible for safe cleanup.

Deleting the 6,642 history files after coordinated database pruning could reclaim about **6.76 GiB** in this workspace. This is a potential estimate, not a deletion authorization or a server disk measurement. The Stage 2 evidence spans September 8–October 16, so a 14-day policy would discard much of the observation history needed to reproduce the audit. Keep the full Stage 2 evidence until the audit is accepted and archived. Preserve active baselines regardless of age.

Deleting artifact files alone would leave snapshot and check rows whose screenshot, text, and comparison views can no longer load. Deleting those rows would shorten the history endpoints. Retention therefore needs a coordinated database-and-file procedure.

## Dry-run script and manifest

The script [cleanup_artifacts.py](../backend/scripts/cleanup_artifacts.py) defaults to dry run. It scans only `screenshots`, `raw_screenshots`, `text`, and `html`; rejects symlinks and paths outside `backend/data`; opens the database read-only; and protects files matching snapshots, check history, or active baselines. Its optional apply mode only accepts an approved manifest and can remove expired orphan files. It does not prune snapshot history or modify the database.

The reviewed dry-run list is [artifact-cleanup-dry-run.csv](artifact-cleanup-dry-run.csv). It classifies all 6,654 expired files as retained; the dry run would delete **zero files** and reclaim **zero bytes**.

Recreate the inventory and manifest from the repository root with:

```bash
python3 backend/scripts/cleanup_artifacts.py \
  --retention-days 14 \
  --manifest plan/artifact-cleanup-dry-run.csv
```

No apply command was run. Any future orphan deletion must be reviewed and approved against its manifest first.

## Database consistency procedure for a future history prune

Before pruning database-referenced snapshots:

1. Quiesce the application and scheduler so no checks or reviews write to the database during maintenance.
2. Create an online SQLite backup with SQLite’s backup API or `.backup` command. Do not copy only `app.db` while WAL mode is active; the WAL may contain committed data. Store the backup outside the data directory and verify it with `PRAGMA integrity_check` and table row counts.
3. In one database transaction, remove only check results outside the approved retention window. Preserve the full Stage 2 audit range until it has been archived and accepted. Keep every active baseline and any snapshot referenced by a retained check result. Delete a snapshot row only after confirming no retained result references it; check-attempt snapshot/result foreign keys use `ON DELETE SET NULL`.
4. Commit the database transaction before unlinking the matching artifact files from the reviewed manifest. Then run `PRAGMA foreign_key_check` and `PRAGMA integrity_check`, compare row counts with the plan, and verify that retained history and comparisons still load.

If the database transaction fails, roll it back and leave all artifact files in place. If file removal fails after the database commit, the remaining files are unreferenced orphans and can be reviewed by a later dry run.

## Evidence boundary

The SSH host key for the documented server was not trusted in this workspace, and local Docker access was denied. These figures describe `backend/data` here only. Before applying any policy to production, repeat the inventory on the server and compare it with the production database and its backup.
