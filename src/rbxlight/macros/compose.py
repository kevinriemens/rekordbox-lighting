"""Pure macro-composition primitive: build one LightingEditModel payload
for one fixture slot from declarative parts (brightness keyframes, colour
stops, strobe windows, a movement spec, a rotate span).

Pure — no DB, no I/O (see rekordbox-lighting-architecture skill, "Pure
functions in generate.py" — this module follows the same rule one layer
up: `generate.py`'s primitives assemble a fixed shape; this module lets a
caller declare arbitrary Brightness/Colour/Strobe/Position/Rotate content
for a single slot, still capability-checked against
`rbxlight.models.FIXTURE_TYPE_CAPABILITIES`).

Reuses `lightingxml.serialize` and the `models.py` dataclasses — never
hand-builds XML strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from rbxlight import lightingxml
from rbxlight.models import (
    FIXTURE_TYPE_CAPABILITIES,
    ColourBlock,
    LightingEditModel,
    MovementBlock,
    Point,
    PointBlock,
    RotateBlock,
    StrobeBlock,
)


class UnknownFixtureTypeError(ValueError):
    """Raised when `fixture_type_id` is not in FIXTURE_TYPE_CAPABILITIES."""


class UnsupportedSectionError(ValueError):
    """Raised when a section (movement/rotate) is requested for a fixture
    type whose hardware doesn't support it.
    """


class InvalidCompositionError(ValueError):
    """Raised when the declared content itself is invalid — out-of-domain
    beats, out-of-range levels, unordered/duplicate stops, degenerate
    strobe windows, too few brightness keyframes, etc.
    """


@dataclass(frozen=True)
class MovementSpec:
    """Declarative movement parameters for one Position/MovementBlock.
    `xleft`/`xright` are not part of this spec — compose_slot_payload
    always spans the block across the full beat range.
    """

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


def compose_slot_payload(
    beats: float,
    fixture_type_id: int,
    *,
    brightness: list[tuple[float, float]],
    colour: list[tuple[float, int]] | None = None,
    strobe: list[tuple[float, float]] | None = None,
    movement: MovementSpec | None = None,
    rotate: tuple[float, float] | None = None,
) -> str:
    """Compose one fixture slot's LightingEditModel XML payload.

    - `brightness`: ordered (beat, level) keyframes, at least 2, each
      beat in [0, beats] and each level in [0.0, 1.0]. The declared
      Brightness block always spans exactly [0, beats], regardless of
      where the first/last keyframe actually sit.
    - `colour`: ordered (beat, signed_argb) stops, first stop at beat 0.
      One stop holds that colour for the whole span. Multiple stops tile
      contiguously: consecutive stops form a gradient block between them;
      the last stop holds to `beats`.
    - `strobe`: (start_beat, end_beat) windows; strobe content exists only
      inside them.
    - `movement`/`rotate`: raise UnsupportedSectionError if the fixture
      type's capabilities don't include position/rotate. If the type
      supports a section but it wasn't requested, that section is
      present-but-empty (never silently dropped from a capable type).

    Raises UnknownFixtureTypeError for an unrecognized fixture_type_id,
    UnsupportedSectionError for movement/rotate on an incapable type, and
    InvalidCompositionError for any out-of-domain/malformed content.
    Pure — no DB, no I/O, deterministic for identical inputs.
    """
    if fixture_type_id not in FIXTURE_TYPE_CAPABILITIES:
        raise UnknownFixtureTypeError(f"unknown fixture_type_id {fixture_type_id}")
    capabilities = FIXTURE_TYPE_CAPABILITIES[fixture_type_id]

    if movement is not None and "position" not in capabilities:
        raise UnsupportedSectionError(
            f"fixture_type_id {fixture_type_id} does not support Position/movement"
        )
    if rotate is not None and "rotate" not in capabilities:
        raise UnsupportedSectionError(
            f"fixture_type_id {fixture_type_id} does not support Rotate"
        )

    brightness_block = _build_brightness(beats, brightness)
    colour_blocks = _build_colour_blocks(beats, colour) if colour else ()
    strobe_blocks = _build_strobe_blocks(beats, strobe) if strobe else ()

    position: tuple[MovementBlock, ...] | None = None
    if "position" in capabilities:
        position = (
            (_build_movement_block(beats, movement),) if movement is not None else ()
        )

    rotate_blocks: tuple[RotateBlock, ...] | None = None
    if "rotate" in capabilities:
        rotate_blocks = (
            (_build_rotate_block(beats, rotate),) if rotate is not None else ()
        )

    gobo_present = False if "gobo" in capabilities else None

    model = LightingEditModel(
        brightness=brightness_block,
        colour=colour_blocks,
        strobe=strobe_blocks,
        position=position,
        rotate=rotate_blocks,
        gobo_present=gobo_present,
    )
    return lightingxml.serialize(model)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _build_brightness(beats: float, keyframes: list[tuple[float, float]]) -> PointBlock:
    _validate_brightness(beats, keyframes)
    last_index = len(keyframes) - 1
    points = tuple(
        Point(x=x, y=y, type=(1 if i == 0 else 3 if i == last_index else 2))
        for i, (x, y) in enumerate(keyframes)
    )
    return PointBlock(xleft=0.0, xright=beats, points=points)


def _validate_brightness(beats: float, keyframes: list[tuple[float, float]]) -> None:
    if len(keyframes) < 2:
        raise InvalidCompositionError(
            "brightness requires at least 2 keyframes (start and end)"
        )
    previous_x: float | None = None
    for x, y in keyframes:
        if not (0.0 <= x <= beats):
            raise InvalidCompositionError(
                f"brightness beat {x} outside domain [0, {beats}]"
            )
        if not (0.0 <= y <= 1.0):
            raise InvalidCompositionError(f"brightness level {y} outside [0.0, 1.0]")
        if previous_x is not None and x <= previous_x:
            raise InvalidCompositionError(
                "brightness beats must be strictly ascending, no duplicates"
            )
        previous_x = x


def _build_colour_blocks(
    beats: float, stops: list[tuple[float, int]]
) -> tuple[ColourBlock, ...]:
    _validate_colour(beats, stops)
    blocks = [
        ColourBlock(xleft=x0, colourleft=c0, xright=x1, colourright=c1)
        for (x0, c0), (x1, c1) in pairwise(stops)
    ]
    last_beat, last_colour = stops[-1]
    if last_beat < beats:
        blocks.append(
            ColourBlock(
                xleft=last_beat,
                colourleft=last_colour,
                xright=beats,
                colourright=last_colour,
            )
        )
    return tuple(blocks)


def _validate_colour(beats: float, stops: list[tuple[float, int]]) -> None:
    if stops[0][0] != 0.0:
        raise InvalidCompositionError("colour stops must begin at beat 0")
    previous_x: float | None = None
    for x, _colour in stops:
        if not (0.0 <= x <= beats):
            raise InvalidCompositionError(
                f"colour beat {x} outside domain [0, {beats}]"
            )
        if previous_x is not None and x <= previous_x:
            raise InvalidCompositionError(
                "colour beats must be strictly ascending, no duplicates"
            )
        previous_x = x


def _build_strobe_blocks(
    beats: float, windows: list[tuple[float, float]]
) -> tuple[StrobeBlock, ...]:
    _validate_strobe(beats, windows)
    return tuple(
        StrobeBlock(xleft=start, strobeleft=1.0, xright=end, stroberight=1.0)
        for start, end in windows
    )


def _validate_strobe(beats: float, windows: list[tuple[float, float]]) -> None:
    for start, end in windows:
        if not (0.0 <= start <= beats) or not (0.0 <= end <= beats):
            raise InvalidCompositionError(
                f"strobe window ({start}, {end}) outside domain [0, {beats}]"
            )
        if end <= start:
            raise InvalidCompositionError(
                f"strobe window end ({end}) must be after start ({start})"
            )


def _build_movement_block(beats: float, spec: MovementSpec) -> MovementBlock:
    return MovementBlock(
        xleft=0.0,
        xright=beats,
        pattern=spec.pattern,
        width=spec.width,
        height=spec.height,
        offset_x=spec.offset_x,
        offset_y=spec.offset_y,
        round_angle=spec.round_angle,
        offset_angle=spec.offset_angle,
        period_time=spec.period_time,
        frequency_x=spec.frequency_x,
        frequency_y=spec.frequency_y,
        phase_x=spec.phase_x,
        phase_y=spec.phase_y,
        type=spec.type,
        direction=spec.direction,
        start_angle=spec.start_angle,
        relative=spec.relative,
    )


def _build_rotate_block(beats: float, span: tuple[float, float]) -> RotateBlock:
    rotateleft, rotateright = span
    return RotateBlock(
        xleft=0.0, rotateleft=rotateleft, xright=beats, rotateright=rotateright
    )
