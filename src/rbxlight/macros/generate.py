"""Pure macro-shape generation primitives: params in, XML string(s) out.
NEVER touch a database or the filesystem — see rekordbox-lighting-architecture
skill, "Pure functions in generate.py".

Every primitive here only ever emits Brightness/Colour/Strobe programming —
sections every fixture_type_id supports (see
rbxlight.models.FIXTURE_TYPE_CAPABILITIES) — so none of them can ever
produce a Position/Rotate/Gobo section a target fixture type doesn't have
hardware for.
"""

from __future__ import annotations

from rbxlight import lightingxml
from rbxlight.models import (
    FIXTURE_TYPE_CAPABILITIES,
    ColourBlock,
    LightingEditModel,
    Point,
    PointBlock,
    StrobeBlock,
)


class UnsupportedFixtureCapabilityError(ValueError):
    """Raised when asked to target a fixture_type_id with a section it does
    not support (see rbxlight.models.FIXTURE_TYPE_CAPABILITIES).
    """


def chase(
    beats: float,
    fixture_type_id: int,
    slot_colours: dict[int, int],
    *,
    overlap: bool = False,
) -> dict[int, str]:
    """Light `slot_colours` (an ordered slot_id -> colour mapping) one after
    another, each for beats / len(slot_colours). Returns {slot_id: xml}.

    With overlap=False, no two slots are lit (brightness > 0) at the same
    beat. Pure — deterministic for identical inputs, no I/O.
    """
    _require_known_fixture_type(fixture_type_id)
    slot_ids = list(slot_colours.keys())
    count = len(slot_ids)
    segment = beats / count
    pad = segment * 0.25 if overlap else 0.0
    windows = _segment_windows(beats, count, pad=pad)
    return {
        slot_id: _single_window_xml(beats, window, slot_colours[slot_id])
        for slot_id, window in zip(slot_ids, windows)
    }


def sweep(
    beats: float, fixture_type_id: int, slot_ids: list[int], colour: int
) -> dict[int, str]:
    """Move a single lit region across slot_ids from first to last. Returns
    {slot_id: xml}. Pure, deterministic.
    """
    _require_known_fixture_type(fixture_type_id)
    windows = _segment_windows(beats, len(slot_ids))
    return {
        slot_id: _single_window_xml(beats, window, colour)
        for slot_id, window in zip(slot_ids, windows)
    }


def pingpong(
    beats: float,
    fixture_type_id: int,
    slot_ids: list[int],
    colour: int,
    traversals: int,
) -> dict[int, str]:
    """Like sweep, but reverses direction at each end and completes exactly
    `traversals` whole back-and-forth passes within `beats`. Pure.
    """
    _require_known_fixture_type(fixture_type_id)
    count = len(slot_ids)
    total_passes = traversals * 2
    pass_duration = beats / total_passes

    windows_by_slot: dict[int, list[tuple[float, float]]] = {
        slot_id: [] for slot_id in slot_ids
    }
    for pass_index in range(total_passes):
        pass_start = pass_index * pass_duration
        order = slot_ids if pass_index % 2 == 0 else list(reversed(slot_ids))
        local_windows = _segment_windows(pass_duration, count)
        for slot_id, (local_start, local_end) in zip(order, local_windows):
            windows_by_slot[slot_id].append(
                (pass_start + local_start, pass_start + local_end)
            )

    return {
        slot_id: _multi_window_xml(beats, windows, colour)
        for slot_id, windows in windows_by_slot.items()
    }


def colour_cycle(beats: float, fixture_type_id: int, palette: list[int]) -> str:
    """Single-fixture XML payload string stepping through `palette` evenly
    across `beats`. Pure, deterministic.
    """
    _require_known_fixture_type(fixture_type_id)
    count = len(palette)
    segment = beats / count
    blocks = []
    for index, colour in enumerate(palette):
        xleft = index * segment
        xright = beats if index == count - 1 else (index + 1) * segment
        blocks.append(
            ColourBlock(
                xleft=xleft, colourleft=colour, xright=xright, colourright=colour
            )
        )

    model = LightingEditModel(
        brightness=_fully_lit_brightness(beats), colour=tuple(blocks), strobe=()
    )
    return lightingxml.serialize(model)


def strobe_hit(
    beats: float, fixture_type_id: int, start_beat: float, end_beat: float
) -> str:
    """Single-fixture XML payload string: a strobe burst confined to
    [start_beat, end_beat], silent (no strobe programming) outside it.
    Pure, deterministic.
    """
    _require_known_fixture_type(fixture_type_id)
    strobe_block = StrobeBlock(
        xleft=start_beat, strobeleft=1.0, xright=end_beat, stroberight=1.0
    )
    model = LightingEditModel(
        brightness=_fully_lit_brightness(beats), colour=(), strobe=(strobe_block,)
    )
    return lightingxml.serialize(model)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _require_known_fixture_type(fixture_type_id: int) -> None:
    if fixture_type_id not in FIXTURE_TYPE_CAPABILITIES:
        raise UnsupportedFixtureCapabilityError(
            f"unknown fixture_type_id {fixture_type_id}"
        )


def _fully_lit_brightness(beats: float) -> PointBlock:
    return PointBlock(
        xleft=0.0,
        xright=beats,
        points=(Point(x=0.0, y=1.0, type=1), Point(x=beats, y=1.0, type=3)),
    )


def _segment_windows(
    beats: float, count: int, *, pad: float = 0.0
) -> list[tuple[float, float]]:
    """count equal windows spanning [0, beats], optionally padded (and
    clamped) on both sides to create overlap between neighbours."""
    segment = beats / count
    windows = []
    for index in range(count):
        start = max(0.0, index * segment - pad)
        end = min(beats, (index + 1) * segment + pad)
        windows.append((start, end))
    return windows


def _merge_windows(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _multi_window_points(
    beats: float, windows: list[tuple[float, float]]
) -> tuple[Point, ...]:
    """Brightness Points for a curve lit only during `windows`, dark
    everywhere else across [0, beats]."""
    merged = _merge_windows(windows)
    waypoints: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in merged:
        if start > cursor:
            waypoints.append((cursor, 0.0))
            waypoints.append((start, 0.0))
        waypoints.append((start, 1.0))
        waypoints.append((end, 1.0))
        cursor = end
    # Always close with an explicit zero point at the very end — even a
    # window that runs right up to `beats` must have a trailing y=0 point
    # so a fixture lit through the last instant still reads as a closed,
    # bounded window rather than one that never turns back off.
    waypoints.append((cursor, 0.0))
    waypoints.append((beats, 0.0))

    deduped: list[tuple[float, float]] = []
    for waypoint in waypoints:
        if deduped and deduped[-1] == waypoint:
            continue
        deduped.append(waypoint)

    last_index = len(deduped) - 1
    return tuple(
        Point(x=x, y=y, type=(1 if idx == 0 else 3 if idx == last_index else 2))
        for idx, (x, y) in enumerate(deduped)
    )


def _single_window_xml(beats: float, window: tuple[float, float], colour: int) -> str:
    return _multi_window_xml(beats, [window], colour)


def _multi_window_xml(
    beats: float, windows: list[tuple[float, float]], colour: int
) -> str:
    brightness = PointBlock(
        xleft=0.0, xright=beats, points=_multi_window_points(beats, windows)
    )
    colour_block = ColourBlock(
        xleft=0.0, colourleft=colour, xright=beats, colourright=colour
    )
    model = LightingEditModel(brightness=brightness, colour=(colour_block,), strobe=())
    return lightingxml.serialize(model)
