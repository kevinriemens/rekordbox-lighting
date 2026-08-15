"""Domain dataclasses + fixture-slot/capability constants.

Contract source: rekordbox-lightingdb-schema skill ("The 25 fixture slots",
"Which XML sections each fixture_type_id supports").
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Fixture slot / capability tables (shared by lightingxml, macros.generate,
# macros.repo, macros.yaml_io)
# ---------------------------------------------------------------------------

#: macro_fixture.id -> fixture_type_id, for all 25 real slots. NOT contiguous.
FIXTURE_SLOT_TYPES: dict[int, int] = {
    1: 1,
    2: 1,
    3: 1,
    4: 1,
    5: 2,
    6: 2,
    7: 2,
    8: 2,
    9: 2,
    10: 2,
    11: 3,
    12: 3,
    13: 3,
    14: 3,
    15: 4,
    16: 5,
    17: 8,
    18: 8,
    19: 9,
    101: 101,
    102: 101,
    105: 102,
    106: 102,
    111: 103,
    112: 103,
}

#: All 25 real fixture slot ids, in ascending id order (NOT position order).
FIXTURE_SLOT_IDS: tuple[int, ...] = tuple(sorted(FIXTURE_SLOT_TYPES.keys()))

#: fixture_type_id -> set of section names ("brightness"/"colour"/"strobe"/
#: "position"/"rotate"/"gobo") that fixture type supports.
FIXTURE_TYPE_CAPABILITIES: dict[int, frozenset[str]] = {
    1: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    2: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    3: frozenset({"brightness", "colour", "strobe", "position", "rotate", "gobo"}),
    4: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    5: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    8: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    9: frozenset({"brightness", "colour", "strobe", "position", "rotate"}),
    101: frozenset({"brightness", "colour", "strobe"}),
    102: frozenset({"brightness", "colour", "strobe"}),
    103: frozenset({"brightness", "colour", "strobe", "position", "rotate", "gobo"}),
}

FACTORY_ID_MAX: int = 916
SENTINEL_NEGATIVE_ID: int = -1
SEPARATOR_ID: int = 10000
USER_ID_START: int = 10001


# ---------------------------------------------------------------------------
# LightingEditModel dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    """One point in a Brightness PointBlock. type: 1=start, 2=interior, 3=end."""

    x: float
    y: float
    type: int


@dataclass(frozen=True)
class PointBlock:
    xleft: float
    xright: float
    points: tuple[Point, ...] = ()


@dataclass(frozen=True)
class ColourBlock:
    xleft: float
    colourleft: int
    xright: float
    colourright: int


@dataclass(frozen=True)
class StrobeBlock:
    xleft: float
    strobeleft: float
    xright: float
    stroberight: float


@dataclass(frozen=True)
class RotateBlock:
    xleft: float
    rotateleft: float
    xright: float
    rotateright: float


@dataclass(frozen=True)
class MovementBlock:
    xleft: float
    xright: float
    pattern: str
    width: float
    height: float
    offset_x: float
    offset_y: float
    round_angle: float
    offset_angle: float
    period_time: float
    frequency_x: float
    frequency_y: float
    phase_x: float
    phase_y: float
    type: str
    direction: str
    start_angle: float | None = None
    relative: float | None = None


@dataclass(frozen=True)
class LightingEditModel:
    """Parsed LightingEditModel XML payload for one macro_data row.

    Brightness/Colour/Strobe are always present in every real payload (even
    if empty). Position/Rotate/Gobo may be entirely ABSENT from the source
    XML (field is None) or present-but-empty (empty tuple) — this
    distinction must round-trip exactly.
    """

    brightness: PointBlock
    colour: tuple[ColourBlock, ...] = ()
    strobe: tuple[StrobeBlock, ...] = ()
    position: tuple[MovementBlock, ...] | None = None
    rotate: tuple[RotateBlock, ...] | None = None
    gobo_present: bool | None = (
        None  # None = <Gobo> absent, False = <Gobo/> present-empty
    )


@dataclass(frozen=True)
class Macro:
    id: int
    name: str
    beats: int
    fixed: int
    thumbnail: str
    preset: int
    enabled: int


@dataclass(frozen=True)
class MacroData:
    id: int
    macro_id: int
    macro_fixture_id: int
    xml: str  # raw LightingEditModel payload string, "" allowed
