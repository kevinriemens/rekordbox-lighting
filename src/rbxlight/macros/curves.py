"""Shared, reusable curve vocabulary that macro recipes bind to.

Extracted from the private helpers formerly inside
`macros/festive_presets.py` (now deleted) — this module owns the public
contract going forward. Pure — no DB, no I/O, no `lightingxml` import.
Output feeds `compose.compose_slot_payload`.

See the module docstring of `tests/macros/test_curves.py` for the full
public contract this module implements.
"""

from __future__ import annotations

import math

from rbxlight.macros import compose

#: Fraction of the shorter of (interval, decay) / (period) used as the
#: instantaneous "sharp" attack/edge width — small enough to read as a
#: cut rather than a ramp, but non-zero so keyframes stay strictly
#: ascending.
_EDGE_FRACTION = 0.02
#: Fraction of hold_beats reserved for the snap transition between two
#: consecutive holds in hold_then_snap_stops.
_SNAP_FRACTION = 0.05
#: Sampling density for raised_cosine_swell, per cycle.
_SAMPLES_PER_CYCLE = 16


class InvalidCurveError(ValueError):
    """Raised when curve parameters are out of domain (non-positive span,
    interval, decay, or period; a level outside [0.0, 1.0]; an empty
    palette).
    """


def _require_positive_span(span: float) -> None:
    if span <= 0.0:
        raise InvalidCurveError(f"span must be positive, got {span}")


def _require_positive(value: float, name: str) -> None:
    if value <= 0.0:
        raise InvalidCurveError(f"{name} must be positive, got {value}")


