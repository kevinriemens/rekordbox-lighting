"""Tests for rbxlight.orchestration.resolve_venue — the shared venue
resolution contract used by both the CLI and any future front-end.
Mirrors the behaviour currently inlined in cli.py's
`_resolve_venue_and_fixtures`, but raises typed exceptions instead of
calling typer.echo/typer.Exit — see rekordbox-lighting-architecture skill
("The Flow That Must Not Break") for why a shared layer must not depend
on typer at all.
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight import orchestration
from tests.fixtures.venue_fixtures import (
    a_small_full_arc_venue,
    a_venue,
    set_lighting_property,
)


class TestResolveVenueExplicit:
    def test_should_return_venue_and_fixtures_when_explicit_id_exists(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an existing venue with fixtures
        venue_id = a_small_full_arc_venue(user_db_conn)

        # When: resolving with an explicit venue id
        result = orchestration.resolve_venue(user_db_conn, venue_id)

        # Then: that venue and its fixtures are returned, sourced explicitly
        assert result.venue.id == venue_id
        assert len(result.fixtures) == 6
        assert result.source == "explicit"

    def test_should_raise_venue_not_found_enumerating_available_venues_when_explicit_id_missing(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: one real venue, but a different id is requested
        a_venue(user_db_conn, venue_id=1, name="Main Room")

        # When / Then: resolving a nonexistent explicit id raises, and the
        # error enumerates the venues that DO exist
        with pytest.raises(orchestration.VenueNotFoundError) as exc_info:
            orchestration.resolve_venue(user_db_conn, 999)

        assert exc_info.value.venue_id == 999
        assert [v.venue.id for v in exc_info.value.venues] == [1]


class TestResolveVenueFromActivePointer:
    def test_should_return_venue_and_fixtures_when_active_pointer_set_and_valid(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an existing venue set as the active venue
        venue_id = a_small_full_arc_venue(user_db_conn)
        set_lighting_property(user_db_conn, "ExecVenueId", str(venue_id))

        # When: resolving with no explicit venue id
        result = orchestration.resolve_venue(user_db_conn, None)

        # Then: the active venue and its fixtures are returned, sourced
        # from the active pointer
        assert result.venue.id == venue_id
        assert len(result.fixtures) == 6
        assert result.source == "active_venue"

    def test_should_raise_no_active_venue_enumerating_available_venues_when_pointer_unset(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: venues exist, but no ExecVenueId is set at all
        a_venue(user_db_conn, venue_id=1, name="Main Room")
        a_venue(user_db_conn, venue_id=2, name="Side Room")

        # When / Then: resolving with no explicit id and no pointer raises
        # a distinct "never picked" error, enumerating available venues
        with pytest.raises(orchestration.NoActiveVenueError) as exc_info:
            orchestration.resolve_venue(user_db_conn, None)

        assert {v.venue.id for v in exc_info.value.venues} == {1, 2}

    def test_should_raise_stale_active_venue_distinguishable_from_no_pointer_set(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a real venue exists, but ExecVenueId points at a venue
        # that does NOT exist
        a_venue(user_db_conn, venue_id=1, name="Main Room")
        set_lighting_property(user_db_conn, "ExecVenueId", "404")

        # When / Then: resolving raises a DIFFERENT typed error than the
        # no-pointer-set case, still enumerating available venues
        with pytest.raises(orchestration.StaleActiveVenueError) as exc_info:
            orchestration.resolve_venue(user_db_conn, None)

        assert not issubclass(
            orchestration.StaleActiveVenueError, orchestration.NoActiveVenueError
        )
        assert not issubclass(
            orchestration.NoActiveVenueError, orchestration.StaleActiveVenueError
        )
        assert exc_info.value.stale_venue_id == 404
        assert [v.venue.id for v in exc_info.value.venues] == [1]

    def test_should_never_collapse_stale_pointer_and_unset_pointer_into_the_same_exception_type(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: two scenarios — no pointer at all, and a dangling pointer
        a_venue(user_db_conn, venue_id=1, name="Main Room")

        # When: no pointer is set
        with pytest.raises(orchestration.NoActiveVenueError) as unset_exc:
            orchestration.resolve_venue(user_db_conn, None)

        # And: the pointer is set but dangling
        set_lighting_property(user_db_conn, "ExecVenueId", "999")
        with pytest.raises(orchestration.StaleActiveVenueError) as stale_exc:
            orchestration.resolve_venue(user_db_conn, None)

        # Then: a caller can tell the two failure modes apart by type alone
        assert type(unset_exc.value) is not type(stale_exc.value)


class TestResolveVenueZeroFixtures:
    def test_should_return_empty_fixture_list_for_a_venue_with_no_fixtures(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue with no patched fixtures at all
        venue_id = a_venue(user_db_conn, venue_id=1, name="Empty Room")

        # When: resolving it explicitly
        result = orchestration.resolve_venue(user_db_conn, venue_id)

        # Then: it resolves successfully with an empty fixture list
        assert result.venue.id == venue_id
        assert result.fixtures == []
