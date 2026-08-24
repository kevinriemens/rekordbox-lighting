"""Tests for rbxlight.macros.repo — read-only macro listing/search queries.

These test the repo-level query functions (list_macros, search_macros) that
power the CLI subcommands `macro list`, `macro search`, and `macro show`.
Contract: read-only guarantee, deterministic id ordering, scope filtering
(preset=0/1/both), case-insensitive LIKE, literal wildcard characters,
and tolerance for empty DBs.
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight.macros import repo
from tests.fixtures.macro_fixtures import (
    ALL_25_SLOT_IDS,
    a_factory_macro,
    a_user_macro,
    a_valid_slot_payload,
    sentinel_macro_rows,
)

# ---------------------------------------------------------------------------
# Scope enum values used by list_macros / search_macros
# ---------------------------------------------------------------------------
_SCOPE_USER = "user"
_SCOPE_FACTORY = "factory"
_SCOPE_ALL = "all"


# ---------------------------------------------------------------------------
# list_macros — filtered macro listing
# ---------------------------------------------------------------------------


class TestListMacrosReturnsFilteredResults:
    def test_should_return_only_user_macros_by_default(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: one user macro and one factory macro
        a_user_macro(macro_db_conn, macro_id=10001, name="USER ONE")
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY ONE")

        # When: listing with default scope (user-only)
        macros = repo.list_macros(macro_db_conn)

        # Then: only the user macro is returned
        assert len(macros) == 1
        assert macros[0].id == 10001
        assert macros[0].name == "USER ONE"

    def test_should_return_user_macros_explicitly(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: one user macro and one factory macro
        a_user_macro(macro_db_conn, macro_id=10001, name="USER ONE")
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY ONE")

        # When: listing with explicit user scope
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_USER)

        # Then: only the user macro is returned
        assert len(macros) == 1
        assert macros[0].id == 10001

    def test_should_return_factory_macros_when_factory_scope(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: one user macro and one factory macro
        a_user_macro(macro_db_conn, macro_id=10001, name="USER ONE")
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY ONE")

        # When: listing with factory scope
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_FACTORY)

        # Then: only the factory macro is returned
        assert len(macros) == 1
        assert macros[0].id == 61
        assert macros[0].name == "FACTORY ONE"

    def test_should_return_both_user_and_factory_macros_with_all_scope(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: one user macro and one factory macro
        a_user_macro(macro_db_conn, macro_id=10001, name="USER ONE")
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY ONE")

        # When: listing with all scope
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_ALL)

        # Then: both macros are returned
        assert len(macros) == 2
        ids = [m.id for m in macros]
        assert 61 in ids
        assert 10001 in ids

    def test_should_order_results_by_id_ascending_regardless_of_insertion_order(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: macros inserted in reverse id order
        a_user_macro(macro_db_conn, macro_id=10010, name="LATER")
        a_user_macro(macro_db_conn, macro_id=10001, name="EARLIER")
        a_user_macro(macro_db_conn, macro_id=10005, name="MIDDLE")

        # When: listing (all scope to include everything)
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_ALL)

        # Then: returned in ascending id order, not insertion order
        assert [m.id for m in macros] == [10001, 10005, 10010]

    def test_should_include_sentinel_rows_in_factory_scope(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the two sentinel rows (id=-1, id=10000) exist
        sentinel_macro_rows(macro_db_conn)

        # When: listing with factory scope
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_FACTORY)

        # Then: both sentinel rows are present (they are preset=1)
        ids = [m.id for m in macros]
        assert -1 in ids
        assert 10000 in ids

    def test_should_not_crash_on_sentinel_rows_with_show(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the two sentinel rows exist
        sentinel_macro_rows(macro_db_conn)

        # When: fetching each sentinel via get_macro
        for sentinel_id in (-1, 10000):
            macro = repo.get_macro(macro_db_conn, sentinel_id)

            # Then: no crash, and it is factory content
            assert macro.id == sentinel_id
            assert macro.preset == 1


class TestListMacrosEmptyDatabase:
    def test_should_return_empty_list_when_no_macros_exist(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an empty macro library (no macro rows at all)
        # When: listing with any scope
        for scope in (_SCOPE_USER, _SCOPE_FACTORY, _SCOPE_ALL):
            macros = repo.list_macros(macro_db_conn, scope=scope)

            # Then: empty list, not an error
            assert macros == []

    def test_should_return_empty_list_when_only_factory_macros_exist_and_user_scope(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: only factory macros
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY")

        # When: listing with user scope
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_USER)

        # Then: empty list
        assert macros == []


# ---------------------------------------------------------------------------
# search_macros — case-insensitive substring search
# ---------------------------------------------------------------------------


class TestSearchMacrosCaseInsensitive:
    def test_should_match_name_case_insensitively(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro named "CHORUS HIT"
        a_user_macro(macro_db_conn, macro_id=10001, name="CHORUS HIT")

        # When: searching with lowercase term
        results = repo.search_macros(macro_db_conn, "chorus", scope=_SCOPE_USER)

        # Then: it matches
        assert len(results) == 1
        assert results[0].id == 10001

    def test_should_match_uppercase_term_against_lowercased_name(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro named "chorus cool"
        a_user_macro(macro_db_conn, macro_id=10001, name="chorus cool")

        # When: searching with uppercase term
        results = repo.search_macros(macro_db_conn, "CHORUS", scope=_SCOPE_USER)

        # Then: it matches
        assert len(results) == 1
        assert results[0].id == 10001

    def test_should_match_as_substring_not_exact(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro named "HIGH DROP1"
        a_user_macro(macro_db_conn, macro_id=10001, name="HIGH DROP1")

        # When: searching for "DROP"
        results = repo.search_macros(macro_db_conn, "DROP", scope=_SCOPE_USER)

        # Then: it matches as a substring
        assert len(results) == 1
        assert results[0].id == 10001

    def test_should_return_empty_list_when_no_matches(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro named "HIGH DROP1"
        a_user_macro(macro_db_conn, macro_id=10001, name="HIGH DROP1")

        # When: searching for a term that doesn't match
        results = repo.search_macros(macro_db_conn, "CHORUS", scope=_SCOPE_USER)

        # Then: empty list, not an error
        assert results == []


class TestSearchMacrosScopeFiltering:
    def test_should_search_factory_macros_only(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user and a factory macro, both containing "CHORUS"
        a_user_macro(macro_db_conn, macro_id=10001, name="CHORUS USER")
        a_factory_macro(macro_db_conn, macro_id=61, name="CHORUS FACTORY")

        # When: searching factory scope
        results = repo.search_macros(macro_db_conn, "CHORUS", scope=_SCOPE_FACTORY)

        # Then: only the factory macro is returned
        assert len(results) == 1
        assert results[0].id == 61

    def test_should_search_all_macros_with_all_scope(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user and a factory macro, both containing "CHORUS"
        a_user_macro(macro_db_conn, macro_id=10001, name="CHORUS USER")
        a_factory_macro(macro_db_conn, macro_id=61, name="CHORUS FACTORY")

        # When: searching all scope
        results = repo.search_macros(macro_db_conn, "CHORUS", scope=_SCOPE_ALL)

        # Then: both macros are returned
        assert len(results) == 2
        ids = {m.id for m in results}
        assert ids == {61, 10001}

    def test_should_search_user_macros_by_default(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user and a factory macro, both containing "DROP"
        a_user_macro(macro_db_conn, macro_id=10001, name="DROP USER")
        a_factory_macro(macro_db_conn, macro_id=61, name="DROP FACTORY")

        # When: searching with default scope (no scope kwarg)
        results = repo.search_macros(macro_db_conn, "DROP")

        # Then: only the user macro is returned
        assert len(results) == 1
        assert results[0].id == 10001


class TestSearchMacrosOrdering:
    def test_should_order_results_by_id_ascending(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: three user macros containing "TEST", inserted out of order
        a_user_macro(macro_db_conn, macro_id=10010, name="TEST C")
        a_user_macro(macro_db_conn, macro_id=10001, name="TEST A")
        a_user_macro(macro_db_conn, macro_id=10005, name="TEST B")

        # When: searching
        results = repo.search_macros(macro_db_conn, "TEST", scope=_SCOPE_USER)

        # Then: returned in ascending id order
        assert [m.id for m in results] == [10001, 10005, 10010]


class TestSearchMacrosEmptyDatabase:
    def test_should_return_empty_list_when_no_macros_exist(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: empty macro library
        # When: searching
        results = repo.search_macros(macro_db_conn, "ANYTHING", scope=_SCOPE_ALL)

        # Then: empty list, not an error
        assert results == []


class TestSearchMacrosLiteralWildcardCharacters:
    def test_should_treat_percent_as_literal_not_wildcard(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: macros whose names contain literal percent characters
        a_user_macro(macro_db_conn, macro_id=10001, name="100% COMPLETE")
        a_user_macro(macro_db_conn, macro_id=10002, name="COMPLETE")

        # When: searching for "100%"
        results = repo.search_macros(macro_db_conn, "100%", scope=_SCOPE_USER)

        # Then: only the macro with the literal "%" in its name matches
        assert len(results) == 1
        assert results[0].id == 10001

    def test_should_treat_underscore_as_literal_not_wildcard(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: macros whose names contain literal underscore characters
        a_user_macro(macro_db_conn, macro_id=10001, name="MID DROP_COOL")
        a_user_macro(macro_db_conn, macro_id=10002, name="MID DROPXCOOL")

        # When: searching for "DROP_COOL"
        results = repo.search_macros(macro_db_conn, "DROP_COOL", scope=_SCOPE_USER)

        # Then: only the macro with the literal "_" matches
        assert len(results) == 1
        assert results[0].id == 10001

    def test_should_match_literal_percent_and_underscore_together(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with both literal % and _ in its name
        a_user_macro(macro_db_conn, macro_id=10001, name="100%_SPECIAL")

        # When: searching for "100%_"
        results = repo.search_macros(macro_db_conn, "100%_", scope=_SCOPE_USER)

        # Then: the literal match is found
        assert len(results) == 1
        assert results[0].id == 10001


# ---------------------------------------------------------------------------
# get_macro — read-only access to any macro, including factory/sentinel
# ---------------------------------------------------------------------------


class TestGetMacroReadAccess:
    def test_should_return_user_macro_by_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user macro
        a_user_macro(macro_db_conn, macro_id=10001, name="USER MACRO", beats=32)

        # When: fetching by id
        macro = repo.get_macro(macro_db_conn, 10001)

        # Then: correct fields returned
        assert macro.id == 10001
        assert macro.name == "USER MACRO"
        assert macro.beats == 32
        assert macro.preset == 0

    def test_should_return_factory_macro_by_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a factory macro
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY MACRO", beats=16)

        # When: fetching by id
        macro = repo.get_macro(macro_db_conn, 61)

        # Then: correct fields returned
        assert macro.id == 61
        assert macro.name == "FACTORY MACRO"
        assert macro.beats == 16
        assert macro.preset == 1

    def test_should_raise_lookup_error_for_nonexistent_id(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an empty macro library
        # When / Then: fetching a nonexistent id raises LookupError
        with pytest.raises(LookupError):
            repo.get_macro(macro_db_conn, 99999)

    @pytest.mark.parametrize("sentinel_id", [-1, 10000])
    def test_should_not_crash_on_sentinel_ids(
        self, macro_db_conn: sqlite3.Connection, sentinel_id: int
    ) -> None:
        # Given: the sentinel rows exist
        sentinel_macro_rows(macro_db_conn)

        # When: fetching a sentinel "macro"
        macro = repo.get_macro(macro_db_conn, sentinel_id)

        # Then: no crash, factory content
        assert macro.id == sentinel_id
        assert macro.preset == 1


# ---------------------------------------------------------------------------
# list_macro_data — the 25-slot fixture payload listing (used by show)
# ---------------------------------------------------------------------------


class TestListMacroDataForShow:
    def test_should_return_exactly_25_rows_for_a_full_macro(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a user macro with all 25 slots programmed
        macro_id = a_user_macro(macro_db_conn, macro_id=10001, name="FULL MACRO")
        for slot_id in ALL_25_SLOT_IDS:
            macro_db_conn.execute(
                "UPDATE macro_data SET data = ? "
                "WHERE macro_id = ? AND macro_fixture_id = ?",
                (a_valid_slot_payload(), macro_id, slot_id),
            )
        macro_db_conn.commit()

        # When: reading macro_data
        rows = repo.list_macro_data(macro_db_conn, macro_id)

        # Then: exactly 25 rows, each with a non-empty payload
        assert len(rows) == 25
        for row in rows:
            assert row.xml != ""

    def test_should_treat_empty_string_payload_as_empty_slot(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with all slots empty
        macro_id = a_user_macro(macro_db_conn, macro_id=10001, name="EMPTY MACRO")

        # When: reading macro_data
        rows = repo.list_macro_data(macro_db_conn, macro_id)

        # Then: all 25 rows have empty string data
        assert len(rows) == 25
        for row in rows:
            assert row.xml == ""


# ---------------------------------------------------------------------------
# Read-only guarantee: no mutation after query operations
# ---------------------------------------------------------------------------


class TestReadOnlyGuarantee:
    def test_list_macros_should_not_modify_the_database(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a seeded macro library
        a_user_macro(macro_db_conn, macro_id=10001, name="USER ONE")
        a_factory_macro(macro_db_conn, macro_id=61, name="FACTORY ONE")

        # When: listing macros
        before_count = macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        repo.list_macros(macro_db_conn, scope=_SCOPE_ALL)

        # Then: macro count is unchanged
        after_count = macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        assert before_count == after_count

    def test_search_macros_should_not_modify_the_database(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a seeded macro library
        a_user_macro(macro_db_conn, macro_id=10001, name="CHORUS HIT")
        a_factory_macro(macro_db_conn, macro_id=61, name="CHORUS FACTORY")

        # When: searching
        before_count = macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        repo.search_macros(macro_db_conn, "CHORUS", scope=_SCOPE_ALL)

        # Then: macro count is unchanged
        after_count = macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0]
        assert before_count == after_count


# ---------------------------------------------------------------------------
# Edge case: insertion order != id order
# ---------------------------------------------------------------------------


class TestDeterministicOrdering:
    def test_list_macros_orders_by_id_not_insertion(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: macros inserted in deliberately non-sequential id order
        a_user_macro(macro_db_conn, macro_id=10020, name="TWENTY")
        a_user_macro(macro_db_conn, macro_id=10003, name="THREE")
        a_user_macro(macro_db_conn, macro_id=10010, name="TEN")

        # When: listing all user macros
        macros = repo.list_macros(macro_db_conn, scope=_SCOPE_USER)

        # Then: ascending id order, not insertion order
        assert [m.id for m in macros] == [10003, 10010, 10020]

    def test_search_macros_orders_by_id_not_insertion(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: macros inserted in deliberately non-sequential id order
        a_user_macro(macro_db_conn, macro_id=10020, name="MACRO TWENTY")
        a_user_macro(macro_db_conn, macro_id=10003, name="MACRO THREE")
        a_user_macro(macro_db_conn, macro_id=10010, name="MACRO TEN")

        # When: searching with a common substring
        results = repo.search_macros(macro_db_conn, "MACRO", scope=_SCOPE_USER)

        # Then: ascending id order, not insertion order
        assert [m.id for m in results] == [10003, 10010, 10020]
