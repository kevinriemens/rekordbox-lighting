"""Tests for the public working-copy write path: rbxlight.safety.working_copy_write.

Contract (rekordbox-lighting-architecture, "The Flow That Must Not Break" +
rekordbox-data-safety, "WORK ON A COPY, NOT ON LIVE"): the working copy is
disposable, never live data, so this path deliberately skips the two things
the live path (safety.write_transaction) always does — the rekordbox-running
guard and the pre-write backup. It still commits on success and rolls back +
re-raises on failure, same as the live path.

Every test resolves paths under tmp_path (via db.WORK_DIR monkeypatch) —
never the real working copy, never live.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import db, safety


@pytest.fixture
def fake_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.setattr(db, "WORK_DIR", work_dir)
    return work_dir


@pytest.fixture
def fake_lightingdb_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A live dir that must never be touched by this path — present only so
    a defect (accidentally resolving live) is observable."""
    live_dir = tmp_path / "LightingDB"
    live_dir.mkdir()
    monkeypatch.setattr(db, "LIGHTINGDB", live_dir)
    monkeypatch.setattr(safety, "LIGHTINGDB", live_dir)
    return live_dir


def _make_db_with_table(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()


class TestWorkingCopyWriteTransaction:
    def test_should_target_the_working_copy_path_not_live(
        self, fake_work_dir: Path, fake_lightingdb_dir: Path
    ) -> None:
        # Given: a working-copy macro.db3 and no matching live file
        _make_db_with_table(fake_work_dir / "macro.db3")

        # When: writing through the working-copy path
        with safety.working_copy_write("macro.db3") as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: the working copy has the row, live was never created/touched
        verify_conn = sqlite3.connect(fake_work_dir / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(1,)]
        assert not (fake_lightingdb_dir / "macro.db3").exists()

    def test_should_commit_on_success(self, fake_work_dir: Path) -> None:
        # Given: a working-copy db
        _make_db_with_table(fake_work_dir / "macro.db3")

        # When: the transaction completes without error
        with safety.working_copy_write("macro.db3") as conn:
            conn.execute("INSERT INTO t (id) VALUES (99)")

        # Then: durably committed
        verify_conn = sqlite3.connect(fake_work_dir / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(99,)]

    def test_should_roll_back_and_reraise_on_failure(self, fake_work_dir: Path) -> None:
        # Given: a working-copy db with known original content
        _make_db_with_table(fake_work_dir / "macro.db3")
        original_bytes = (fake_work_dir / "macro.db3").read_bytes()

        # When: the transaction body raises
        with (
            pytest.raises(RuntimeError, match="boom"),
            safety.working_copy_write("macro.db3") as conn,
        ):
            conn.execute("INSERT INTO t (id) VALUES (1)")
            raise RuntimeError("boom")

        # Then: byte-for-byte unchanged
        assert (fake_work_dir / "macro.db3").read_bytes() == original_bytes

    def test_should_not_check_whether_rekordbox_is_running(
        self,
        fake_work_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: guard_rekordbox_not_running would raise if called at all
        _make_db_with_table(fake_work_dir / "macro.db3")

        def _fail_if_called() -> None:
            raise AssertionError(
                "working-copy write path must never check rekordbox status"
            )

        monkeypatch.setattr(safety, "guard_rekordbox_not_running", _fail_if_called)

        # When / Then: the write succeeds without invoking the guard at all
        with safety.working_copy_write("macro.db3") as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

    def test_should_not_take_a_backup(
        self, fake_work_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a backup root that would receive a backup if one were taken
        backup_root = tmp_path / "backups"
        monkeypatch.setattr(safety, "BACKUP_ROOT", backup_root)
        _make_db_with_table(fake_work_dir / "macro.db3")

        # When: writing through the working-copy path
        with safety.working_copy_write("macro.db3") as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: no backup directory was ever created — the whole point of
        # this path is that it never touches live data, so there is nothing
        # to back up
        assert not backup_root.exists()
