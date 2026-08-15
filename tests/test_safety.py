"""Tests for rbxlight.safety — backup, restore, process guard, write
transaction. Contract: rekordbox-data-safety skill (NON-NEGOTIABLE RULES).

Every test monkeypatches safety.LIGHTINGDB / safety.BACKUP_ROOT to tmp_path
sandboxes — none of this ever touches the real rekordbox app-support dir.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rbxlight import safety
from rbxlight.safety import (
    BackupCorruptedError,
    RekordboxRunningError,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_lightingdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake LightingDB dir with macro.db3/user.db3/master.db3 dummy
    content, wired up as safety's module-level LIGHTINGDB."""
    live_dir = tmp_path / "LightingDB"
    live_dir.mkdir()
    (live_dir / "macro.db3").write_bytes(b"macro-content-v1")
    (live_dir / "user.db3").write_bytes(b"user-content-v1")
    (live_dir / "master.db3").write_bytes(b"master-content-huge-readonly")
    monkeypatch.setattr(safety, "LIGHTINGDB", live_dir)
    return live_dir


@pytest.fixture
def fake_backup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(safety, "BACKUP_ROOT", backup_root)
    return backup_root


@pytest.fixture
def rekordbox_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """pgrep finds nothing (returncode 1 == not running)."""

    class _Result:
        returncode = 1

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


@pytest.fixture
def rekordbox_running(monkeypatch: pytest.MonkeyPatch) -> None:
    """pgrep finds the process (returncode 0 == running)."""

    class _Result:
        returncode = 0

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


class TestGuardRekordboxNotRunning:
    def test_should_raise_when_rekordbox_is_running(
        self, rekordbox_running: None
    ) -> None:
        # Given: pgrep reports rekordbox is running
        # When / Then: the guard refuses
        with pytest.raises(RekordboxRunningError):
            safety.guard_rekordbox_not_running()

    def test_should_not_raise_when_rekordbox_is_not_running(
        self, rekordbox_not_running: None
    ) -> None:
        # Given: pgrep reports rekordbox is not running
        # When / Then: the guard passes silently
        safety.guard_rekordbox_not_running()


class TestBackupAll:
    def test_should_copy_macro_and_user_db_into_timestamped_dir(
        self, fake_lightingdb: Path, fake_backup_root: Path
    ) -> None:
        # Given: a fake live LightingDB directory
        # When: a backup is taken
        backup_dir = safety.backup_all("test trigger")

        # Then: macro.db3 and user.db3 are copied byte-for-byte
        assert (backup_dir / "macro.db3").read_bytes() == b"macro-content-v1"
        assert (backup_dir / "user.db3").read_bytes() == b"user-content-v1"

    def test_should_never_copy_master_db_wholesale(
        self, fake_lightingdb: Path, fake_backup_root: Path
    ) -> None:
        # Given: a fake live LightingDB directory including master.db3
        # When: a backup is taken
        backup_dir = safety.backup_all("test trigger")

        # Then: the 512MB read-only factory library is never duplicated
        assert not (backup_dir / "master.db3").exists()

    def test_should_write_manifest_with_timestamp_trigger_and_per_file_hash_and_size(
        self, fake_lightingdb: Path, fake_backup_root: Path
    ) -> None:
        # Given: a fake live LightingDB directory
        trigger = "rbxlight macro create --write --name 'HIGH DROP1'"

        # When: a backup is taken
        backup_dir = safety.backup_all(trigger)
        manifest = json.loads((backup_dir / "manifest.json").read_text())

        # Then: manifest records when, why, and per-file origin/size/hash
        assert manifest["trigger_command"] == trigger
        assert manifest.get("timestamp")

        macro_entry = manifest["files"]["macro.db3"]
        assert macro_entry["bytes"] == len(b"macro-content-v1")
        assert macro_entry["sha256"] == _sha256(fake_lightingdb / "macro.db3")
        assert macro_entry["source"] == str(fake_lightingdb / "macro.db3")

        user_entry = manifest["files"]["user.db3"]
        assert user_entry["bytes"] == len(b"user-content-v1")
        assert user_entry["sha256"] == _sha256(fake_lightingdb / "user.db3")

    def test_should_create_a_new_timestamped_dir_on_each_call(
        self, fake_lightingdb: Path, fake_backup_root: Path
    ) -> None:
        # Given: a fake live LightingDB directory
        # When: two backups are taken back to back
        first = safety.backup_all("trigger 1")
        second = safety.backup_all("trigger 2")

        # Then: each gets its own directory
        assert first != second
        assert first.exists() and second.exists()


