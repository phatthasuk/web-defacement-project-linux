import csv
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cleanup_artifacts as cleanup  # noqa: E402


class CleanupArtifactsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.tmp_path = Path(self.temporary.name)
        self.data = self.tmp_path / "data"
        for name in cleanup.ARTIFACT_DIRS:
            (self.data / name).mkdir(parents=True)
        self.database = self.data / "app.db"
        connection = sqlite3.connect(self.database)
        connection.executescript(
            """
            CREATE TABLE snapshots (id TEXT PRIMARY KEY, is_baseline INTEGER NOT NULL);
            CREATE TABLE check_results (
                baseline_snapshot_id TEXT NOT NULL,
                current_snapshot_id TEXT NOT NULL
            );
            CREATE TABLE check_attempts (snapshot_id TEXT);
            INSERT INTO snapshots VALUES ('baseline-id', 1);
            INSERT INTO snapshots VALUES ('history-id', 0);
            INSERT INTO check_results VALUES ('baseline-id', 'history-id');
            """
        )
        connection.commit()
        connection.close()
        old_ns = int((datetime.now(UTC) - timedelta(days=20)).timestamp() * 1_000_000_000)
        for name in ("baseline-id.png", "history-id.png", "a-orphan.png", "z-orphan.png"):
            path = self.data / "screenshots" / name
            path.write_bytes(b"synthetic-data")
            os.utime(path, ns=(old_ns, old_ns))

    def build_manifest(self) -> tuple[Path, datetime]:
        manifest = self.tmp_path / "approved.csv"
        root = cleanup.validate_data_root(self.data)
        directories = cleanup.validate_artifact_dirs(root)
        connection = cleanup.open_database(self.database, acquire_write_lock=False)
        try:
            ids, baselines, history = cleanup.read_snapshot_refs(connection)
        finally:
            connection.close()
        cutoff = datetime.now(UTC) - timedelta(days=14)
        rows, _, _ = cleanup.collect_rows(root, cutoff, directories, ids, baselines, history)
        cleanup.write_manifest(manifest, rows)
        return manifest, cutoff

    def apply(self, manifest: Path, cutoff: datetime) -> tuple[int, int]:
        root = cleanup.validate_data_root(self.data)
        return cleanup.apply_approved_orphans(
            manifest,
            root,
            self.database,
            cutoff,
            cleanup.validate_artifact_dirs(root),
            writers_stopped=True,
        )

    def test_deletes_only_approved_expired_orphans_and_keeps_history(self) -> None:
        manifest, cutoff = self.build_manifest()
        deleted, deleted_bytes = self.apply(manifest, cutoff)

        self.assertEqual(deleted, 2)
        self.assertEqual(deleted_bytes, len(b"synthetic-data") * 2)
        self.assertFalse((self.data / "screenshots" / "a-orphan.png").exists())
        self.assertFalse((self.data / "screenshots" / "z-orphan.png").exists())
        self.assertTrue((self.data / "screenshots" / "baseline-id.png").exists())
        self.assertTrue((self.data / "screenshots" / "history-id.png").exists())

    def test_same_size_file_with_changed_mtime_aborts_before_any_delete(self) -> None:
        manifest, cutoff = self.build_manifest()
        changed = self.data / "screenshots" / "z-orphan.png"
        changed.write_bytes(b"different-data")
        old_ns = int((datetime.now(UTC) - timedelta(days=19)).timestamp() * 1_000_000_000)
        os.utime(changed, ns=(old_ns, old_ns))

        with self.assertRaisesRegex(RuntimeError, "modification time changed"):
            self.apply(manifest, cutoff)

        self.assertTrue((self.data / "screenshots" / "a-orphan.png").exists())
        self.assertTrue(changed.exists())

    def test_outside_path_in_manifest_aborts_before_any_delete(self) -> None:
        manifest, cutoff = self.build_manifest()
        outside = self.tmp_path / "outside.png"
        outside.write_bytes(b"synthetic-data")
        with manifest.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row["disposition"] == "delete_if_approved_orphan":
                row["path"] = str(outside)
                row["relative_path"] = "screenshots/../../outside.png"
                break
        with manifest.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=cleanup.MANIFEST_FIELDS,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)

        with self.assertRaisesRegex(RuntimeError, "outside an allowed artifact directory"):
            self.apply(manifest, cutoff)

        self.assertTrue((self.data / "screenshots" / "a-orphan.png").exists())
        self.assertTrue(outside.exists())

    def test_artifact_symlink_file_and_directory_are_rejected(self) -> None:
        outside = self.tmp_path / "outside.png"
        outside.write_bytes(b"outside")
        (self.data / "screenshots" / "link.png").symlink_to(outside)
        root = cleanup.validate_data_root(self.data)
        directories = cleanup.validate_artifact_dirs(root)

        with self.assertRaisesRegex(RuntimeError, "symlink artifact"):
            cleanup.collect_rows(
                root,
                datetime.now(UTC),
                directories,
                set(),
                set(),
                set(),
            )

        shutil.rmtree(self.data / "screenshots")
        (self.data / "screenshots").symlink_to(self.tmp_path, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink artifact directory"):
            cleanup.validate_artifact_dirs(root)

    def test_manifest_output_cannot_replace_database_or_artifact(self) -> None:
        root = cleanup.validate_data_root(self.data)
        directories = cleanup.validate_artifact_dirs(root)
        with self.assertRaisesRegex(RuntimeError, "database"):
            cleanup.assert_manifest_path_is_safe(
                self.database, root, self.database, directories, must_exist=False
            )
        with self.assertRaisesRegex(RuntimeError, "artifact directory"):
            cleanup.assert_manifest_path_is_safe(
                self.data / "screenshots" / "manifest.csv",
                root,
                self.database,
                directories,
                must_exist=False,
            )
        approved = self.tmp_path / "approved.csv"
        approved.write_text("approved", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "cannot overwrite"):
            cleanup.validate_manifest_paths(root, self.database, directories, approved, approved)

    def test_apply_requires_writer_stop_confirmation(self) -> None:
        manifest, cutoff = self.build_manifest()
        root = cleanup.validate_data_root(self.data)
        with self.assertRaisesRegex(RuntimeError, "writers must be stopped"):
            cleanup.apply_approved_orphans(
                manifest,
                root,
                self.database,
                cutoff,
                cleanup.validate_artifact_dirs(root),
                writers_stopped=False,
            )


if __name__ == "__main__":
    unittest.main()
