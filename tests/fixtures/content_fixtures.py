"""Factories that seed `content` rows into a throwaway user.db3 connection
(see conftest.make_user_db / user_db_conn) for rbxlight.phrases.repo tests
and the ninth-bank experiment tests.

These build REAL rows in a real (throwaway) SQLite connection — not mocks.

`content` holds thousands of rows of irreplaceable user work in the real
library — see rekordbox-lightingdb-schema skill ("content") and
rekordbox-data-safety. Some real rows legitimately reference a
macro_pattern id with no matching row (content has no FK enforcement) —
that is a pre-existing condition, not corruption; see
a_track_with_dangling_macro_pattern_id below.
"""

from __future__ import annotations

import sqlite3


def insert_content_row(
    conn: sqlite3.Connection,
    *,
    content_id: int,
    song_id: int = 1,
    master_db_id: int = 1,
    macro_pattern_id: int = 1,
) -> int:
    conn.execute(
        "INSERT INTO content (id, song_id, master_db_id, macro_pattern_id) "
        "VALUES (?, ?, ?, ?)",
        (content_id, song_id, master_db_id, macro_pattern_id),
    )
    conn.commit()
    return content_id


def a_track(
    conn: sqlite3.Connection,
    *,
    content_id: int = 1,
    song_id: int = 1,
    macro_pattern_id: int = 1,
) -> int:
    """An ordinary track (content row) pointing at a real macro_pattern id."""
    return insert_content_row(
        conn, content_id=content_id, song_id=song_id, macro_pattern_id=macro_pattern_id
    )


def a_track_with_dangling_macro_pattern_id(
    conn: sqlite3.Connection,
    *,
    content_id: int = 999,
    macro_pattern_id: int = 55555,
) -> int:
    """A content row whose macro_pattern_id references no existing
    macro_pattern row — a real, pre-existing condition in the live
    library (see rekordbox-lightingdb-schema / physical-rig-profile
    skills), not corruption. content has no FK enforcement, so this is a
    perfectly legal row; code must never assume referential integrity
    here.
    """
    return insert_content_row(
        conn, content_id=content_id, macro_pattern_id=macro_pattern_id
    )


def many_tracks(
    conn: sqlite3.Connection, *, content_ids: tuple[int, ...], macro_pattern_id: int = 1
) -> tuple[int, ...]:
    """Several ordinary content rows sharing the same macro_pattern_id —
    used to prove a repoint touches exactly one row and leaves the rest
    alone."""
    for content_id in content_ids:
        a_track(conn, content_id=content_id, macro_pattern_id=macro_pattern_id)
    return content_ids
