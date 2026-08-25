"""Factories for rbxlight.macros.compose test data: brightness keyframe
lists, colour stop lists, strobe windows, and movement specs.

These are plain input data (tuples/dataclasses), not collaborators — real
values throughout, per the mocking policy (mock collaborators, factory
real data).
"""

from __future__ import annotations

from rbxlight.macros.compose import MovementSpec
from tests.fixtures.colour_fixtures import a_reference_colour

RED = a_reference_colour("red")[0]
GREEN = a_reference_colour("green")[0]
BLUE = a_reference_colour("blue")[0]


def a_minimal_brightness_keyframes(beats: float = 32.0) -> list[tuple[float, float]]:
    """The minimum valid case: exactly a start and an end, no interior
    points."""
    return [(0.0, 0.0), (beats, 1.0)]


def a_brightness_ramp_with_interior_points(
    beats: float = 32.0,
) -> list[tuple[float, float]]:
    """Start + two interior points + end."""
    return [(0.0, 0.0), (8.0, 1.0), (24.0, 0.5), (beats, 0.0)]


def a_single_colour_stop() -> list[tuple[float, int]]:
    """One stop -> one block holding one colour for the whole span."""
    return [(0.0, RED)]


def a_colour_gradient_stops(beats: float = 32.0) -> list[tuple[float, int]]:
    """Three ordered stops, all distinct colours, starting at beat 0."""
    return [(0.0, RED), (beats / 2, GREEN), (beats * 0.75, BLUE)]


def a_colour_hold_stops(beats: float = 32.0) -> list[tuple[float, int]]:
    """Two consecutive stops sharing the same colour — a hold, not a
    gradient, but must still tile correctly."""
    return [(0.0, RED), (beats / 2, RED)]


def a_strobe_window(
    start_beat: float = 4.0, end_beat: float = 8.0
) -> list[tuple[float, float]]:
    return [(start_beat, end_beat)]


def a_strobe_window_covering_full_span(
    beats: float = 32.0,
) -> list[tuple[float, float]]:
    return [(0.0, beats)]


def a_movement_spec(
    *,
    pattern: str = "Circle",
    width: float = 0.5,
    height: float = 0.5,
    offset_x: float = 0.5,
    offset_y: float = 0.5,
    round_angle: float = 0.0,
    offset_angle: float = 0.0,
    period_time: float = 20000.0,
    frequency_x: float = 2.0,
    frequency_y: float = 3.0,
    phase_x: float = 90.0,
    phase_y: float = 0.0,
    type: str = "Loop",
    direction: str = "Forward",
) -> MovementSpec:
    """A movement spec using the safe/common defaults observed in the
    live library (see rekordbox-lightingdb-schema skill)."""
    return MovementSpec(
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
    )


def a_rotate_span() -> tuple[float, float]:
    return (0.0, 360.0)
