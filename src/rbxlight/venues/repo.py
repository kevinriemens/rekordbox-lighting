"""user.db3 read access: venue, fixture, and the active-venue lighting
property. See rekordbox-lightingdb-schema skill ("user.db3 tables").

`conn` is always passed in — this module never opens its own connection,
consistent with rbxlight.macros.repo.
"""

from __future__ import annotations

import sqlite3

from rbxlight.venues.models import Fixture, Venue


def get_venue(conn: sqlite3.Connection, venue_id: int) -> Venue:
    """Fetch a venue row. Raises LookupError if venue_id doesn't exist."""
    row = conn.execute(
        'SELECT id, name, "order", enabled FROM venue WHERE id = ?',
        (venue_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"venue {venue_id} not found")
    return Venue(id=row[0], name=row[1], order=row[2], enabled=row[3])


def list_fixtures(conn: sqlite3.Connection, venue_id: int) -> list[Fixture]:
    """Fetch every fixture patched into venue_id, ordered by the fixture's
    `order` column. Multiple fixtures sharing the same macro_fixture_id
    (slot collisions) are all returned — never deduplicated, never an
    error. Returns an empty list for a venue with no fixtures.
    """
    rows = conn.execute(
        "SELECT id, name, venue_id, fixture_master_id, mode_num, "
        'macro_fixture_id, universe_num, start_addr, color_num, "order", '
        "offset_x, offset_y, limit_min_x, limit_max_x, limit_min_y, "
        "limit_max_y, tilt_reversal "
        'FROM fixture WHERE venue_id = ? ORDER BY "order"',
        (venue_id,),
    ).fetchall()
    return [
        Fixture(
            id=row[0],
            name=row[1],
            venue_id=row[2],
            fixture_master_id=row[3],
            mode_num=row[4],
            macro_fixture_id=row[5],
            universe_num=row[6],
            start_addr=row[7],
            color_num=row[8],
            order=row[9],
            offset_x=row[10],
            offset_y=row[11],
            limit_min_x=row[12],
            limit_max_x=row[13],
            limit_min_y=row[14],
            limit_max_y=row[15],
            tilt_reversal=row[16],
        )
        for row in rows
    ]


def get_exec_venue_id(conn: sqlite3.Connection) -> int | None:
    """Read lighting_property.ExecVenueId (the currently active venue).
    Returns None if the key is absent.
    """
    row = conn.execute(
        "SELECT value FROM lighting_property WHERE key = 'ExecVenueId'"
    ).fetchone()
    if row is None:
        return None
    return int(row[0])
