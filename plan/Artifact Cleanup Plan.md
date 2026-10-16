# Artifact Cleanup Plan

**Status:** Linux hardening and local-workspace dry run complete. No real artifact files or database rows were deleted or changed, no migration was run, and no service was stopped.

**Apply readiness:** **Not ready for production.** The production host and its mounted database were not accessible for verification. The verified local workspace dry run has **0 eligible orphan files and 0 bytes to reclaim**, so there is nothing to apply from this inventory.

## Deployment data path and evidence limits

The repository's production `docker-compose.yml` sets `DATABASE_URL=sqlite:////app/data/app.db` and `DATA_DIR=/app/data`, and bind mounts `./backend/data` on the host to `/app/data` in the backend container. Resolving Compose from this checkout maps that source to `/home/filtervisual/Desktop/github/web-defacement-project-linux/backend/data`; the database in this checkout is `backend/data/app.db`.

This identifies the path configured by the Compose file in this checkout. It does **not** prove that the same Compose file, checkout, mount source, database, or data is currently deployed on the Linux server. Docker daemon access from this workspace failed with `permission denied` for `/var/run/docker.sock`; the documented SSH host key was not trusted. Do not treat the workspace database as production evidence. Re-run the read-only inventory on the deployment host and verify its Compose project and mount before considering cleanup.

The backend scheduler runs in-process with the FastAPI application when `SCHEDULER_ENABLED` is true. The Compose backend is therefore the writer to stop for maintenance, along with any separate process or deployment that writes to the same SQLite database. The Dockerfile runs `alembic upgrade head` on container startup; restarting the service can apply pending migrations. This task did not start or restart the service.

## Read-only schema and migration check

Checked on **2026-10-16 08:39 UTC** using host Python **3.12.3** (meets the 3.11 minimum), SQLite opened in read-only/query-only mode, and source migration files parsed without invoking Alembic:

- Current database migration revision: `7e3a9c2f1b64`.
- Source migration head: `7e3a9c2f1b64` (9 revision files inspected).
- `check_attempts` exists with 15 columns; the database also contains `snapshots`, `check_results`, and `alembic_version`.
- Counts: 3,594 snapshots, 3,624 check results, and 97 check attempts; 14 snapshots are active baselines.

The inspected workspace database is at the source head and contains `check_attempts`; no schema repair or migration was needed or run. If a deployment database lacks `check_attempts`, its schema is behind the durable-check-retries migration (or is otherwise inconsistent). The cleanup script stops with an explicit missing-table error because references cannot be classified safely without it. Inspect that deployment's migration revision and take a verified backup; use the project's planned migration procedure separately, never as an automatic cleanup response.

## Linux artifact inventory

Filesystem inventory measured on **2026-10-16 08:39 UTC**. Modification ranges below are exact UTC timestamps. Decimal byte totals are shown for file sizes; the host filesystem display rounds capacity to whole GiB.

| Directory | Files | Bytes | Modification range (UTC) |
|---|---:|---:|---|
| `screenshots` | 3,594 | 9,642,091,589 | 2026-09-08 09:59:29.202253 to 2026-10-16 08:02:05.063984 |
| `raw_screenshots` | 815 | 1,933,404,899 | 2026-10-08 04:17:10.689368 to 2026-10-16 08:02:05.065009 |
| `html` | 3,594 | 1,593,766,375 | 2026-09-08 09:59:29.203739 to 2026-10-16 08:02:05.066244 |
| `text` | 3,594 | 59,993,328 | 2026-09-08 09:59:29.203300 to 2026-10-16 08:02:05.065950 |

At the inventory time, `df -h backend/data` reported a 98G filesystem, 73G used, 21G available, 79% used. This is the workspace host's filesystem, not a production-server capacity check.

A 14-day dry run used cutoff **2026-10-02 08:39:35.817006 UTC**. It inventoried **6,660** expired artifacts: 6,648 files referenced by check history (2,216 snapshot IDs, 7,261,384,315 bytes) and 12 files from four older active baselines (13,574,138 bytes). All were retained. There were **0 safe expired orphans**, so cleanup would delete **0 files and reclaim 0 bytes**. All 3,594 screenshot, HTML, and text artifacts are snapshot-ID matched, and all 815 raw screenshots have database references.

Much of this workspace's Stage 2 evidence dates from September 8 onward. A 14-day retention policy would discard evidence that may still be needed for audit reproduction. Preserve it until the audit is accepted and archived. History and baseline artifacts are not candidates for this orphan-only script. Any later history pruning requires a separately reviewed, transactional database-and-artifact retention plan.

## Hardened script and synthetic checks

[cleanup_artifacts.py](../backend/scripts/cleanup_artifacts.py) remains dry-run by default. It requires Python 3.11+, uses a read-only SQLite connection for inventory, rejects symlink data/artifact directories and symlink/non-regular artifact files, and enforces path containment. Apply validation checks every manifest row before unlinking anything, including absolute/relative path agreement, allowed directory, snapshot ID, database disposition, expiry, exact `mtime_ns`, and exact size. A same-size file with a changed modification time is rejected. It rechecks candidates immediately before unlinking and uses directory file descriptors with no-follow flags.

