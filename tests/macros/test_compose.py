"""Tests for rbxlight.macros.compose — the pure macro-composition
primitive. Contract: task requirements component A ("Composition
primitive (pure — no DB, no I/O)").

compose_slot_payload(beats, fixture_type_id, *, brightness, colour=None,
strobe=None, movement=None, rotate=None) -> str (a complete
LightingEditModel XML payload for one fixture slot). Pure — no DB, no I/O.
"""

from __future__ import annotations

import inspect
from itertools import pairwise

import pytest

from rbxlight import lightingxml
from rbxlight.macros import compose
from rbxlight.models import FIXTURE_TYPE_CAPABILITIES
from tests.fixtures.compose_fixtures import (
    BLUE,
    GREEN,
    RED,
    a_brightness_ramp_with_interior_points,
    a_colour_gradient_stops,
    a_colour_hold_stops,
    a_minimal_brightness_keyframes,
    a_movement_spec,
    a_rotate_span,
    a_single_colour_stop,
    a_strobe_window,
    a_strobe_window_covering_full_span,
)

_BEATS = 32.0

#: Fixture types with full capability, incl. movement/rotate (Par, Bar,
#: Moving Head). See rbxlight.models.FIXTURE_TYPE_CAPABILITIES.
_FULL_TYPE = 1
_MOVING_HEAD_TYPE = 3
#: Fixture types with ONLY brightness/colour/strobe — no movement, no
#: rotate, no gobo (Par Simple / Bar Simple).
_RESTRICTED_TYPE = 101
_UNKNOWN_TYPE = 9999


class TestPurityIsStructural:
    def test_should_not_accept_a_connection_or_path_parameter(self) -> None:
        # Given: the composition primitive's signature
        params = inspect.signature(compose.compose_slot_payload).parameters

        # Then: no parameter name suggests a DB/IO collaborator
        assert not any(
            "conn" in name or "connection" in name or "path" in name for name in params
        )


class TestDeterminism:
    def test_should_produce_identical_output_when_called_twice_with_same_inputs(
        self,
    ) -> None:
        # Given: identical, fully-populated inputs
        kwargs = {
            "beats": _BEATS,
            "fixture_type_id": _MOVING_HEAD_TYPE,
            "brightness": a_brightness_ramp_with_interior_points(_BEATS),
            "colour": a_colour_gradient_stops(_BEATS),
            "strobe": a_strobe_window(),
            "movement": a_movement_spec(),
            "rotate": a_rotate_span(),
        }

        # When: composed twice
        first = compose.compose_slot_payload(**kwargs)
        second = compose.compose_slot_payload(**kwargs)

        # Then: byte-identical output
        assert first == second


class TestRoundTrip:
    def test_should_round_trip_exactly_when_fully_populated(self) -> None:
        # Given: a fully-populated payload for a moving head slot
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_brightness_ramp_with_interior_points(_BEATS),
            colour=a_colour_gradient_stops(_BEATS),
            strobe=a_strobe_window(),
            movement=a_movement_spec(),
            rotate=a_rotate_span(),
        )

        # When: parsed, serialized, and parsed again
        model = lightingxml.parse(xml)
        reserialized = lightingxml.serialize(model)
        reparsed = lightingxml.parse(reserialized)

        # Then: the model is unchanged by the round trip
        assert reparsed == model
        assert reserialized == xml

    def test_should_round_trip_exactly_when_minimally_populated(self) -> None:
        # Given: only the required brightness keyframes, nothing else
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # When: round-tripped
        model = lightingxml.parse(xml)
        reserialized = lightingxml.serialize(model)

        # Then: byte-identical re-serialization
        assert reserialized == xml


class TestBrightness:
    def test_should_mark_first_keyframe_start_last_end_middle_interior(self) -> None:
        # Given: a ramp with 2 interior points
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_brightness_ramp_with_interior_points(_BEATS),
        )

        # When: parsed
        model = lightingxml.parse(xml)
        points = sorted(model.brightness.points, key=lambda p: p.x)

        # Then: type 1 first, type 3 last, type 2 in between
        assert points[0].type == 1
        assert points[-1].type == 3
        assert all(p.type == 2 for p in points[1:-1])
        assert len(points) == 4

    def test_should_span_the_full_beat_range_regardless_of_keyframe_positions(
        self,
    ) -> None:
        # Given: keyframes that don't touch beat 0 or beat `beats`
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=[(2.0, 0.0), (30.0, 1.0)],
        )

        # When: parsed
        model = lightingxml.parse(xml)

        # Then: the block's declared span is exactly [0, beats]
        assert model.brightness.xleft == 0.0
        assert model.brightness.xright == _BEATS

    def test_should_accept_exactly_two_keyframes_as_the_minimum_valid_case(
        self,
    ) -> None:
        # Given/When: exactly a start and an end
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # Then: composes without error, exactly 2 points
        model = lightingxml.parse(xml)
        assert len(model.brightness.points) == 2

    @pytest.mark.parametrize("level", [0.0, 1.0])
    def test_should_accept_boundary_brightness_levels(self, level: float) -> None:
        # Given/When: a level of exactly 0.0 or exactly 1.0
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=[(0.0, level), (_BEATS, level)],
        )

        # Then: composes without error
        model = lightingxml.parse(xml)
        assert model.brightness.points[0].y == level

    @pytest.mark.parametrize("beat", [0.0, _BEATS])
    def test_should_accept_boundary_beat_values(self, beat: float) -> None:
        # Given/When: a keyframe exactly at beat 0 or exactly at beat `beats`
        other = _BEATS if beat == 0.0 else 0.0
        keyframes = sorted([(beat, 0.5), (other, 0.5)])

        # Then: composes without error
        compose.compose_slot_payload(
            beats=_BEATS, fixture_type_id=_FULL_TYPE, brightness=keyframes
        )


