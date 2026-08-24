"""Tests for rbxlight.orchestration's layout regenerate / layout install
contract — the shared logic behind the CLI's `layout regenerate` /
`layout install` commands (see cli.py), extracted so a future front-end
can drive the same operations. Contract:
rekordbox-lighting-architecture + rekordbox-data-safety ("DRY-RUN BY
DEFAULT" — a plan is a value, not an action).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import orchestration
from rbxlight.preview import layout as preview_layout
from rbxlight.venues import repo as venues_repo
from tests.fixtures.venue_fixtures import a_small_full_arc_venue


def _fixtures_for(user_conn: sqlite3.Connection, venue_id: int) -> list:
    return venues_repo.list_fixtures(user_conn, venue_id)


class TestBuildLayoutRegeneratePlan:
    def test_should_describe_the_resulting_layout_with_no_file_created(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a venue with fixtures, no previously saved layout
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"

        # When: building a regenerate plan (no --write)
        plan = orchestration.build_layout_regenerate_plan(
            venue_id, fixtures, layout_dir
        )

        # Then: it describes the resulting entries, and no file is created
        assert plan.venue_id == venue_id
        assert plan.unchanged_count == 0
        assert not layout_dir.exists() or not any(layout_dir.iterdir())
        assert plan.touches_live is False


class TestApplyLayoutRegeneratePreservesCalibration:
    def test_should_survive_user_pan_tilt_calibration_across_regeneration(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a saved layout in which the user has hand-calibrated a
        # moving head's pan/tilt sweep
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)

        original = preview_layout.generate_layout(venue_id, fixtures)
        calibrated_entries = tuple(
            entry.__class__(
                fixture_id=entry.fixture_id,
                x=entry.x,
                y=entry.y,
                label=entry.label,
                kind=entry.kind,
                rotation=entry.rotation,
                pan_degrees=123.0,
                tilt_degrees=45.0,
            )
            if entry.fixture_id == fixtures[0].id
            else entry
            for entry in original.entries
        )
        calibrated = original.__class__(venue_id=venue_id, entries=calibrated_entries)
        preview_layout.save_layout(layout_path, calibrated)

        # When: regenerating and writing
        result = orchestration.apply_layout_regenerate(venue_id, fixtures, layout_dir)

        # Then: the calibration survives onto the regenerated layout —
        # this is the single most safety-critical assertion in this suite
        regenerated_entry = next(
            entry for entry in result.entries if entry.fixture_id == fixtures[0].id
        )
        assert regenerated_entry.pan_degrees == 123.0
        assert regenerated_entry.tilt_degrees == 45.0

        reloaded = preview_layout.load_layout(layout_path)
        reloaded_entry = next(
            entry for entry in reloaded.entries if entry.fixture_id == fixtures[0].id
        )
        assert reloaded_entry.pan_degrees == 123.0
        assert reloaded_entry.tilt_degrees == 45.0


class TestApplyLayoutRegenerateStructurePreservation:
    def test_should_preserve_a_customised_structure_without_reset_structure(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a saved layout with a customised truss structure
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)

        custom_structure = ((0.0, 0.0), (0.0, 200.0), (300.0, 200.0), (300.0, 0.0))
        original = preview_layout.generate_layout(venue_id, fixtures, custom_structure)
        preview_layout.save_layout(layout_path, original)

        # When: regenerating and writing WITHOUT --reset-structure
        result = orchestration.apply_layout_regenerate(
            venue_id, fixtures, layout_dir, reset_structure=False
        )

        # Then: the customised structure is preserved
        assert result.structure_cm == custom_structure

    def test_should_reset_structure_to_default_when_reset_structure_given(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: the same customised structure as above
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)

        custom_structure = ((0.0, 0.0), (0.0, 200.0), (300.0, 200.0), (300.0, 0.0))
        original = preview_layout.generate_layout(venue_id, fixtures, custom_structure)
        preview_layout.save_layout(layout_path, original)

        # When: regenerating and writing WITH --reset-structure
        result = orchestration.apply_layout_regenerate(
            venue_id, fixtures, layout_dir, reset_structure=True
        )

        # Then: the structure resets to the default arch, the
        # customisation is discarded
        assert result.structure_cm == preview_layout.arch_outline_cm()


class TestBuildLayoutRegeneratePlanDryRunLeavesFileUntouched:
    def test_should_report_a_diff_and_leave_the_saved_layout_file_byte_identical(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a saved layout, and a regenerate that would change
        # fixture positions (a different structure shifts every position)
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)

        original = preview_layout.generate_layout(venue_id, fixtures)
        preview_layout.save_layout(layout_path, original)
        original_bytes = layout_path.read_bytes()

        # When: building a regenerate plan (no --write) with a structure
        # that WOULD move every fixture
        different_structure = (
            (0.0, 0.0),
            (0.0, 999.0),
            (999.0, 999.0),
            (999.0, 0.0),
        )
        plan = orchestration.build_layout_regenerate_plan(
            venue_id, fixtures, layout_dir, structure_cm=different_structure
        )

        # Then: the diff reports what would change, and the file on disk
        # is untouched
        assert len(plan.diffs) > 0
        assert layout_path.read_bytes() == original_bytes


class TestBuildLayoutInstallPlan:
    def test_should_describe_changes_with_existing_layout_unchanged_when_venue_matches(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a layout file whose venue id matches the target venue
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)

        existing = preview_layout.generate_layout(venue_id, fixtures)
        preview_layout.save_layout(layout_path, existing)
        original_bytes = layout_path.read_bytes()

        incoming_path = tmp_path / "exported_layout.json"
        preview_layout.save_layout(incoming_path, existing)

        # When: building an install plan (no --write)
        plan = orchestration.build_layout_install_plan(
            incoming_path, venue_id, fixtures, layout_dir
        )

        # Then: it describes the plan, and the existing saved layout is
        # unchanged on disk
        assert plan.venue_id == venue_id
        assert plan.touches_live is False
        assert layout_path.read_bytes() == original_bytes

    def test_should_raise_typed_error_and_write_nothing_when_venue_id_mismatches(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a layout file for a DIFFERENT venue than the target
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"

        other_venue_layout = preview_layout.generate_layout(999, fixtures)
        incoming_path = tmp_path / "exported_layout.json"
        preview_layout.save_layout(incoming_path, other_venue_layout)

        # When / Then: building the install plan raises, and nothing is
        # written
        with pytest.raises(orchestration.LayoutVenueMismatchError):
            orchestration.build_layout_install_plan(
                incoming_path, venue_id, fixtures, layout_dir
            )

        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
        assert not layout_path.exists()

    def test_should_report_missing_fixture_ids_as_structured_data(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a layout file that omits a fixture present in the target
        # venue
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"

        missing_fixture = fixtures[0]
        incoming_full = preview_layout.generate_layout(venue_id, fixtures)
        trimmed_entries = tuple(
            entry
            for entry in incoming_full.entries
            if entry.fixture_id != missing_fixture.id
        )
        trimmed_layout = incoming_full.__class__(
            venue_id=venue_id, entries=trimmed_entries
        )
        incoming_path = tmp_path / "exported_layout.json"
        preview_layout.save_layout(incoming_path, trimmed_layout)

        # When: building the install plan
        plan = orchestration.build_layout_install_plan(
            incoming_path, venue_id, fixtures, layout_dir
        )

        # Then: the missing fixture id is reported as structured data,
        # not pre-formatted text
        assert plan.missing_from_incoming_fixture_ids == (missing_fixture.id,)
        assert isinstance(plan.missing_from_incoming_fixture_ids, tuple)

    def test_should_report_incoming_fixture_ids_no_longer_patched_into_venue(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: an incoming layout that references a fixture id no
        # longer present among the venue's current fixtures
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"

        incoming_full = preview_layout.generate_layout(venue_id, fixtures)
        orphaned_entry = incoming_full.entries[0].__class__(
            **{
                **incoming_full.entries[0].__dict__,
                "fixture_id": max(f.id for f in fixtures) + 1000,
            }
        )
        incoming_layout = incoming_full.__class__(
            venue_id=venue_id,
            entries=(*incoming_full.entries, orphaned_entry),
        )
        incoming_path = tmp_path / "exported_layout.json"
        preview_layout.save_layout(incoming_path, incoming_layout)

        # When: building the install plan
        plan = orchestration.build_layout_install_plan(
            incoming_path, venue_id, fixtures, layout_dir
        )

        # Then: the orphaned incoming fixture id is reported as
        # structured data, and no venue fixture is reported missing
        assert plan.missing_from_venue_fixture_ids == (orphaned_entry.fixture_id,)
        assert isinstance(plan.missing_from_venue_fixture_ids, tuple)
        assert plan.missing_from_incoming_fixture_ids == ()


class TestApplyLayoutInstall:
    def test_should_save_the_layout_when_venue_matches_and_no_fixtures_missing(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a layout file with no missing fixtures and matching venue
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = _fixtures_for(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"

        incoming = preview_layout.generate_layout(venue_id, fixtures)
        incoming_path = tmp_path / "exported_layout.json"
        preview_layout.save_layout(incoming_path, incoming)

        plan = orchestration.build_layout_install_plan(
            incoming_path, venue_id, fixtures, layout_dir
        )

        # When: installing with writing
        orchestration.apply_layout_install(plan, layout_dir)

        # Then: the layout is saved to disk for this venue
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
        saved = preview_layout.load_layout(layout_path)
        assert saved is not None
        assert saved.venue_id == venue_id