Manifest output is refused if it resolves to the database, an artifact, or a path inside an artifact directory; it also refuses to overwrite the approved manifest. Apply mode requires `--approved-manifest` and `--confirm-writers-stopped`. The flag is an operator attestation, so the operator must actually stop every application/scheduler writer first. The script also holds a SQLite exclusive writer lock while validating and unlinking; it does not alter database rows.

Synthetic tests were run with:

```bash
python3 -m unittest discover -s backend/tests -p 'test_cleanup_artifacts.py' -v
```

All 6 tests passed. They verify retaining baselines/history, deleting only approved expired synthetic orphans, rejecting a changed same-size file, rejecting an out-of-bound path before any deletion, rejecting symlink files/directories, and protecting database/artifact/approved-manifest output paths and writer-stop attestation. These are synthetic fixtures; no real data was used for apply testing.

The current-workspace dry-run CSV is [artifact-cleanup-linux-dry-run.csv](artifact-cleanup-linux-dry-run.csv). The original [artifact-cleanup-dry-run.csv](artifact-cleanup-dry-run.csv) was left intact. Recreate the workspace inventory from the repository root with:

```bash
python3 backend/scripts/cleanup_artifacts.py \
  --retention-days 14 \
  --manifest plan/artifact-cleanup-linux-dry-run.csv
```

## Future maintenance procedure

These commands are for the deployment host, from the directory containing its verified `docker-compose.yml`. Confirm its resolved bind mount and database first; replace the sample backup destination with a protected path outside the data directory. Stop any other process writing to that database as well.

1. Stop the backend cleanly so the in-process scheduler drains and exits, then verify it is stopped:

   ```bash
   sudo docker compose stop backend
   sudo docker compose ps -a backend
   ```

2. Make an online SQLite backup with Python's backup API. This includes committed WAL contents without copying only the live database file. Keep the backup outside the mounted data directory:

   ```bash
   python3 - <<'PY'
   import sqlite3
   source = sqlite3.connect('file:backend/data/app.db?mode=ro', uri=True)
   backup = sqlite3.connect('/secure/backup/app-pre-cleanup.db')
   source.backup(backup)
   backup.close()
   source.close()
   PY
   ```

3. Verify the backup before maintenance. Keep the integrity and row-count output with the maintenance record:

   ```bash
   python3 - <<'PY'
   import sqlite3
   db = sqlite3.connect('file:/secure/backup/app-pre-cleanup.db?mode=ro', uri=True)
   print('integrity:', db.execute('PRAGMA integrity_check').fetchall())
   print('foreign keys:', db.execute('PRAGMA foreign_key_check').fetchall())
   for table in ('snapshots', 'check_results', 'check_attempts'):
       print(table, db.execute(f'SELECT count(*) FROM {table}').fetchone()[0])
   db.close()
   PY
   ```

4. If a separately reviewed manifest ever contains expired orphans, first produce and inspect a fresh dry run on the deployment host. Apply only after confirming the manifest against that same database and stopping all writers:

   ```bash
   python3 backend/scripts/cleanup_artifacts.py \
     --data-dir backend/data --database backend/data/app.db \
     --retention-days 14 --manifest plan/artifact-cleanup-linux-dry-run.csv
   # Review the manifest and confirm backup verification and stopped writers first.
   python3 backend/scripts/cleanup_artifacts.py \
     --data-dir backend/data --database backend/data/app.db \
     --retention-days 14 --apply-orphans \
     --approved-manifest plan/artifact-cleanup-linux-dry-run.csv \
     --confirm-writers-stopped
   ```

   The command is a template, not an instruction to apply this workspace manifest to production. This workspace manifest has zero orphan candidates and should not be applied. The manifest must come from the verified deployment data and database.

5. To restore after a failed maintenance, keep the backend stopped. Preserve the current `app.db`, `app.db-wal`, and `app.db-shm` together in a recovery directory; do not discard sidecars from a live database. Validate the backup first, then copy it to a temporary file in the database directory, set ownership and permissions to match the deployment, move the existing database and sidecars aside, and atomically rename the verified backup copy to `backend/data/app.db`. Keep all recovery copies until the restored service is verified. Restart and inspect:

   ```bash
   sudo docker compose up -d backend
   sudo docker compose ps backend
   sudo docker compose logs --tail=100 backend
   ```

   The container entrypoint runs `alembic upgrade head` at startup, so check migration state and backup before restart. After startup, repeat read-only integrity, foreign-key, table-count, and application health checks. Do not restore an old database while leaving later artifacts or database sidecars mixed with it; follow the recovery procedure for the verified deployment layout.

## Limitations and decision

The inventory, schema, and free-space figures above describe only this Linux workspace. The Docker daemon could not be queried and the documented SSH host key could not be validated, so live container state, remote Python version, production schema, production database path, and production artifact counts remain unverified. No service was stopped and no production command was run.

**Decision:** Apply mode is not ready for production because deployment state and backup are unverified. For the inspected local workspace, there is no orphan cleanup to perform: **0 files / 0 bytes**. Keep the evidence; if disk pressure requires reclamation, separately evaluate a reviewed retention archive/prune process that preserves required audit history and active baselines.