class TestRestoreFromBackup:
    """Restore capability must be provable independently of any write
    feature — these tests never call write_transaction."""

    def test_should_restore_live_files_to_exactly_the_backed_up_state(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a backup of the original live state
        backup_dir = safety.backup_all("pre-change backup")

        # And: live files have since changed
        (fake_lightingdb / "macro.db3").write_bytes(b"CORRUPTED-OR-CHANGED")
        (fake_lightingdb / "user.db3").write_bytes(b"CORRUPTED-OR-CHANGED-TOO")

        # When: restoring from that backup
        safety.restore_from_backup(backup_dir)

        # Then: live files are back to exactly the captured state,
        # verified by content hash
        assert (fake_lightingdb / "macro.db3").read_bytes() == b"macro-content-v1"
        assert (fake_lightingdb / "user.db3").read_bytes() == b"user-content-v1"
        assert _sha256(fake_lightingdb / "macro.db3") == _sha256(
            backup_dir / "macro.db3"
        )

    def test_should_raise_when_rekordbox_is_running(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_running: None
    ) -> None:
        # Given: rekordbox is running (restore must guard exactly like write does)
        # When / Then: restore refuses before touching any file
        with pytest.raises(RekordboxRunningError):
            safety.restore_from_backup(fake_backup_root / "does-not-matter")

    def test_should_raise_backup_corrupted_error_when_hash_mismatches_manifest(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a backup that has since been tampered with on disk
        backup_dir = safety.backup_all("pre-tamper backup")
        (backup_dir / "macro.db3").write_bytes(b"TAMPERED-BACKUP-CONTENT")

        # When / Then: restore refuses rather than trusting a corrupt backup
        with pytest.raises(BackupCorruptedError):
            safety.restore_from_backup(backup_dir)

        # And: live files are untouched by the refused restore
        assert (fake_lightingdb / "macro.db3").read_bytes() == b"macro-content-v1"


class TestWriteTransaction:
    def test_should_refuse_when_rekordbox_is_running(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_running: None
    ) -> None:
        # Given: rekordbox is running
        backups_before = (
            list(fake_backup_root.glob("*")) if fake_backup_root.exists() else []
        )

        # When / Then: the write is refused before any backup is taken
        with (
            pytest.raises(RekordboxRunningError),
            safety.write_transaction("macro.db3", "test write"),
        ):
            pytest.fail("should never reach the transaction body")

        backups_after = (
            list(fake_backup_root.glob("*")) if fake_backup_root.exists() else []
        )
        assert backups_after == backups_before

    def test_should_take_a_backup_before_yielding_the_connection(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: rekordbox is not running
        # When: a write transaction is opened
        with safety.write_transaction("macro.db3", "test write") as conn:
            # Then: a backup already exists by the time the body runs
            assert fake_backup_root.exists()
            assert len(list(fake_backup_root.glob("*"))) == 1
            assert isinstance(conn, sqlite3.Connection)

    def test_should_leave_db_byte_for_byte_unchanged_when_write_fails(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: an actual (throwaway) SQLite file as macro.db3, so the
        # deliberate failure below is the only error in play
        (fake_lightingdb / "macro.db3").write_bytes(b"")
        conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()
        original_bytes = (fake_lightingdb / "macro.db3").read_bytes()

        # When: a write transaction raises partway through
        with (
            pytest.raises(RuntimeError, match="boom"),
            safety.write_transaction("macro.db3", "test write") as conn,
        ):
            conn.execute("CREATE TABLE whatever (id INTEGER)")
            raise RuntimeError("boom")

        # Then: the target database is byte-for-byte identical to before
        assert (fake_lightingdb / "macro.db3").read_bytes() == original_bytes

    def test_should_commit_changes_when_write_succeeds(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: an actual (throwaway) SQLite file as macro.db3
        (fake_lightingdb / "macro.db3").write_bytes(b"")
        conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.commit()
        conn.close()

        # When: a write transaction commits successfully
        with safety.write_transaction("macro.db3", "test write") as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: the change is durably committed
        verify_conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(1,)]


class TestAssert25Rows:
    @pytest.fixture
    def conn(self, tmp_path: Path):
        db_path = tmp_path / "macro.db3"
        c = sqlite3.connect(db_path)
        c.executescript(
            "CREATE TABLE macro_data (id INTEGER PRIMARY KEY, macro_id INTEGER, "
            "macro_fixture_id INTEGER, data TEXT);"
        )
        yield c
        c.close()

    def test_should_not_raise_when_macro_has_exactly_25_rows_with_no_nulls(
        self, conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with exactly one row per expected slot, all data=""
        for slot_id in safety.EXPECTED_FIXTURE_SLOT_IDS:
            conn.execute(
                "INSERT INTO macro_data (macro_id, macro_fixture_id, data) VALUES (1, ?, '')",
                (slot_id,),
            )
        conn.commit()

        # When / Then: assertion passes
        safety.assert_25_rows(conn, macro_id=1)

    def test_should_raise_when_a_slot_is_missing(
        self, conn: sqlite3.Connection
    ) -> None:
        # Given: only 24 of the 25 expected slots
        missing_slot = next(iter(safety.EXPECTED_FIXTURE_SLOT_IDS))
        for slot_id in safety.EXPECTED_FIXTURE_SLOT_IDS:
            if slot_id == missing_slot:
                continue
            conn.execute(
                "INSERT INTO macro_data (macro_id, macro_fixture_id, data) VALUES (1, ?, '')",
                (slot_id,),
            )
        conn.commit()

        # When / Then: assertion fails, naming what's missing
        with pytest.raises(AssertionError, match=str(missing_slot)):
            safety.assert_25_rows(conn, macro_id=1)

    def test_should_raise_when_a_row_has_null_data(
        self, conn: sqlite3.Connection
    ) -> None:
        # Given: 25 rows, one with NULL data instead of ""
        for slot_id in safety.EXPECTED_FIXTURE_SLOT_IDS:
            conn.execute(
                "INSERT INTO macro_data (macro_id, macro_fixture_id, data) VALUES (1, ?, ?)",
                (slot_id, None),
            )
        conn.commit()

        # When / Then: assertion fails
        with pytest.raises(AssertionError):
            safety.assert_25_rows(conn, macro_id=1)
