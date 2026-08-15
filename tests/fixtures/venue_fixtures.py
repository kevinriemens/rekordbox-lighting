"""Factories that seed venue/fixture/lighting_property rows into a
throwaway user.db3 connection (see conftest.make_user_db / user_db_conn)
for rbxlight.venues.repo and rbxlight.preview.* tests.

These build REAL rows in a real (throwaway) SQLite connection — not mocks.

NOTE: fixture_master_id values below are NOT synthetic — see the
"CONTRADICTION" flagged in the test-suite report for why. They are still
grounded in the physical-rig-profile skill's physical hardware table.
DMX start addresses and the active venue name ARE synthetic (see below).
"""

from __future__ import annotations

import sqlite3

from rbxlight.venues.models import Fixture

#: fixture_master_id values matching rbxlight.preview.layout.KIND_BY_MASTER_ID
#: (production code) 1:1 — NOT replaced with placeholders. See the
#: "CONTRADICTION" note in this task's report: swapping these breaks fixture
#: kind classification because that lookup table is hardcoded in src/ and
#: out of this test-suite's scope to edit.
LM70S_MASTER_ID: int = 13417  # Moving head
TILT_BLOCK_MASTER_ID: int = 17404  # decomposed bar tilt block
PIXEL_CELL_MASTER_ID: int = 32282  # decomposed bar pixel cell
PAR_MASTER_ID: int = 19231  # Par
#: Deliberately not one of the four known rig hardware ids.
UNKNOWN_MASTER_ID: int = 77777

#: Synthetic DMX start addresses for a made-up test rig — structurally
#: equivalent to a real bar-decomposition patch (see
#: rekordbox-lightingdb-schema / physical-rig-profile skills) but not
#: sourced from any live venue. NOT sequential per fixture type, and NOT
#: the order the repository actually returns fixtures in — see
#: a_full_arc_fixture_list()'s docstring. Each bar's tilt block owns the 9
#: cell addresses that fall after it, up to the next bar's tilt address:
#: bar 1's tilt (501) owns 507-539 (cells at 507,511,...,539); bar 2's
#: tilt (544) owns 550-582 (cells at 550,554,...,582).
HEAD_ADDRS: tuple[int, ...] = (2, 16, 30, 44)
BAR_1_TILT_ADDR: int = 501
BAR_1_CELL_ADDRS: tuple[int, ...] = (507, 511, 515, 519, 523, 527, 531, 535, 539)
BAR_2_TILT_ADDR: int = 544
BAR_2_CELL_ADDRS: tuple[int, ...] = (550, 554, 558, 562, 566, 570, 574, 578, 582)
PAR_ADDRS: tuple[int, ...] = (600, 607, 614)

#: The synthetic active test venue, per lighting_property.ExecVenueId.
ACTIVE_VENUE_ID: int = 2
ACTIVE_VENUE_NAME: str = "TestVenue"


def insert_venue_row(
    conn: sqlite3.Connection,
    *,
    venue_id: int = ACTIVE_VENUE_ID,
    name: str = ACTIVE_VENUE_NAME,
    order: int = 1,
    enabled: int = 1,
) -> int:
    conn.execute(
        'INSERT INTO venue (id, name, "order", enabled) VALUES (?, ?, ?, ?)',
        (venue_id, name, order, enabled),
    )
    conn.commit()
    return venue_id


def insert_fixture_row(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    name: str,
    venue_id: int = ACTIVE_VENUE_ID,
    fixture_master_id: int = LM70S_MASTER_ID,
    macro_fixture_id: int = 11,
    mode_num: int = 1,
    universe_num: int = 1,
    start_addr: int = 1,
    color_num: int = 0,
    order: int = 0,
    offset_x: int = 127,
    offset_y: int = 127,
    limit_min_x: int = 0,
    limit_max_x: int = 255,
    limit_min_y: int = 0,
    limit_max_y: int = 255,
    tilt_reversal: int = 0,
) -> int:
    """A fixture row. offset_x/offset_y default to 127/127 — the centred
    placeholder rekordbox itself stores (see preview requirements: this
    value is NEVER a real physical layout position).
    """
    conn.execute(
        "INSERT INTO fixture ("
        "id, name, venue_id, fixture_master_id, mode_num, macro_fixture_id, "
        'universe_num, start_addr, color_num, "order", offset_x, offset_y, '
        "limit_min_x, limit_max_x, limit_min_y, limit_max_y, tilt_reversal"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fixture_id,
            name,
            venue_id,
            fixture_master_id,
            mode_num,
            macro_fixture_id,
            universe_num,
            start_addr,
            color_num,
            order,
            offset_x,
            offset_y,
            limit_min_x,
            limit_max_x,
            limit_min_y,
            limit_max_y,
            tilt_reversal,
        ),
    )
    conn.commit()
    return fixture_id


