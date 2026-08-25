"""user.db3 `content` (the per-track bank assignment) read/write. Permanent,
reusable repo functions — the initial slice of the future phrases/repo.py
described in rekordbox-lighting-architecture ("content + phrase_data
read/write"); `phrase_data` accessors are a future addition, out of scope
here.

See rekordbox-lightingdb-schema skill ("content"). `content` holds
thousands of rows of irreplaceable user work in the real library — see
rekordbox-data-safety skill. Some real content rows legitimately reference
a macro_pattern id that doesn't exist (no FK enforcement in the real
schema); this module must never assume referential integrity.

`conn` is always passed in — this module never opens its own connection.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Content:
    """One row of `content` — a track's per-bank macro_pattern assignment."""

    id: int
    song_id: int
    master_db_id: int
    macro_pattern_id: int


def get_content(conn: sqlite3.Connection, content_id: int) -> Content:
    """Fetch a content row. Raises LookupError if it doesn't exist.

    Never validates that `macro_pattern_id` resolves to a real
    macro_pattern row — a dangling reference is a real, pre-existing
    condition in the live data, not corruption.
    """
    row = conn.execute(
        "SELECT id, song_id, master_db_id, macro_pattern_id FROM content WHERE id = ?",
        (content_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"content {content_id} not found")
    return Content(
        id=row[0], song_id=row[1], master_db_id=row[2], macro_pattern_id=row[3]
    )


def update_content_macro_pattern_id(
    conn: sqlite3.Connection, content_id: int, macro_pattern_id: int
) -> None:
    """Repoint content_id's macro_pattern_id. Touches only the target row.

    Raises LookupError if content_id doesn't exist — never a silent no-op.
    Never validates that the new macro_pattern_id resolves to a real
    macro_pattern row (see get_content docstring — this is a legal state
    in the real library).
    """
    cursor = conn.execute(
        "UPDATE content SET macro_pattern_id = ? WHERE id = ?",
        (macro_pattern_id, content_id),
    )
    if cursor.rowcount == 0:
        raise LookupError(f"content {content_id} not found")
