"""Factories that seed macro_pattern/macro_assign rows into a throwaway
macro.db3 connection (see conftest.make_macro_db / macro_db_conn) for
rbxlight.macros.patterns tests and the ninth-bank experiment tests.

These build REAL rows in a real (throwaway) SQLite connection — not mocks.

Real-world shape (rekordbox-lightingdb-schema skill, "macro_pattern",
"How macros get selected for a track"): 27 rows, ids 1..27, `pattern` holds
1..8 for the eight named banks plus 99 for the INTERLUDE (non-bank) case,
`energy` is 1=HIGH/2=MID/3=LOW, and phase count depends on energy: 11 for
HIGH, 10 for MID, 6 for LOW/INTERLUDE — never uniform, never assumed.
"""

from __future__ import annotations

import sqlite3

#: energy codes — see rekordbox-lightingdb-schema skill ("macro_pattern").
ENERGY_HIGH: int = 1
ENERGY_MID: int = 2
ENERGY_LOW: int = 3

#: Real-world phase counts per energy (rekordbox-lightingdb-schema skill,
#: "How macros get selected for a track"). Deliberately NOT uniform —
#: tests must exercise more than one of these to prove phase count is
#: copied from the source bank, never assumed.
PHASE_COUNT_BY_ENERGY: dict[int, int] = {ENERGY_HIGH: 11, ENERGY_MID: 10, ENERGY_LOW: 6}

#: The 9 real pattern values per energy: 1..8 (named banks) + 99 (INTERLUDE).
REAL_PATTERN_VALUES: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8, 99)


def insert_macro_pattern_row(
    conn: sqlite3.Connection,
    *,
    pattern_id: int,
    energy: int = ENERGY_HIGH,
    pattern: int = 1,
) -> int:
    conn.execute(
        "INSERT INTO macro_pattern (id, energy, pattern) VALUES (?, ?, ?)",
        (pattern_id, energy, pattern),
    )
    conn.commit()
    return pattern_id


def insert_macro_assign_row(
    conn: sqlite3.Connection,
    *,
    macro_pattern_id: int,
    phase: int,
    macro_id: int = 100,
    initial_macro_id: int | None = None,
) -> None:
    conn.execute(
        "INSERT INTO macro_assign "
        "(macro_pattern_id, phase, macro_id, initial_macro_id) VALUES (?, ?, ?, ?)",
        (
            macro_pattern_id,
            phase,
            macro_id,
            initial_macro_id if initial_macro_id is not None else macro_id,
        ),
    )
    conn.commit()


def a_macro_pattern_with_phases(
    conn: sqlite3.Connection,
    *,
    pattern_id: int,
    energy: int = ENERGY_HIGH,
    pattern: int = 1,
    phase_count: int = PHASE_COUNT_BY_ENERGY[ENERGY_HIGH],
    macro_id_base: int = 1000,
) -> int:
    """A macro_pattern row plus `phase_count` macro_assign rows (phase
    1..phase_count) — a realistic "bank" ready to clone phase assignments
    from. `phase_count` defaults to the real HIGH-energy count (11); pass
    PHASE_COUNT_BY_ENERGY[ENERGY_MID] (10) etc. for a different bank so
    tests can prove phase count is copied, not assumed.
    """
    insert_macro_pattern_row(
        conn, pattern_id=pattern_id, energy=energy, pattern=pattern
    )
    for phase in range(1, phase_count + 1):
        insert_macro_assign_row(
            conn,
            macro_pattern_id=pattern_id,
            phase=phase,
            macro_id=macro_id_base + phase,
        )
    return pattern_id


def a_high_energy_bank(conn: sqlite3.Connection, *, pattern_id: int = 1) -> int:
    """A HIGH-energy (11-phase) bank — one of the two phase counts
    required by "the phase count is copied, never assumed"."""
    return a_macro_pattern_with_phases(
        conn,
        pattern_id=pattern_id,
        energy=ENERGY_HIGH,
        pattern=1,
        phase_count=PHASE_COUNT_BY_ENERGY[ENERGY_HIGH],
    )


def a_mid_energy_bank(conn: sqlite3.Connection, *, pattern_id: int = 2) -> int:
    """A MID-energy (10-phase) bank — the other phase count required by
    "the phase count is copied, never assumed"."""
    return a_macro_pattern_with_phases(
        conn,
        pattern_id=pattern_id,
        energy=ENERGY_MID,
        pattern=1,
        phase_count=PHASE_COUNT_BY_ENERGY[ENERGY_MID],
    )


def the_27_real_macro_patterns(conn: sqlite3.Connection) -> None:
    """Seeds the real-world shape: 27 rows, ids 1..27 — 3 energies x 9
    pattern values (1..8 + 99), each with its real-world phase count.
    Used for id-allocation tests grounded in the actual library shape
    (new bank -> id 28).
    """
    pattern_id = 1
    for energy in (ENERGY_HIGH, ENERGY_MID, ENERGY_LOW):
        for pattern in REAL_PATTERN_VALUES:
            a_macro_pattern_with_phases(
                conn,
                pattern_id=pattern_id,
                energy=energy,
                pattern=pattern,
                phase_count=PHASE_COUNT_BY_ENERGY[energy],
                macro_id_base=pattern_id * 100,
            )
            pattern_id += 1


def non_contiguous_macro_patterns(conn: sqlite3.Connection) -> tuple[int, ...]:
    """A deliberately sparse, non-contiguous set of macro_pattern ids
    (1, 5, 9, 40) — proves id allocation is derived from the actual
    current maximum, never hardcoded to "one past 27". Returns the ids
    seeded.
    """
    ids = (1, 5, 9, 40)
    for pattern_id in ids:
        a_macro_pattern_with_phases(conn, pattern_id=pattern_id, phase_count=1)
    return ids
