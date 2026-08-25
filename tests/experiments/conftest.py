"""Shared fixtures for rbxlight.experiments.ninth_bank tests: a working
copy (macro.db3 + user.db3) wired up as db.WORK_DIR, seeded with a source
bank ready to clone from and a target track ready to repoint.

Mirrors the working-copy fixture pattern already established for
safety.working_copy_write tests (tests/test_working_copy_write.py) — this
module never touches live, so every test resolves paths under tmp_path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import db
from tests.conftest import make_macro_db, make_user_db
from tests.fixtures.content_fixtures import a_track
from tests.fixtures.pattern_fixtures import a_high_energy_bank


@pytest.fixture
def ninth_bank_work_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """A working copy with one HIGH-energy (11-phase) source bank and one
    target track, wired up as db.WORK_DIR. Returns paths + the ids of the
    seeded source bank / target track.
    """
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    macro_path = make_macro_db(work_dir / "macro.db3")
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    macro_conn = sqlite3.connect(macro_path)
    source_pattern_id = a_high_energy_bank(macro_conn, pattern_id=1)
    macro_conn.close()

    user_conn = sqlite3.connect(user_path)
    content_id = a_track(user_conn, content_id=1, macro_pattern_id=1)
    user_conn.close()

    return {
        "work_dir": work_dir,
        "macro_path": macro_path,
        "user_path": user_path,
        "source_pattern_id": source_pattern_id,
        "content_id": content_id,
    }


@pytest.fixture
def ninth_bank_work_dir_no_tracks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """Same shape as `ninth_bank_work_dir`, but user.db3 has ZERO content
    rows. Bank-only apply must never query or write user.db3 at all — this
    fixture proves it, since there is nothing there for a stray read/write
    to accidentally touch or silently succeed against.
    """
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    macro_path = make_macro_db(work_dir / "macro.db3")
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    macro_conn = sqlite3.connect(macro_path)
    source_pattern_id = a_high_energy_bank(macro_conn, pattern_id=1)
    macro_conn.close()

    return {
        "work_dir": work_dir,
        "macro_path": macro_path,
        "user_path": user_path,
        "source_pattern_id": source_pattern_id,
    }
