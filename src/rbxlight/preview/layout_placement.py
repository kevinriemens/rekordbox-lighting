"""Fixture placement: mount fixtures onto the stage/truss structure by
kind and DMX address order, then normalize everything into one shared
[0, 1] frame.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from rbxlight.models import FIXTURE_SLOT_TYPES
from rbxlight.preview.layout_geometry import (
    NormalizationFrame,
    _normalize_point,
    _structure_bounds,
    arch_outline_cm,
    normalize_rotation,
)
from rbxlight.preview.layout_segments import (
    _classify_segments,
    _point_along_segments,
    _run_segments,
)
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