def set_lighting_property(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO lighting_property (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()


def a_venue(
    conn: sqlite3.Connection,
    *,
    venue_id: int = ACTIVE_VENUE_ID,
    name: str = ACTIVE_VENUE_NAME,
) -> int:
    return insert_venue_row(conn, venue_id=venue_id, name=name)


def a_moving_head_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    venue_id: int = ACTIVE_VENUE_ID,
    macro_fixture_id: int = 11,
    name: str = "LM70S #1",
) -> int:
    return insert_fixture_row(
        conn,
        fixture_id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=LM70S_MASTER_ID,
        macro_fixture_id=macro_fixture_id,
    )


def a_tilt_block_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    venue_id: int = ACTIVE_VENUE_ID,
    macro_fixture_id: int = 111,
    name: str = "Bar 1 Tilt",
) -> int:
    return insert_fixture_row(
        conn,
        fixture_id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=TILT_BLOCK_MASTER_ID,
        macro_fixture_id=macro_fixture_id,
    )


def a_bar_cell_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    venue_id: int = ACTIVE_VENUE_ID,
    macro_fixture_id: int = 5,
    name: str = "Bar 1 Cell 1",
) -> int:
    return insert_fixture_row(
        conn,
        fixture_id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=PIXEL_CELL_MASTER_ID,
        macro_fixture_id=macro_fixture_id,
    )


def a_par_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    venue_id: int = ACTIVE_VENUE_ID,
    macro_fixture_id: int = 1,
    name: str = "LPC008S #1",
) -> int:
    return insert_fixture_row(
        conn,
        fixture_id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=PAR_MASTER_ID,
        macro_fixture_id=macro_fixture_id,
    )


def an_unclassified_fixture(
    conn: sqlite3.Connection,
    *,
    fixture_id: int,
    venue_id: int = ACTIVE_VENUE_ID,
    macro_fixture_id: int = 17,
    name: str = "Unknown Rig Fixture",
) -> int:
    """A fixture whose master id matches none of the 4 known rig hardware
    profiles — exercises the classification fallback."""
    return insert_fixture_row(
        conn,
        fixture_id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=UNKNOWN_MASTER_ID,
        macro_fixture_id=macro_fixture_id,
    )


def a_small_full_arc_venue(conn: sqlite3.Connection) -> int:
    """Seeds a small slice of the synthetic active test venue (id=2,
    TestVenue): 2 moving heads, 1 tilt block, 2 bar cells, 1 par —
    ordinary case, no slot collisions.
    """
    venue_id = a_venue(conn)
    a_moving_head_fixture(conn, fixture_id=1, macro_fixture_id=11, name="LM70S #1")
    a_moving_head_fixture(conn, fixture_id=2, macro_fixture_id=12, name="LM70S #2")
    a_tilt_block_fixture(conn, fixture_id=3, macro_fixture_id=111, name="Bar 1 Tilt")
    a_bar_cell_fixture(conn, fixture_id=4, macro_fixture_id=5, name="Bar 1 Cell 2")
    a_bar_cell_fixture(conn, fixture_id=5, macro_fixture_id=16, name="Bar 1 Cell 1")
    a_par_fixture(conn, fixture_id=6, macro_fixture_id=1, name="LPC008S #1")
    return venue_id


def a_venue_with_slot_collisions(conn: sqlite3.Connection) -> int:
    """Mirrors the synthetic test rig's documented slot-collision shape
    (physical-rig-profile skill): 3 fixtures sharing macro_fixture_id=16
    (Mirrorball Spot), plus 2 more slots doubled up (macro_fixture_id=5
    and =12).
    """
    venue_id = a_venue(conn)
    # Three fixtures on the same slot (16).
    a_bar_cell_fixture(conn, fixture_id=10, macro_fixture_id=16, name="Bar 1 Cell 1")
    a_bar_cell_fixture(conn, fixture_id=11, macro_fixture_id=16, name="Bar 2 Cell 1")
    a_moving_head_fixture(conn, fixture_id=12, macro_fixture_id=16, name="Spare Head")
    # Two more doubled-up slots.
    a_bar_cell_fixture(conn, fixture_id=13, macro_fixture_id=5, name="Bar 1 Cell 2")
    a_bar_cell_fixture(conn, fixture_id=14, macro_fixture_id=5, name="Bar 2 Cell 2")
    a_moving_head_fixture(conn, fixture_id=15, macro_fixture_id=12, name="LM70S #2")
    a_par_fixture(conn, fixture_id=16, macro_fixture_id=12, name="LPC008S #2")
    return venue_id


