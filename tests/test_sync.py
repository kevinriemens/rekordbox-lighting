"""Tests for rbxlight.sync — pull (live -> work/), push (work/ -> live),
staleness protection. Contract: rekordbox-data-safety skill ("Working copy
model") and rekordbox-lighting-architecture skill ("The Flow That Must Not
Break").
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from rbxlight import safety, sync
from rbxlight.sync import StaleWorkingCopyError


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


@pytest.fixture
def live_dir(tmp_path: Path) -> Path:
    live = tmp_path / "LightingDB"
    live.mkdir()
    (live / "macro.db3").write_bytes(b"macro-live-v1")
    (live / "user.db3").write_bytes(b"user-live-v1")
    (live / "master.db3").write_bytes(b"master-huge-readonly")
    return live


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    return work


@pytest.fixture
def backup_root(tmp_path: Path) -> Path:
    return tmp_path / "backups"


class TestPull:
    def test_should_copy_macro_and_user_db_into_work_dir(
        self, live_dir: Path, work_dir: Path, rekordbox_not_running: None
    ) -> None:
        # Given: a live LightingDB directory and an empty working area
        # When: pulling
        sync.pull(live_dir, work_dir)

        # Then: macro.db3 and user.db3 are copied byte-for-byte into work_dir
        assert (work_dir / "macro.db3").read_bytes() == b"macro-live-v1"
        assert (work_dir / "user.db3").read_bytes() == b"user-live-v1"

    def test_should_never_copy_master_db_into_work_dir(
        self, live_dir: Path, work_dir: Path, rekordbox_not_running: None
    ) -> None:
        # Given/When: pulling
        sync.pull(live_dir, work_dir)

        # Then: the large factory-library database is never in the working area
        assert not (work_dir / "master.db3").exists()

    def test_should_record_live_file_hash_at_pull_time(
        self, live_dir: Path, work_dir: Path, rekordbox_not_running: None
    ) -> None:
        # Given: known live file content
        expected_macro_hash = _sha256(live_dir / "macro.db3")
        expected_user_hash = _sha256(live_dir / "user.db3")

        # When: pulling
        pull_state_path = sync.pull(live_dir, work_dir)
        state = json.loads(pull_state_path.read_text())

        # Then: the pull-state records each file's hash at that moment
        assert state["sha256"]["macro.db3"] == expected_macro_hash
        assert state["sha256"]["user.db3"] == expected_user_hash

    def test_should_refuse_when_rekordbox_is_running(
        self, live_dir: Path, work_dir: Path, rekordbox_running: None
    ) -> None:
        # Given: rekordbox is running
        # When / Then: pull is refused
        with pytest.raises(safety.RekordboxRunningError):
            sync.pull(live_dir, work_dir)

        # And: nothing was copied
        assert not work_dir.exists() or not (work_dir / "macro.db3").exists()


class TestPushStaleness:
    def test_should_refuse_when_live_file_changed_since_pull(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pull, then the live file drifting (rekordbox or the user
        # touched it) before push
        sync.pull(live_dir, work_dir)
        (live_dir / "macro.db3").write_bytes(b"macro-live-v2-drifted")

        # When / Then: push refuses, naming the drifted file — a hard stop
        with pytest.raises(StaleWorkingCopyError, match="macro.db3"):
            sync.push(live_dir, work_dir, backup_root, "test push")

        # And: live is untouched by the refused push
        assert (live_dir / "macro.db3").read_bytes() == b"macro-live-v2-drifted"

    def test_should_not_take_a_backup_when_refusing_a_stale_push(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a stale working copy
        sync.pull(live_dir, work_dir)
        (live_dir / "user.db3").write_bytes(b"user-live-v2-drifted")

        # When: push is attempted and refused
        with pytest.raises(StaleWorkingCopyError):
            sync.push(live_dir, work_dir, backup_root, "test push")

        # Then: no backup was taken for a refused push
        assert not backup_root.exists() or list(backup_root.glob("*")) == []

    def test_should_succeed_when_live_file_unchanged_since_pull(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pull with no drift, and a local change in the working copy
        sync.pull(live_dir, work_dir)
        (work_dir / "macro.db3").write_bytes(b"macro-edited-locally")

        # When: pushing
        sync.push(live_dir, work_dir, backup_root, "test push")

        # Then: live reflects the working copy's change
        assert (live_dir / "macro.db3").read_bytes() == b"macro-edited-locally"


class TestPushForce:
    def test_should_bypass_staleness_check_when_forced(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a drifted live file after pull
        sync.pull(live_dir, work_dir)
        (live_dir / "macro.db3").write_bytes(b"macro-live-v2-drifted")
        (work_dir / "macro.db3").write_bytes(b"macro-edited-locally")

        # When: pushing with force=True
        sync.push(live_dir, work_dir, backup_root, "forced push", force=True)

        # Then: the push proceeds despite the drift
        assert (live_dir / "macro.db3").read_bytes() == b"macro-edited-locally"

    def test_should_still_take_a_backup_when_forced(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a drifted live file after pull
        sync.pull(live_dir, work_dir)
        (live_dir / "macro.db3").write_bytes(b"macro-live-v2-drifted")

        # When: forcing the push
        sync.push(live_dir, work_dir, backup_root, "forced push", force=True)

        # Then: a backup of LIVE was still taken before overwriting
        assert backup_root.exists()
        backup_dirs = list(backup_root.glob("*"))
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / "macro.db3").read_bytes() == b"macro-live-v2-drifted"


class TestPushBacksUpLiveNotWorkingCopy:
    def test_should_back_up_the_live_databases_not_the_working_copy(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pull, then a working-copy edit that differs from live
        sync.pull(live_dir, work_dir)
        (work_dir / "macro.db3").write_bytes(b"macro-edited-locally")

        # When: pushing
        sync.push(live_dir, work_dir, backup_root, "test push")

        # Then: the backup captured what was on LIVE before the push, not
        # the (different) working-copy content
        backup_dirs = list(backup_root.glob("*"))
        assert len(backup_dirs) == 1
        assert (backup_dirs[0] / "macro.db3").read_bytes() == b"macro-live-v1"

    def test_should_refuse_push_when_rekordbox_is_running(
        self,
        live_dir: Path,
        work_dir: Path,
        backup_root: Path,
        rekordbox_not_running: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a successful pull, then rekordbox starts running before push
        sync.pull(live_dir, work_dir)

        class _Result:
            returncode = 0

        monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())

        # When / Then: push is refused
        with pytest.raises(safety.RekordboxRunningError):
            sync.push(live_dir, work_dir, backup_root, "test push")


class TestResolvePathDefaultsToWorkingCopy:
    def test_should_resolve_to_work_dir_by_default(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: db.py's WORK_DIR pointed at a sandbox
        from rbxlight import db

        monkeypatch.setattr(db, "WORK_DIR", tmp_path / "work")

        # When: resolving a db path without live=True
        result = db.resolve_path("macro.db3")

        # Then: it resolves to the working copy, never live
        assert result == tmp_path / "work" / "macro.db3"

    def test_should_resolve_to_live_dir_only_when_explicitly_requested(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: db.py's LIGHTINGDB pointed at a sandbox
        from rbxlight import db

        monkeypatch.setattr(db, "LIGHTINGDB", tmp_path / "live")

        # When: explicitly resolving the live path (only sync.py should do this)
        result = db.resolve_path("macro.db3", live=True)

        # Then: it resolves to live
        assert result == tmp_path / "live" / "macro.db3"
