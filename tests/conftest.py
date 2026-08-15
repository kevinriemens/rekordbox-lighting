"""Shared pytest fixtures for the rbxlight test suite.

IMPORTANT: these tests must NEVER open, read, or write anything under the
real user's rekordbox application-support directory. `_guard_real_home`
below monkeypatches Path.home() for every test so any accidental use of the
real default (~/Library/Application Support/Pioneer/rekordbox6/LightingDB)
resolves into a throwaway sandbox instead.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _guard_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a test resolve to the real rekordbox app-support directory."""
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", lambda: fake_home)


# ---------------------------------------------------------------------------
# macro.db3 throwaway schema
# ---------------------------------------------------------------------------

MACRO_DB_SCHEMA = """
CREATE TABLE macro (
  id        INTEGER PRIMARY KEY,
  name      TEXT,
  beats     INTEGER,
  fixed     INTEGER,
  thumbnail TEXT,
  preset    INTEGER,
  enabled   INTEGER
);

CREATE TABLE macro_data (
  id               INTEGER PRIMARY KEY,
  macro_id         INTEGER,
  macro_fixture_id INTEGER,
  data             TEXT
);

CREATE TABLE macro_fixture (
  id              INTEGER PRIMARY KEY,
  name            TEXT,
  fixture_type_id INTEGER
);
"""

# The 25 real fixture slots, id -> (name, fixture_type_id) — see
# rekordbox-lightingdb-schema skill.
FIXTURE_SLOTS: dict[int, tuple[str, int]] = {
    1: ("Par Light 1", 1),
    2: ("Par Light 2", 1),
    3: ("Par Light 3", 1),
    4: ("Par Light 4", 1),
    5: ("Bar Light 1", 2),
    6: ("Bar Light 2", 2),
    7: ("Bar Light 3", 2),
    8: ("Bar Light 4", 2),
    9: ("Bar Light 5", 2),
    10: ("Bar Light 6", 2),
    11: ("Moving Head 1", 3),
    12: ("Moving Head 2", 3),
    13: ("Moving Head 3", 3),
    14: ("Moving Head 4", 3),
    15: ("Strobe", 4),
    16: ("Mirrorball Spot", 5),
    17: ("Effect 1", 8),
    18: ("Effect 2", 8),
    19: ("Laser", 9),
    101: ("Par Light 1 (Simple)", 101),
    102: ("Par Light 2 (Simple)", 101),
    105: ("Bar Light 1 (Simple)", 102),
    106: ("Bar Light 2 (Simple)", 102),
    111: ("Moving Head 1 (Simple)", 103),
    112: ("Moving Head 2 (Simple)", 103),
}


def _seed_fixture_slots(conn: sqlite3.Connection) -> None:
    conn.executemany(
        "INSERT INTO macro_fixture (id, name, fixture_type_id) VALUES (?, ?, ?)",
        [(slot_id, name, ftype) for slot_id, (name, ftype) in FIXTURE_SLOTS.items()],
    )


def make_macro_db(path: Path) -> Path:
    """Build a throwaway macro.db3-shaped SQLite file with the 25 fixture slots
    seeded and NO macro rows — callers add their own macro/macro_data rows.
    """
    conn = sqlite3.connect(path)
    try:
        conn.executescript(MACRO_DB_SCHEMA)
        _seed_fixture_slots(conn)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def macro_db_path(tmp_path: Path) -> Path:
    """Empty (fixture-slots-only) throwaway macro.db3 file."""
    return make_macro_db(tmp_path / "macro.db3")


@pytest.fixture
def macro_db_conn(macro_db_path: Path):
    conn = sqlite3.connect(macro_db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# user.db3 throwaway schema — venue/fixture patch + lighting_property, the
# subset of user.db3 the preview-export feature reads. See
# rekordbox-lightingdb-schema skill ("user.db3 tables").
# ---------------------------------------------------------------------------

USER_DB_SCHEMA = """
CREATE TABLE venue (
  id      INTEGER PRIMARY KEY,
  name    TEXT,
  "order" INTEGER,
  enabled INTEGER
);

CREATE TABLE fixture (
  id                INTEGER PRIMARY KEY,
  name              TEXT,
  venue_id          INTEGER,
  fixture_master_id INTEGER,
  mode_num          INTEGER,
  macro_fixture_id  INTEGER,
  universe_num      INTEGER,
  start_addr        INTEGER,
  color_num         INTEGER,
  "order"           INTEGER,
  offset_x          INTEGER,
  offset_y          INTEGER,
  limit_min_x       INTEGER,
  limit_max_x       INTEGER,
  limit_min_y       INTEGER,
  limit_max_y       INTEGER,
  tilt_reversal     INTEGER
);

CREATE TABLE lighting_property (
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


def make_user_db(path: Path) -> Path:
    """Build a throwaway user.db3-shaped SQLite file (schema only — no
    venue/fixture/property rows). Callers add their own rows.
    """
    conn = sqlite3.connect(path)
    try:
        conn.executescript(USER_DB_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


@pytest.fixture
def user_db_path(tmp_path: Path) -> Path:
    """Empty (schema-only) throwaway user.db3 file."""
    return make_user_db(tmp_path / "user.db3")


@pytest.fixture
def user_db_conn(user_db_path: Path):
    conn = sqlite3.connect(user_db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
