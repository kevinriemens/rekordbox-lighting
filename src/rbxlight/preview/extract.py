"""Program extraction: decode one macro_data.data XML payload into the
JSON-contract-shaped `program` dict for a single fixture slot.

Colours are exposed as separate alpha/red/green/blue components (never the
raw signed int32) so the renderer never has to repeat the decode. Beat
positions are clamped to the macro's `beats` so a payload never asks the
renderer to draw past the end of the timeline. `gobo` is always null —
gobo data is never extracted for the preview (a design-preview
simplification, not a reproduction of rekordbox's playback engine).
"""

from __future__ import annotations

import copy

from rbxlight import lightingxml
from rbxlight.colors import signed_to_argb
from rbxlight.models import FIXTURE_TYPE_CAPABILITIES

#: The exact "no programming for this slot" shape — brightness is null,
#: every block section is an empty list, gobo is null.
EMPTY_PROGRAM: dict = {
    "brightness": None,
    "colour": [],
    "strobe": [],
    "position": [],
    "rotate": [],
    "gobo": None,
}


def _clamp(value: float, beats: float) -> float:
    """Clamp a beat position into [0, beats] — never negative, never past
    the macro's end, no matter what beats is (including 0)."""
    return max(0.0, min(value, beats))


def build_fixture_program(xml_payload: str, fixture_type_id: int, beats: float) -> dict:
    """Parse xml_payload (a macro_data.data value, possibly "") and return
    a JSON-contract-shaped program dict for a slot of the given
    fixture_type_id, clamped to [0, beats].

    - xml_payload == "" -> a fresh copy of EMPTY_PROGRAM.
    - brightness points are returned in ascending beat (x) order.
    - colour/strobe blocks are always lists (never null), even when empty.
    - position/rotate are forced to [] for a fixture_type_id that doesn't
      support that section (see rbxlight.models.FIXTURE_TYPE_CAPABILITIES),
      regardless of what the raw payload happens to contain.
    - gobo is always None.
    """
    if xml_payload == "":
        return copy.deepcopy(EMPTY_PROGRAM)

    model = lightingxml.parse(xml_payload)
    assert model is not None  # parse() only returns None for "", excluded above
    capabilities = FIXTURE_TYPE_CAPABILITIES.get(fixture_type_id, frozenset())

    sorted_points = sorted(model.brightness.points, key=lambda point: point.x)
    brightness = {
        "xleft": _clamp(model.brightness.xleft, beats),
        "xright": _clamp(model.brightness.xright, beats),
        "points": [
            {"x": _clamp(point.x, beats), "y": point.y, "type": point.type}
            for point in sorted_points
        ],
    }

    colour = [
        {
            "xleft": _clamp(block.xleft, beats),
            "xright": _clamp(block.xright, beats),
            "left": dict(zip("argb", signed_to_argb(block.colourleft))),
            "right": dict(zip("argb", signed_to_argb(block.colourright))),
        }
        for block in model.colour
    ]

    strobe = [
        {
            "xleft": _clamp(block.xleft, beats),
            "xright": _clamp(block.xright, beats),
            "left": block.strobeleft,
            "right": block.stroberight,
        }
        for block in model.strobe
    ]

    position: list[dict] = []
    if "position" in capabilities and model.position is not None:
        position = [
            {
                "pattern": block.pattern,
                "type": block.type,
                "direction": block.direction,
                "period_time": block.period_time,
                "width": block.width,
                "height": block.height,
                "offset_x": block.offset_x,
                "offset_y": block.offset_y,
                "xleft": _clamp(block.xleft, beats),
                "xright": _clamp(block.xright, beats),
            }
            for block in model.position
        ]

    rotate: list[dict] = []
    if "rotate" in capabilities and model.rotate is not None:
        rotate = [
            {
                "xleft": _clamp(block.xleft, beats),
                "xright": _clamp(block.xright, beats),
                "left": block.rotateleft,
                "right": block.rotateright,
            }
            for block in model.rotate
        ]

    return {
        "brightness": brightness,
        "colour": colour,
        "strobe": strobe,
        "position": position,
        "rotate": rotate,
        "gobo": None,
    }
