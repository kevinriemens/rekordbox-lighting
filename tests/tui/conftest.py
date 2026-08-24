"""Shared fixtures for tests/tui/. Builds throwaway working-copy DBs in
tmp_path and monkeypatches rbxlight.db.WORK_DIR / safety.LIGHTINGDB /
safety.BACKUP_ROOT — the same pattern tests/test_cli.py already uses.
Never touches anything under the real rekordbox app-support directory
(enforced doubly by tests/conftest.py's autouse _guard_real_home).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rbxlight import db, safety
from tests.conftest import make_macro_db, make_user_db
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


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
def work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "work"
    directory.mkdir()
    monkeypatch.setattr(db, "WORK_DIR", directory)
    return directory


@pytest.fixture
def work_macro_db(work_dir: Path) -> Path:
    return make_macro_db(work_dir / "macro.db3")


@pytest.fixture
def work_user_db(work_dir: Path) -> Path:
    return make_user_db(work_dir / "user.db3")


@pytest.fixture
def live_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "LightingDB"
    directory.mkdir()
    monkeypatch.setattr(safety, "LIGHTINGDB", directory)
    return directory


@pytest.fixture
def backup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "backups"
    monkeypatch.setattr(safety, "BACKUP_ROOT", directory)
    return directory


def make_prompter(*answers: object) -> ScriptedPrompter:
    return ScriptedPrompter(answers=list(answers))


@pytest.fixture
def renderer() -> RecordingRenderer:
    return RecordingRenderer()
