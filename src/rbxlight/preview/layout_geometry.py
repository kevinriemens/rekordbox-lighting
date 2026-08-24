"""Pure geometry helpers for the reference rig arch shape and the shared
normalized [0, 1] coordinate convention used by rig layouts.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rbxlight.preview.layout_io import RigLayout

# ---------------------------------------------------------------------------
# Real truss geometry (physical-rig-profile skill, "Physical truss
# geometry"): a 5-segment arch, described left to right as seen from the
# audience. Connection pieces join adjacent segments; these constants are
# the real-world segment lengths/angle, in cm/degrees.
# ---------------------------------------------------------------------------

VERTICAL_SEGMENT_LENGTH_CM: float = 150.0
DIAGONAL_SEGMENT_LENGTH_CM: float = 100.0
TOP_SEGMENT_LENGTH_CM: float = 100.0
DIAGONAL_ANGLE_DEG: float = 45.0

#: Ground/sky convention for the normalized vertical axis: the ground is
#: the LARGER end of [0, 1] — a floor-standing fixture must never render
#: near the top of the screen.
GROUND_Y: float = 1.0
SKY_Y: float = 0.0

#: Fraction of the normalized [0, 1] range reserved as margin on every
#: side, so nothing lands exactly on the 0/1 edge (which would clip in a
#: renderer).
#:
#: Mirrored in JavaScript as TRUSS_MARGIN_FRACTION in template.html, which
#: inverts this margin reservation and the y-axis flip in _normalize_point
#: to recover real-world centimetres. Change one without the other and
#: structure_cm exports silently corrupted coordinates — no crash, no test.
_MARGIN_FRACTION: float = 0.05


def arch_outline_cm() -> tuple[tuple[float, float], ...]:
    """The real truss shape: 6 vertices (5 segments), in cm, left to
    right as seen from the audience, y-up, origin at the base of the left
    vertical segment.

    Segments: 150cm vertical up, 100cm at 45deg up-right, 100cm
    horizontal, 100cm at 45deg down-right, 150cm vertical down. Overall
    bounding box: approximately 241cm wide x 221cm tall.
    """
    angle_rad = math.radians(DIAGONAL_ANGLE_DEG)
    dx = DIAGONAL_SEGMENT_LENGTH_CM * math.cos(angle_rad)
    dy = DIAGONAL_SEGMENT_LENGTH_CM * math.sin(angle_rad)

    p0 = (0.0, 0.0)
    p1 = (0.0, VERTICAL_SEGMENT_LENGTH_CM)
    p2 = (p1[0] + dx, p1[1] + dy)
    p3 = (p2[0] + TOP_SEGMENT_LENGTH_CM, p2[1])
    p4 = (p3[0] + dx, p3[1] - dy)
    p5 = (p4[0], p4[1] - VERTICAL_SEGMENT_LENGTH_CM)
    return (p0, p1, p2, p3, p4, p5)


def normalize_rotation(degrees: float) -> float:
    """Wrap any degree value into [0, 360)."""
    return degrees % 360.0


def _normalize_point(
    x_cm: float,
    y_cm: float,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
) -> tuple[float, float]:
    """Map a cm position into normalized [0, 1] space (with margin),
    inverting the vertical axis so ground -> GROUND_Y and up -> SKY_Y.

    A zero-width/height frame (e.g. a perfectly flat, single-row
    horizontal structure with no vertical extent at all) maps every
    point on that axis to the centre of the normalized range rather than
    dividing by zero.
    """
    frac_x = 0.5 if max_x == min_x else (x_cm - min_x) / (max_x - min_x)
    frac_y = 0.5 if max_y == min_y else (y_cm - min_y) / (max_y - min_y)
    nx = _MARGIN_FRACTION + frac_x * (1 - 2 * _MARGIN_FRACTION)
    ny = _MARGIN_FRACTION + (1 - frac_y) * (1 - 2 * _MARGIN_FRACTION)
    return nx, ny


def normalized_arch_outline() -> tuple[tuple[float, float], ...]:
    """`arch_outline_cm()`, normalized into the same [0, 1] convention
    used by `generate_layout` (ground at the bottom, sky at the top),
    using the arch's own bounding box ONLY — this is deliberately NOT the
    same frame `generate_layout` uses for its fixtures (see
    `normalized_structure` for that). Kept only because older tests still
    exercise it as a "different bounding box" reference point; production
    code should call `normalized_structure` instead.
    """
    points = arch_outline_cm()
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return tuple(_normalize_point(x, y, min_x, max_x, min_y, max_y) for x, y in points)


def _structure_bounds(
    structure_cm: Sequence[tuple[float, float]],
) -> tuple[float, float, float, float]:
    """The structure polyline's own bounding box: (min_x, max_x, min_y,
    max_y). Generalizes the old hardcoded `arch_width = p5[0]` concept
    into a real footprint-bounds derived from whatever shape is given.
    """
    xs = [point[0] for point in structure_cm]
    ys = [point[1] for point in structure_cm]
    return min(xs), max(xs), min(ys), max(ys)


@dataclass(frozen=True)
class NormalizationFrame:
    """The single cm bounding box (structure polyline unioned with every
    computed fixture position) used to normalize a RigLayout's fixtures
    AND its structure into one shared [0, 1] space. Persisted alongside
    the layout because fixture positions are stored already-normalized —
    the cm frame that produced them is not otherwise recoverable.
    """

    min_x: float
    max_x: float
    min_y: float
    max_y: float


def frame_cm_to_dict(frame: NormalizationFrame | None) -> dict | None:
    """JSON-serializable representation of a NormalizationFrame, or None.
    Shared by `layout_to_dict` and `preview.payload.build_preview_payload`
    — `frame_cm` is mirrored verbatim in both, never recomputed.
    """
    if frame is None:
        return None
    return {
        "min_x": frame.min_x,
        "max_x": frame.max_x,
        "min_y": frame.min_y,
        "max_y": frame.max_y,
    }


def normalized_structure(layout: RigLayout) -> tuple[tuple[float, float], ...]:
    """`layout.structure_cm`, normalized through the SAME frame used to
    normalize `layout`'s fixtures (`layout.frame_cm`) — the single shared
    frame requirement. Falls back to the structure's own bounding box for
    a legacy layout with no persisted frame. Same margin and same
    y-inversion convention as `_normalize_point` (ground = high y).
    """
    if layout.frame_cm is not None:
        min_x, max_x = layout.frame_cm.min_x, layout.frame_cm.max_x
        min_y, max_y = layout.frame_cm.min_y, layout.frame_cm.max_y
    else:
        min_x, max_x, min_y, max_y = _structure_bounds(layout.structure_cm)
    return tuple(
        _normalize_point(x, y, min_x, max_x, min_y, max_y)
        for x, y in layout.structure_cm
    )