# ---------------------------------------------------------------------------
# In-memory Fixture dataclass factory — for tests exercising pure functions
# (rbxlight.preview.layout) that operate on Fixture objects directly, with
# no database involved at all.
# ---------------------------------------------------------------------------


def a_fixture_model(
    *,
    fixture_id: int,
    name: str = "LM70S #1",
    venue_id: int = ACTIVE_VENUE_ID,
    fixture_master_id: int = LM70S_MASTER_ID,
    macro_fixture_id: int = 11,
    mode_num: int = 1,
    universe_num: int = 1,
    start_addr: int = 1,
    color_num: int = 0,
    order: int = 0,
    offset_x: int = 127,
    offset_y: int = 127,
    limit_min_x: int = 0,
    limit_max_x: int = 255,
    limit_min_y: int = 0,
    limit_max_y: int = 255,
    tilt_reversal: int = 0,
) -> Fixture:
    """A real Fixture dataclass instance — no database involved. Used by
    rbxlight.preview.layout tests, which take `Sequence[Fixture]` directly.
    """
    return Fixture(
        id=fixture_id,
        name=name,
        venue_id=venue_id,
        fixture_master_id=fixture_master_id,
        mode_num=mode_num,
        macro_fixture_id=macro_fixture_id,
        universe_num=universe_num,
        start_addr=start_addr,
        color_num=color_num,
        order=order,
        offset_x=offset_x,
        offset_y=offset_y,
        limit_min_x=limit_min_x,
        limit_max_x=limit_max_x,
        limit_min_y=limit_min_y,
        limit_max_y=limit_max_y,
        tilt_reversal=tilt_reversal,
    )


def a_full_arc_fixture_list() -> list[Fixture]:
    """The synthetic test venue's (id=2, TestVenue) 27-fixture
    composition, in the same repository order rbxlight.venues.repo
    actually returns fixtures in — NOT the convenient
    `tilt, its 9 cells, tilt, its 9 cells` ordering this factory used to
    fabricate (that convenient ordering masked a real bar/cell-grouping
    bug; see rbxlight.preview.layout.generate_layout's regression tests):

    tilt_block x2, moving_head x4, bar_cell x18, par x3 — BOTH tilt
    blocks arrive before any cell.

    Synthetic DMX start addresses (see the *_ADDR(S) constants above) are
    set on every fixture, since rbxlight.preview.layout.generate_layout
    must group each bar's 9 cells with its tilt block by DMX ADDRESS, not
    by list position:

    - bar 1's tilt (ch501) owns cells at ch507-539 ("Bar 1 Cell 1".."9")
    - bar 2's tilt (ch544) owns cells at ch550-582 ("Bar 2 Cell 1".."9")
    - moving heads 1-2 (list order) -> the two diagonal segments; heads
      3-4 (list order) -> the horizontal top segment
    - the 3 par fixtures split left/right (first half of the list left,
      remainder right)

     Deliberately excludes any entry for the fogger/smoke machine — it has
     no DMX fixture-table presence (direct_control only, see
     physical-rig-profile skill), so no fixture row exists for it in any
     real venue and none should be fabricated here.
    """
    fixtures: list[Fixture] = []
    fixture_id = 1

    for bar, addr in ((1, BAR_1_TILT_ADDR), (2, BAR_2_TILT_ADDR)):
        fixtures.append(
            a_fixture_model(
                fixture_id=fixture_id,
                name=f"Bar {bar} Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=addr,
            )
        )
        fixture_id += 1

    for i, addr in enumerate(HEAD_ADDRS, start=1):
        fixtures.append(
            a_fixture_model(
                fixture_id=fixture_id,
                name=f"LM70S #{i}",
                fixture_master_id=LM70S_MASTER_ID,
                start_addr=addr,
            )
        )
        fixture_id += 1

    for bar, addrs in ((1, BAR_1_CELL_ADDRS), (2, BAR_2_CELL_ADDRS)):
        for cell, addr in enumerate(addrs, start=1):
            fixtures.append(
                a_fixture_model(
                    fixture_id=fixture_id,
                    name=f"Bar {bar} Cell {cell}",
                    fixture_master_id=PIXEL_CELL_MASTER_ID,
                    start_addr=addr,
                )
            )
            fixture_id += 1

    for i, addr in enumerate(PAR_ADDRS, start=1):
        fixtures.append(
            a_fixture_model(
                fixture_id=fixture_id,
                name=f"LPC008S #{i}",
                fixture_master_id=PAR_MASTER_ID,
                start_addr=addr,
            )
        )
        fixture_id += 1

    return fixtures
