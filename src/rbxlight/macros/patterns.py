"""macro.db3 `macro_pattern` (the bank/energy combinations) and
`macro_assign` (phase -> concrete macro mapping) read/write. Permanent,
reusable repo functions — see rekordbox-lighting-architecture skill on
repo-vs-orchestration placement; rbxlight.experiments.ninth_bank is the
disposable orchestration built on top of this module.

See rekordbox-lightingdb-schema skill ("macro_pattern", "macro_assign",
"How macros get selected for a track") for the table shapes and the
non-uniform phase-count-per-energy fact this module must never hardcode.

`conn` is always passed in — this module never opens its own connection.
That is `db.py` / `safety.py`'s job, which is what keeps every write on the
guarded path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class MacroPattern:
    """One row of macro_pattern — an energy x pattern "bank" combination."""

    id: int
    energy: int
    pattern: int


@dataclass(frozen=True)
class MacroAssign:
    """One row of macro_assign — a single phase's concrete macro mapping
    for a given macro_pattern.
    """

    macro_pattern_id: int
    phase: int
    macro_id: int
    initial_macro_id: int


def _row_to_macro_pattern(row: sqlite3.Row) -> MacroPattern:
    """Convert a macro_pattern SELECT row to a MacroPattern dataclass."""
    return MacroPattern(id=row[0], energy=row[1], pattern=row[2])


def get_macro_pattern(conn: sqlite3.Connection, pattern_id: int) -> MacroPattern:
    """Fetch a macro_pattern row. Raises LookupError if it doesn't exist."""
    row = conn.execute(
        "SELECT id, energy, pattern FROM macro_pattern WHERE id = ?",
        (pattern_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"macro_pattern {pattern_id} not found")
    return _row_to_macro_pattern(row)


def list_macro_patterns(conn: sqlite3.Connection) -> list[MacroPattern]:
    """List every macro_pattern row, ordered by id ascending. Empty table
    -> empty list.
    """
    rows = conn.execute(
        "SELECT id, energy, pattern FROM macro_pattern ORDER BY id"
    ).fetchall()
    return [_row_to_macro_pattern(row) for row in rows]


def list_macro_assign(
    conn: sqlite3.Connection, macro_pattern_id: int
) -> list[MacroAssign]:
    """List every macro_assign row for macro_pattern_id, ordered by phase
    ascending. A pattern with zero phase rows -> empty list, not an error.
    """
    rows = conn.execute(
        "SELECT macro_pattern_id, phase, macro_id, initial_macro_id "
        "FROM macro_assign WHERE macro_pattern_id = ? ORDER BY phase",
        (macro_pattern_id,),
    ).fetchall()
    return [
        MacroAssign(
            macro_pattern_id=row[0],
            phase=row[1],
            macro_id=row[2],
            initial_macro_id=row[3],
        )
        for row in rows
    ]


def next_macro_pattern_id(conn: sqlite3.Connection) -> int:
    """One past the current maximum macro_pattern.id — derived from the
    table's actual contents, NEVER hardcoded. An empty table allocates 1.
    """
    row = conn.execute("SELECT MAX(id) FROM macro_pattern").fetchone()
    max_id = row[0] if row is not None and row[0] is not None else 0
    return max_id + 1


def create_macro_pattern(
    conn: sqlite3.Connection, *, energy: int, pattern: int
) -> MacroPattern:
    """Insert a new macro_pattern row at `next_macro_pattern_id(conn)`."""
    new_id = next_macro_pattern_id(conn)
    conn.execute(
        "INSERT INTO macro_pattern (id, energy, pattern) VALUES (?, ?, ?)",
        (new_id, energy, pattern),
    )
    return MacroPattern(id=new_id, energy=energy, pattern=pattern)


def clone_macro_assign(
    conn: sqlite3.Connection, *, source_pattern_id: int, target_pattern_id: int
) -> list[MacroAssign]:
    """Clone every macro_assign row from source_pattern_id to
    target_pattern_id, preserving phase/macro_id/initial_macro_id and
    restamping only macro_pattern_id.

    The number of rows created follows whatever the source bank actually
    has — different banks genuinely have different phase counts (11 at
    HIGH energy for most banks, 10 for the CLUB/MID banks). Hardcoding
    any phase count here is a defect.

    Raises LookupError if the source has no macro_assign rows at all
    (whether because the source macro_pattern id doesn't exist, or it
    exists but has zero phases) — nothing is written in that case.
    """
    source_rows = list_macro_assign(conn, source_pattern_id)
    if not source_rows:
        raise LookupError(
            f"macro_pattern {source_pattern_id} has no macro_assign rows to clone"
        )

    created: list[MacroAssign] = []
    for row in source_rows:
        conn.execute(
            "INSERT INTO macro_assign "
            "(macro_pattern_id, phase, macro_id, initial_macro_id) VALUES (?, ?, ?, ?)",
            (target_pattern_id, row.phase, row.macro_id, row.initial_macro_id),
        )
        created.append(replace(row, macro_pattern_id=target_pattern_id))
    return created


def delete_macro_pattern(conn: sqlite3.Connection, pattern_id: int) -> None:
    """Delete a macro_pattern row. Idempotent — a safe no-op if absent."""
    conn.execute("DELETE FROM macro_pattern WHERE id = ?", (pattern_id,))


def delete_macro_assign(conn: sqlite3.Connection, macro_pattern_id: int) -> None:
    """Delete every macro_assign row for macro_pattern_id. Idempotent — a
    safe no-op if none exist.
    """
    conn.execute(
        "DELETE FROM macro_assign WHERE macro_pattern_id = ?", (macro_pattern_id,)
    )
