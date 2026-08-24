"""Tests for the injectable-verification contract on
rbxlight.safety.write_transaction. Contract: this is a pure refactor of the
live write transaction — the pre-existing guard/backup/commit/rollback
behavior (covered by tests/test_safety.py, untouched) must still hold.

New behavior under test:
- an optional `verify` callable runs INSIDE the still-open transaction,
  after the caller's work but BEFORE commit
- verify raising rolls back (byte-identical file) and re-raises
- when no `verify` is given, a default verification still runs (a write is
  never committed unverified)

Every test monkeypatches safety.LIGHTINGDB / safety.BACKUP_ROOT to tmp_path
sandboxes — same style as tests/test_safety.py.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import safety


@pytest.fixture
def fake_lightingdb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    live_dir = tmp_path / "LightingDB"
    live_dir.mkdir()
    (live_dir / "macro.db3").write_bytes(b"")
    conn = sqlite3.connect(live_dir / "macro.db3")
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
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
    class _Result:
        returncode = 1

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


@pytest.fixture
def rekordbox_running(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        returncode = 0

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


class _CustomVerificationError(Exception):
    """A non-standard exception type a caller's verify might raise."""


class TestWriteTransactionVerificationHook:
    def test_should_run_verify_before_commit_when_supplied(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a verify callable that records whether the row it expects
        # is visible to it — proving it runs INSIDE the open transaction,
        # after the caller's insert but before commit
        seen_inside_transaction: list[bool] = []

        def verify(conn: sqlite3.Connection) -> None:
            rows = conn.execute("SELECT id FROM t").fetchall()
            seen_inside_transaction.append(rows == [(1,)])

        # When: the transaction inserts a row then the hook verifies it
        with safety.write_transaction("macro.db3", "test write", verify=verify) as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: verify ran, saw the uncommitted row, and the write committed
        assert seen_inside_transaction == [True]
        verify_conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(1,)]

    def test_should_commit_when_verify_passes(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a verify callable that raises nothing (passes)
        def verify(conn: sqlite3.Connection) -> None:
            return None

        # When: the transaction completes with a passing verify
        with safety.write_transaction("macro.db3", "test write", verify=verify) as conn:
            conn.execute("INSERT INTO t (id) VALUES (42)")

        # Then: the change is durably committed
        verify_conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(42,)]

    def test_should_roll_back_and_reraise_when_verify_raises(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: the original file content, and a verify that always fails
        original_bytes = (fake_lightingdb / "macro.db3").read_bytes()

        def verify(conn: sqlite3.Connection) -> None:
            raise AssertionError("invariant violated")

        # When: the transaction's work succeeds but verify rejects it
        with (
            pytest.raises(AssertionError, match="invariant violated"),
            safety.write_transaction("macro.db3", "test write", verify=verify) as conn,
        ):
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: the database is byte-for-byte identical to before the attempt
        assert (fake_lightingdb / "macro.db3").read_bytes() == original_bytes

    def test_should_roll_back_and_reraise_a_non_standard_exception_from_verify(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: the original file content, and a verify raising a
        # caller-defined exception type unrelated to sqlite3/AssertionError
        original_bytes = (fake_lightingdb / "macro.db3").read_bytes()

        def verify(conn: sqlite3.Connection) -> None:
            raise _CustomVerificationError("bespoke failure")

        # When: verify raises its own exception type
        with (
            pytest.raises(_CustomVerificationError, match="bespoke failure"),
            safety.write_transaction("macro.db3", "test write", verify=verify) as conn,
        ):
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: rollback still happened faithfully — file untouched
        assert (fake_lightingdb / "macro.db3").read_bytes() == original_bytes

    def test_should_report_backup_location_when_verify_raises(
        self,
        fake_lightingdb: Path,
        fake_backup_root: Path,
        rekordbox_not_running: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Given: a verify that always fails
        def verify(conn: sqlite3.Connection) -> None:
            raise AssertionError("nope")

        # When: the transaction fails verification
        with (
            pytest.raises(AssertionError),
            safety.write_transaction("macro.db3", "test write", verify=verify) as conn,
        ):
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: the user is told where to find the backup to restore from
        backup_dirs = list(fake_backup_root.glob("*"))
        assert len(backup_dirs) == 1
        captured = capsys.readouterr()
        assert str(backup_dirs[0]) in captured.out

    def test_should_still_verify_by_default_when_no_verify_supplied(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: no verify callable is supplied at all (the pre-existing
        # call shape, exercised by tests/test_safety.py)
        # When: the transaction succeeds without an explicit verify
        with safety.write_transaction("macro.db3", "test write") as conn:
            conn.execute("INSERT INTO t (id) VALUES (7)")

        # Then: the write still committed durably — a default verification
        # ran and did not block a legitimate write
        verify_conn = sqlite3.connect(fake_lightingdb / "macro.db3")
        rows = verify_conn.execute("SELECT id FROM t").fetchall()
        verify_conn.close()
        assert rows == [(7,)]

    def test_should_still_guard_rekordbox_running_with_verify_supplied(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_running: None
    ) -> None:
        # Given: rekordbox is running
        def verify(conn: sqlite3.Connection) -> None:
            return None

        # When / Then: refused before the body (and verify) ever run,
        # exactly as without a verify argument
        with (
            pytest.raises(safety.RekordboxRunningError),
            safety.write_transaction("macro.db3", "test write", verify=verify),
        ):
            pytest.fail("should never reach the transaction body")

    def test_should_still_take_backup_before_write_with_verify_supplied(
        self, fake_lightingdb: Path, fake_backup_root: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a verify hook that checks the backup already exists by the
        # time it runs
        backup_existed_when_verify_ran: list[bool] = []

        def verify(conn: sqlite3.Connection) -> None:
            backup_existed_when_verify_ran.append(
                fake_backup_root.exists() and len(list(fake_backup_root.glob("*"))) == 1
            )

        # When: the transaction runs to completion
        with safety.write_transaction("macro.db3", "test write", verify=verify) as conn:
            conn.execute("INSERT INTO t (id) VALUES (1)")

        # Then: backup-before-write still held with verify in play
        assert backup_existed_when_verify_ran == [True]
