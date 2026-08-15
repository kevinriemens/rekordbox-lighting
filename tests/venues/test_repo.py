"""Tests for rbxlight.venues.repo — user.db3 venue/fixture/lighting_property
reads. Contract: rekordbox-lightingdb-schema skill ("user.db3 tables") and
physical-rig-profile skill (real slot-collision shape of the active venue).
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight.venues import repo
from tests.fixtures.venue_fixtures import (
    ACTIVE_VENUE_ID,
    ACTIVE_VENUE_NAME,
    a_moving_head_fixture,
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
