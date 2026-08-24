"""Thin domain wrappers the menu screens call through. Every function
here reads location constants (`db.WORK_DIR`, `safety.LIGHTINGDB`,
`safety.BACKUP_ROOT`) fresh at call time via the modules they belong to
— never bound at import time — so test monkeypatches (and real config)
take effect for every call. See rekordbox-data-safety skill.

No typer/click, no print — this module returns values and raises the
same typed exceptions the domain layer already raises. The menu screens
translate those into clean rendered messages.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rbxlight import db, orchestration, safety
from rbxlight.macros import repo as macros_repo
from rbxlight.venues import repo as venues_repo

_MACRO_DB_NAME = "macro.db3"
_USER_DB_NAME = "user.db3"


@contextmanager
def readonly_working_copy(db_name: str) -> Iterator[sqlite3.Connection]:
    """Thin pass-through to `db.readonly_working_copy` — kept here so
    every menu screen imports collaborators from this one module.
    """
    with db.readonly_working_copy(db_name) as conn:
        yield conn


# ---------------------------------------------------------------------------
# Macros — read-only
# ---------------------------------------------------------------------------


def list_macros(scope: str) -> list[macros_repo.Macro]:
    with readonly_working_copy(_MACRO_DB_NAME) as conn:
        return macros_repo.list_macros(conn, scope=scope)


def search_macros(term: str, scope: str) -> list[macros_repo.Macro]:
    with readonly_working_copy(_MACRO_DB_NAME) as conn:
        return macros_repo.search_macros(conn, term, scope=scope)


def get_macro_detail(
    macro_id: int,
) -> tuple[macros_repo.Macro, list[macros_repo.SlotStatus]]:
    """Raises LookupError if macro_id doesn't exist."""
    with readonly_working_copy(_MACRO_DB_NAME) as conn:
        macro = macros_repo.get_macro(conn, macro_id)
        slots = macros_repo.get_slot_statuses(conn, macro_id)
        return macro, slots


# ---------------------------------------------------------------------------
# Macros — mutating (working copy only)
# ---------------------------------------------------------------------------


def build_create_macro_plan(*, name: str, beats: int) -> macros_repo.CreateMacroPlan:
    return macros_repo.build_create_macro_plan(
        name=name, beats=beats, target_path=db.resolve_path(_MACRO_DB_NAME)
    )


def create_macro(*, name: str, beats: int) -> macros_repo.Macro:
    with safety.working_copy_write(_MACRO_DB_NAME) as conn:
        return macros_repo.create_macro(conn, name=name, beats=beats, payloads={})


def build_delete_macro_plan(macro_id: int) -> macros_repo.DeleteMacroPlan:
    """Raises LookupError if macro_id doesn't exist."""
    path = db.resolve_path(_MACRO_DB_NAME)
    conn = db.connect_readonly(path)
    try:
        return macros_repo.build_delete_macro_plan(
            conn, macro_id=macro_id, target_path=path
        )
    finally:
        conn.close()


def delete_macro(macro_id: int) -> None:
    """Raises macros_repo.FactoryMacroImmutableError for preset=1 rows."""
    with safety.working_copy_write(_MACRO_DB_NAME) as conn:
        macros_repo.delete_macro(conn, macro_id)


# ---------------------------------------------------------------------------
# Venues — read-only
# ---------------------------------------------------------------------------


def list_venues() -> tuple[list[venues_repo.VenueWithFixtureCount], int | None]:
    with readonly_working_copy(_USER_DB_NAME) as conn:
        entries = venues_repo.list_venues_with_fixture_counts(conn)
        active_id = venues_repo.get_exec_venue_id(conn)
        return entries, active_id


def resolve_venue(venue_id: int | None) -> orchestration.VenueResolution:
    """Raises orchestration.VenueNotFoundError / NoActiveVenueError /
    StaleActiveVenueError."""
    with readonly_working_copy(_USER_DB_NAME) as conn:
        return orchestration.resolve_venue(conn, venue_id)


# ---------------------------------------------------------------------------
# Backups — read-only
# ---------------------------------------------------------------------------


def list_backups() -> list[safety.BackupInfo]:
    return safety.list_backups()


# ---------------------------------------------------------------------------
# Preview — read-only with respect to the databases (may persist a
# generated layout file, matching orchestration.generate_preview).
# ---------------------------------------------------------------------------


def generate_preview_for_menu(macro_id: int, venue_id: int) -> Path:
    """Resolve `venue_id` against the working copy, generate the preview
    HTML for `macro_id`, and return the output path. Raises the same
    typed exceptions as `orchestration.resolve_venue` /
    `orchestration.generate_preview`.
    """
    output_path = Path(f"preview_{macro_id}.html")
    with (
        readonly_working_copy(_MACRO_DB_NAME) as macro_conn,
        readonly_working_copy(_USER_DB_NAME) as user_conn,
    ):
        result = orchestration.resolve_venue(user_conn, venue_id)
        return orchestration.generate_preview(
            macro_conn,
            user_conn,
            macro_id,
            result.venue.id,
            result.fixtures,
            orchestration.default_layout_dir(),
            output_path,
        )
