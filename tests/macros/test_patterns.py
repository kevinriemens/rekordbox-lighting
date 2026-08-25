"""Tests for rbxlight.macros.patterns — macro_pattern (the bank/energy
combinations) and macro_assign (phase -> concrete macro mapping) read/write.

Permanent, reusable repo functions — see rekordbox-lighting-architecture
skill on repo-vs-orchestration placement: this module is the permanent
repo layer, distinct from disposable one-off orchestration scripts built
on top of it.

Contract sources: rekordbox-lightingdb-schema skill ("macro_pattern",
"macro_assign", "How macros get selected for a track") +
rekordbox-data-safety skill (id allocation must never be hardcoded, see
"macro preset / id-range convention" for the analogous macro.id rule).

`conn` is always passed in — this module never opens its own connection.
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight.macros import patterns
from tests.fixtures.pattern_fixtures import (
    ENERGY_HIGH,
    ENERGY_MID,
    PHASE_COUNT_BY_ENERGY,
    a_high_energy_bank,
    a_macro_pattern_with_phases,
    a_mid_energy_bank,
    insert_macro_pattern_row,
    non_contiguous_macro_patterns,
    the_27_real_macro_patterns,
)


class TestGetMacroPattern:
    def test_should_return_the_matching_row(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a seeded macro_pattern row
        insert_macro_pattern_row(macro_db_conn, pattern_id=3, energy=2, pattern=5)

        # When: fetching it
        result = patterns.get_macro_pattern(macro_db_conn, 3)

        # Then: fields match what was seeded
        assert result.id == 3
        assert result.energy == 2
        assert result.pattern == 5

    def test_should_raise_lookup_error_for_a_nonexistent_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no macro_pattern row with this id
        # When / Then: a clear, predictable failure
        with pytest.raises(LookupError):
            patterns.get_macro_pattern(macro_db_conn, 99999)


class TestListMacroPatterns:
    def test_should_return_empty_list_for_an_empty_table(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no macro_pattern rows at all
        # When: listing
        result = patterns.list_macro_patterns(macro_db_conn)

        # Then: empty, not an error
        assert result == []

    def test_should_list_all_27_real_world_rows_ordered_by_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real-world 27-row shape
        the_27_real_macro_patterns(macro_db_conn)

        # When: listing
        result = patterns.list_macro_patterns(macro_db_conn)

        # Then: 27 rows, ascending id order
        assert len(result) == 27
        assert [row.id for row in result] == list(range(1, 28))


class TestMacroPatternIdAllocation:
    """Requirement: the new bank's id is derived from what's already in
    the table (one past the current maximum), never hardcoded.
    """

    def test_should_allocate_one_past_the_real_world_maximum(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real-world 27-row shape (max id = 27)
        the_27_real_macro_patterns(macro_db_conn)

        # When: creating a new bank
        created = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=9)

        # Then: id = 28, never hardcoded
        assert created.id == 28

    def test_should_allocate_one_past_a_non_contiguous_maximum(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a database whose existing max id (40) is NOT 27 — proves
        # allocation is derived from actual contents, not assumed
        non_contiguous_macro_patterns(macro_db_conn)

        # When: creating a new bank
        created = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=9)

        # Then: id = 41, one past the true maximum
        assert created.id == 41

    def test_should_allocate_id_1_for_an_empty_table(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no macro_pattern rows at all
        # When: creating the first bank
        created = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=1)

        # Then: id = 1
        assert created.id == 1

    def test_should_never_collide_across_successive_creations(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real-world 27-row shape
        the_27_real_macro_patterns(macro_db_conn)

        # When: creating two new banks back to back
        first = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=9)
        second = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=9)

        # Then: strictly increasing, no collision
        assert first.id == 28
        assert second.id == 29

    def test_should_store_the_given_energy_and_pattern_value(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an empty table
        # When: creating a bank with the "unknown" pattern value 9
        created = patterns.create_macro_pattern(macro_db_conn, energy=ENERGY_HIGH, pattern=9)

        # Then: fields round-trip via a fresh read
        fetched = patterns.get_macro_pattern(macro_db_conn, created.id)
        assert fetched.energy == ENERGY_HIGH
        assert fetched.pattern == 9


class TestListMacroAssign:
    def test_should_return_empty_list_when_pattern_has_no_phase_rows(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro_pattern row with zero macro_assign rows
        insert_macro_pattern_row(macro_db_conn, pattern_id=1)

        # When: listing its phase assignments
        result = patterns.list_macro_assign(macro_db_conn, 1)

        # Then: empty, not an error
        assert result == []

    def test_should_return_rows_ordered_by_phase(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a HIGH-energy bank with 11 phases
        a_high_energy_bank(macro_db_conn, pattern_id=1)

        # When: listing
        result = patterns.list_macro_assign(macro_db_conn, 1)

        # Then: exactly 11 rows, ascending phase order
        assert [row.phase for row in result] == list(range(1, 12))
        assert all(row.macro_pattern_id == 1 for row in result)


class TestCloneMacroAssign:
    """Requirement: the phase count is copied, never assumed — different
    banks genuinely have different phase counts. Covered with two source
    banks of different phase counts (11 and 10).
    """

    def test_should_create_exactly_11_rows_when_source_is_high_energy(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a HIGH-energy source bank (11 real phases) and an empty
        # target bank row
        a_high_energy_bank(macro_db_conn, pattern_id=1)
        insert_macro_pattern_row(macro_db_conn, pattern_id=28, energy=ENERGY_HIGH, pattern=9)

        # When: cloning phase assignments
        created = patterns.clone_macro_assign(
            macro_db_conn, source_pattern_id=1, target_pattern_id=28
        )

        # Then: row count follows the SOURCE's actual count (11), not a
        # hardcoded assumption
        assert len(created) == PHASE_COUNT_BY_ENERGY[ENERGY_HIGH] == 11
        assert len(patterns.list_macro_assign(macro_db_conn, 28)) == 11

    def test_should_create_exactly_10_rows_when_source_is_mid_energy(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a MID-energy source bank (10 real phases) — a DIFFERENT
        # phase count from the HIGH case above
        a_mid_energy_bank(macro_db_conn, pattern_id=2)
        insert_macro_pattern_row(macro_db_conn, pattern_id=28, energy=ENERGY_MID, pattern=9)

        # When: cloning phase assignments
        created = patterns.clone_macro_assign(
            macro_db_conn, source_pattern_id=2, target_pattern_id=28
        )

        # Then: row count follows the SOURCE's actual count (10)
        assert len(created) == PHASE_COUNT_BY_ENERGY[ENERGY_MID] == 10
        assert len(patterns.list_macro_assign(macro_db_conn, 28)) == 10

    def test_should_target_the_given_pattern_id_not_the_source(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a source bank and a distinct target bank
        a_high_energy_bank(macro_db_conn, pattern_id=1)
        insert_macro_pattern_row(macro_db_conn, pattern_id=28)

        # When: cloning
        created = patterns.clone_macro_assign(
            macro_db_conn, source_pattern_id=1, target_pattern_id=28
        )

        # Then: every created row is stamped with the TARGET id
        assert all(row.macro_pattern_id == 28 for row in created)
        # And the source's own rows are untouched (still 11)
        assert len(patterns.list_macro_assign(macro_db_conn, 1)) == 11

    def test_should_preserve_phase_macro_id_and_initial_macro_id_per_row(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a source bank with distinct macro_id values per phase
        a_macro_pattern_with_phases(
            macro_db_conn, pattern_id=1, phase_count=3, macro_id_base=5000
        )
        insert_macro_pattern_row(macro_db_conn, pattern_id=28)

        # When: cloning
        created = patterns.clone_macro_assign(
            macro_db_conn, source_pattern_id=1, target_pattern_id=28
        )

        # Then: phase/macro_id/initial_macro_id carried over exactly,
        # only macro_pattern_id changes
        by_phase = {row.phase: row for row in created}
        assert by_phase[1].macro_id == 5001
        assert by_phase[2].macro_id == 5002
        assert by_phase[3].macro_id == 5003
        assert all(row.initial_macro_id == row.macro_id for row in created)

    def test_should_raise_lookup_error_when_source_has_no_assign_rows(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro_pattern row that exists but has zero macro_assign
        # rows — nothing to clone
        insert_macro_pattern_row(macro_db_conn, pattern_id=1)
        insert_macro_pattern_row(macro_db_conn, pattern_id=28)

        # When / Then: a clear failure, not a silent 0-row clone
        with pytest.raises(LookupError):
            patterns.clone_macro_assign(
                macro_db_conn, source_pattern_id=1, target_pattern_id=28
            )

    def test_should_write_nothing_when_source_pattern_does_not_exist_at_all(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: source_pattern_id refers to no macro_pattern row
        insert_macro_pattern_row(macro_db_conn, pattern_id=28)

        # When / Then: raises, and nothing was created for the target
        with pytest.raises(LookupError):
            patterns.clone_macro_assign(
                macro_db_conn, source_pattern_id=99999, target_pattern_id=28
            )
        assert patterns.list_macro_assign(macro_db_conn, 28) == []


class TestDeleteMacroPatternAndAssign:
    """Undo primitives — used by the ninth-bank experiment's revert path."""

    def test_delete_macro_pattern_should_remove_the_row(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an existing macro_pattern row
        insert_macro_pattern_row(macro_db_conn, pattern_id=28, pattern=9)

        # When: deleting it
        patterns.delete_macro_pattern(macro_db_conn, 28)

        # Then: gone
        with pytest.raises(LookupError):
            patterns.get_macro_pattern(macro_db_conn, 28)

    def test_delete_macro_assign_should_remove_every_phase_row(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a bank with cloned phase assignments
        a_high_energy_bank(macro_db_conn, pattern_id=28)

        # When: deleting its phase assignments
        patterns.delete_macro_assign(macro_db_conn, 28)

        # Then: none remain
        assert patterns.list_macro_assign(macro_db_conn, 28) == []

    def test_delete_macro_pattern_should_be_a_safe_no_op_when_absent(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no row with this id — deleting must not raise, so a
        # double-revert or defensive cleanup call is always safe
        # When / Then: no exception
        patterns.delete_macro_pattern(macro_db_conn, 99999)

    def test_delete_macro_assign_should_be_a_safe_no_op_when_absent(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no macro_assign rows for this pattern id
        # When / Then: no exception
        patterns.delete_macro_assign(macro_db_conn, 99999)
