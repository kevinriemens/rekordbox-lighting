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
from dataclasses import dataclass
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

#: All valid values of LayoutEntry.kind.
VALID_KINDS: frozenset[str] = frozenset(
    {"moving_head", "bar_cell", "par", "tilt_block", "effect", "other"}
)

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
    """
    frac_x = (x_cm - min_x) / (max_x - min_x)
    frac_y = (y_cm - min_y) / (max_y - min_y)
    nx = _MARGIN_FRACTION + frac_x * (1 - 2 * _MARGIN_FRACTION)
    ny = _MARGIN_FRACTION + (1 - frac_y) * (1 - 2 * _MARGIN_FRACTION)
    return nx, ny


def normalized_arch_outline() -> tuple[tuple[float, float], ...]:
    """`arch_outline_cm()`, normalized into the same [0, 1] convention
    used by `generate_layout` (ground at the bottom, sky at the top),
    using the arch's own bounding box. Used by the preview payload so the
    renderer can draw the truss.
    """
    points = arch_outline_cm()
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return tuple(_normalize_point(x, y, min_x, max_x, min_y, max_y) for x, y in points)


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
    *,
    reverse_cell_order: bool = False,
) -> RigLayout:
    """Produce one LayoutEntry per fixture, mounting each on the real
    arch by kind + DMX address order (never list position — grouping and
    ordering must be identical for any input ordering of the same
    fixtures):

    - moving_head #1-2 (lowest DMX address first) -> the two diagonal
      segments, rotation +/-DIAGONAL_ANGLE_DEG
    - moving_head #3+ (address order) -> spaced evenly along the
      horizontal top segment, rotation 0
    - each tilt_block + the bar_cell fixtures whose DMX address falls in
      its channel range (see `_bar_address_ranges`) -> one bar, mounted
      VERTICALLY: the lowest-address tilt on the inside of the left
      vertical segment, the next on the right vertical segment. Grouping
      is by DMX address ONLY — never by list position, since the real
      repository returns both tilt blocks before any cell.
    - pars -> first half by address stand left of the arch, remainder
      stand right, all on the ground, below every bar cell
    - a bar_cell whose address falls outside every tilt block's range is
      reported in `RigLayout.unmapped_cell_ids` and positioned at the
      arch centre (never on either bar's leg)

    `reverse_cell_order` mirrors each bar's cell ordering along its
    height and changes nothing else. Pure and deterministic — identical
    fixtures in, identical layout out, regardless of input ordering.
    """
    fixture_list = list(fixtures)
    if not fixture_list:
        return RigLayout(venue_id=venue_id, entries=())

    _p0, p1, p2, p3, p4, p5 = arch_outline_cm()
    arch_width = p5[0]

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

    # --- moving heads: first two on the diagonals, rest along the top ---
    diag_heads = moving_heads[:2]
    top_heads = moving_heads[2:]
    diag_specs = ((p1, p2, DIAGONAL_ANGLE_DEG), (p3, p4, -DIAGONAL_ANGLE_DEG))
    for fixture, (start, end, angle) in zip(diag_heads, diag_specs):
        positions[fixture.id] = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        rotations[fixture.id] = angle

    n_top = len(top_heads)
    for i, fixture in enumerate(top_heads):
        frac = (i + 1) / (n_top + 1)
        positions[fixture.id] = (p2[0] + frac * (p3[0] - p2[0]), p2[1])
        rotations[fixture.id] = 0.0

    # --- bars: 9 cells mounted vertically, tilt block co-located ---
    bar_x_by_index = (0.0, arch_width)
    for bar_index, group in enumerate(bar_groups[:2]):
        bar_x = bar_x_by_index[bar_index]
        n_cells = len(group.cells)
        for i, cell in enumerate(group.cells):
            slot = (n_cells - 1 - i) if reverse_cell_order else i
            y_cm = (slot + 0.5) / n_cells * VERTICAL_SEGMENT_LENGTH_CM
            positions[cell.id] = (bar_x, y_cm)
            rotations[cell.id] = 0.0

        positions[group.tilt.id] = (bar_x, VERTICAL_SEGMENT_LENGTH_CM / 2)
        rotations[group.tilt.id] = normalize_rotation(
            DEFAULT_TILT_BLOCK_ROTATION_DEGREES
        )

    # --- pars: ground level, split left/right outside the arch footprint ---
    split = (len(pars) + 1) // 2
    left_pars, right_pars = pars[:split], pars[split:]
    for i, fixture in enumerate(left_pars):
        positions[fixture.id] = (-_PAR_GROUND_OFFSET_CM - i * _PAR_SPACING_CM, 0.0)
        rotations[fixture.id] = 0.0
    for i, fixture in enumerate(right_pars):
        positions[fixture.id] = (
            arch_width + _PAR_GROUND_OFFSET_CM + i * _PAR_SPACING_CM,
            0.0,
        )
        rotations[fixture.id] = 0.0

    # --- anything unclassified/unmounted: centre of the arch ---
    for fixture in fixture_list:
        if fixture.id not in positions:
            positions[fixture.id] = (arch_width / 2, VERTICAL_SEGMENT_LENGTH_CM / 2)
            rotations[fixture.id] = 0.0

    # --- normalize: bounding box is the arch outline unioned with every
    # fixture position, plus a margin so nothing lands exactly on 0/1 ---
    all_points = list(arch_outline_cm()) + list(positions.values())
    xs = [pt[0] for pt in all_points]
    ys = [pt[1] for pt in all_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    entries = tuple(
        LayoutEntry(
            fixture_id=fixture.id,
            x=_normalize_point(*positions[fixture.id], min_x, max_x, min_y, max_y)[0],
            y=_normalize_point(*positions[fixture.id], min_x, max_x, min_y, max_y)[1],
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

    fresh_by_id = {
        entry.fixture_id: entry
        for entry in generate_layout(venue_id, fixture_list).entries
    }

    merged_entries = tuple(
        existing_by_id[fixture.id]
        if fixture.id in existing_by_id
        else fresh_by_id[fixture.id]
        for fixture in fixture_list
    )
    merged_layout = RigLayout(venue_id=venue_id, entries=merged_entries)
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
    }


def layout_from_dict(data: dict) -> RigLayout:
    """Inverse of layout_to_dict. Missing "rotation" (layout files written
    before rotation support existed) defaults to 0.0 rather than failing.
    Missing "pan_degrees"/"tilt_degrees" (layout files written before
    pan/tilt sweep support existed) default to DEFAULT_PAN_DEGREES /
    DEFAULT_TILT_DEGREES for the same reason.
    """
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
    )
