"""Structure polyline segmentation: classify a rig's stage/truss polyline
into oriented segments (vertical / horizontal / diagonal) so placement
rules can key off shape-generic roles instead of fixed indices.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class _StructureSegment:
    """One segment of a structure polyline, classified by orientation so
    shape-generic placement rules can be applied against roles
    (vertical/diagonal/horizontal) instead of fixed indices.
    """

    index: int
    start: tuple[float, float]
    end: tuple[float, float]
    orientation: str  # "vertical" | "horizontal" | "diagonal"
    length: float


#: Tolerance (cm) below which a segment's dx or dy is treated as zero
#: when classifying its orientation.
_ORIENTATION_EPS_CM: float = 1e-6


def _classify_segments(
    structure_cm: Sequence[tuple[float, float]],
) -> list[_StructureSegment]:
    """Walk the polyline's segments and classify each by orientation:
    "vertical" (no horizontal drift), "horizontal" (no vertical drift),
    else "diagonal". This is what shape-generic placement rules key off
    instead of fixed indices into the default arch's 6-tuple.
    """
    segments: list[_StructureSegment] = []
    for i in range(len(structure_cm) - 1):
        start, end = structure_cm[i], structure_cm[i + 1]
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if abs(dx) < _ORIENTATION_EPS_CM and abs(dy) >= _ORIENTATION_EPS_CM:
            orientation = "vertical"
        elif abs(dy) < _ORIENTATION_EPS_CM and abs(dx) >= _ORIENTATION_EPS_CM:
            orientation = "horizontal"
        else:
            orientation = "diagonal"
        segments.append(
            _StructureSegment(i, start, end, orientation, math.hypot(dx, dy))
        )
    return segments


def _point_along_segments(
    segments: Sequence[_StructureSegment], fraction: float
) -> tuple[float, float]:
    """Map `fraction` in [0, 1] to a point along the concatenation of
    `segments`, parametrized by cumulative arc length. Used to distribute
    fixtures along a run when their natural role (diagonal/vertical) is
    absent from the structure.
    """
    total_length = sum(segment.length for segment in segments)
    if total_length <= 0:
        return segments[0].start
    target = max(0.0, min(fraction, 1.0)) * total_length
    accumulated = 0.0
    for segment in segments:
        if target <= accumulated + segment.length or segment is segments[-1]:
            t = 0.0 if segment.length == 0 else (target - accumulated) / segment.length
            t = max(0.0, min(t, 1.0))
            return (
                segment.start[0] + t * (segment.end[0] - segment.start[0]),
                segment.start[1] + t * (segment.end[1] - segment.start[1]),
            )
        accumulated += segment.length
    return segments[-1].end


def _run_segments(
    segments: Sequence[_StructureSegment],
) -> list[_StructureSegment]:
    """The segments used to distribute fixtures whose natural role is
    absent from the structure: the horizontal segments if any exist,
    else the whole polyline (e.g. a straight horizontal run, which is
    itself classified "horizontal" and so already covered by the first
    case).
    """
    horizontals = [
        segment for segment in segments if segment.orientation == "horizontal"
    ]
    return horizontals if horizontals else list(segments)


class DegenerateStructureError(ValueError):
    """Raised when a loaded layout's `structure_cm` cannot describe a
    valid polyline: fewer than two vertices, all vertices identical, or
    any non-finite coordinate.
    """


def _validate_structure_cm(points: Sequence[tuple[float, float]]) -> None:
    if len(points) < 2:
        raise DegenerateStructureError(
            f"structure_cm must have at least two vertices to describe a "
            f"polyline; got {len(points)}."
        )
    for x, y in points:
        if not (math.isfinite(x) and math.isfinite(y)):
            raise DegenerateStructureError(
                f"structure_cm contains a non-finite coordinate: ({x!r}, {y!r})."
            )
    if len(set(points)) == 1:
        raise DegenerateStructureError(
            "structure_cm's vertices are all identical — a degenerate "
            "zero-length polyline."
        )
