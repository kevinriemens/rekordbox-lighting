"""Tests for rbxlight.preview.payload — building the full preview payload
dict from a macro (macro.db3) + a venue's fixture patch (user.db3) + a rig
layout. Contract: task requirements ("Preview payload") + the renderer's
agreed JSON contract.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rbxlight.preview import layout, payload
from rbxlight.preview.layout import MARGIN_FRACTION, RigLayout
from rbxlight.preview.payload import (
    DEFAULT_BPM,
    MacroNotFoundError,
    MissingLayoutEntryError,
    VenueNotFoundError,
)
from rbxlight.venues import repo as venues_repo
from tests.fixtures.macro_fixtures import a_user_macro, insert_macro_data_row
from tests.fixtures.venue_fixtures import (
    ACTIVE_VENUE_NAME,
    a_small_full_arc_venue,
    a_venue,
    a_venue_with_slot_collisions,
)

_SWEEP_PAYLOAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<LightingEditModel ver="1.0">\n'
    "  <Brightness>\n"
    '    <PointBlock xleft="0" xright="32">\n'
    '      <Point x="0" y="1.0" type="1"/>\n'
    '      <Point x="32" y="1.0" type="3"/>\n'
    "    </PointBlock>\n"
    "  </Brightness>\n"
    "  <Colour>\n"
    '    <ColourBlock xleft="0" colourleft="-65536" xright="32" colourright="-16776961"/>\n'
    "  </Colour>\n"
    "  <Strobe/>\n"
    "</LightingEditModel>"
)


def _layout_for(user_conn: sqlite3.Connection, venue_id: int) -> RigLayout:
    fixtures = venues_repo.list_fixtures(user_conn, venue_id)
    return layout.generate_layout(venue_id, fixtures)


class TestBuildPreviewPayload:
    def test_should_include_macro_identity_and_beats(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro and a venue with fixtures
        macro_id = a_user_macro(
            macro_db_conn, macro_id=10008, name="AI TEST SWEEP", beats=32
        )
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the macro's identity and length are recorded
        assert result["macro"] == {"id": 10008, "name": "AI TEST SWEEP", "beats": 32}

    def test_should_include_venue_identity(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro and a named venue
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_venue(user_db_conn, venue_id=2, name=ACTIVE_VENUE_NAME)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the venue's identity is recorded
        assert result["venue"] == {"id": 2, "name": ACTIVE_VENUE_NAME}

    def test_should_default_bpm_when_not_overridden(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no explicit bpm
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the default tempo is used
        assert result["bpm"] == DEFAULT_BPM

    def test_should_use_an_overridden_bpm(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: an explicit bpm override
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload with bpm=140
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout, bpm=140
        )

        # Then: the override is used
        assert result["bpm"] == 140

    def test_should_include_one_fixture_entry_per_venue_fixture(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue with 6 fixtures
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: 6 fixture entries
        assert len(result["fixtures"]) == 6

    def test_should_include_layout_position_slot_and_type_for_each_fixture(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue with a moving head on slot 11
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: fixture 1 (LM70S #1, slot 11) carries its layout + slot info
        entry = next(f for f in result["fixtures"] if f["id"] == 1)
        assert entry["label"] == "LM70S #1"
        assert entry["kind"] == "moving_head"
        assert 0.0 <= entry["x"] <= 1.0
        assert 0.0 <= entry["y"] <= 1.0
        assert entry["slot_id"] == 11
        assert entry["slot_name"] == "Moving Head 1"
        assert entry["fixture_type_id"] == 3
        assert "program" in entry

    def test_should_resolve_non_contiguous_simple_slot_ids_correctly(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a fixture patched into a Simple slot (111 — non-contiguous range)
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_venue(user_db_conn)
        from tests.fixtures.venue_fixtures import a_tilt_block_fixture

        a_tilt_block_fixture(
            user_db_conn, fixture_id=1, venue_id=venue_id, macro_fixture_id=111
        )
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the Simple slot resolves correctly
        entry = result["fixtures"][0]
        assert entry["slot_id"] == 111
        assert entry["slot_name"] == "Moving Head 1 (Simple)"
        assert entry["fixture_type_id"] == 103

    def test_should_resolve_multiple_fixtures_on_the_same_slot_to_identical_programming(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: the real active venue's slot-collision shape (3 fixtures on
        # slot 16) and real programming on that slot
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        insert_macro_data_row(
            macro_db_conn, macro_id=macro_id, macro_fixture_id=16, data=_SWEEP_PAYLOAD
        )
        # a_user_macro already inserted an empty row for slot 16 — overwrite it
        macro_db_conn.execute(
            "UPDATE macro_data SET data = ? WHERE macro_id = ? AND macro_fixture_id = ?",
            (_SWEEP_PAYLOAD, macro_id, 16),
        )
        macro_db_conn.commit()
        venue_id = a_venue_with_slot_collisions(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: this must not error, and every fixture on slot 16 gets the
        # exact same program
        slot_16_fixtures = [f for f in result["fixtures"] if f["slot_id"] == 16]
        assert len(slot_16_fixtures) == 3
        programs = [f["program"] for f in slot_16_fixtures]
        assert all(p == programs[0] for p in programs)

    def test_should_produce_all_dark_fixtures_when_every_slot_is_empty(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro where every slot is unprogrammed (the default from
        # a_user_macro, which stores "" for every slot)
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: every fixture is dark (explicit empty program), a valid preview
        for entry in result["fixtures"]:
            assert entry["program"]["brightness"] is None
            assert entry["program"]["colour"] == []

    def test_should_not_raise_when_macro_beats_is_zero(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with a beat length of zero
        macro_id = a_user_macro(macro_db_conn, macro_id=10008, beats=0)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: no crash, and beats is faithfully recorded as 0
        assert result["macro"]["beats"] == 0

    def test_should_raise_macro_not_found_error_for_unknown_macro(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no macro with this id
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When / Then: a clear, specific error
        with pytest.raises(MacroNotFoundError):
            payload.build_preview_payload(
                macro_db_conn, user_db_conn, 999999, venue_id, rig_layout
            )

    def test_should_raise_venue_not_found_error_for_unknown_venue(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: no venue with this id
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        empty_layout = RigLayout(venue_id=999999, entries=())

        # When / Then: a clear, specific error
        with pytest.raises(VenueNotFoundError):
            payload.build_preview_payload(
                macro_db_conn, user_db_conn, macro_id, 999999, empty_layout
            )

    def test_should_raise_when_layout_is_missing_an_entry_for_a_current_fixture(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue with fixtures, but a layout that doesn't cover them
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        incomplete_layout = RigLayout(venue_id=venue_id, entries=())

        # When / Then: a clear error, not a silent default/crash elsewhere
        with pytest.raises(MissingLayoutEntryError):
            payload.build_preview_payload(
                macro_db_conn, user_db_conn, macro_id, venue_id, incomplete_layout
            )

    def test_should_be_json_serializable_with_no_non_finite_numbers(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a fully built payload with real programming
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        macro_db_conn.execute(
            "UPDATE macro_data SET data = ? WHERE macro_id = ? AND macro_fixture_id = ?",
            (_SWEEP_PAYLOAD, macro_id, 11),
        )
        macro_db_conn.commit()
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building and serializing the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: json.dumps with allow_nan=False never raises (no NaN/Infinity)
        serialized = json.dumps(result, allow_nan=False)
        assert isinstance(serialized, str)

    def test_should_never_exceed_the_macros_beat_length(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a short macro (8 beats) with a payload written for a longer one
        macro_id = a_user_macro(macro_db_conn, macro_id=10008, beats=8)
        macro_db_conn.execute(
            "UPDATE macro_data SET data = ? WHERE macro_id = ? AND macro_fixture_id = ?",
            (_SWEEP_PAYLOAD, macro_id, 11),  # payload authored for 32 beats
        )
        macro_db_conn.commit()
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: no fixture's program has any beat position past 8
        entry = next(f for f in result["fixtures"] if f["slot_id"] == 11)
        assert entry["program"]["brightness"]["xright"] <= 8.0

    def test_should_work_with_read_only_connections(
        self,
        macro_db_path: Path,
        user_db_path: Path,
    ) -> None:
        # Given: a macro + venue seeded via ordinary write connections...
        write_macro_conn = sqlite3.connect(macro_db_path)
        macro_id = a_user_macro(write_macro_conn, macro_id=10008)
        write_macro_conn.close()

        write_user_conn = sqlite3.connect(user_db_path)
        venue_id = a_small_full_arc_venue(write_user_conn)
        write_user_conn.close()

        # ...then reopened as structurally read-only connections
        ro_macro_conn = sqlite3.connect(f"file:{macro_db_path}?mode=ro", uri=True)
        ro_user_conn = sqlite3.connect(f"file:{user_db_path}?mode=ro", uri=True)
        rig_layout = _layout_for(ro_user_conn, venue_id)

        # When: building the payload using only read-only connections
        result = payload.build_preview_payload(
            ro_macro_conn, ro_user_conn, macro_id, venue_id, rig_layout
        )

        # Then: it succeeds — no write was ever attempted
        assert result["macro"]["id"] == macro_id

    def test_should_normalize_the_truss_into_the_same_frame_as_fixture_positions(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a venue whose fixtures extend beyond the structure's own
        # footprint (ground pars stand outside the arch — see task
        # requirement 5, "One shared normalized frame")
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the truss is normalized through the SAME shared frame the
        # layout used for its own fixtures — no separate, mismatched
        # bounding box, no renderer-side correction required
        expected_truss = tuple(
            tuple(point) for point in layout.normalized_structure(rig_layout)
        )
        actual_truss = tuple(tuple(point) for point in result["truss"])
        assert actual_truss == expected_truss

    def test_should_keep_the_payload_shape_unchanged_by_the_shared_frame_and_reference_box_change(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a fully built payload
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: same top-level keys and value shapes as before, PLUS the
        # new real-world (cm) reference box — this is a deliberate
        # tripwire against accidental payload growth, so it is extended
        # to the new intended shape rather than weakened. "truss" stays a
        # sequence of (x, y) pairs of real numbers; the exact Python
        # container type (list vs tuple) isn't the contract, JSON
        # serializability of that shape is.
        assert set(result.keys()) == {
            "macro",
            "venue",
            "bpm",
            "truss",
            "fixtures",
            "frame_cm",
            "margin_fraction",
        }
        for point in result["truss"]:
            assert len(point) == 2
            assert isinstance(point[0], (int, float))
            assert isinstance(point[1], (int, float))
        assert set(result["frame_cm"].keys()) == {"min_x", "max_x", "min_y", "max_y"}
        for value in result["frame_cm"].values():
            assert isinstance(value, (int, float))
        serialized = json.dumps(result, allow_nan=False)
        assert isinstance(serialized, str)

    def test_should_include_a_real_world_reference_box_matching_the_layouts_frame(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a layout built with its own cm normalization frame — the
        # real-world box every fixture position was normalized against
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)
        assert rig_layout.frame_cm is not None

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the embedded reference box matches the exact cm frame the
        # layout was built with — what lets the browser display true
        # measurements and convert an edit back into real-world
        # coordinates
        assert result["frame_cm"] == {
            "min_x": rig_layout.frame_cm.min_x,
            "max_x": rig_layout.frame_cm.max_x,
            "min_y": rig_layout.frame_cm.min_y,
            "max_y": rig_layout.frame_cm.max_y,
        }

    def test_should_expose_the_normalization_margin_fraction_as_data(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a fully built payload
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        rig_layout = _layout_for(user_db_conn, venue_id)

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, rig_layout
        )

        # Then: the margin fraction is carried as data, using the exact
        # constant the normalization code itself uses — not a re-hardcoded
        # literal duplicated by the renderer
        assert result["margin_fraction"] == MARGIN_FRACTION
        assert isinstance(result["margin_fraction"], float)
        serialized = json.dumps(result, allow_nan=False)
        assert isinstance(serialized, str)

    def test_should_produce_a_usable_payload_when_the_layout_has_no_reference_box(
        self, macro_db_conn: sqlite3.Connection, user_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a layout with no persisted cm frame at all (e.g. loaded
        # from a file saved before this field existed — see
        # rbxlight.preview.layout's frame_cm defaulting convention)
        macro_id = a_user_macro(macro_db_conn, macro_id=10008)
        venue_id = a_small_full_arc_venue(user_db_conn)
        generated = _layout_for(user_db_conn, venue_id)
        frameless_layout = RigLayout(
            venue_id=generated.venue_id,
            entries=generated.entries,
            unmapped_cell_ids=generated.unmapped_cell_ids,
            structure_cm=generated.structure_cm,
            frame_cm=None,
        )

        # When: building the payload
        result = payload.build_preview_payload(
            macro_db_conn, user_db_conn, macro_id, venue_id, frameless_layout
        )

        # Then: still a usable, fully JSON-serializable payload — the
        # reference box is simply absent, not a crash
        assert result["frame_cm"] is None
        serialized = json.dumps(result, allow_nan=False)
        assert isinstance(serialized, str)
