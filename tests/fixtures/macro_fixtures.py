"""Factories that seed macro/macro_data rows into a throwaway macro.db3
connection (see conftest.make_macro_db / macro_db_conn) for
rbxlight.macros.repo tests.

These build REAL rows in a real (throwaway) SQLite connection — not mocks.
The connection/collaborator being exercised is the DB itself; only actual
external services would be mocked, and there are none here.
"""

from __future__ import annotations

import sqlite3

#: The 25 real fixture slot ids (see rbxlight.models.FIXTURE_SLOT_IDS).
ALL_25_SLOT_IDS: tuple[int, ...] = (
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    18,
    19,
    101,
    102,
    105,
    106,
    111,
    112,
)

#: The older, pre-Simple-slot format: just slots 1..19.
LEGACY_19_SLOT_IDS: tuple[int, ...] = tuple(range(1, 20))

_SIMPLE_VALID_PAYLOAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<LightingEditModel ver="1.0">\n'
    "  <Brightness>\n"
    '    <PointBlock xleft="0" xright="32">\n'
    '      <Point x="0" y="0" type="1"/>\n'
    '      <Point x="32" y="0" type="3"/>\n'
    "    </PointBlock>\n"
    "  </Brightness>\n"
    "  <Colour/>\n"
    "  <Strobe/>\n"
    "</LightingEditModel>"
)


def insert_macro_row(
    conn: sqlite3.Connection,
    *,
    macro_id: int,
    name: str = "Test Macro",
    beats: int = 32,
    fixed: int = 0,
    thumbnail: str = "USER_SCENE.png",
    preset: int = 0,
    enabled: int = 1,
) -> int:
    conn.execute(
        "INSERT INTO macro (id, name, beats, fixed, thumbnail, preset, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (macro_id, name, beats, fixed, thumbnail, preset, enabled),
    )
    conn.commit()
    return macro_id


def insert_macro_data_row(
    conn: sqlite3.Connection,
    *,
    macro_id: int,
    macro_fixture_id: int,
    data: str = "",
) -> None:
    conn.execute(
        "INSERT INTO macro_data (macro_id, macro_fixture_id, data) VALUES (?, ?, ?)",
        (macro_id, macro_fixture_id, data),
    )
    conn.commit()


def a_factory_macro(
    conn: sqlite3.Connection,
    *,
    macro_id: int = 61,
    name: str = "FACTORY MACRO",
    beats: int = 32,
    slot_ids: tuple[int, ...] = ALL_25_SLOT_IDS,
) -> int:
    """A preset=1 macro (factory content — must never be updated/deleted)
    with a full, valid 25-row macro_data set."""
    insert_macro_row(conn, macro_id=macro_id, name=name, beats=beats, preset=1)
    for slot_id in slot_ids:
        insert_macro_data_row(
            conn, macro_id=macro_id, macro_fixture_id=slot_id, data=""
        )
    return macro_id


def a_user_macro(
    conn: sqlite3.Connection,
    *,
    macro_id: int = 10001,
    name: str = "USER MACRO",
    beats: int = 32,
    slot_ids: tuple[int, ...] = ALL_25_SLOT_IDS,
) -> int:
    """A preset=0 (user) macro with a full, valid 25-row macro_data set."""
    insert_macro_row(conn, macro_id=macro_id, name=name, beats=beats, preset=0)
    for slot_id in slot_ids:
        insert_macro_data_row(
            conn, macro_id=macro_id, macro_fixture_id=slot_id, data=""
        )
    return macro_id


def sentinel_macro_rows(conn: sqlite3.Connection) -> None:
    """The two real sentinel rows: id=-1 (factory) and id=10000 (SEPARATOR
    marker) — both preset=1, neither a usable macro."""
    insert_macro_row(conn, macro_id=-1, name="(sentinel)", preset=1)
    insert_macro_row(conn, macro_id=10000, name="SEPARATOR", preset=1)


def a_macro_with_19_rows(conn: sqlite3.Connection, *, macro_id: int = 500) -> int:
    """Older, pre-Simple-slot format macro_data set (19 rows: slots 1..19,
    no 101/102/105/106/111/112 rows at all)."""
    insert_macro_row(conn, macro_id=macro_id, name="LEGACY 19-ROW", preset=1)
    for slot_id in LEGACY_19_SLOT_IDS:
        insert_macro_data_row(
            conn, macro_id=macro_id, macro_fixture_id=slot_id, data=""
        )
    return macro_id


def a_macro_with_150_rows(conn: sqlite3.Connection, *, macro_id: int = 999) -> int:
    """The known factory-library anomaly: 150 macro_data rows for one
    macro — duplicates of the 25 legit slot ids (macro_data.id is a
    separate autoincrement PK, so repeating a macro_fixture_id per
    macro_id is a realistic anomaly, not a schema violation)."""
    insert_macro_row(conn, macro_id=macro_id, name="ANOMALY 150-ROW", preset=1)
    row_count = 0
    while row_count < 150:
        for slot_id in ALL_25_SLOT_IDS:
            if row_count >= 150:
                break
            insert_macro_data_row(
                conn, macro_id=macro_id, macro_fixture_id=slot_id, data=""
            )
            row_count += 1
    return macro_id


def a_macro_with_unknown_fixture_id_rows(
    conn: sqlite3.Connection, *, macro_id: int = 998
) -> int:
    """A macro with some macro_data rows whose macro_fixture_id doesn't
    resolve to any of the 25 known slots — reading must ignore these
    rows, not crash on them."""
    insert_macro_row(conn, macro_id=macro_id, name="UNKNOWN-SLOT ROWS", preset=1)
    for slot_id in ALL_25_SLOT_IDS:
        insert_macro_data_row(
            conn, macro_id=macro_id, macro_fixture_id=slot_id, data=""
        )
    for unknown_slot_id in (9999, 8888):
        insert_macro_data_row(
            conn, macro_id=macro_id, macro_fixture_id=unknown_slot_id, data=""
        )
    return macro_id


def a_valid_slot_payload() -> str:
    """A minimal, valid, parseable LightingEditModel payload — used where
    a test needs "some real programming" without caring about its shape."""
    return _SIMPLE_VALID_PAYLOAD


def a_full_payload_map(payload: str = "") -> dict[int, str]:
    """{slot_id: payload} for all 25 real slots — the shape macros.repo
    create_macro's `payloads` argument expects a subset or full set of."""
    return {slot_id: payload for slot_id in ALL_25_SLOT_IDS}
