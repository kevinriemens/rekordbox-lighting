"""Tests for rbxlight.macros.repo — macro.db3 read/write, id allocation,
25-row invariant, factory immutability. Contract: rekordbox-data-safety
skill ("The 25-row invariant") and rekordbox-lightingdb-schema skill
("macro preset / id-range convention").
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight.macros import repo
from rbxlight.macros.repo import FactoryMacroImmutableError
from rbxlight.models import FIXTURE_SLOT_IDS
from tests.fixtures.macro_fixtures import (
    ALL_25_SLOT_IDS,
    a_factory_macro,
    a_macro_with_19_rows,
    a_macro_with_150_rows,
    a_macro_with_unknown_fixture_id_rows,
    a_user_macro,
    a_valid_slot_payload,
    sentinel_macro_rows,
)


class TestCreateMacroWritesExactly25Rows:
    def test_should_write_one_row_per_fixture_slot(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a payload for every slot
        payloads = {slot_id: a_valid_slot_payload() for slot_id in ALL_25_SLOT_IDS}

        # When: creating a new macro
        macro = repo.create_macro(
            macro_db_conn, name="NEW MACRO", beats=32, payloads=payloads
        )
        rows = repo.list_macro_data(macro_db_conn, macro.id)

        # Then: exactly 25 rows, one per slot
        assert len(rows) == 25
        assert {row.macro_fixture_id for row in rows} == set(FIXTURE_SLOT_IDS)

    def test_should_never_write_fewer_than_25_rows_when_payloads_are_partial(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: only 3 of the 25 slots have programming
        partial_payloads = {
            1: a_valid_slot_payload(),
            5: a_valid_slot_payload(),
            11: a_valid_slot_payload(),
        }

        # When: creating a new macro
        macro = repo.create_macro(
            macro_db_conn, name="PARTIAL", beats=32, payloads=partial_payloads
        )
        rows = repo.list_macro_data(macro_db_conn, macro.id)

        # Then: still exactly 25 rows
        assert len(rows) == 25

    def test_should_store_unprogrammed_slots_as_empty_string_not_missing_or_null(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: only slot 1 has programming
        payloads = {1: a_valid_slot_payload()}

        # When: creating a new macro
        macro = repo.create_macro(
            macro_db_conn, name="MOSTLY EMPTY", beats=32, payloads=payloads
        )
        rows = {
            row.macro_fixture_id: row
            for row in repo.list_macro_data(macro_db_conn, macro.id)
        }

        # Then: every other slot is present with data == "" (not missing, not None)
        for slot_id in ALL_25_SLOT_IDS:
            if slot_id == 1:
                continue
            assert slot_id in rows
            assert rows[slot_id].xml == ""
            assert rows[slot_id].xml is not None


class TestMacroIdAllocation:
    def test_should_allocate_id_in_user_range_above_factory_range_when_no_user_macros_exist(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: only factory macros exist (ids well below the user range)
        a_factory_macro(macro_db_conn, macro_id=61)
        a_factory_macro(macro_db_conn, macro_id=916)

        # When: creating a new (first) user macro
        macro = repo.create_macro(
            macro_db_conn, name="FIRST USER MACRO", beats=32, payloads={}
        )

        # Then: it lands in the user range, above the factory range
        assert macro.id >= 10001
        assert macro.preset == 0

    def test_should_never_collide_with_an_existing_macro_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an existing user macro at id 10005
        a_user_macro(macro_db_conn, macro_id=10005)

        # When: creating another new macro
        macro = repo.create_macro(
            macro_db_conn, name="NEXT USER MACRO", beats=32, payloads={}
        )

        # Then: the new id is strictly greater than every existing id
        assert macro.id > 10005

    def test_should_allocate_sequential_ids_across_multiple_creates(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an empty macro library
        # When: creating two macros back to back
        first = repo.create_macro(macro_db_conn, name="ONE", beats=32, payloads={})
        second = repo.create_macro(macro_db_conn, name="TWO", beats=32, payloads={})

        # Then: distinct, non-colliding ids
        assert second.id != first.id
        assert second.id > first.id


class TestFactoryMacroImmutability:
    def test_should_refuse_to_update_a_factory_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a factory (preset=1) macro
        macro_id = a_factory_macro(macro_db_conn, macro_id=61)

        # When / Then: updating any of its slots is refused
        with pytest.raises(FactoryMacroImmutableError):
            repo.update_macro_data(macro_db_conn, macro_id, 1, a_valid_slot_payload())

    def test_should_refuse_to_delete_a_factory_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a factory (preset=1) macro
        macro_id = a_factory_macro(macro_db_conn, macro_id=61)

        # When / Then: deleting it is refused
        with pytest.raises(FactoryMacroImmutableError):
            repo.delete_macro(macro_db_conn, macro_id)

    def test_should_allow_updating_a_user_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user (preset=0) macro
        macro_id = a_user_macro(macro_db_conn, macro_id=10001)

        # When: updating one of its slots
        repo.update_macro_data(macro_db_conn, macro_id, 1, a_valid_slot_payload())
        rows = {
            row.macro_fixture_id: row
            for row in repo.list_macro_data(macro_db_conn, macro_id)
        }

        # Then: the change is applied
        assert rows[1].xml == a_valid_slot_payload()

    @pytest.mark.parametrize("sentinel_id", [-1, 10000])
    def test_should_refuse_to_update_a_sentinel_row(
        self, macro_db_conn: sqlite3.Connection, sentinel_id: int
    ) -> None:
        # Given: the real sentinel rows (negative id, SEPARATOR id) — both preset=1
        sentinel_macro_rows(macro_db_conn)

        # When / Then: touching a sentinel row is refused like any factory row
        with pytest.raises(FactoryMacroImmutableError):
            repo.update_macro_data(
                macro_db_conn, sentinel_id, 1, a_valid_slot_payload()
            )


class TestTolerantReads:
    def test_should_not_crash_on_legacy_19_row_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro stored in the older, pre-Simple-slot 19-row format
        macro_id = a_macro_with_19_rows(macro_db_conn, macro_id=500)

        # When: reading it
        rows = repo.list_macro_data(macro_db_conn, macro_id)

        # Then: no crash, and only the 19 stored rows are returned
        assert len(rows) == 19

    def test_should_not_crash_on_150_row_anomaly_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the known factory-library anomaly (150 macro_data rows)
        macro_id = a_macro_with_150_rows(macro_db_conn, macro_id=999)

        # When: reading it
        rows = repo.list_macro_data(macro_db_conn, macro_id)

        # Then: no crash — reading tolerates the anomalous row count
        assert len(rows) > 0

    def test_should_ignore_rows_with_unknown_fixture_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with 2 rows whose macro_fixture_id isn't one of the 25 known slots
        macro_id = a_macro_with_unknown_fixture_id_rows(macro_db_conn, macro_id=998)

        # When: reading it
        rows = repo.list_macro_data(macro_db_conn, macro_id)

        # Then: only rows resolving to a known slot are returned
        assert all(row.macro_fixture_id in FIXTURE_SLOT_IDS for row in rows)
        assert len(rows) == 25

    @pytest.mark.parametrize("sentinel_id", [-1, 10000])
    def test_should_not_crash_reading_sentinel_macro_rows(
        self, macro_db_conn: sqlite3.Connection, sentinel_id: int
    ) -> None:
        # Given: the real sentinel rows exist in the library
        sentinel_macro_rows(macro_db_conn)

        # When: fetching a sentinel "macro"
        macro = repo.get_macro(macro_db_conn, sentinel_id)

        # Then: no crash, and it's reported as factory/non-writable content
        assert macro.id == sentinel_id
        assert macro.preset == 1
