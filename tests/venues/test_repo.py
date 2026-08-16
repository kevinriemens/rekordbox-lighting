"""Tests for rbxlight.venues.repo — user.db3 venue/fixture/lighting_property
reads. Contract: rekordbox-lightingdb-schema skill ("user.db3 tables") and
physical-rig-profile skill (real slot-collision shape of the active venue).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import db
from rbxlight.venues import repo
from tests.conftest import make_user_db
from tests.fixtures.venue_fixtures import (
    ACTIVE_VENUE_ID,
    ACTIVE_VENUE_NAME,
    MULTI_VENUE_DUP_NAME,
    a_moving_head_fixture,
    a_multi_venue_database,
    a_par_fixture,
    a_small_full_arc_venue,
    a_venue,
    a_venue_with_slot_collisions,
    set_lighting_property,
)


class TestGetVenue:
    def test_should_return_venue_when_it_exists(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a seeded venue row
        a_venue(user_db_conn, venue_id=ACTIVE_VENUE_ID, name=ACTIVE_VENUE_NAME)

        # When: fetching it
        venue = repo.get_venue(user_db_conn, ACTIVE_VENUE_ID)

        # Then: its fields are returned
        assert venue.id == ACTIVE_VENUE_ID
        assert venue.name == ACTIVE_VENUE_NAME

    def test_should_raise_lookup_error_when_venue_does_not_exist(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no venue rows at all
        # When / Then: fetching an unknown venue id fails clearly
        with pytest.raises(LookupError):
            repo.get_venue(user_db_conn, 999)


class TestListFixtures:
    def test_should_return_empty_list_for_a_venue_with_no_fixtures(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue with no fixture rows
        venue_id = a_venue(user_db_conn)

        # When: listing its fixtures
        fixtures = repo.list_fixtures(user_db_conn, venue_id)

        # Then: an empty list, not an error
        assert fixtures == []

    def test_should_return_every_fixture_patched_into_the_venue(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a small realistic venue slice
        venue_id = a_small_full_arc_venue(user_db_conn)

        # When: listing fixtures
        fixtures = repo.list_fixtures(user_db_conn, venue_id)

        # Then: all 6 seeded fixtures are present
        assert len(fixtures) == 6
        assert {f.id for f in fixtures} == {1, 2, 3, 4, 5, 6}

    def test_should_not_error_when_multiple_fixtures_share_a_slot(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real active venue's documented ceiling — 3 fixtures on
        # slot 16, plus 2 more doubled-up slots (physical-rig-profile skill)
        venue_id = a_venue_with_slot_collisions(user_db_conn)

        # When: listing fixtures
        fixtures = repo.list_fixtures(user_db_conn, venue_id)

        # Then: every fixture is returned, including the collided ones
        assert len(fixtures) == 7
        slot_16_fixtures = [f for f in fixtures if f.macro_fixture_id == 16]
        assert len(slot_16_fixtures) == 3

    def test_should_only_return_fixtures_for_the_requested_venue(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: two venues, each with fixtures
        venue_one = a_venue(user_db_conn, venue_id=1, name="Venue One")
        venue_two = a_venue(user_db_conn, venue_id=2, name="Venue Two")
        a_moving_head_fixture(user_db_conn, fixture_id=1, venue_id=venue_one)
        a_moving_head_fixture(user_db_conn, fixture_id=2, venue_id=venue_two)

        # When: listing fixtures for venue_one only
        fixtures = repo.list_fixtures(user_db_conn, venue_one)

        # Then: only venue_one's fixture is returned
        assert [f.id for f in fixtures] == [1]


class TestGetExecVenueId:
    def test_should_return_the_active_venue_id_when_set(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real key rekordbox stores for the active venue
        set_lighting_property(user_db_conn, "ExecVenueId", str(ACTIVE_VENUE_ID))

        # When: reading the active venue id
        exec_venue_id = repo.get_exec_venue_id(user_db_conn)

        # Then: it round-trips as an int
        assert exec_venue_id == ACTIVE_VENUE_ID

    def test_should_return_none_when_the_property_is_absent(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no lighting_property rows at all
        # When: reading the active venue id
        exec_venue_id = repo.get_exec_venue_id(user_db_conn)

        # Then: None, not an error
        assert exec_venue_id is None


class TestListVenuesWithFixtureCounts:
    """Contract for the read-only venue-enumeration capability backing the
    `rbxlight venue list` CLI command. See task requirement E."""

    def test_should_include_a_venue_with_zero_fixtures_showing_count_zero(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a database with one populated venue and one empty venue
        venue_ids = a_multi_venue_database(user_db_conn)

        # When: enumerating venues with fixture counts
        result = repo.list_venues_with_fixture_counts(user_db_conn)

        # Then: the empty venue is present, not hidden, with a count of 0
        empty = next(r for r in result if r.venue.id == venue_ids["empty"])
        assert empty.fixture_count == 0

    def test_should_count_fixtures_correctly_per_venue(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: two venues, each patched with a different fixture count
        venue_one = a_venue(user_db_conn, venue_id=11, name="Venue One")
        venue_two = a_venue(user_db_conn, venue_id=22, name="Venue Two")
        a_par_fixture(user_db_conn, fixture_id=1, venue_id=venue_one)
        a_par_fixture(user_db_conn, fixture_id=2, venue_id=venue_two)
        a_par_fixture(user_db_conn, fixture_id=3, venue_id=venue_two)

        # When: enumerating venues with fixture counts
        result = repo.list_venues_with_fixture_counts(user_db_conn)

        # Then: each venue's count reflects only its own fixtures
        by_id = {r.venue.id: r.fixture_count for r in result}
        assert by_id[venue_one] == 1
        assert by_id[venue_two] == 2

    def test_should_count_multiple_fixtures_sharing_the_same_slot(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real active venue's documented ceiling — several
        # fixtures sharing macro_fixture_id slots within one venue
        venue_id = a_venue_with_slot_collisions(user_db_conn)

        # When: enumerating venues with fixture counts
        result = repo.list_venues_with_fixture_counts(user_db_conn)

        # Then: every fixture counts, slot collisions included (7 seeded)
        entry = next(r for r in result if r.venue.id == venue_id)
        assert entry.fixture_count == 7

    def test_should_return_empty_list_when_no_venues_exist(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no venue rows at all
        # When: enumerating venues with fixture counts
        result = repo.list_venues_with_fixture_counts(user_db_conn)

        # Then: an empty list, not an error
        assert result == []

    def test_should_order_deterministically_regardless_of_insertion_order(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: venues with non-sequential, non-contiguous ids, inserted
        # out of id order
        a_venue(user_db_conn, venue_id=999, name="Highest")
        a_venue(user_db_conn, venue_id=3, name="Lowest")
        a_venue(user_db_conn, venue_id=50, name="Middle")

        # When: enumerating venues with fixture counts, twice
        first = [r.venue.id for r in repo.list_venues_with_fixture_counts(user_db_conn)]
        second = [
            r.venue.id for r in repo.list_venues_with_fixture_counts(user_db_conn)
        ]

        # Then: the ordering is stable and does not depend on incidental
        # row/insertion order
        assert first == second
        assert first == sorted(first)

    def test_should_distinguish_venues_with_identical_names_by_id(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: two venues sharing the exact same name, different ids
        venue_ids = a_multi_venue_database(user_db_conn)

        # When: enumerating venues with fixture counts
        result = repo.list_venues_with_fixture_counts(user_db_conn)

        # Then: both are present, both named identically, but distinguishable by id
        dup_entries = [r for r in result if r.venue.name == MULTI_VENUE_DUP_NAME]
        assert {r.venue.id for r in dup_entries} == {
            venue_ids["dup_a"],
            venue_ids["dup_b"],
        }

    def test_should_work_over_a_read_only_connection(self, tmp_path: Path) -> None:
        # Given: a real user.db3 file with venues, opened strictly read-only
        # — a structural (not just conventional) guarantee this is a read
        path = make_user_db(tmp_path / "user.db3")
        setup_conn = sqlite3.connect(path)
        a_multi_venue_database(setup_conn)
        setup_conn.close()

        ro_conn = db.connect_readonly(path)
        try:
            # When: enumerating venues over the read-only connection
            result = repo.list_venues_with_fixture_counts(ro_conn)
        finally:
            ro_conn.close()

        # Then: it succeeds — a write attempt would have raised on this
        # connection, so success here proves it never wrote
        assert len(result) == 4
