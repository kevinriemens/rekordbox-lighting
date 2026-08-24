"""macro.db3 read/write, id allocation, 25-row invariant enforcement. See
rekordbox-data-safety skill ("The 25-row invariant") and
rekordbox-lightingdb-schema skill ("macro preset / id-range convention").

`conn` is always passed in — this module never opens its own connection.
That is `db.py` / `safety.py`'s job, which is what keeps every write on the
guarded path.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rbxlight.models import FIXTURE_SLOT_IDS, FIXTURE_SLOT_TYPES, Macro, MacroData

#: SQL column list shared by every macro SELECT in this module.
_MACRO_COLUMNS: str = "id, name, beats, fixed, thumbnail, preset, enabled"

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


@dataclass(frozen=True)
class CreateMacroPlan:
    """A typed, immutable description of what `macro create` WOULD do —
    the render-facts a dry-run needs, built with zero writes.
    """

    name: str
    beats: int
    target_path: Path
    touches_live: bool


def build_create_macro_plan(
    *, name: str, beats: int, target_path: Path
) -> CreateMacroPlan:
    """Build a CreateMacroPlan. Never touches the database — the working
    copy is disposable but a plan is still built with zero writes."""
    return CreateMacroPlan(
        name=name, beats=beats, target_path=target_path, touches_live=False
    )


@dataclass(frozen=True)
class DeleteMacroPlan:
    """A typed, immutable description of what `macro delete` WOULD do —
    the render-facts a dry-run needs, built with zero writes.
    """

    macro_id: int
    macro_name: str
    beats: int
    target_path: Path
    touches_live: bool


def build_delete_macro_plan(
    conn: sqlite3.Connection, *, macro_id: int, target_path: Path
) -> DeleteMacroPlan:
    """Build a DeleteMacroPlan by looking up the target macro. Raises
    LookupError if it doesn't exist (same predictable failure mode as
    get_macro). Read-only — never deletes anything.
    """
    macro = get_macro(conn, macro_id)
    return DeleteMacroPlan(
        macro_id=macro.id,
        macro_name=macro.name,
        beats=macro.beats,
        target_path=target_path,
        touches_live=False,
    )


def _row_to_macro(row: sqlite3.Row) -> Macro:
    """Convert a macro SELECT row to a Macro dataclass."""
    return Macro(
        id=row[0],
        name=row[1],
        beats=row[2],
        fixed=row[3],
        thumbnail=row[4],
        preset=row[5],
        enabled=row[6],
    )


def _scope_where(scope: str) -> str:
    """Return the WHERE clause fragment for a scope filter."""
    if scope == "user":
        return " WHERE preset = 0"
    if scope == "factory":
        return " WHERE preset = 1"
    return ""


def get_macro(conn: sqlite3.Connection, macro_id: int) -> Macro:
    """Fetch a macro row. Must not crash for sentinel ids (-1, 10000)."""
    row = conn.execute(
        f"SELECT {_MACRO_COLUMNS} FROM macro WHERE id = ?",
        (macro_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"macro {macro_id} not found")
    return _row_to_macro(row)


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


def list_macros(conn: sqlite3.Connection, *, scope: str = "user") -> list[Macro]:
    """List macros filtered by scope, ordered by id ascending.

    scope: "user" (preset=0), "factory" (preset=1), or "all" (both).
    Returns Macro dataclass instances. Empty DB → empty list.
    """
    where = _scope_where(scope)
    rows = conn.execute(
        f"SELECT {_MACRO_COLUMNS} FROM macro{where} ORDER BY id"
    ).fetchall()
    return [_row_to_macro(row) for row in rows]


def search_macros(
    conn: sqlite3.Connection, term: str, *, scope: str = "user"
) -> list[Macro]:
    """Search macros by case-insensitive substring match on name.

    LIKE wildcards in `term` are escaped as literals (backslash-first:
    ``→ \\, % → \\%, _ → \\_``). scope: "user", "factory", or "all".
    Ordered by id ascending. Empty DB or no matches → empty list.
    """
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    where = _scope_where(scope)
    name_clause = (
        " AND name LIKE ? ESCAPE '\\'" if where else "WHERE name LIKE ? ESCAPE '\\'"
    )
    rows = conn.execute(
        f"SELECT {_MACRO_COLUMNS} FROM macro {where}{name_clause} ORDER BY id",
        (f"%{escaped}%",),
    ).fetchall()
    return [_row_to_macro(row) for row in rows]
