"""macro.db3 read/write, id allocation, 25-row invariant enforcement. See
rekordbox-data-safety skill ("The 25-row invariant") and
rekordbox-lightingdb-schema skill ("macro preset / id-range convention").

`conn` is always passed in — this module never opens its own connection.
That is `db.py` / `safety.py`'s job, which is what keeps every write on the
guarded path.
"""

from __future__ import annotations

import sqlite3

from rbxlight.models import FIXTURE_SLOT_IDS, FIXTURE_SLOT_TYPES, Macro, MacroData

#: Default row values for a newly-created user macro.
_DEFAULT_FIXED: int = 0
_DEFAULT_THUMBNAIL: str = "USER_SCENE.png"
_DEFAULT_ENABLED: int = 1
_USER_PRESET: int = 0

#: `id` floor a new user macro must land above (see "macro preset / id-range
#: convention" — factory range tops out at 916, SEPARATOR sentinel is 10000).
_USER_ID_FLOOR: int = 10000


class FactoryMacroImmutableError(RuntimeError):
    """Raised when an operation would update/delete a preset=1 macro row."""


def get_macro(conn: sqlite3.Connection, macro_id: int) -> Macro:
    """Fetch a macro row. Must not crash for sentinel ids (-1, 10000)."""
    row = conn.execute(
        "SELECT id, name, beats, fixed, thumbnail, preset, enabled "
        "FROM macro WHERE id = ?",
        (macro_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"macro {macro_id} not found")
    return Macro(
        id=row[0],
        name=row[1],
        beats=row[2],
        fixed=row[3],
        thumbnail=row[4],
        preset=row[5],
        enabled=row[6],
    )


def list_macro_data(conn: sqlite3.Connection, macro_id: int) -> list[MacroData]:
    """Fetch macro_data rows for macro_id, tolerating the older 19-row
    format and the known 150-row anomaly. Never crashes on a row whose
    macro_fixture_id doesn't resolve to one of the 25 known slots — such
    rows are ignored, not raised on.
    """
    rows = conn.execute(
        "SELECT id, macro_id, macro_fixture_id, data FROM macro_data WHERE macro_id = ?",
        (macro_id,),
    ).fetchall()
    return [
        MacroData(id=row[0], macro_id=row[1], macro_fixture_id=row[2], xml=row[3])
        for row in rows
        if row[2] in FIXTURE_SLOT_TYPES
    ]


def create_macro(
    conn: sqlite3.Connection,
    name: str,
    beats: int,
    payloads: dict[int, str],
) -> Macro:
    """Insert a new user macro (preset=0).

    id = max(existing id, 10000) + 1, guaranteed >= 10001 and never
    colliding with an existing id. Inserts exactly one macro_data row per
    slot in FIXTURE_SLOT_IDS (25 total) — any slot missing from `payloads`
    is stored with data="" (never a missing row, never NULL).
    """
    row = conn.execute("SELECT MAX(id) FROM macro").fetchone()
    max_existing_id = row[0] if row is not None and row[0] is not None else 0
    new_id = max(max_existing_id, _USER_ID_FLOOR) + 1

    conn.execute(
        "INSERT INTO macro (id, name, beats, fixed, thumbnail, preset, enabled) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            new_id,
            name,
            beats,
            _DEFAULT_FIXED,
            _DEFAULT_THUMBNAIL,
            _USER_PRESET,
            _DEFAULT_ENABLED,
        ),
    )
    conn.executemany(
        "INSERT INTO macro_data (macro_id, macro_fixture_id, data) VALUES (?, ?, ?)",
        [(new_id, slot_id, payloads.get(slot_id, "")) for slot_id in FIXTURE_SLOT_IDS],
    )

    return Macro(
        id=new_id,
        name=name,
        beats=beats,
        fixed=_DEFAULT_FIXED,
        thumbnail=_DEFAULT_THUMBNAIL,
        preset=_USER_PRESET,
        enabled=_DEFAULT_ENABLED,
    )


def update_macro_data(
    conn: sqlite3.Connection, macro_id: int, macro_fixture_id: int, xml: str
) -> None:
    """Update one macro_data row's payload.

    Raises FactoryMacroImmutableError if the target macro's preset == 1
    (factory content) — including the id=-1 and id=10000 sentinel rows.
    """
    macro = get_macro(conn, macro_id)
    if macro.preset == 1:
        raise FactoryMacroImmutableError(
            f"macro {macro_id} is factory content (preset=1) and cannot be modified"
        )
    conn.execute(
        "UPDATE macro_data SET data = ? WHERE macro_id = ? AND macro_fixture_id = ?",
        (xml, macro_id, macro_fixture_id),
    )


def delete_macro(conn: sqlite3.Connection, macro_id: int) -> None:
    """Delete a user macro and its macro_data rows.

    Raises FactoryMacroImmutableError if the target macro's preset == 1.
    """
    macro = get_macro(conn, macro_id)
    if macro.preset == 1:
        raise FactoryMacroImmutableError(
            f"macro {macro_id} is factory content (preset=1) and cannot be deleted"
        )
    conn.execute("DELETE FROM macro_data WHERE macro_id = ?", (macro_id,))
    conn.execute("DELETE FROM macro WHERE id = ?", (macro_id,))
