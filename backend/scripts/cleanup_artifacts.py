#!/usr/bin/env python3
"""Dry-run-first inventory of expired screenshot, text, and HTML artifacts.

Only expired files that have no matching Snapshot row are eligible for removal.
Snapshot artifacts (including baselines and check-history evidence) are always
retained by this script. A referenced-history retention policy needs a separate
database maintenance procedure and is deliberately out of scope here.

Examples, run from the repository root:
    python3 backend/scripts/cleanup_artifacts.py --manifest plan/artifact-cleanup-dry-run.csv
    python3 backend/scripts/cleanup_artifacts.py --apply-orphans \
        --approved-manifest plan/artifact-cleanup-dry-run.csv
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

ARTIFACT_DIRS = ("screenshots", "raw_screenshots", "text", "html")


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_data = repo_root / "backend" / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--database", type=Path, default=default_data / "app.db")
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--manifest", type=Path, help="Write the dry-run manifest CSV")
    parser.add_argument(
        "--apply-orphans",
        action="store_true",
        help="Delete only expired, unreferenced files listed in an approved manifest",
    )
    parser.add_argument("--approved-manifest", type=Path)
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("--retention-days must be positive")
    if args.apply_orphans and not args.approved_manifest:
        parser.error("--apply-orphans requires --approved-manifest")
    if args.approved_manifest and not args.apply_orphans:
        parser.error("--approved-manifest is only valid with --apply-orphans")
    return args


def read_snapshot_ids(database: Path) -> tuple[set[str], set[str], set[str]]:
    """Return snapshot ids, active baseline ids, and history-referenced ids."""
    database = database.resolve(strict=True)
    uri = f"file:{quote(database.as_posix(), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        ids: set[str] = set()
        baselines: set[str] = set()
        for snapshot_id, is_baseline in connection.execute(
            "SELECT id, is_baseline FROM snapshots"
        ):
            ids.add(snapshot_id)
            if is_baseline:
                baselines.add(snapshot_id)
        history: set[str] = set()
        for baseline_id, current_id in connection.execute(
            "SELECT baseline_snapshot_id, current_snapshot_id FROM check_results"
        ):
            history.update((baseline_id, current_id))
        history.update(
            snapshot_id
            for (snapshot_id,) in connection.execute(
                "SELECT snapshot_id FROM check_attempts WHERE snapshot_id IS NOT NULL"
            )
        )
        return ids, baselines, history
    finally:
        connection.close()


def contained_file(path: Path, data_root: Path, allowed_dir: Path) -> bool:
    """Reject symlinks and paths that resolve outside the approved data tree."""
    try:
        if path.is_symlink() or not path.is_file():
            return False
        resolved = path.resolve(strict=True)
        return resolved.is_relative_to(allowed_dir) and resolved.is_relative_to(data_root)
    except OSError:
        return False


def disposition(path: Path, snapshot_ids: set[str], baseline_ids: set[str], history_ids: set[str]) -> tuple[str, str]:
    snapshot_id = path.stem
    if snapshot_id in baseline_ids:
        return "retain_baseline", "Active baseline; never eligible for deletion"
    if snapshot_id in history_ids:
        return "retain_check_history", "Referenced by a check result or check attempt"
    if snapshot_id in snapshot_ids:
        return "retain_snapshot_record", "Snapshot row is still exposed in snapshot history"
    return "delete_if_approved_orphan", "No matching Snapshot row; expired orphan only"


def collect_rows(
    data_root: Path,
    cutoff: datetime,
    snapshot_ids: set[str],
    baseline_ids: set[str],
    history_ids: set[str],
) -> tuple[list[dict[str, object]], int, int]:
    rows: list[dict[str, object]] = []
    orphan_files = 0
    orphan_bytes = 0
    for directory_name in ARTIFACT_DIRS:
        allowed_dir = data_root / directory_name
        if not allowed_dir.is_dir():
            continue
        for path in sorted(allowed_dir.iterdir()):
            if not contained_file(path, data_root, allowed_dir):
                continue
            stat = path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, UTC)
            if mtime >= cutoff:
                continue
            action, reason = disposition(path, snapshot_ids, baseline_ids, history_ids)
            if action == "delete_if_approved_orphan":
                orphan_files += 1
                orphan_bytes += stat.st_size
            rows.append(
                {
                    "path": str(path.resolve()),
                    "relative_path": str(path.relative_to(data_root)),
                    "mtime_utc": mtime.isoformat(),
                    "age_days": round((datetime.now(UTC) - mtime).total_seconds() / 86400, 2),
                    "bytes": stat.st_size,
                    "snapshot_id": path.stem,
                    "disposition": action,
                    "reason": reason,
                }
            )
    return rows, orphan_files, orphan_bytes


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "path",
        "relative_path",
        "mtime_utc",
        "age_days",
        "bytes",
        "snapshot_id",
        "disposition",
        "reason",
    )
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def delete_approved_orphans(
    manifest_path: Path,
    data_root: Path,
    cutoff: datetime,
    snapshot_ids: set[str],
    baseline_ids: set[str],
    history_ids: set[str],
) -> int:
    deleted = 0
    with manifest_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row.get("disposition") != "delete_if_approved_orphan":
                continue
            path = Path(row["path"])
            if not path.is_absolute() or not path.exists():
                continue
            allowed_dir = data_root / path.parent.name
            if allowed_dir.name not in ARTIFACT_DIRS or not contained_file(path, data_root, allowed_dir):
                raise RuntimeError(f"Refusing path outside approved artifact directories: {path}")
            if path.stem in snapshot_ids or path.stem in baseline_ids or path.stem in history_ids:
                raise RuntimeError(f"Refusing file that became database-referenced: {path}")
            stat = path.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, UTC)
            if mtime >= cutoff or stat.st_size != int(row["bytes"]):
                raise RuntimeError(f"File changed since manifest approval; refusing: {path}")
            path.unlink()
            deleted += 1
    return deleted


def main() -> int:
    args = parse_args()
    data_root = args.data_dir.resolve(strict=True)
    database = args.database.resolve(strict=True)
    if not database.is_relative_to(data_root):
        raise SystemExit("Refusing: database must be within --data-dir")
    cutoff = datetime.now(UTC) - timedelta(days=args.retention_days)
    snapshot_ids, baseline_ids, history_ids = read_snapshot_ids(database)
    rows, orphan_files, orphan_bytes = collect_rows(
        data_root, cutoff, snapshot_ids, baseline_ids, history_ids
    )

    if args.manifest:
        write_manifest(args.manifest, rows)
        print(f"Manifest: {args.manifest.resolve()}")
    print(f"Mode: {'APPLY APPROVED ORPHANS' if args.apply_orphans else 'DRY RUN'}")
    print(f"Cutoff UTC: {cutoff.isoformat()}")
    print(f"Snapshot rows: {len(snapshot_ids)}; active baselines: {len(baseline_ids)}")
    print(f"Expired artifact files inventoried: {len(rows)}")
    print(f"Safe orphan deletion candidates: {orphan_files} ({orphan_bytes} bytes)")
    print(f"Other expired files retained for snapshot/history: {len(rows) - orphan_files}")
    if args.apply_orphans:
        deleted = delete_approved_orphans(
            args.approved_manifest,
            data_root,
            cutoff,
            snapshot_ids,
            baseline_ids,
            history_ids,
        )
        print(f"Deleted approved orphan files: {deleted}")
    else:
        print("No files deleted. Snapshot files require coordinated database retention work.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        print(f"cleanup_artifacts: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
