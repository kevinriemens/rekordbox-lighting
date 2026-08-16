"""Rig layout description: the on-screen position, label, kind, and
rotation of every fixture in a venue. This is NOT rekordbox data —
user.db3's fixture.offset_x/offset_y are a centred placeholder, never a
real physical layout — so this tool maintains its own editable description
on disk (JSON), one file per venue.

Positions are normalized to [0, 1] on both axes so the renderer (built by
another agent against this payload) is resolution-independent. The
vertical axis follows an explicit ground/sky convention (`GROUND_Y`,
`SKY_Y`) rather than leaving "up" ambiguous.

Geometry: the reference rig is a 5-segment arch (see physical-rig-profile
skill, "Physical truss geometry"). `arch_outline_cm()` is the pure
geometric shape; `generate_layout()` mounts fixtures onto it by kind and
patch order, then normalizes everything (fixtures + the outline) into one
consistent [0, 1] frame.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from rbxlight.models import FIXTURE_SLOT_TYPES
from rbxlight.venues.models import Fixture

#: fixture_master_id -> kind, for the 4 known reference rig hardware
#: profiles (see physical-rig-profile skill, "Physical hardware").
KIND_BY_MASTER_ID: dict[int, str] = {
    13417: "moving_head",  # LM70S
    17404: "tilt_block",  # Super Storm1500B Tilt (decomposed L1015 tilt)
    32282: "bar_cell",  # 18x10W Pixel Bar (decomposed L1015 cell)
    19231: "par",  # LPC008S
}

#: macro_fixture slot's fixture_type_id that falls back to "effect" when
#: the fixture's master id isn't one of the 4 known hardware profiles.
_EFFECT_SLOT_TYPE_ID: int = 8

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

#: Ground clearance + spacing for pars standing outside the arch footprint.
_PAR_GROUND_OFFSET_CM: float = 50.0
_PAR_SPACING_CM: float = 40.0

#: Real hardware constant (physical-rig-profile skill, "The L1015
#: decomposition"): each L1015 bar's 43 physical channels are re-declared
#: in venue 2 as one tilt block followed by 9 cells, with one spare
#: channel at the end. A bar_cell can only ever belong to the tilt block
#: whose DMX start address is <= its own and within this many channels of
#: it — this is what makes address-based grouping correct instead of
#: relying on fixture list position.
BAR_CHANNEL_SPAN: int = 43


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


#: Default total angular sweep (degrees) for a moving head's pan/tilt
#: axes. Rekordbox does not record this — it is a hardware property the
#: user can correct per fixture in the layout file (never hardcoded per
#: model; see physical-rig-profile skill).
DEFAULT_PAN_DEGREES: float = 540.0
DEFAULT_TILT_DEGREES: float = 270.0

#: DEFAULT mounting rotation (degrees) for a bar's tilt block. Each L1015
#: bar is mounted vertically on its end, on the inside of an arch leg —
#: this rotates its tilt axis 90 degrees from the horizontal-overhead
#: case, so the tilt sweep renders horizontally instead of vertically.
#: This is user-editable layout data (correctable per fixture, like
#: DEFAULT_PAN_DEGREES above), never a hardware constant — rekordbox
#: does not record how a fixture is physically mounted.
DEFAULT_TILT_BLOCK_ROTATION_DEGREES: float = 90.0


@dataclass(frozen=True)
class LayoutEntry:
    fixture_id: int
    x: float
    y: float
    label: str
    kind: str
    rotation: float = 0.0
    pan_degrees: float = DEFAULT_PAN_DEGREES
    tilt_degrees: float = DEFAULT_TILT_DEGREES

    def __post_init__(self) -> None:
        object.__setattr__(self, "rotation", normalize_rotation(self.rotation))


@dataclass(frozen=True)
class RigLayout:
    venue_id: int
    entries: tuple[LayoutEntry, ...]
    #: bar_cell fixtures whose DMX address fell outside every tilt
    #: block's address range — reported, never silently merged onto
    #: either bar's leg. Mirrors LayoutMergeResult.orphan_fixture_ids.
    unmapped_cell_ids: tuple[int, ...] = ()
    #: The stage/truss polyline, in cm — user-owned data, same category
    #: as pan/tilt calibration. Defaults to the standard 5-segment arch.
    structure_cm: tuple[tuple[float, float], ...] = field(
        default_factory=arch_outline_cm
    )
    #: The single cm bounding box used to normalize both `structure_cm`
    #: and every entry's (x, y) — persisted because fixture positions are
    #: stored already-normalized, discarding the cm frame that produced
    #: them. None for a legacy layout saved before this field existed.
    frame_cm: NormalizationFrame | None = None


@dataclass(frozen=True)
class LayoutDiffEntry:
    """One fixture's difference between two RigLayouts, as produced by
    diff_layouts(). Either side may be None: absent from `old` means the
    fixture is new (no "old" side); absent from `new` means it no longer
    exists (no "new" side).
    """

    fixture_id: int
    label: str
    old_x: float | None
    old_y: float | None
    old_rotation: float | None
    new_x: float | None
    new_y: float | None
    new_rotation: float | None


def diff_layouts(old: RigLayout, new: RigLayout) -> tuple[LayoutDiffEntry, ...]:
    """Pure diff between two layouts, by fixture_id. Unchanged fixtures
    (identical x, y, and rotation on both sides) are omitted entirely.
    Deterministically ordered by fixture_id, regardless of the order
    entries appear in either input.
    """
    old_by_id = {entry.fixture_id: entry for entry in old.entries}
    new_by_id = {entry.fixture_id: entry for entry in new.entries}

    diffs: list[LayoutDiffEntry] = []
    for fixture_id in sorted(set(old_by_id) | set(new_by_id)):
        old_entry = old_by_id.get(fixture_id)
        new_entry = new_by_id.get(fixture_id)

        if old_entry is not None and new_entry is not None:
            unchanged = (
                old_entry.x == new_entry.x
                and old_entry.y == new_entry.y
                and old_entry.rotation == new_entry.rotation
            )
            if unchanged:
                continue

        reference_entry = old_entry if old_entry is not None else new_entry
        assert reference_entry is not None  # fixture_id came from old_by_id | new_by_id
        label = reference_entry.label
        diffs.append(
            LayoutDiffEntry(
                fixture_id=fixture_id,
                label=label,
                old_x=old_entry.x if old_entry is not None else None,
                old_y=old_entry.y if old_entry is not None else None,
                old_rotation=old_entry.rotation if old_entry is not None else None,
                new_x=new_entry.x if new_entry is not None else None,
                new_y=new_entry.y if new_entry is not None else None,
                new_rotation=new_entry.rotation if new_entry is not None else None,
            )
        )

    return tuple(diffs)


def apply_prior_calibration(
    fresh: RigLayout, prior_entries: Sequence[LayoutEntry]
) -> RigLayout:
    """Rebuild `fresh` with each entry's pan_degrees/tilt_degrees replaced
    by the matching fixture's prior calibration, when one exists.
    Position, rotation, label, and kind always come from `fresh` — only
    pan/tilt sweep calibration is preserved. Used by `layout regenerate`
    so a fresh algorithmic reposition never wipes a user's pan/tilt
    calibration. Pure: no I/O.
    """
    prior_by_id = {entry.fixture_id: entry for entry in prior_entries}
    entries = tuple(
        LayoutEntry(
            fixture_id=entry.fixture_id,
            x=entry.x,
            y=entry.y,
            label=entry.label,
            kind=entry.kind,
            rotation=entry.rotation,
            pan_degrees=prior.pan_degrees,
            tilt_degrees=prior.tilt_degrees,
        )
        if (prior := prior_by_id.get(entry.fixture_id)) is not None
        else entry
        for entry in fresh.entries
    )
    return RigLayout(
        venue_id=fresh.venue_id,
        entries=entries,
        structure_cm=fresh.structure_cm,
        frame_cm=fresh.frame_cm,
    )


@dataclass
class _BarGroup:
    """Internal grouping used while generating a layout: one tilt block
    plus the (up to 9) bar_cell fixtures mounted on the same vertical,
    grouped by DMX address range (see `_bar_address_ranges`), never by
    list position."""

    tilt: Fixture
    cells: list[Fixture]


def _bar_address_ranges(
    tilt_blocks: Sequence[Fixture],
) -> list[tuple[Fixture, int, int]]:
    """For each tilt block, sorted by its own DMX start address (never
    by list position), the half-open [start, end) address range it owns:
    from its own start address up to whichever comes first — the next
    bar's start address, or BAR_CHANNEL_SPAN channels later (the real
    L1015's total width). The span cap is what keeps the highest-address
    bar's range bounded, so a stray out-of-range cell can never fall
    inside it by default.
    """
    sorted_tilts = sorted(tilt_blocks, key=lambda f: f.start_addr)
    ranges: list[tuple[Fixture, int, int]] = []
    for i, tilt in enumerate(sorted_tilts):
        end_addr = tilt.start_addr + BAR_CHANNEL_SPAN
        if i + 1 < len(sorted_tilts):
            end_addr = min(end_addr, sorted_tilts[i + 1].start_addr)
        ranges.append((tilt, tilt.start_addr, end_addr))
    return ranges


@dataclass(frozen=True)
class LayoutMergeResult:
    """Result of ensure_layout: the (possibly merged) layout, plus any
    fixture ids an existing layout referenced that no longer exist in the
    venue's current fixture list — reported, never silently dropped.
    """

    layout: RigLayout
    orphan_fixture_ids: tuple[int, ...]


def classify_fixture_kind(fixture: Fixture) -> str:
    """Classify a fixture's `kind` from what it actually IS
    (fixture_master_id), never from its current macro slot assignment.

    Falls back to "effect" for an unrecognized master id patched into an
    Effect-type slot (fixture_type_id 8), else "other".
    """
    kind = KIND_BY_MASTER_ID.get(fixture.fixture_master_id)
    if kind is not None:
        return kind
    slot_type_id = FIXTURE_SLOT_TYPES.get(fixture.macro_fixture_id)
    if slot_type_id == _EFFECT_SLOT_TYPE_ID:
        return "effect"
    return "other"


def generate_layout(
    venue_id: int,
    fixtures: Sequence[Fixture],
    structure_cm: tuple[tuple[float, float], ...] | None = None,
    *,
    reverse_cell_order: bool = False,
) -> RigLayout:
    """Produce one LayoutEntry per fixture, mounting each onto
    `structure_cm` (the default 5-segment arch when None) by kind + DMX
    address order (never list position — grouping and ordering must be
    identical for any input ordering of the same fixtures).

    Placement is shape-generic: the structure's segments are classified
    by orientation (vertical / diagonal / horizontal) and length, and the
    per-kind rules below apply against those ROLES rather than fixed
    indices into the default arch:

    - moving_head: the lowest-address heads (one per diagonal segment,
      in polyline order) mount at that segment's own midpoint, rotated
      to the segment's own angle. Every remaining head distributes
      evenly (address order) along the structure's horizontal segments,
      or the whole polyline if it has none, rotation 0.
    - tilt_block + the bar_cell fixtures whose DMX address falls in its
      channel range (see `_bar_address_ranges`) -> one bar. When the
      structure has at least as many vertical segments as bar groups,
      each group mounts VERTICALLY on its own vertical segment (lowest-
      address tilt on the first vertical in polyline order); otherwise
      every group distributes along the run in disjoint, address-ordered
      blocks (never interleaved between groups).
    - pars -> first half by address stand outside the structure's own
      footprint on one side, remainder on the other, all at the
      structure's own ground level (its lowest cm y).
    - a bar_cell whose address falls outside every tilt block's range is
      reported in `RigLayout.unmapped_cell_ids` and positioned at the
      footprint's centre (never on either bar's leg).
    - anything left unclassified/unmounted also lands at the footprint's
      centre.

    `reverse_cell_order` mirrors each bar's cell ordering along its own
    run and changes nothing else. Pure and deterministic — identical
    fixtures in, identical layout out, regardless of input ordering.

    The returned layout also carries `structure_cm` (the shape actually
    used) and `frame_cm` (the single cm bounding box — structure unioned
    with every computed fixture position — used to normalize both).
    """
    fixture_list = list(fixtures)
    structure = structure_cm if structure_cm is not None else arch_outline_cm()
    segments = _classify_segments(structure)
    verticals = [segment for segment in segments if segment.orientation == "vertical"]
    diagonals = [segment for segment in segments if segment.orientation == "diagonal"]
    min_x, max_x, min_y, max_y = _structure_bounds(structure)

    moving_heads = sorted(
        (f for f in fixture_list if classify_fixture_kind(f) == "moving_head"),
        key=lambda f: f.start_addr,
    )
    pars = sorted(
        (f for f in fixture_list if classify_fixture_kind(f) == "par"),
        key=lambda f: f.start_addr,
    )

    tilt_blocks = [f for f in fixture_list if classify_fixture_kind(f) == "tilt_block"]
    bar_cells = [f for f in fixture_list if classify_fixture_kind(f) == "bar_cell"]

    bar_ranges = _bar_address_ranges(tilt_blocks)
    bar_groups: list[_BarGroup] = [
        _BarGroup(tilt=tilt, cells=[]) for tilt, _, _ in bar_ranges
    ]

    unmapped_cell_ids: list[int] = []
    for cell in sorted(bar_cells, key=lambda f: f.start_addr):
        for group, (_tilt, start_addr, end_addr) in zip(bar_groups, bar_ranges):
            if start_addr <= cell.start_addr < end_addr and len(group.cells) < 9:
                group.cells.append(cell)
                break
        else:
            unmapped_cell_ids.append(cell.id)

    positions: dict[int, tuple[float, float]] = {}
    rotations: dict[int, float] = {}

    # --- moving heads: one per diagonal segment at that segment's own
    # angle, remainder distributed along the horizontal run (or the
    # whole polyline, if it has no horizontal segment either) ---
    diag_heads = moving_heads[: len(diagonals)]
    top_heads = moving_heads[len(diagonals) :]
    for fixture, segment in zip(diag_heads, diagonals):
        positions[fixture.id] = (
            (segment.start[0] + segment.end[0]) / 2,
            (segment.start[1] + segment.end[1]) / 2,
        )
        dx = segment.end[0] - segment.start[0]
        dy = segment.end[1] - segment.start[1]
        rotations[fixture.id] = normalize_rotation(math.degrees(math.atan2(dy, dx)))

    top_run = _run_segments(segments)
    n_top = len(top_heads)
    for i, fixture in enumerate(top_heads):
        frac = (i + 1) / (n_top + 1)
        positions[fixture.id] = _point_along_segments(top_run, frac)
        rotations[fixture.id] = 0.0

    # --- bars: one group per vertical segment when there are enough of
    # them, else every group distributes along the run in disjoint,
    # address-ordered blocks ---
    if len(verticals) >= len(bar_groups):
        for group, vertical in zip(bar_groups, verticals):
            seg_min_y = min(vertical.start[1], vertical.end[1])
            seg_max_y = max(vertical.start[1], vertical.end[1])
            seg_height = seg_max_y - seg_min_y
            bar_x = vertical.start[0]
            n_cells = len(group.cells)
            for i, cell in enumerate(group.cells):
                slot = (n_cells - 1 - i) if reverse_cell_order else i
                y_cm = seg_min_y + (slot + 0.5) / n_cells * seg_height
                positions[cell.id] = (bar_x, y_cm)
                rotations[cell.id] = 0.0

            positions[group.tilt.id] = (bar_x, seg_min_y + seg_height / 2)
            rotations[group.tilt.id] = normalize_rotation(
                DEFAULT_TILT_BLOCK_ROTATION_DEGREES
            )
    else:
        # Each group gets its own equal-width zone along the run, tilt at
        # the zone's centre, cells confined to the zone's middle 60% —
        # so even two same-sized groups' farthest-out cell always stays
        # strictly closer to its own zone centre than to a neighbouring
        # zone's, regardless of cell count.
        run = _run_segments(segments)
        n_groups = len(bar_groups)
        zone_width = 1.0 / n_groups
        for g, group in enumerate(bar_groups):
            zone_low = g * zone_width
            tilt_frac = zone_low + zone_width / 2
            positions[group.tilt.id] = _point_along_segments(run, tilt_frac)
            rotations[group.tilt.id] = normalize_rotation(
                DEFAULT_TILT_BLOCK_ROTATION_DEGREES
            )

            n_cells = len(group.cells)
            for i, cell in enumerate(group.cells):
                slot = (n_cells - 1 - i) if reverse_cell_order else i
                inner_frac = (slot + 0.5) / n_cells
                cell_frac = zone_low + zone_width * (0.2 + 0.6 * inner_frac)
                positions[cell.id] = _point_along_segments(run, cell_frac)
                rotations[cell.id] = 0.0

    # --- pars: ground level, split outside the structure's own footprint ---
    split = (len(pars) + 1) // 2
    left_pars, right_pars = pars[:split], pars[split:]
    for i, fixture in enumerate(left_pars):
        positions[fixture.id] = (
            min_x - _PAR_GROUND_OFFSET_CM - i * _PAR_SPACING_CM,
            min_y,
        )
        rotations[fixture.id] = 0.0
    for i, fixture in enumerate(right_pars):
        positions[fixture.id] = (
            max_x + _PAR_GROUND_OFFSET_CM + i * _PAR_SPACING_CM,
            min_y,
        )
        rotations[fixture.id] = 0.0

    # --- anything unclassified/unmounted: centre of the footprint ---
    centre = ((min_x + max_x) / 2, (min_y + max_y) / 2)
    for fixture in fixture_list:
        if fixture.id not in positions:
            positions[fixture.id] = centre
            rotations[fixture.id] = 0.0

    # --- normalize: ONE shared frame is the structure unioned with every
    # computed fixture position, plus a margin so nothing lands exactly
    # on 0/1 ---
    all_points = list(structure) + list(positions.values())
    xs = [pt[0] for pt in all_points]
    ys = [pt[1] for pt in all_points]
    frame_min_x, frame_max_x = min(xs), max(xs)
    frame_min_y, frame_max_y = min(ys), max(ys)

    normalized_positions = {
        fixture_id: _normalize_point(
            *cm_position, frame_min_x, frame_max_x, frame_min_y, frame_max_y
        )
        for fixture_id, cm_position in positions.items()
    }
    entries = tuple(
        LayoutEntry(
            fixture_id=fixture.id,
            x=normalized_positions[fixture.id][0],
            y=normalized_positions[fixture.id][1],
            label=fixture.name,
            kind=classify_fixture_kind(fixture),
            rotation=rotations[fixture.id],
        )
        for fixture in fixture_list
    )
    return RigLayout(
        venue_id=venue_id,
        entries=entries,
        unmapped_cell_ids=tuple(sorted(unmapped_cell_ids)),
        structure_cm=structure,
        frame_cm=NormalizationFrame(
            min_x=frame_min_x,
            max_x=frame_max_x,
            min_y=frame_min_y,
            max_y=frame_max_y,
        ),
    )


def load_layout(path: Path) -> RigLayout | None:
    """Read a layout description from disk. Returns None if the file does
    not exist (this is the normal "never generated yet" case, not an
    error).
    """
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return layout_from_dict(data)


def save_layout(path: Path, layout: RigLayout) -> None:
    """Write a layout description to disk as JSON, atomically: write to a
    temp file in the same directory, then `os.replace` it into place, so
    an interrupted save can never leave a truncated/corrupt file at
    `path`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(layout_to_dict(layout), indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(data)
        os.replace(tmp_name, str(path))
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


class InvalidSavedLayoutError(ValueError):
    """Raised by `load_layout_file` when a file that is expected to
    already be a saved layout export cannot be parsed as one: invalid
    JSON, missing required fields, or a required field with the wrong
    type. Degenerate stage/truss geometry is a distinct, already-typed
    failure mode (`DegenerateStructureError`) and is never wrapped by
    this one.
    """


def load_layout_file(path: Path) -> RigLayout:
    """Load a layout file expected to already exist — e.g. a file
    exported by the offline visualizer for `layout install`.

    Unlike `load_layout` (which treats a missing file as the normal
    "never generated yet" case and returns None), any failure to parse
    `path` as a well-formed saved layout raises InvalidSavedLayoutError
    with an actionable message. `DegenerateStructureError` from
    `layout_from_dict`'s structure validation propagates unchanged, not
    wrapped.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InvalidSavedLayoutError(f"could not read {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise InvalidSavedLayoutError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InvalidSavedLayoutError(
            f"{path} must contain a JSON object describing a saved layout, "
            f"got {type(data).__name__}."
        )

    try:
        return layout_from_dict(data)
    except DegenerateStructureError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise InvalidSavedLayoutError(
            f"{path} is not a valid saved layout: {exc}"
        ) from exc


def ensure_layout(
    path: Path, venue_id: int, fixtures: Sequence[Fixture]
) -> LayoutMergeResult:
    """Load path if it exists; otherwise generate a brand new layout.

    When a layout already exists: every existing entry for a fixture still
    present in `fixtures` is preserved UNCHANGED (the user's adjusted
    positions/rotations are never silently overwritten). A new entry is
    generated only for a fixture with no existing entry. Any existing
    entry whose fixture_id has no match in `fixtures` is removed from the
    returned layout but reported via `orphan_fixture_ids` — never silently
    dropped from the caller's knowledge, only from the renderable set.

    The (possibly merged) result is written back to `path`.
    """
    fixture_list = list(fixtures)
    fixture_ids = {fixture.id for fixture in fixture_list}

    existing = load_layout(path)
    existing_by_id = (
        {entry.fixture_id: entry for entry in existing.entries} if existing else {}
    )

    orphan_fixture_ids = tuple(
        sorted(
            fixture_id for fixture_id in existing_by_id if fixture_id not in fixture_ids
        )
    )

    # structure is user-owned data too — a saved custom shape is never
    # silently reset back to the default arch just because the venue's
    # fixture patch changed (mirrors layout regenerate's own behavior).
    target_structure = existing.structure_cm if existing is not None else None
    fresh = generate_layout(venue_id, fixture_list, target_structure)
    fresh_by_id = {entry.fixture_id: entry for entry in fresh.entries}

    merged_entries = tuple(
        existing_by_id[fixture.id]
        if fixture.id in existing_by_id
        else fresh_by_id[fixture.id]
        for fixture in fixture_list
    )
    merged_layout = RigLayout(
        venue_id=venue_id,
        entries=merged_entries,
        structure_cm=fresh.structure_cm,
        frame_cm=fresh.frame_cm,
    )
    save_layout(path, merged_layout)

    return LayoutMergeResult(
        layout=merged_layout, orphan_fixture_ids=orphan_fixture_ids
    )


def layout_path_for_venue(venue_id: int, base_dir: Path) -> Path:
    """Default on-disk path for a venue's layout description."""
    return base_dir / f"layout_venue_{venue_id}.json"


def layout_to_dict(layout: RigLayout) -> dict:
    """JSON-serializable representation of a RigLayout (used by
    save_layout, exposed for tests that assert on-disk shape directly).
    """
    return {
        "venue_id": layout.venue_id,
        "entries": [
            {
                "fixture_id": entry.fixture_id,
                "x": entry.x,
                "y": entry.y,
                "label": entry.label,
                "kind": entry.kind,
                "rotation": entry.rotation,
                "pan_degrees": entry.pan_degrees,
                "tilt_degrees": entry.tilt_degrees,
            }
            for entry in layout.entries
        ],
        "structure_cm": [list(point) for point in layout.structure_cm],
        "frame_cm": frame_cm_to_dict(layout.frame_cm),
    }


def layout_from_dict(data: dict) -> RigLayout:
    """Inverse of layout_to_dict. Missing "rotation" (layout files written
    before rotation support existed) defaults to 0.0 rather than failing.
    Missing "pan_degrees"/"tilt_degrees" (layout files written before
    pan/tilt sweep support existed) default to DEFAULT_PAN_DEGREES /
    DEFAULT_TILT_DEGREES for the same reason. Missing "structure_cm"
    (layout files written before stage geometry existed) defaults to the
    standard arch; missing "frame_cm" defaults to None (recovered from
    the structure's own bounding box by `normalized_structure`). Same
    optional-field defaulting precedent as rotation/pan/tilt above — no
    schema version, no migration step.

    Raises DegenerateStructureError if the loaded `structure_cm` cannot
    describe a valid polyline.
    """
    raw_structure = data.get("structure_cm")
    structure_cm = (
        tuple((float(x), float(y)) for x, y in raw_structure)
        if raw_structure is not None
        else arch_outline_cm()
    )
    _validate_structure_cm(structure_cm)

    raw_frame = data.get("frame_cm")
    frame_cm = (
        NormalizationFrame(
            min_x=raw_frame["min_x"],
            max_x=raw_frame["max_x"],
            min_y=raw_frame["min_y"],
            max_y=raw_frame["max_y"],
        )
        if raw_frame is not None
        else None
    )

    return RigLayout(
        venue_id=data["venue_id"],
        entries=tuple(
            LayoutEntry(
                fixture_id=entry["fixture_id"],
                x=entry["x"],
                y=entry["y"],
                label=entry["label"],
                kind=entry["kind"],
                rotation=entry.get("rotation", 0.0),
                pan_degrees=entry.get("pan_degrees", DEFAULT_PAN_DEGREES),
                tilt_degrees=entry.get("tilt_degrees", DEFAULT_TILT_DEGREES),
            )
            for entry in data["entries"]
        ),
        structure_cm=structure_cm,
        frame_cm=frame_cm,
    )
