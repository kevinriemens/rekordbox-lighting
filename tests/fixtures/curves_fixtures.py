"""Factories for rbxlight.macros.curves test data: colour palettes used
to exercise hold_then_snap_stops / smooth_loop_stops.

These are plain input data (lists of signed int32 ARGB ints), not
collaborators — real values throughout, per the mocking policy (mock
collaborators, factory real data). Colours are built via the same
reference-colour table used by tests/fixtures/colour_fixtures.py so a
failing assertion prints a recognizable value, not an opaque int.
"""

from __future__ import annotations

from tests.fixtures.colour_fixtures import a_reference_colour

RED = a_reference_colour("red")[0]
GREEN = a_reference_colour("green")[0]
BLUE = a_reference_colour("blue")[0]
YELLOW = a_reference_colour("yellow")[0]
MAGENTA = a_reference_colour("magenta")[0]


def a_four_colour_palette() -> list[int]:
    """Four distinct colours — the common case for palette-walking
    curves."""
    return [RED, GREEN, BLUE, YELLOW]


def a_single_colour_palette() -> list[int]:
    """Exactly one colour — the degenerate-but-valid case."""
    return [MAGENTA]


def an_empty_palette() -> list[int]:
    """Zero colours — the invalid case every palette-walking curve must
    reject."""
    return []