class TestColour:
    def test_should_hold_a_single_colour_for_the_whole_span_with_one_stop(
        self,
    ) -> None:
        # Given: a single colour stop
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            colour=a_single_colour_stop(),
        )

        # When: parsed
        model = lightingxml.parse(xml)

        # Then: exactly one block spanning the whole span, holding one colour
        assert len(model.colour) == 1
        block = model.colour[0]
        assert block.xleft == 0.0
        assert block.xright == _BEATS
        assert block.colourleft == block.colourright == RED

    def test_should_tile_contiguously_with_no_gaps_or_overlaps(self) -> None:
        # Given: an ordered set of colour stops
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            colour=a_colour_gradient_stops(_BEATS),
        )

        # When: parsed and sorted by position
        model = lightingxml.parse(xml)
        blocks = sorted(model.colour, key=lambda b: b.xleft)

        # Then: first block starts at 0, last ends at beats, no gaps/overlaps
        assert blocks[0].xleft == 0.0
        assert blocks[-1].xright == _BEATS
        for earlier, later in pairwise(blocks):
            assert earlier.xright == later.xleft

    def test_should_carry_gradient_endpoints_between_consecutive_stops(self) -> None:
        # Given: two distinct-colour stops
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            colour=[(0.0, RED), (_BEATS, GREEN)],
        )

        # When: parsed
        model = lightingxml.parse(xml)
        blocks = sorted(model.colour, key=lambda b: b.xleft)

        # Then: the block spanning the two stops carries both colours as
        # its start/end — a gradient, not a hold
        assert blocks[0].colourleft == RED
        assert blocks[0].colourright == GREEN

    def test_should_tile_correctly_when_consecutive_stops_share_the_same_colour(
        self,
    ) -> None:
        # Given: a hold (same colour twice), not a gradient
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            colour=a_colour_hold_stops(_BEATS),
        )

        # When: parsed
        model = lightingxml.parse(xml)
        blocks = sorted(model.colour, key=lambda b: b.xleft)

        # Then: still tiles contiguously across the whole span
        assert blocks[0].xleft == 0.0
        assert blocks[-1].xright == _BEATS
        for earlier, later in pairwise(blocks):
            assert earlier.xright == later.xleft


class TestStrobe:
    def test_should_be_present_only_inside_the_given_window(self) -> None:
        # Given: one strobe window
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            strobe=a_strobe_window(4.0, 8.0),
        )

        # When: parsed
        model = lightingxml.parse(xml)

        # Then: exactly one block, confined to the window
        assert len(model.strobe) == 1
        block = model.strobe[0]
        assert block.xleft == 4.0
        assert block.xright == 8.0

    def test_should_have_no_strobe_content_when_no_windows_given(self) -> None:
        # Given/When: no strobe argument at all
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # Then: an empty (but present) Strobe section
        model = lightingxml.parse(xml)
        assert model.strobe == ()

    def test_should_accept_a_window_covering_the_entire_span(self) -> None:
        # Given/When: a strobe window spanning [0, beats]
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_FULL_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            strobe=a_strobe_window_covering_full_span(_BEATS),
        )

        # Then: composes without error
        model = lightingxml.parse(xml)
        assert model.strobe[0].xleft == 0.0
        assert model.strobe[0].xright == _BEATS


class TestMovementAndRotateIndependence:
    def test_should_allow_movement_without_rotate(self) -> None:
        # Given/When: movement given, rotate omitted
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            movement=a_movement_spec(),
        )

        # Then: position populated, rotate present-but-empty
        model = lightingxml.parse(xml)
        assert model.position is not None and len(model.position) == 1
        assert model.rotate == ()

    def test_should_allow_rotate_without_movement(self) -> None:
        # Given/When: rotate given, movement omitted
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            rotate=a_rotate_span(),
        )

        # Then: rotate populated, position present-but-empty
        model = lightingxml.parse(xml)
        assert model.rotate is not None and len(model.rotate) == 1
        assert model.position == ()

    def test_should_span_the_full_beat_range_for_movement_and_rotate_blocks(
        self,
    ) -> None:
        # Given/When: both movement and rotate given
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
            movement=a_movement_spec(),
            rotate=a_rotate_span(),
        )

        # Then: both blocks span [0, beats]
        model = lightingxml.parse(xml)
        assert model.position[0].xleft == 0.0
        assert model.position[0].xright == _BEATS
        assert model.rotate[0].xleft == 0.0
        assert model.rotate[0].xright == _BEATS


