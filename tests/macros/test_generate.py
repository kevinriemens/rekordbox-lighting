"""Tests for rbxlight.macros.generate — pure macro-shape primitives.
Contract: rekordbox-lighting-architecture skill ("Pure functions in
generate.py") + task requirements ("Macro generation primitives").

None of these functions accept a database connection — purity is enforced
structurally by the signature, and verified behaviorally here via
determinism (same inputs -> same output, every call).
"""

from __future__ import annotations

import inspect
from itertools import pairwise

import pytest

from rbxlight import lightingxml
from rbxlight.macros import generate
from tests.fixtures.colour_fixtures import a_reference_colour

_RED = a_reference_colour("red")[0]
_BLUE = a_reference_colour("blue")[0]
_GREEN = a_reference_colour("green")[0]

#: Fixture type that supports brightness/colour/strobe only (Simple Par) —
#: used to prove generators never rely on movement capability.
_RESTRICTED_TYPE = 101
#: Fixture type with full capability (Par).
_FULL_TYPE = 1


def _lit_windows(xml: str) -> list[tuple[float, float]]:
    """[(start_beat, end_beat), ...] where brightness y > 0, derived from a
    generator's brightness PointBlock."""
    model = lightingxml.parse(xml)
    points = sorted(model.brightness.points, key=lambda p: p.x)
    windows: list[tuple[float, float]] = []
    window_start: float | None = None
    for point in points:
        if point.y > 0 and window_start is None:
            window_start = point.x
        elif point.y == 0 and window_start is not None:
            windows.append((window_start, point.x))
            window_start = None
    return windows


class TestPurityIsStructural:
    """No generator accepts anything resembling a DB connection."""

    @pytest.mark.parametrize(
        "func",
        [
            generate.chase,
            generate.sweep,
            generate.pingpong,
            generate.colour_cycle,
            generate.strobe_hit,
        ],
    )
    def test_should_not_accept_a_connection_parameter(self, func) -> None:
        # Given: a generator function
        params = inspect.signature(func).parameters

        # Then: no parameter name suggests a DB/IO collaborator
        assert not any(
            "conn" in name or "connection" in name or "path" in name for name in params
        )


class TestDeterminism:
    def test_should_produce_identical_output_when_called_twice_with_same_chase_inputs(
        self,
    ) -> None:
        # Given: identical inputs
        slot_colours = {1: _RED, 2: _GREEN, 3: _BLUE}

        # When: called twice
        first = generate.chase(32.0, _FULL_TYPE, slot_colours)
        second = generate.chase(32.0, _FULL_TYPE, slot_colours)

        # Then: byte-identical output
        assert first == second

    def test_should_produce_identical_output_when_called_twice_with_same_colour_cycle_inputs(
        self,
    ) -> None:
        # Given: identical inputs
        palette = [_RED, _GREEN, _BLUE]

        # When: called twice
        first = generate.colour_cycle(32.0, _FULL_TYPE, palette)
        second = generate.colour_cycle(32.0, _FULL_TYPE, palette)

        # Then: byte-identical output
        assert first == second


class TestChase:
    def test_should_light_each_fixture_for_its_share_with_no_two_lit_simultaneously(
        self,
    ) -> None:
        # Given: 4 fixtures sharing a 32-beat macro, no overlap requested
        slot_colours = {1: _RED, 2: _GREEN, 3: _BLUE, 4: _RED}

        # When: generating a chase
        result = generate.chase(32.0, _FULL_TYPE, slot_colours, overlap=False)

        # Then: each fixture's lit window doesn't intersect any other's
        windows_by_slot = {
            slot_id: _lit_windows(xml) for slot_id, xml in result.items()
        }
        all_windows = [w for windows in windows_by_slot.values() for w in windows]
        all_windows.sort()
        for (start_a, end_a), (start_b, end_b) in pairwise(all_windows):
            assert end_a <= start_b

    def test_should_return_one_payload_per_fixture_slot(self) -> None:
        # Given: 3 fixtures
        slot_colours = {1: _RED, 5: _GREEN, 11: _BLUE}

        # When: generating a chase
        result = generate.chase(32.0, _FULL_TYPE, slot_colours)

        # Then: one XML payload per requested slot
        assert set(result.keys()) == {1, 5, 11}

    def test_should_never_position_outside_the_macro_beat_length(self) -> None:
        # Given: a chase across a short 16-beat macro
        slot_colours = {1: _RED, 2: _GREEN}
        beats = 16.0

        # When: generating
        result = generate.chase(beats, _FULL_TYPE, slot_colours)

        # Then: no point falls outside [0, beats]
        for xml in result.values():
            model = lightingxml.parse(xml)
            for point in model.brightness.points:
                assert 0.0 <= point.x <= beats


