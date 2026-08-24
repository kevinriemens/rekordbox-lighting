"""Tests for dry-run plan objects on macro create/delete: typed, immutable
descriptions of what WOULD happen, built with zero writes. Contract:
rekordbox-lighting-architecture ("dry-run by default") +
rekordbox-data-safety ("DRY-RUN BY DEFAULT").
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from rbxlight.macros import repo
from tests.fixtures.macro_fixtures import a_user_macro


class TestBuildCreateMacroPlan:
    def test_should_report_name_beats_target_path_and_no_live_data_touched(
        self, tmp_path: Path
    ) -> None:
        # Given: a target working-copy macro.db3 path
        target_path = tmp_path / "macro.db3"

        # When: building a create-macro plan
        plan = repo.build_create_macro_plan(
            name="HIGH DROP1", beats=32, target_path=target_path
        )

        # Then: it carries the facts needed to render it
        assert plan.name == "HIGH DROP1"
        assert plan.beats == 32
        assert plan.target_path == target_path
        assert plan.touches_live is False

    def test_should_perform_no_write_when_building(self, tmp_path: Path) -> None:
        # Given: no macro.db3 file exists yet at the target path
        target_path = tmp_path / "macro.db3"
        assert not target_path.exists()

        # When: building the plan
        repo.build_create_macro_plan(name="X", beats=16, target_path=target_path)

        # Then: still absent — building a plan writes nothing
        assert not target_path.exists()

    def test_should_be_immutable(self, tmp_path: Path) -> None:
        # Given: a built plan
        plan = repo.build_create_macro_plan(
            name="X", beats=16, target_path=tmp_path / "macro.db3"
        )

        # When / Then: mutating any field raises
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.name = "CHANGED"  # type: ignore[misc]


class TestBuildDeleteMacroPlan:
    def test_should_report_macro_identity_target_path_and_no_live_data_touched(
        self, macro_db_conn: sqlite3.Connection, macro_db_path: Path
    ) -> None:
        # Given: an existing user macro
        macro_id = a_user_macro(macro_db_conn, macro_id=10005, name="DROP FX", beats=64)

        # When: building a delete-macro plan
        plan = repo.build_delete_macro_plan(
            macro_db_conn, macro_id=macro_id, target_path=macro_db_path
        )

        # Then: it carries the facts needed to render it
        assert plan.macro_id == macro_id
        assert plan.macro_name == "DROP FX"
        assert plan.beats == 64
        assert plan.target_path == macro_db_path
        assert plan.touches_live is False

    def test_should_perform_no_write_when_building(
        self, macro_db_conn: sqlite3.Connection, macro_db_path: Path
    ) -> None:
        # Given: an existing user macro and the db file's current bytes
        macro_id = a_user_macro(macro_db_conn, macro_id=10006)
        macro_db_conn.commit()
        original_bytes = macro_db_path.read_bytes()

        # When: building a delete plan (does not delete)
        repo.build_delete_macro_plan(
            macro_db_conn, macro_id=macro_id, target_path=macro_db_path
        )

        # Then: the macro row is still there, file bytes unchanged
        assert repo.get_macro(macro_db_conn, macro_id) is not None
        assert macro_db_path.read_bytes() == original_bytes

    def test_should_raise_lookup_error_for_a_nonexistent_macro(
        self, macro_db_conn: sqlite3.Connection, macro_db_path: Path
    ) -> None:
        # Given: no macro with this id exists — same predictable failure
        # mode as repo.get_macro
        # When / Then: building the plan raises, rather than returning a
        # plan describing a delete of nothing
        with pytest.raises(LookupError):
            repo.build_delete_macro_plan(
                macro_db_conn, macro_id=99999, target_path=macro_db_path
            )

    def test_should_be_immutable(
        self, macro_db_conn: sqlite3.Connection, macro_db_path: Path
    ) -> None:
        # Given: a built delete plan
        macro_id = a_user_macro(macro_db_conn, macro_id=10007)
        plan = repo.build_delete_macro_plan(
            macro_db_conn, macro_id=macro_id, target_path=macro_db_path
        )

        # When / Then: mutating any field raises
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.macro_id = 1  # type: ignore[misc]
