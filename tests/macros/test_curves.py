"""Tests for rbxlight.macros.curves — the shared, reusable curve
vocabulary that macro recipes bind to. Extracted from the private
helpers formerly inside macros/festive_presets.py (now deleted); this
module owns the public contract going forward.

Pure — no DB, no I/O, no `lightingxml` import in the module under test.
Output feeds `compose.compose_slot_payload` (already built, already
tested) — this file does not re-test composition itself, but does
verify curves output is always valid *input* to it (a handful of
integration checks), per the task's edge-case list.

Public contract defined by this file (`rbxlight.macros.curves`):

    class InvalidCurveError(ValueError): ...

    def constant_level(span: float, level: float) -> list[tuple[float, float]]
        Flat brightness line at `level` across [0, span]. Exactly 2
        keyframes: (0.0, level), (span, level).

    def raised_cosine_swell(
        span: float, floor: float, peak: float, cycles: int, *,
        phase: float = 0.0,
    ) -> list[tuple[float, float]]
        y(t) = floor + (peak - floor) * (1 - cos(2*pi*cycles*(t-phase)/span)) / 2
        sampled (with exact extrema included) over [0, span]. `phase`
        wraps modulo span/cycles (equivalently modulo span for
        cycles == 1) — any phase value, however large or negative,
        produces the same shape as its wrapped equivalent. cycles == 0
        collapses to a constant `floor` line.

    def attack_decay_pulses(
        span: float, floor: float, peak: float, interval: float,
        decay: float, *, phase: float = 0.0,
    ) -> list[tuple[float, float]]
        `floor` everywhere except a sharp attack to `peak` at each beat
        in {(phase mod interval) + k*interval : k = 0, 1, 2, ...} ∩
        [0, span], each followed by a decay back to `floor` over
        `decay` beats (clipped to span). Consecutive pulses may
        overlap when decay > interval — both peaks still land, no
        keyframe is ever emitted outside [0, span].

    def square_wave(
        span: float, low: float, high: float, period: float, *,
        phase: float = 0.0, duty: float = 0.5,
    ) -> list[tuple[float, float]]
        `low` everywhere except `high` inside each window
        [(phase mod period) + k*period, ... + duty*period] ∩ [0, span].
        Hard transitions — every keyframe's y is exactly `low` or
        exactly `high`, never an intermediate ramp value.

    def hold_then_snap_stops(
        palette: list[int], span: float, hold_beats: float, *,
        start_index: int = 0,
    ) -> list[tuple[float, int]]
        Walks `palette` cyclically from `start_index` (wraps modulo
        len(palette)), holding each colour for most of `hold_beats`
        before a short snap to the next — reads as a cut, not a
        gradient. First stop at beat 0.

    def smooth_loop_stops(
        palette: list[int], span: float, *, start_index: int = 0,
    ) -> list[tuple[float, int]]
        Evenly-spaced stops walking `palette` cyclically from
        `start_index` (wraps modulo len(palette)), full gradients
        between consecutive stops, closing back to the starting colour
        at `span` so it loops seamlessly.

    def dedupe_ascending(points: list[tuple[float, T]]) -> list[tuple[float, T]]
        Returns `points` with any entry whose x <= the previously KEPT
        x dropped (first of a duplicate/regressing run wins). Result is
        always strictly ascending in x. Works for any second-element
        type (brightness floats, colour ints).

    def movement_spec(
        *, pattern: str, width: float, height: float, period_time: float,
        type: str, direction: str,
        offset_x: float = 0.5, offset_y: float = 0.5,
        round_angle: float = 0.0, offset_angle: float = 0.0,
        frequency_x: float = 2.0, frequency_y: float = 3.0,
        phase_x: float = 90.0, phase_y: float = 0.0,
        start_angle: float | None = None, relative: float | None = None,
    ) -> compose.MovementSpec
        Convenience constructor defaulting the rarely-varied
        MovementSpec fields to the schema-observed safe defaults (see
        rekordbox-lightingdb-schema skill).
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from rbxlight import lightingxml
from rbxlight.macros import compose, curves
from tests.fixtures.curves_fixtures import (
    a_four_colour_palette,
    a_single_colour_palette,
    an_empty_palette,
)

_SPAN = 32.0
#: Par (full capability, no gobo) and Moving Head (full capability incl.
#: gobo) — see rbxlight.models.FIXTURE_TYPE_CAPABILITIES.
_PAR_TYPE = 1
_MOVING_HEAD_TYPE = 3
#: Par (Simple) — brightness/colour/strobe only, no position/rotate.
_RESTRICTED_TYPE = 101


def _value_at(points: list[tuple[float, float]], beat: float) -> float:
    """Linearly interpolate `points` at `beat`, mirroring how rekordbox
    interpolates between consecutive Brightness keyframes. Test-only
    utility — lets tests assert "the curve's value at an arbitrary
    beat" without pinning the exact keyframe list.
    """
    if beat <= points[0][0]:
        return points[0][1]
    if beat >= points[-1][0]:
        return points[-1][1]
    for (x0, y0), (x1, y1) in pairwise(points):
        if x0 <= beat <= x1:
            if x1 == x0:
                return y1
            fraction = (beat - x0) / (x1 - x0)
            return y0 + fraction * (y1 - y0)
    raise AssertionError(f"beat {beat} not covered by points {points}")


def _assert_strictly_ascending(points: list[tuple[float, object]]) -> None:
    for (x0, _), (x1, _) in pairwise(points):
        assert x1 > x0, f"not strictly ascending: {x0} -> {x1}"


def _assert_within_span(points: list[tuple[float, object]], span: float) -> None:
    for x, _ in points:
        assert 0.0 <= x <= span, f"x={x} outside [0, {span}]"


# ---------------------------------------------------------------------------
# constant_level
# ---------------------------------------------------------------------------


class TestConstantLevel:
    def test_should_return_exactly_two_keyframes(self) -> None:
        # Given/When: a flat level across the span
        points = curves.constant_level(_SPAN, 0.6)

        # Then: minimum valid brightness shape — start and end only
        assert len(points) == 2

    def test_should_hold_the_level_at_both_endpoints(self) -> None:
        # Given/When
        points = curves.constant_level(_SPAN, 0.6)

        # Then: both endpoints carry the given level
        assert points[0] == (0.0, 0.6)
        assert points[-1] == (_SPAN, 0.6)

    def test_should_hold_the_level_everywhere_in_between(self) -> None:
        # Given/When
        points = curves.constant_level(_SPAN, 0.6)

        # Then: interpolated value anywhere in the span is still 0.6
        assert _value_at(points, _SPAN / 3) == pytest.approx(0.6)

    @pytest.mark.parametrize("level", [0.0, 1.0])
    def test_should_accept_boundary_levels(self, level: float) -> None:
        # Given/When
        points = curves.constant_level(_SPAN, level)

        # Then: composes without complaint at the 0.0/1.0 boundary
        assert points[0][1] == level

    @pytest.mark.parametrize("level", [-0.01, 1.01])
    def test_should_raise_for_a_level_outside_0_to_1(self, level: float) -> None:
        # Given/When/Then
        with pytest.raises(curves.InvalidCurveError):
            curves.constant_level(_SPAN, level)

    @pytest.mark.parametrize("span", [0.0, -5.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        # Given/When/Then
        with pytest.raises(curves.InvalidCurveError):
            curves.constant_level(span, 0.5)

    def test_should_be_deterministic(self) -> None:
        # Given/When: called twice with identical arguments
        first = curves.constant_level(_SPAN, 0.6)
        second = curves.constant_level(_SPAN, 0.6)

        # Then: identical output
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        # Given: a constant-level curve as the whole brightness section
        points = curves.constant_level(_SPAN, 0.5)

        # When: composed for a restricted (Par Simple) slot
        xml = compose.compose_slot_payload(
            beats=_SPAN, fixture_type_id=_RESTRICTED_TYPE, brightness=points
        )

        # Then: parses and round-trips without error
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# raised_cosine_swell
# ---------------------------------------------------------------------------


class TestRaisedCosineSwell:
    def test_should_reach_exact_floor_and_exact_peak(self) -> None:
        # Given/When: a single full cycle
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=1)

        # Then: the extremes are hit exactly, not merely approached
        ys = [y for _, y in points]
        assert min(ys) == pytest.approx(0.2, abs=1e-9)
        assert max(ys) == pytest.approx(0.9, abs=1e-9)

    def test_should_stay_within_floor_and_peak_bounds(self) -> None:
        # Given/When
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=3)

        # Then: never overshoots either bound
        assert all(0.2 - 1e-9 <= y <= 0.9 + 1e-9 for _, y in points)

    def test_should_ramp_smoothly_rather_than_snap(self) -> None:
        # Given/When: floor and peak are distinct
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=1)

        # Then: some keyframe sits strictly between the two extremes —
        # a genuine ramp, not a hard two-value switch
        assert any(0.2 < y < 0.9 for _, y in points)

    def test_should_place_the_peak_at_half_span_with_no_phase_offset(self) -> None:
        # Given/When: one full cycle, phase 0
        points = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=0.0
        )

        # Then: the peak lands exactly at the midpoint
        peak_x = max(points, key=lambda p: p[1])[0]
        assert peak_x == pytest.approx(_SPAN / 2)

    @pytest.mark.parametrize(
        "phase",
        [5.0, 5.0 + _SPAN, 5.0 - _SPAN, 5.0 - 2 * _SPAN],
        ids=["plain", "plus_one_span", "minus_one_span", "minus_two_spans"],
    )
    def test_should_wrap_any_phase_congruent_modulo_span(self, phase: float) -> None:
        # Given: several phase values, all congruent to 5.0 mod span
        points = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=phase
        )

        # Then: the peak always lands at the same wrapped location
        peak_x = max(points, key=lambda p: p[1])[0]
        expected = (_SPAN / 2 + 5.0) % _SPAN
        assert peak_x == pytest.approx(expected)

    def test_should_be_unaffected_by_shifting_phase_by_a_whole_span(self) -> None:
        # Given: two phases one full span apart
        first = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=3.0
        )
        second = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=3.0 + _SPAN
        )

        # Then: identical shape
        assert first == second

    def test_should_actually_move_the_peak_for_a_non_trivial_phase_offset(
        self,
    ) -> None:
        # Given: two phases that are NOT congruent modulo the span
        unshifted = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=0.0
        )
        shifted = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=1, phase=_SPAN / 4
        )

        # Then: the peak location genuinely differs
        unshifted_peak_x = max(unshifted, key=lambda p: p[1])[0]
        shifted_peak_x = max(shifted, key=lambda p: p[1])[0]
        assert shifted_peak_x != pytest.approx(unshifted_peak_x)

    def test_should_collapse_to_a_constant_floor_when_cycles_is_zero(self) -> None:
        # Given/When: zero complete cycles
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=0)

        # Then: never swells — flat at floor throughout
        assert all(y == pytest.approx(0.2) for _, y in points)
        assert len(points) >= 2

    def test_should_produce_more_extrema_with_more_cycles(self) -> None:
        # Given/When: one cycle vs three cycles across the same span
        one_cycle = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=1)
        three_cycles = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=3)

        # Then: three complete swells produce (at least) three times the
        # peak occurrences of one swell
        def _peak_count(points: list[tuple[float, float]]) -> int:
            return sum(1 for _, y in points if y == pytest.approx(0.9, abs=1e-9))

        assert _peak_count(three_cycles) >= _peak_count(one_cycle) * 3 - 1

    def test_should_handle_floor_equal_to_peak(self) -> None:
        # Given/When: zero amplitude
        points = curves.raised_cosine_swell(_SPAN, floor=0.5, peak=0.5, cycles=2)

        # Then: constant at that shared value throughout
        assert all(y == pytest.approx(0.5) for _, y in points)

    def test_should_handle_floor_greater_than_peak(self) -> None:
        # Given/When: an inverted swell (floor above peak)
        points = curves.raised_cosine_swell(_SPAN, floor=0.9, peak=0.2, cycles=1)

        # Then: bounds still respected, just swapped
        ys = [y for _, y in points]
        assert min(ys) == pytest.approx(0.2, abs=1e-9)
        assert max(ys) == pytest.approx(0.9, abs=1e-9)

    def test_should_produce_strictly_ascending_positions(self) -> None:
        # Given/When
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=2)

        # Then
        _assert_strictly_ascending(points)
        _assert_within_span(points, _SPAN)

    @pytest.mark.parametrize("span", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        # Given/When/Then
        with pytest.raises(curves.InvalidCurveError):
            curves.raised_cosine_swell(span, floor=0.2, peak=0.9, cycles=1)

    @pytest.mark.parametrize("floor, peak", [(-0.1, 0.5), (0.5, 1.1)])
    def test_should_raise_when_floor_or_peak_outside_0_to_1(
        self, floor: float, peak: float
    ) -> None:
        # Given/When/Then
        with pytest.raises(curves.InvalidCurveError):
            curves.raised_cosine_swell(_SPAN, floor=floor, peak=peak, cycles=1)

    def test_should_be_deterministic(self) -> None:
        # Given/When
        first = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=2, phase=3.0
        )
        second = curves.raised_cosine_swell(
            _SPAN, floor=0.2, peak=0.9, cycles=2, phase=3.0
        )

        # Then
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        # Given: a swell as the whole brightness section
        points = curves.raised_cosine_swell(_SPAN, floor=0.2, peak=0.9, cycles=2)

        # When: composed for a full-capability slot
        xml = compose.compose_slot_payload(
            beats=_SPAN, fixture_type_id=_PAR_TYPE, brightness=points
        )

        # Then: parses and round-trips without error
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# attack_decay_pulses
# ---------------------------------------------------------------------------


def _expected_pulse_beats(span: float, interval: float, phase: float) -> list[float]:
    """Test-only replica of the documented pulse-timing contract."""
    normalized_phase = phase % interval
    beats: list[float] = []
    k = 0
    while True:
        beat = normalized_phase + k * interval
        if beat > span:
            break
        beats.append(beat)
        k += 1
    return beats


class TestAttackDecayPulses:
    def test_should_place_a_peak_at_each_expected_pulse_beat(self) -> None:
        # Given: a widely-spaced, non-overlapping pulse train
        span, interval, decay, phase = 20.0, 5.0, 0.5, 1.0
        points = curves.attack_decay_pulses(
            span, floor=0.1, peak=1.0, interval=interval, decay=decay, phase=phase
        )

        # When: sampling at each expected pulse beat
        expected = _expected_pulse_beats(span, interval, phase)

        # Then: the curve is at peak exactly there
        for beat in expected:
            assert _value_at(points, beat) == pytest.approx(1.0, abs=1e-6)

    def test_should_return_to_floor_between_non_overlapping_pulses(self) -> None:
        # Given: pulses far enough apart that decay never overlaps
        span, interval, decay, phase = 20.0, 5.0, 0.5, 1.0
        points = curves.attack_decay_pulses(
            span, floor=0.1, peak=1.0, interval=interval, decay=decay, phase=phase
        )

        # Then: halfway between two consecutive pulses, we're back at floor
        assert _value_at(points, phase + interval / 2) == pytest.approx(0.1, abs=1e-6)

    def test_should_allow_overlapping_pulses_when_decay_exceeds_interval(self) -> None:
        # Given: decay much longer than the repeat interval
        span, interval, decay, phase = 20.0, 2.0, 5.0, 1.0
        points = curves.attack_decay_pulses(
            span, floor=0.1, peak=1.0, interval=interval, decay=decay, phase=phase
        )

        # When: sampling at each expected pulse beat
        expected = _expected_pulse_beats(span, interval, phase)

        # Then: every pulse still reaches peak, and the sequence is
        # still a valid strictly-ascending keyframe list despite overlap
        for beat in expected:
            assert _value_at(points, beat) == pytest.approx(1.0, abs=1e-6)
        _assert_strictly_ascending(points)
        assert len(expected) > 1  # the overlap scenario is non-trivial

    def test_should_not_emit_keyframes_outside_the_span(self) -> None:
        # Given: a pulse train that runs right up to the end of the span
        points = curves.attack_decay_pulses(
            span=10.0, floor=0.1, peak=1.0, interval=3.0, decay=4.0, phase=1.0
        )

        # Then
        _assert_within_span(points, 10.0)

    def test_should_be_unaffected_by_shifting_phase_by_a_whole_interval(self) -> None:
        # Given: two phases one interval apart
        first = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )
        second = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=5.0
        )

        # Then: identical pulse train
        assert first == second

    def test_should_wrap_a_negative_phase(self) -> None:
        # Given: a negative phase and its interval-wrapped equivalent
        negative = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=-1.0
        )
        wrapped = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=3.0
        )

        # Then: identical pulse train
        assert negative == wrapped

    def test_should_stay_within_floor_and_peak_bounds(self) -> None:
        # Given/When
        points = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )

        # Then
        assert all(0.1 - 1e-9 <= y <= 1.0 + 1e-9 for _, y in points)

    def test_should_produce_strictly_ascending_positions(self) -> None:
        # Given/When
        points = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )

        # Then
        _assert_strictly_ascending(points)

    @pytest.mark.parametrize("span", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.attack_decay_pulses(
                span, floor=0.1, peak=1.0, interval=4.0, decay=0.5
            )

    @pytest.mark.parametrize("interval", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_interval(self, interval: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.attack_decay_pulses(
                _SPAN, floor=0.1, peak=1.0, interval=interval, decay=0.5
            )

    @pytest.mark.parametrize("decay", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_decay(self, decay: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.attack_decay_pulses(
                _SPAN, floor=0.1, peak=1.0, interval=4.0, decay=decay
            )

    def test_should_be_deterministic(self) -> None:
        first = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )
        second = curves.attack_decay_pulses(
            span=20.0, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        # Given
        points = curves.attack_decay_pulses(
            span=_SPAN, floor=0.1, peak=1.0, interval=4.0, decay=0.5, phase=1.0
        )

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN, fixture_type_id=_PAR_TYPE, brightness=points
        )

        # Then
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# square_wave
# ---------------------------------------------------------------------------


def _expected_windows(
    span: float, period: float, phase: float, duty: float
) -> list[tuple[float, float]]:
    """Test-only replica of the documented window-timing contract."""
    normalized_phase = phase % period
    windows: list[tuple[float, float]] = []
    k = 0
    while True:
        start = normalized_phase + k * period
        if start > span:
            break
        end = min(span, start + duty * period)
        windows.append((start, end))
        k += 1
    return windows


class TestSquareWave:
    def test_should_only_ever_be_low_or_high_never_intermediate(self) -> None:
        # Given/When: a square wave — hard transitions, no ramp
        points = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0)

        # Then: every keyframe value is exactly one of the two levels
        assert all(y in (0.1, 0.9) for _, y in points)

    def test_should_be_high_inside_each_expected_window(self) -> None:
        # Given
        span, period, phase, duty = 20.0, 4.0, 1.0, 0.5
        points = curves.square_wave(
            span, low=0.1, high=0.9, period=period, phase=phase, duty=duty
        )

        # When: sampling the middle of each expected high window
        for start, end in _expected_windows(span, period, phase, duty):
            midpoint = (start + end) / 2

            # Then
            assert _value_at(points, midpoint) == pytest.approx(0.9)

    def test_should_be_low_between_windows(self) -> None:
        # Given
        span, period, phase, duty = 20.0, 4.0, 1.0, 0.5
        points = curves.square_wave(
            span, low=0.1, high=0.9, period=period, phase=phase, duty=duty
        )
        windows = _expected_windows(span, period, phase, duty)

        # When: sampling just after one window ends and before the next begins
        gap_midpoint = (windows[0][1] + windows[1][0]) / 2

        # Then
        assert _value_at(points, gap_midpoint) == pytest.approx(0.1)

    def test_should_be_unaffected_by_shifting_phase_by_a_whole_period(self) -> None:
        # Given
        first = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=1.0)
        second = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=9.0)

        # Then
        assert first == second

    def test_should_wrap_a_negative_phase(self) -> None:
        # Given
        negative = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=-1.0)
        wrapped = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=7.0)

        # Then
        assert negative == wrapped

    def test_should_produce_strictly_ascending_positions(self) -> None:
        points = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0)
        _assert_strictly_ascending(points)
        _assert_within_span(points, _SPAN)

    def test_should_stay_within_low_and_high_bounds(self) -> None:
        points = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0)
        assert all(0.1 - 1e-9 <= y <= 0.9 + 1e-9 for _, y in points)

    @pytest.mark.parametrize("span", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.square_wave(span, low=0.1, high=0.9, period=8.0)

    @pytest.mark.parametrize("period", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_period(self, period: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.square_wave(_SPAN, low=0.1, high=0.9, period=period)

    @pytest.mark.parametrize("low, high", [(-0.1, 0.5), (0.5, 1.1)])
    def test_should_raise_when_low_or_high_outside_0_to_1(
        self, low: float, high: float
    ) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.square_wave(_SPAN, low=low, high=high, period=8.0)

    def test_should_be_deterministic(self) -> None:
        first = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=1.0)
        second = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0, phase=1.0)
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        points = curves.square_wave(_SPAN, low=0.1, high=0.9, period=8.0)
        xml = compose.compose_slot_payload(
            beats=_SPAN, fixture_type_id=_PAR_TYPE, brightness=points
        )
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# hold_then_snap_stops
# ---------------------------------------------------------------------------


class TestHoldThenSnapStops:
    def test_should_start_at_beat_zero(self) -> None:
        # Given/When
        stops = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)

        # Then
        assert stops[0][0] == 0.0

    def test_should_start_from_the_given_palette_offset(self) -> None:
        # Given
        palette = a_four_colour_palette()

        # When
        stops = curves.hold_then_snap_stops(palette, _SPAN, 8.0, start_index=2)

        # Then
        assert stops[0][1] == palette[2]

    def test_should_wrap_a_palette_offset_larger_than_the_palette_length(self) -> None:
        # Given
        palette = a_four_colour_palette()
        n = len(palette)

        # When
        wrapped = curves.hold_then_snap_stops(palette, _SPAN, 8.0, start_index=n + 2)
        direct = curves.hold_then_snap_stops(palette, _SPAN, 8.0, start_index=2)

        # Then: wrapping produces the identical result
        assert wrapped == direct

    def test_should_hold_each_colour_for_most_of_its_interval_before_snapping(
        self,
    ) -> None:
        # Given: a 3-colour palette walked over exactly 3 holds
        palette = a_four_colour_palette()[:3]
        hold_beats = 8.0
        span = hold_beats * 3

        # When
        stops = curves.hold_then_snap_stops(palette, span, hold_beats)

        # Then: each non-final hold has a repeated-colour pair spanning
        # most (not all) of the hold interval — a hold, then a snap
        holds_by_colour: dict[int, list[float]] = {}
        for beat, colour in stops:
            holds_by_colour.setdefault(colour, []).append(beat)

        for index in range(2):  # first two holds are non-final
            colour = palette[index]
            beats_for_colour = sorted(holds_by_colour[colour])
            assert len(beats_for_colour) >= 2
            start, held_until = beats_for_colour[0], beats_for_colour[1]
            assert held_until - start >= hold_beats * 0.5
            assert held_until < start + hold_beats

    def test_should_walk_the_palette_cyclically(self) -> None:
        # Given: a span covering the palette exactly twice
        palette = a_four_colour_palette()
        hold_beats = 4.0
        span = hold_beats * len(palette) * 2

        # When
        stops = curves.hold_then_snap_stops(palette, span, hold_beats)

        # Then: the colour landing exactly on each hold's start beat
        # matches the expected cyclic walk
        by_beat = dict(stops)
        for i in range(len(palette) * 2):
            expected_colour = palette[i % len(palette)]
            assert by_beat[i * hold_beats] == expected_colour

    def test_should_handle_a_single_colour_palette(self) -> None:
        # Given/When
        stops = curves.hold_then_snap_stops(a_single_colour_palette(), _SPAN, 8.0)

        # Then: still valid — starts at 0, only ever that one colour
        assert stops[0][0] == 0.0
        colour = a_single_colour_palette()[0]
        assert all(c == colour for _, c in stops)

    def test_should_raise_for_an_empty_palette(self) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.hold_then_snap_stops(an_empty_palette(), _SPAN, 8.0)

    @pytest.mark.parametrize("span", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.hold_then_snap_stops(a_four_colour_palette(), span, 8.0)

    @pytest.mark.parametrize("hold_beats", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_hold_beats(
        self, hold_beats: float
    ) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, hold_beats)

    def test_should_produce_strictly_ascending_positions_within_the_span(self) -> None:
        stops = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)
        _assert_strictly_ascending(stops)
        _assert_within_span(stops, _SPAN)

    def test_should_be_deterministic(self) -> None:
        first = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)
        second = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        # Given
        stops = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN,
            fixture_type_id=_PAR_TYPE,
            brightness=curves.constant_level(_SPAN, 0.8),
            colour=stops,
        )

        # Then
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# smooth_loop_stops
# ---------------------------------------------------------------------------


class TestSmoothLoopStops:
    def test_should_start_at_beat_zero_with_the_given_offset_colour(self) -> None:
        # Given
        palette = a_four_colour_palette()

        # When
        stops = curves.smooth_loop_stops(palette, _SPAN, start_index=1)

        # Then
        assert stops[0] == (0.0, palette[1])

    def test_should_close_back_to_the_starting_colour_at_the_span(self) -> None:
        # Given
        palette = a_four_colour_palette()

        # When
        stops = curves.smooth_loop_stops(palette, _SPAN)

        # Then: seamless loop closure
        assert stops[-1] == (_SPAN, palette[0])

    def test_should_space_stops_evenly_across_the_palette(self) -> None:
        # Given
        palette = a_four_colour_palette()
        n = len(palette)

        # When
        stops = curves.smooth_loop_stops(palette, _SPAN)

        # Then: n evenly-spaced walking stops plus the final closure
        assert len(stops) == n + 1
        for index, (beat, colour) in enumerate(stops[:n]):
            assert beat == pytest.approx(index * (_SPAN / n))
            assert colour == palette[index]

    def test_should_wrap_a_palette_offset_larger_than_the_palette_length(self) -> None:
        # Given
        palette = a_four_colour_palette()
        n = len(palette)

        # When
        wrapped = curves.smooth_loop_stops(palette, _SPAN, start_index=n + 1)
        direct = curves.smooth_loop_stops(palette, _SPAN, start_index=1)

        # Then
        assert wrapped == direct

    def test_should_never_repeat_a_colour_between_consecutive_walking_stops(
        self,
    ) -> None:
        # Given: distinct colours throughout
        palette = a_four_colour_palette()

        # When
        stops = curves.smooth_loop_stops(palette, _SPAN)

        # Then: no two adjacent walking stops (excluding the final
        # closure) share a colour — a genuine gradient, not a hold
        walking_stops = stops[:-1]
        for (_, colour_a), (_, colour_b) in pairwise(walking_stops):
            assert colour_a != colour_b

    def test_should_handle_a_single_colour_palette(self) -> None:
        # Given/When
        colour = a_single_colour_palette()[0]
        stops = curves.smooth_loop_stops(a_single_colour_palette(), _SPAN)

        # Then: degenerate but valid — same colour at both ends
        assert stops[0] == (0.0, colour)
        assert stops[-1] == (_SPAN, colour)

    def test_should_raise_for_an_empty_palette(self) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.smooth_loop_stops(an_empty_palette(), _SPAN)

    @pytest.mark.parametrize("span", [0.0, -1.0])
    def test_should_raise_for_a_non_positive_span(self, span: float) -> None:
        with pytest.raises(curves.InvalidCurveError):
            curves.smooth_loop_stops(a_four_colour_palette(), span)

    def test_should_produce_strictly_ascending_positions_within_the_span(self) -> None:
        stops = curves.smooth_loop_stops(a_four_colour_palette(), _SPAN)
        _assert_strictly_ascending(stops)
        _assert_within_span(stops, _SPAN)

    def test_should_be_deterministic(self) -> None:
        first = curves.smooth_loop_stops(a_four_colour_palette(), _SPAN)
        second = curves.smooth_loop_stops(a_four_colour_palette(), _SPAN)
        assert first == second

    def test_should_compose_into_a_valid_payload(self) -> None:
        # Given
        stops = curves.smooth_loop_stops(a_four_colour_palette(), _SPAN)

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN,
            fixture_type_id=_PAR_TYPE,
            brightness=curves.constant_level(_SPAN, 0.8),
            colour=stops,
        )

        # Then
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml


# ---------------------------------------------------------------------------
# dedupe_ascending
# ---------------------------------------------------------------------------


class TestDedupeAscending:
    def test_should_return_empty_for_empty_input(self) -> None:
        assert curves.dedupe_ascending([]) == []

    def test_should_leave_a_strictly_ascending_sequence_unchanged(self) -> None:
        # Given
        points = [(0.0, 0.1), (1.0, 0.5), (2.0, 0.9)]

        # When/Then
        assert curves.dedupe_ascending(points) == points

    def test_should_drop_points_with_a_duplicate_x(self) -> None:
        # Given: a duplicate x at position 1.0
        points = [(0.0, 0.1), (1.0, 0.5), (1.0, 0.6), (2.0, 0.9)]

        # When
        result = curves.dedupe_ascending(points)

        # Then: only the first occurrence of x=1.0 survives
        assert result == [(0.0, 0.1), (1.0, 0.5), (2.0, 0.9)]

    def test_should_drop_points_that_regress_backwards(self) -> None:
        # Given: a point that moves backwards in x
        points = [(0.0, 0.1), (2.0, 0.5), (1.0, 0.9), (3.0, 0.2)]

        # When
        result = curves.dedupe_ascending(points)

        # Then: the regressing point is dropped, not reordered
        assert result == [(0.0, 0.1), (2.0, 0.5), (3.0, 0.2)]

    def test_should_guarantee_the_result_is_strictly_ascending(self) -> None:
        # Given: a mixed bag of duplicates and regressions
        points = [(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (0.5, 2.0), (2.0, 3.0)]

        # When
        result = curves.dedupe_ascending(points)

        # Then
        _assert_strictly_ascending(result)

    def test_should_work_with_integer_second_elements_too(self) -> None:
        # Given: colour stops (int second element), not just brightness floats
        stops = [(0.0, -65536), (0.0, -256), (1.0, -1)]

        # When
        result = curves.dedupe_ascending(stops)

        # Then
        assert result == [(0.0, -65536), (1.0, -1)]

    def test_should_be_deterministic(self) -> None:
        points = [(0.0, 0.1), (1.0, 0.5), (1.0, 0.9), (2.0, 0.2)]
        assert curves.dedupe_ascending(points) == curves.dedupe_ascending(points)


# ---------------------------------------------------------------------------
# movement_spec
# ---------------------------------------------------------------------------


class TestMovementSpec:
    def test_should_set_the_given_required_fields(self) -> None:
        # Given/When
        spec = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
        )

        # Then
        assert spec.pattern == "Circle"
        assert spec.width == 30.0
        assert spec.height == 40.0
        assert spec.period_time == 20000.0
        assert spec.type == "Loop"
        assert spec.direction == "Forward"

    def test_should_default_the_rarely_varied_fields_to_schema_safe_defaults(
        self,
    ) -> None:
        # Given/When: only the required fields supplied
        spec = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
        )

        # Then: matches rekordbox-lightingdb-schema's documented safe
        # defaults for the near-constant MovementBlock fields
        assert spec.offset_x == 0.5
        assert spec.offset_y == 0.5
        assert spec.round_angle == 0.0
        assert spec.offset_angle == 0.0
        assert spec.frequency_x == 2.0
        assert spec.frequency_y == 3.0
        assert spec.phase_x == 90.0
        assert spec.phase_y == 0.0
        assert spec.start_angle is None
        assert spec.relative is None

    def test_should_allow_overriding_a_rarely_varied_field(self) -> None:
        # Given/When
        spec = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
            frequency_x=4.0,
        )

        # Then
        assert spec.frequency_x == 4.0

    def test_should_return_a_compose_movement_spec_instance(self) -> None:
        # Given/When
        spec = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
        )

        # Then
        assert isinstance(spec, compose.MovementSpec)

    def test_should_compose_into_a_valid_moving_head_payload(self) -> None:
        # Given
        spec = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
        )

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=curves.constant_level(_SPAN, 1.0),
            movement=spec,
        )

        # Then
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml
        assert model.position is not None and len(model.position) == 1


# ---------------------------------------------------------------------------
# Cross-cutting: curves combine into one realistic, fully-populated slot
# ---------------------------------------------------------------------------


class TestCurvesCombineIntoARealisticSlot:
    def test_should_compose_a_fully_populated_moving_head_slot(self) -> None:
        # Given: every curve family feeding one slot at once, the way a
        # real macro recipe would use this module
        brightness = curves.raised_cosine_swell(_SPAN, floor=0.25, peak=1.0, cycles=2)
        colour = curves.smooth_loop_stops(a_four_colour_palette(), _SPAN)
        movement = curves.movement_spec(
            pattern="Circle",
            width=30.0,
            height=40.0,
            period_time=20000.0,
            type="Loop",
            direction="Forward",
        )

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN,
            fixture_type_id=_MOVING_HEAD_TYPE,
            brightness=brightness,
            colour=colour,
            movement=movement,
        )

        # Then: a single fully-populated payload round-trips exactly
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml

    def test_should_compose_a_fully_populated_par_slot_with_pulses_and_snaps(
        self,
    ) -> None:
        # Given: the "hit" vocabulary (attack-decay + hold-then-snap)
        brightness = curves.attack_decay_pulses(
            _SPAN, floor=0.15, peak=1.0, interval=4.0, decay=0.5, phase=0.5
        )
        colour = curves.hold_then_snap_stops(a_four_colour_palette(), _SPAN, 8.0)

        # When
        xml = compose.compose_slot_payload(
            beats=_SPAN, fixture_type_id=_PAR_TYPE, brightness=brightness, colour=colour
        )

        # Then
        model = lightingxml.parse(xml)
        assert lightingxml.serialize(model) == xml