class TestSweep:
    def test_should_move_lit_region_from_first_to_last_fixture(self) -> None:
        # Given: an ordered set of fixtures
        slot_ids = [1, 2, 3, 4]

        # When: generating a sweep
        result = generate.sweep(32.0, _FULL_TYPE, slot_ids, _RED)

        # Then: each successive fixture's lit window starts no earlier than
        # the previous fixture's — the lit region moves start to end
        starts = []
        for slot_id in slot_ids:
            windows = _lit_windows(result[slot_id])
            assert windows, f"slot {slot_id} was never lit"
            starts.append(windows[0][0])
        assert starts == sorted(starts)

    def test_should_never_position_outside_the_macro_beat_length(self) -> None:
        # Given: a sweep across a 64-beat macro
        beats = 64.0

        # When: generating
        result = generate.sweep(beats, _FULL_TYPE, [1, 2, 3], _BLUE)

        # Then: no point falls outside [0, beats]
        for xml in result.values():
            model = lightingxml.parse(xml)
            for point in model.brightness.points:
                assert 0.0 <= point.x <= beats


class TestPingpong:
    def test_should_light_first_fixture_more_than_once_across_a_full_traversal(
        self,
    ) -> None:
        # Given: a 2-fixture ping-pong completing 1 whole traversal (there and back)
        slot_ids = [1, 2]

        # When: generating
        result = generate.pingpong(32.0, _FULL_TYPE, slot_ids, _RED, traversals=1)

        # Then: the first fixture is lit at the start AND again after the
        # reversal — a plain one-way sweep would only light it once
        first_windows = _lit_windows(result[1])
        assert len(first_windows) >= 2

    def test_should_never_position_outside_the_macro_beat_length(self) -> None:
        # Given: a ping-pong across a 32-beat macro
        beats = 32.0

        # When: generating
        result = generate.pingpong(beats, _FULL_TYPE, [1, 2, 3], _GREEN, traversals=2)

        # Then: no point falls outside [0, beats]
        for xml in result.values():
            model = lightingxml.parse(xml)
            for point in model.brightness.points:
                assert 0.0 <= point.x <= beats


class TestColourCycle:
    def test_should_step_through_palette_across_macro_length(self) -> None:
        # Given: a 3-colour palette across a 30-beat macro
        palette = [_RED, _GREEN, _BLUE]
        beats = 30.0

        # When: generating a colour cycle
        xml = generate.colour_cycle(beats, _FULL_TYPE, palette)
        model = lightingxml.parse(xml)

        # Then: the colour steps through the palette, in order, contiguously
        # covering [0, beats]
        blocks = sorted(model.colour, key=lambda b: b.xleft)
        assert [b.colourleft for b in blocks] == palette
        assert blocks[0].xleft == 0.0
        assert blocks[-1].xright == beats
        for a, b in pairwise(blocks):
            assert a.xright == b.xleft


class TestStrobeHit:
    def test_should_confine_burst_to_requested_range_and_be_silent_outside_it(
        self,
    ) -> None:
        # Given: a strobe hit requested for beats 10..14 of a 32-beat macro
        beats = 32.0

        # When: generating
        xml = generate.strobe_hit(beats, _FULL_TYPE, start_beat=10.0, end_beat=14.0)
        model = lightingxml.parse(xml)

        # Then: strobe programming exists only within the requested range
        assert len(model.strobe) == 1
        block = model.strobe[0]
        assert block.xleft == 10.0
        assert block.xright == 14.0
        assert block.strobeleft > 0
        assert block.stroberight > 0


class TestNeverEmitsUnsupportedCapability:
    """Generators only ever touch Brightness/Colour/Strobe — sections every
    fixture type supports — so targeting a movement-restricted type must
    never produce Position/Rotate/Gobo programming."""

    def test_should_never_emit_position_rotate_or_gobo_when_targeting_restricted_type(
        self,
    ) -> None:
        # Given: a fixture type with no Position/Rotate/Gobo hardware
        slot_colours = {101: _RED, 102: _GREEN}

        # When: generating with every primitive
        chase_result = generate.chase(32.0, _RESTRICTED_TYPE, slot_colours)
        colour_xml = generate.colour_cycle(32.0, _RESTRICTED_TYPE, [_RED, _GREEN])
        strobe_xml = generate.strobe_hit(32.0, _RESTRICTED_TYPE, 0.0, 4.0)

        # Then: none of the output ever has movement-family programming
        for xml in list(chase_result.values()) + [colour_xml, strobe_xml]:
            model = lightingxml.parse(xml)
            assert not model.position
            assert not model.rotate
            assert not model.gobo_present