class TestThreeStatePresence:
    """Present-with-content, present-but-empty, and absent must all
    survive round-trip exactly (mirrors the golden-corpus invariant)."""

    def test_should_emit_supported_unspecified_sections_as_present_but_empty(
        self,
    ) -> None:
        # Given: a type supporting movement/rotate, neither requested
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # Then: present-but-empty, not absent
        model = lightingxml.parse(xml)
        assert model.position == ()
        assert model.rotate == ()

    def test_should_omit_unsupported_sections_entirely(self) -> None:
        # Given: a type with no movement/rotate/gobo hardware
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_RESTRICTED_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # Then: absent (None), not present-empty
        model = lightingxml.parse(xml)
        assert model.position is None
        assert model.rotate is None
        assert model.gobo_present is None

    def test_should_emit_gobo_present_empty_only_for_gobo_capable_types(self) -> None:
        # Given: a moving-head type (gobo-capable)
        xml = compose.compose_slot_payload(
            beats=_BEATS,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=a_minimal_brightness_keyframes(_BEATS),
        )

        # Then: Gobo present-but-empty
        model = lightingxml.parse(xml)
        assert model.gobo_present is False


class TestCapabilityRejections:
    def test_should_raise_when_movement_requested_for_a_type_without_position_support(
        self,
    ) -> None:
        # Given: a type with no movement hardware (Par Simple)
        # When / Then: requesting movement raises
        with pytest.raises(compose.UnsupportedSectionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_RESTRICTED_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                movement=a_movement_spec(),
            )

    def test_should_raise_when_rotate_requested_for_a_type_without_rotate_support(
        self,
    ) -> None:
        # Given: a type with no rotate hardware
        # When / Then: requesting rotate raises
        with pytest.raises(compose.UnsupportedSectionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_RESTRICTED_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                rotate=a_rotate_span(),
            )

    def test_should_raise_when_fixture_type_is_unknown(self) -> None:
        # Given: an fixture_type_id that isn't in FIXTURE_TYPE_CAPABILITIES
        assert _UNKNOWN_TYPE not in FIXTURE_TYPE_CAPABILITIES

        # When / Then: composing for it raises
        with pytest.raises(compose.UnknownFixtureTypeError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_UNKNOWN_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
            )


class TestDomainRejections:
    def test_should_raise_when_brightness_beat_is_below_zero(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(-1.0, 0.0), (_BEATS, 1.0)],
            )

    def test_should_raise_when_brightness_beat_is_beyond_beats(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(0.0, 0.0), (_BEATS + 1.0, 1.0)],
            )

    def test_should_raise_when_colour_stop_beat_is_outside_domain(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                colour=[(0.0, RED), (_BEATS + 5.0, BLUE)],
            )

    def test_should_raise_when_strobe_window_beat_is_outside_domain(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                strobe=[(-1.0, 4.0)],
            )

    def test_should_raise_when_brightness_level_is_below_zero(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(0.0, -0.1), (_BEATS, 1.0)],
            )

    def test_should_raise_when_brightness_level_is_above_one(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(0.0, 0.0), (_BEATS, 1.1)],
            )

    def test_should_raise_when_brightness_beats_are_unordered(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(10.0, 0.0), (5.0, 1.0), (_BEATS, 1.0)],
            )

    def test_should_raise_when_brightness_beats_are_duplicated(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=[(0.0, 0.0), (0.0, 1.0), (_BEATS, 1.0)],
            )

    def test_should_raise_when_colour_beats_are_unordered_or_duplicated(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                colour=[(0.0, RED), (0.0, BLUE)],
            )

    def test_should_raise_when_colour_stops_do_not_begin_at_beat_zero(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                colour=[(1.0, RED), (_BEATS, BLUE)],
            )

    def test_should_raise_when_strobe_window_end_equals_start(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                strobe=[(4.0, 4.0)],
            )

    def test_should_raise_when_strobe_window_end_is_before_start(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                strobe=[(8.0, 4.0)],
            )

    def test_should_raise_when_strobe_window_falls_outside_the_span(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS,
                fixture_type_id=_FULL_TYPE,
                brightness=a_minimal_brightness_keyframes(_BEATS),
                strobe=[(30.0, _BEATS + 2.0)],
            )

    def test_should_raise_with_zero_brightness_keyframes(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS, fixture_type_id=_FULL_TYPE, brightness=[]
            )

    def test_should_raise_with_exactly_one_brightness_keyframe(self) -> None:
        with pytest.raises(compose.InvalidCompositionError):
            compose.compose_slot_payload(
                beats=_BEATS, fixture_type_id=_FULL_TYPE, brightness=[(0.0, 1.0)]
            )
