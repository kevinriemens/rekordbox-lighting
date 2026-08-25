"""Tests for rbxlight.phrases.repo — the `content` table (the per-track
bank assignment) of user.db3. Permanent, reusable repo functions — the
initial slice of the future phrases/repo.py described in
rekordbox-lighting-architecture ("content + phrase_data read/write"); only
the content accessors this project currently needs are covered here.
phrase_data accessors are a future addition, out of scope for this suite.

Contract source: rekordbox-lightingdb-schema skill ("content"). `content`
holds thousands of rows of irreplaceable user work in the real library —
see rekordbox-data-safety skill. Some real content rows legitimately
reference a macro_pattern id that doesn't exist; this module must never
assume referential integrity (see CONTEXT in the ninth-bank experiment
task and tests/fixtures/content_fixtures.py).

`conn` is always passed in — this module never opens its own connection.
"""

from __future__ import annotations

import sqlite3

import pytest

from rbxlight.phrases import repo
from tests.fixtures.content_fixtures import (
    a_track,
    a_track_with_dangling_macro_pattern_id,
    many_tracks,
)


class TestGetContent:
    def test_should_return_the_matching_row(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a seeded content row
        a_track(user_db_conn, content_id=42, song_id=7, macro_pattern_id=3)

        # When: fetching it
        result = repo.get_content(user_db_conn, 42)

        # Then: fields match what was seeded
        assert result.id == 42
        assert result.song_id == 7
        assert result.macro_pattern_id == 3

    def test_should_raise_lookup_error_for_a_nonexistent_id(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no content row with this id
        # When / Then: a clear, predictable failure
        with pytest.raises(LookupError):
            repo.get_content(user_db_conn, 99999)

    def test_should_tolerate_a_dangling_macro_pattern_id(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a real, pre-existing condition — content.macro_pattern_id
        # referencing no existing macro_pattern row (no FK enforcement)
        a_track_with_dangling_macro_pattern_id(
            user_db_conn, content_id=999, macro_pattern_id=55555
        )

        # When: fetching it
        result = repo.get_content(user_db_conn, 999)

        # Then: returned as-is, no validation, no crash
        assert result.macro_pattern_id == 55555


class TestUpdateContentMacroPatternId:
    def test_should_repoint_the_target_row(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a track pointing at bank 1
        a_track(user_db_conn, content_id=1, macro_pattern_id=1)

        # When: repointing it to a new bank
        repo.update_content_macro_pattern_id(user_db_conn, 1, 28)

        # Then: the change is durable and readable back
        assert repo.get_content(user_db_conn, 1).macro_pattern_id == 28

    def test_should_touch_only_the_target_row(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: several tracks sharing the same bank
        many_tracks(user_db_conn, content_ids=(1, 2, 3), macro_pattern_id=1)

        # When: repointing only content_id=2
        repo.update_content_macro_pattern_id(user_db_conn, 2, 28)

        # Then: only the target row changed
        assert repo.get_content(user_db_conn, 1).macro_pattern_id == 1
        assert repo.get_content(user_db_conn, 2).macro_pattern_id == 28
        assert repo.get_content(user_db_conn, 3).macro_pattern_id == 1

    def test_should_raise_lookup_error_for_a_nonexistent_id(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no content row with this id
        # When / Then: a clear, predictable failure — never a silent no-op
        with pytest.raises(LookupError):
            repo.update_content_macro_pattern_id(user_db_conn, 99999, 28)

    def test_should_not_validate_that_the_new_macro_pattern_id_exists(
        self, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a track, and a macro_pattern_id that doesn't exist in any
        # macro_pattern table this connection knows about (content has no
        # FK enforcement in the real schema — see CONTEXT)
        a_track(user_db_conn, content_id=1, macro_pattern_id=1)

        # When / Then: no validation error — this is a legal state in the
        # real library
        repo.update_content_macro_pattern_id(user_db_conn, 1, 424242)
        assert repo.get_content(user_db_conn, 1).macro_pattern_id == 424242