def _require_unit_interval(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise InvalidCurveError(f"{name} must be within [0.0, 1.0], got {value}")


def dedupe_ascending[T](points: list[tuple[float, T]]) -> list[tuple[float, T]]:
    """Returns `points` with any entry whose x <= the previously KEPT x
    dropped (first of a duplicate/regressing run wins). Result is always
    strictly ascending in x. Works for any second-element type
    (brightness floats, colour ints).
    """
    result: list[tuple[float, T]] = []
    for x, y in points:
        if result and x <= result[-1][0]:
            continue
        result.append((x, y))
    return result


def constant_level(span: float, level: float) -> list[tuple[float, float]]:
    """Flat brightness line at `level` across [0, span]. Exactly 2
    keyframes: (0.0, level), (span, level).
    """
    _require_positive_span(span)
    _require_unit_interval(level, "level")
    return [(0.0, level), (span, level)]


def raised_cosine_swell(
    span: float,
    floor: float,
    peak: float,
    cycles: int,
    *,
    phase: float = 0.0,
) -> list[tuple[float, float]]:
    """y(t) = floor + (peak - floor) * (1 - cos(2*pi*cycles*(t-phase)/span)) / 2
    sampled (with exact extrema included) over [0, span]. `phase` wraps
    modulo span/cycles (equivalently modulo span for cycles == 1) — any
    phase value, however large or negative, produces the same shape as
    its wrapped equivalent. cycles == 0 collapses to a constant `floor`
    line.
    """
    _require_positive_span(span)
    _require_unit_interval(floor, "floor")
    _require_unit_interval(peak, "peak")

    if cycles == 0:
        return [(0.0, floor), (span, floor)]

    period = span / cycles
    wrapped_phase = phase % period

    def y_at(t: float) -> float:
        angle = 2.0 * math.pi * (t - wrapped_phase) / period
        return floor + (peak - floor) * (1.0 - math.cos(angle)) / 2.0

    total_samples = cycles * _SAMPLES_PER_CYCLE
    grid = [k * span / total_samples for k in range(total_samples + 1)]

    extrema: list[float] = [0.0, span]
    k = 0
    while True:
        trough_t = wrapped_phase + k * period
        if trough_t > span:
            break
        extrema.append(trough_t)
        peak_t = trough_t + period / 2.0
        if peak_t <= span:
            extrema.append(peak_t)
        k += 1

    all_ts = sorted(set(grid) | set(extrema))
    return [(t, y_at(t)) for t in all_ts]


def attack_decay_pulses(
    span: float,
    floor: float,
    peak: float,
    interval: float,
    decay: float,
    *,
    phase: float = 0.0,
) -> list[tuple[float, float]]:
    """`floor` everywhere except a sharp attack to `peak` at each beat in
    {(phase mod interval) + k*interval : k = 0, 1, 2, ...} ∩ [0, span],
    each followed by a decay back to `floor` over `decay` beats (clipped
    to span). Consecutive pulses may overlap when decay > interval —
    both peaks still land, no keyframe is ever emitted outside [0, span].
    """
    _require_positive_span(span)
    _require_positive(interval, "interval")
    _require_positive(decay, "decay")

    attack_width = min(interval, decay) * _EDGE_FRACTION
    wrapped_phase = phase % interval

    raw: list[tuple[float, float]] = [(0.0, floor), (span, floor)]
    k = 0
    while True:
        beat = wrapped_phase + k * interval
        if beat > span:
            break
        attack_start = max(0.0, beat - attack_width)
        decay_end = min(span, beat + decay)
        raw.append((attack_start, floor))
        raw.append((beat, peak))
        raw.append((decay_end, floor))
        k += 1

    raw.sort(key=lambda point: point[0])
    return dedupe_ascending(raw)


def square_wave(
    span: float,
    low: float,
    high: float,
    period: float,
    *,
    phase: float = 0.0,
    duty: float = 0.5,
) -> list[tuple[float, float]]:
    """`low` everywhere except `high` inside each window
    [(phase mod period) + k*period, ... + duty*period] ∩ [0, span]. Hard
    transitions — every keyframe's y is exactly `low` or exactly `high`,
    never an intermediate ramp value.
    """
    _require_positive_span(span)
    _require_positive(period, "period")
    _require_unit_interval(low, "low")
    _require_unit_interval(high, "high")

    edge = period * _EDGE_FRACTION
    wrapped_phase = phase % period

    raw: list[tuple[float, float]] = [(0.0, low), (span, low)]
    k = 0
    while True:
        start = wrapped_phase + k * period
        if start > span:
            break
        end = min(span, start + duty * period)
        raw.append((max(0.0, start - edge), low))
        raw.append((start, high))
        raw.append((end, high))
        raw.append((min(span, end + edge), low))
        k += 1

    raw.sort(key=lambda point: point[0])
    return dedupe_ascending(raw)


def hold_then_snap_stops(
    palette: list[int],
    span: float,
    hold_beats: float,
    *,
    start_index: int = 0,
) -> list[tuple[float, int]]:
    """Walks `palette` cyclically from `start_index` (wraps modulo
    len(palette)), holding each colour for most of `hold_beats` before a
    short snap to the next — reads as a cut, not a gradient. First stop
    at beat 0.
    """
    if not palette:
        raise InvalidCurveError("palette must not be empty")
    _require_positive_span(span)
    _require_positive(hold_beats, "hold_beats")

    n = len(palette)
    holds: list[tuple[float, int]] = []
    i = 0
    while i * hold_beats < span:
        start = i * hold_beats
        holds.append((start, palette[(start_index + i) % n]))
        i += 1

    snap_width = hold_beats * _SNAP_FRACTION
    stops: list[tuple[float, int]] = []
    for index, (start, colour) in enumerate(holds):
        stops.append((start, colour))
        if index < len(holds) - 1:
            next_start = holds[index + 1][0]
            held_until = next_start - snap_width
            if held_until > start:
                stops.append((held_until, colour))

    return dedupe_ascending(stops)


def smooth_loop_stops(
    palette: list[int], span: float, *, start_index: int = 0
) -> list[tuple[float, int]]:
    """Evenly-spaced stops walking `palette` cyclically from
    `start_index` (wraps modulo len(palette)), full gradients between
    consecutive stops, closing back to the starting colour at `span` so
    it loops seamlessly.
    """
    if not palette:
        raise InvalidCurveError("palette must not be empty")
    _require_positive_span(span)

    n = len(palette)
    step = span / n
    rotated = [palette[(start_index + i) % n] for i in range(n)]
    stops = [(i * step, colour) for i, colour in enumerate(rotated)]
    stops.append((span, rotated[0]))
    return stops


def movement_spec(
    *,
    pattern: str,
    width: float,
    height: float,
    period_time: float,
    type: str,
    direction: str,
    offset_x: float = 0.5,
    offset_y: float = 0.5,
    round_angle: float = 0.0,
    offset_angle: float = 0.0,
    frequency_x: float = 2.0,
    frequency_y: float = 3.0,
    phase_x: float = 90.0,
    phase_y: float = 0.0,
    start_angle: float | None = None,
    relative: float | None = None,
) -> compose.MovementSpec:
    """Convenience constructor defaulting the rarely-varied MovementSpec
    fields to the schema-observed safe defaults (see
    rekordbox-lightingdb-schema skill).
    """
    return compose.MovementSpec(
        pattern=pattern,
        width=width,
        height=height,
        offset_x=offset_x,
        offset_y=offset_y,
        round_angle=round_angle,
        offset_angle=offset_angle,
        period_time=period_time,
        frequency_x=frequency_x,
        frequency_y=frequency_y,
        phase_x=phase_x,
        phase_y=phase_y,
        type=type,
        direction=direction,
        start_angle=start_angle,
        relative=relative,
    )
