#!/usr/bin/env python3
"""Dry-run-first inventory of expired screenshot, text, and HTML artifacts.

Only expired files with no matching Snapshot row are eligible for removal.
Snapshot artifacts (including baselines and check-history evidence) are always
retained. Database history pruning requires a separate maintenance procedure.

Examples, from the repository root:
    python3 backend/scripts/cleanup_artifacts.py --manifest plan/cleanup-dry-run.csv
    python3 backend/scripts/cleanup_artifacts.py --apply-orphans \
        --confirm-writers-stopped --approved-manifest plan/cleanup-dry-run.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
import sqlite3
import stat
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from urllib.parse import quote

ARTIFACT_DIRS = ("screenshots", "raw_screenshots", "text", "html")
MANIFEST_FIELDS = (
    "path",
    "relative_path",
    "mtime_utc",
    "mtime_ns",
    "age_days",
    "bytes",
    "snapshot_id",
    "disposition",
    "reason",
)
DISPOSITIONS = {
    "retain_baseline",
    "retain_check_history",
    "retain_snapshot_record",
    "delete_if_approved_orphan",
}


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_data = repo_root / "backend" / "data"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--database", type=Path, default=default_data / "app.db")
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--manifest", type=Path, help="Write a new dry-run manifest CSV")
    parser.add_argument(
        "--apply-orphans",
        action="store_true",
        help="Delete only approved expired orphan files; never deletes snapshot files",
    )
    parser.add_argument("--approved-manifest", type=Path)
    parser.add_argument(
        "--confirm-writers-stopped",
        action="store_true",
        help="Confirm all app/scheduler processes writing this database are stopped",
    )
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("--retention-days must be positive")
    if args.apply_orphans:
        if not args.approved_manifest:
            parser.error("--apply-orphans requires --approved-manifest")
        if not args.confirm_writers_stopped:
            parser.error("--apply-orphans requires --confirm-writers-stopped")
    elif args.approved_manifest or args.confirm_writers_stopped:
        parser.error("--approved-manifest and --confirm-writers-stopped require --apply-orphans")
    return args


def validate_data_root(path: Path) -> Path:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlink data directory: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise RuntimeError(f"Data path is not a directory: {resolved}")
    return resolved


def validate_artifact_dirs(data_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for name in ARTIFACT_DIRS:
        directory = data_root / name
        if not directory.exists() and not directory.is_symlink():
            continue
        if directory.is_symlink():
            raise RuntimeError(f"Refusing symlink artifact directory: {directory}")
        resolved = directory.resolve(strict=True)
        if not resolved.is_dir() or resolved.parent != data_root:
            raise RuntimeError(f"Invalid artifact directory boundary: {directory}")
        result[name] = resolved
    return result


def canonical_database(path: Path, data_root: Path) -> Path:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlink database path: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_file() or not resolved.is_relative_to(data_root):
        raise RuntimeError("Database must be an existing file inside --data-dir")
    return resolved


def assert_manifest_path_is_safe(
    path: Path,
    data_root: Path,
    database: Path,
    artifact_dirs: dict[str, Path],
    *,
    must_exist: bool,
) -> Path:
    if path.is_symlink():
        raise RuntimeError(f"Refusing symlink manifest path: {path}")
    if must_exist:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise RuntimeError(f"Manifest is not a regular file: {resolved}")
    else:
        parent = path.parent.resolve(strict=True)
        if not parent.is_dir():
            raise RuntimeError(f"Manifest parent is not a directory: {parent}")
        resolved = parent / path.name
    if resolved == database:
        raise RuntimeError("Manifest path cannot be the SQLite database")
    if any(resolved == directory or resolved.is_relative_to(directory) for directory in artifact_dirs.values()):
        raise RuntimeError("Manifest path cannot be inside an artifact directory")
    if not must_exist and resolved.exists() and not resolved.is_file():
        raise RuntimeError(f"Manifest output is not a regular file: {resolved}")
    return resolved


def database_uri(database: Path, mode: str) -> str:
    return f"file:{quote(database.as_posix(), safe='/')}?mode={mode}"


def open_database(database: Path, *, acquire_write_lock: bool) -> sqlite3.Connection:
    mode = "rw" if acquire_write_lock else "ro"
    connection = sqlite3.connect(
        database_uri(database, mode),
        uri=True,
        timeout=0 if acquire_write_lock else 5,
        isolation_level=None,
    )
    if acquire_write_lock:
        # In SQLite WAL mode this obtains the one-writer lock without changing
        # rows. It prevents database references changing during file deletion.
        connection.execute("BEGIN EXCLUSIVE")
    connection.execute("PRAGMA query_only=ON")
    return connection


def read_snapshot_refs(
    connection: sqlite3.Connection,
) -> tuple[set[str], set[str], set[str]]:
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"snapshots", "check_results", "check_attempts"}
    missing = required - tables
    if missing:
        raise RuntimeError(
            "Database schema is missing "
            + ", ".join(sorted(missing))
            + "; check schema state read-only and do not run migrations automatically"
        )

    snapshot_ids: set[str] = set()
    baseline_ids: set[str] = set()
    for snapshot_id, is_baseline in connection.execute(
        "SELECT id, is_baseline FROM snapshots"
    ):
        snapshot_ids.add(snapshot_id)
        if is_baseline:
            baseline_ids.add(snapshot_id)
    history_ids: set[str] = set()
    for baseline_id, current_id in connection.execute(
        "SELECT baseline_snapshot_id, current_snapshot_id FROM check_results"
    ):
        history_ids.update((baseline_id, current_id))
    history_ids.update(
        snapshot_id
        for (snapshot_id,) in connection.execute(
            "SELECT snapshot_id FROM check_attempts WHERE snapshot_id IS NOT NULL"
        )
    )
    return snapshot_ids, baseline_ids, history_ids


def classify(snapshot_id: str, snapshot_ids: set[str], baseline_ids: set[str], history_ids: set[str]) -> tuple[str, str]:
    if snapshot_id in baseline_ids:
        return "retain_baseline", "Active baseline; never eligible for deletion"
    if snapshot_id in history_ids:
        return "retain_check_history", "Referenced by a check result or check attempt"
    if snapshot_id in snapshot_ids:
        return "retain_snapshot_record", "Snapshot row remains available in snapshot history"
    return "delete_if_approved_orphan", "No matching Snapshot row; expired orphan only"


def regular_contained_file(path: Path, data_root: Path, allowed_dir: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"Cannot stat artifact: {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise RuntimeError(f"Refusing symlink artifact: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"Unexpected non-file in artifact directory: {path}")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(allowed_dir) or not resolved.is_relative_to(data_root):
        raise RuntimeError(f"Artifact path escapes data directory: {path}")
    return info


def collect_rows(
    data_root: Path,
    cutoff: datetime,
    artifact_dirs: dict[str, Path],
    snapshot_ids: set[str],
    baseline_ids: set[str],
    history_ids: set[str],
) -> tuple[list[dict[str, object]], int, int]:
    rows: list[dict[str, object]] = []
    orphan_files = 0
    orphan_bytes = 0
    now = datetime.now(UTC)
    for directory_name, allowed_dir in artifact_dirs.items():
        for path in sorted(allowed_dir.iterdir()):
            info = regular_contained_file(path, data_root, allowed_dir)
            mtime = datetime.fromtimestamp(info.st_mtime, UTC)
            if mtime >= cutoff:
                continue
            action, reason = classify(path.stem, snapshot_ids, baseline_ids, history_ids)
            if action == "delete_if_approved_orphan":
                orphan_files += 1
                orphan_bytes += info.st_size
            rows.append(
                {
                    "path": str(path.resolve(strict=True)),
                    "relative_path": f"{directory_name}/{path.name}",
                    "mtime_utc": mtime.isoformat(),
                    "mtime_ns": info.st_mtime_ns,
                    "age_days": round((now - mtime).total_seconds() / 86400, 2),
                    "bytes": info.st_size,
                    "snapshot_id": path.stem,
                    "disposition": action,
                    "reason": reason,
                }
            )
    return rows, orphan_files, orphan_bytes


def validate_manifest_paths(
    data_root: Path,
    database: Path,
    artifact_dirs: dict[str, Path],
    approved_manifest: Path,
    output_manifest: Path | None,
) -> None:
    if approved_manifest.is_symlink():
        raise RuntimeError(f"Refusing symlink approved manifest: {approved_manifest}")
    approved = approved_manifest.resolve(strict=True)
    if not approved.is_file():
        raise RuntimeError("Approved manifest is not a regular file")
    if approved == database or any(
        approved == directory or approved.is_relative_to(directory)
        for directory in artifact_dirs.values()
    ):
        raise RuntimeError("Approved manifest cannot be the database or an artifact")
    if output_manifest is not None:
        if output_manifest == approved:
            raise RuntimeError("--manifest cannot overwrite --approved-manifest")
        if output_manifest == database:
            raise RuntimeError("--manifest cannot overwrite the database")
        if any(
            output_manifest == directory or output_manifest.is_relative_to(directory)
            for directory in artifact_dirs.values()
        ):
            raise RuntimeError("--manifest cannot be inside an artifact directory")


def write_manifest(path: Path, rows: list[dict[str, object]]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=MANIFEST_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def validate_approved_manifest(
    manifest_path: Path,
    data_root: Path,
    cutoff: datetime,
    artifact_dirs: dict[str, Path],
    snapshot_ids: set[str],
    baseline_ids: set[str],
    history_ids: set[str],
) -> list[tuple[Path, int, int]]:
    """Validate every row before returning any eligible deletion candidates."""
    validated: list[tuple[Path, int, int]] = []
    seen: set[Path] = set()
    with manifest_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != MANIFEST_FIELDS:
            raise RuntimeError("Approved manifest has an unexpected or incomplete header")
        for line_number, row in enumerate(reader, start=2):
            try:
                if set(row) != set(MANIFEST_FIELDS) or any(value is None for value in row.values()):
                    raise RuntimeError("Manifest row has missing or extra columns")
                relative = PurePosixPath(row["relative_path"])
                if (
                    len(relative.parts) != 2
                    or relative.parts[0] not in artifact_dirs
                    or any(part in ("", ".", "..") for part in relative.parts)
                ):
                    raise RuntimeError("Manifest relative path is outside an allowed artifact directory")
                directory_name, filename = relative.parts
                expected = artifact_dirs[directory_name] / filename
                supplied = Path(row["path"])
                if not supplied.is_absolute() or supplied.resolve(strict=True) != expected.resolve(strict=True):
                    raise RuntimeError("Manifest absolute and relative paths do not match")
                if expected in seen:
                    raise RuntimeError("Manifest contains a duplicate path")
                seen.add(expected)
                info = regular_contained_file(expected, data_root, artifact_dirs[directory_name])
                if info.st_size != int(row["bytes"]):
                    raise RuntimeError("File size changed since manifest creation")
                if info.st_mtime_ns != int(row["mtime_ns"]):
                    raise RuntimeError("File modification time changed since manifest creation")
                mtime = datetime.fromtimestamp(info.st_mtime, UTC)
                if mtime >= cutoff:
                    raise RuntimeError("File is no longer outside the retention window")
                if row["snapshot_id"] != expected.stem:
                    raise RuntimeError("Manifest snapshot ID does not match its filename")
                expected_disposition, _ = classify(
                    expected.stem, snapshot_ids, baseline_ids, history_ids
                )
                if row["disposition"] not in DISPOSITIONS or row["disposition"] != expected_disposition:
                    raise RuntimeError("Manifest disposition no longer matches database references")
                if expected_disposition == "delete_if_approved_orphan":
                    validated.append((expected, info.st_size, info.st_mtime_ns))
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid manifest row {line_number}: {exc}") from exc
            except RuntimeError as exc:
                raise RuntimeError(f"Invalid manifest row {line_number}: {exc}") from exc
    return validated


def apply_approved_orphans(
    manifest_path: Path,
    data_root: Path,
    database: Path,
    cutoff: datetime,
    artifact_dirs: dict[str, Path],
    *,
    writers_stopped: bool,
) -> tuple[int, int]:
    if not writers_stopped:
        raise RuntimeError("Application/scheduler writers must be stopped before apply mode")

    connection = open_database(database, acquire_write_lock=True)
    try:
        snapshot_ids, baseline_ids, history_ids = read_snapshot_refs(connection)
        # This validates all manifest rows first. A bad row aborts before the
        # first unlink, including when a changed file keeps the same byte size.
        candidates = validate_approved_manifest(
            manifest_path,
            data_root,
            cutoff,
            artifact_dirs,
            snapshot_ids,
            baseline_ids,
            history_ids,
        )
        for path, expected_size, expected_mtime_ns in candidates:
            allowed_dir = artifact_dirs[path.parent.name]
            info = regular_contained_file(path, data_root, allowed_dir)
            if info.st_size != expected_size or info.st_mtime_ns != expected_mtime_ns:
                raise RuntimeError(f"File changed during apply validation: {path}")
        total_bytes = 0
        for path, expected_size, expected_mtime_ns in candidates:
            parent_fd = os.open(
                artifact_dirs[path.parent.name],
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            )
            try:
                info = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_size != expected_size
                    or info.st_mtime_ns != expected_mtime_ns
                ):
                    raise RuntimeError(f"File changed during apply: {path}")
                os.unlink(path.name, dir_fd=parent_fd)
                total_bytes += expected_size
            finally:
                os.close(parent_fd)
        return len(candidates), total_bytes
    finally:
        if connection.in_transaction:
            connection.rollback()
        connection.close()


def main() -> int:
    if sys.version_info < (3, 11):
        raise SystemExit("cleanup_artifacts requires Python 3.11 or newer")
    args = parse_args()
    data_root = validate_data_root(args.data_dir)
    artifact_dirs = validate_artifact_dirs(data_root)
    database = canonical_database(args.database, data_root)
    output_manifest = None
    if args.manifest:
        output_manifest = assert_manifest_path_is_safe(
            args.manifest,
            data_root,
            database,
            artifact_dirs,
            must_exist=False,
        )
    approved_manifest = None
    if args.approved_manifest:
        approved_manifest = args.approved_manifest
        validate_manifest_paths(
            data_root,
            database,
            artifact_dirs,
            approved_manifest,
            output_manifest,
        )
        approved_manifest = approved_manifest.resolve(strict=True)

    cutoff = datetime.now(UTC) - timedelta(days=args.retention_days)
    connection = open_database(database, acquire_write_lock=False)
    try:
        snapshot_ids, baseline_ids, history_ids = read_snapshot_refs(connection)
    finally:
        connection.close()
    rows, orphan_files, orphan_bytes = collect_rows(
        data_root, cutoff, artifact_dirs, snapshot_ids, baseline_ids, history_ids
    )

    if output_manifest is not None:
        write_manifest(output_manifest, rows)
        print(f"Manifest: {output_manifest}")
    print(f"Mode: {'APPLY APPROVED ORPHANS' if args.apply_orphans else 'DRY RUN'}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Data directory: {data_root}")
    print(f"Database: {database}")
    print(f"Cutoff UTC: {cutoff.isoformat()}")
    print(f"Snapshot rows: {len(snapshot_ids)}; active baselines: {len(baseline_ids)}")
    print(f"Expired artifact files inventoried: {len(rows)}")
    print(f"Safe orphan deletion candidates: {orphan_files} ({orphan_bytes} bytes)")
    print(f"Other expired files retained for snapshot/history: {len(rows) - orphan_files}")
    if args.apply_orphans:
        deleted, deleted_bytes = apply_approved_orphans(
            approved_manifest,
            data_root,
            database,
            cutoff,
            artifact_dirs,
            writers_stopped=args.confirm_writers_stopped,
        )
        print(f"Deleted approved orphan files: {deleted} ({deleted_bytes} bytes)")
    else:
        print("No files deleted. Snapshot files require coordinated database retention work.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, RuntimeError, csv.Error) as exc:
        print(f"cleanup_artifacts: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
