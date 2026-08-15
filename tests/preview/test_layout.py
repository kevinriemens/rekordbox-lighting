"""Tests for rbxlight.preview.layout — rig layout description generation,
persistence, and non-destructive regeneration. Contract: task requirements
("Physical rig layout geometry") + physical-rig-profile skill (fixture-kind
classification grounded in real hardware) + rekordbox-data-safety skill
(atomic writes to a file this tool owns).

Geometry contract this suite pins down (see rbxlight.preview.layout
docstrings once implemented):

- `layout.arch_outline_cm()` — 6 vertices (5 segments) of the real truss,
  in cm, left-to-right, y-up, origin at the base of the left vertical.
- `layout.VERTICAL_SEGMENT_LENGTH_CM` (150.0), `DIAGONAL_SEGMENT_LENGTH_CM`
  (100.0), `TOP_SEGMENT_LENGTH_CM` (100.0), `DIAGONAL_ANGLE_DEG` (45.0).
- `layout.normalize_rotation(degrees)` — wraps any degree value into
  [0, 360).
- `LayoutEntry.rotation: float = 0.0`, normalized on construction.
- `layout.GROUND_Y == 1.0`, `layout.SKY_Y == 0.0` — explicit convention:
  the ground is the LARGER end of the normalized y range.
- `generate_layout(venue_id, fixtures, *, reverse_cell_order=False)` —
  mounts fixtures on the arch by kind + patch order:
    - moving_head #1-2 (list order) -> the two diagonal segments,
      rotation defaulting to +/-DIAGONAL_ANGLE_DEG (normalized)
    - moving_head #3+ (list order) -> spaced evenly along the horizontal
      top segment, rotation 0
    - 1st tilt_block + the 9 bar_cell fixtures following it -> bar 1
      (left vertical segment)
    - 2nd tilt_block + the 9 bar_cell fixtures following it -> bar 2
      (right vertical segment)
    - pars -> first half of list order stand left of the arch, remainder
      stand right, all on the ground, outside the arch's footprint
- `save_layout` writes atomically (temp file + `os.replace`) so an
  interrupted save cannot leave a truncated/corrupt file at the target
  path.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from rbxlight.preview import layout
from rbxlight.preview.layout import LayoutEntry, RigLayout
from tests.fixtures.venue_fixtures import (
    BAR_1_CELL_ADDRS,
    BAR_1_TILT_ADDR,
    BAR_2_CELL_ADDRS,
    BAR_2_TILT_ADDR,
    HEAD_ADDRS,
    LM70S_MASTER_ID,
    PAR_ADDRS,
    PAR_MASTER_ID,
    PIXEL_CELL_MASTER_ID,
    TILT_BLOCK_MASTER_ID,
    UNKNOWN_MASTER_ID,
    a_fixture_model,
    a_full_arc_fixture_list,
)


def _by_label(result: RigLayout, label: str) -> LayoutEntry:
    return next(e for e in result.entries if e.label == label)


class TestClassifyFixtureKind:
    @pytest.mark.parametrize(
        "master_id,expected_kind",
        [
            (LM70S_MASTER_ID, "moving_head"),
            (TILT_BLOCK_MASTER_ID, "tilt_block"),
            (PIXEL_CELL_MASTER_ID, "bar_cell"),
            (PAR_MASTER_ID, "par"),
        ],
        ids=["lm70s", "tilt_block", "pixel_cell", "par"],
    )
    def test_should_classify_known_rig_hardware_by_master_id(
        self, master_id: int, expected_kind: str
    ) -> None:
        # Given: a fixture whose master id is one of the 4 known rig profiles
        fixture = a_fixture_model(fixture_id=1, fixture_master_id=master_id)

        # When: classifying its kind
        kind = layout.classify_fixture_kind(fixture)

        # Then: it maps to the hardware-grounded kind, not the macro slot
        assert kind == expected_kind

    def test_should_classify_unknown_master_id_in_an_effect_slot_as_effect(
        self,
    ) -> None:
        # Given: an unrecognized master id patched into an Effect slot (t8)
        fixture = a_fixture_model(
            fixture_id=1, fixture_master_id=UNKNOWN_MASTER_ID, macro_fixture_id=17
        )

        # When: classifying its kind
        kind = layout.classify_fixture_kind(fixture)

        # Then: falls back to "effect"
        assert kind == "effect"

    def test_should_classify_unknown_master_id_in_a_non_effect_slot_as_other(
        self,
    ) -> None:
        # Given: an unrecognized master id patched into a Par slot (t1)
        fixture = a_fixture_model(
            fixture_id=1, fixture_master_id=UNKNOWN_MASTER_ID, macro_fixture_id=1
        )

        # When: classifying its kind
        kind = layout.classify_fixture_kind(fixture)

        # Then: falls back to "other"
        assert kind == "other"

    def test_should_never_classify_by_macro_slot_assignment_alone(self) -> None:
        # Given: a real LM70S patched (unusually) into a Par slot
        fixture = a_fixture_model(
            fixture_id=1, fixture_master_id=LM70S_MASTER_ID, macro_fixture_id=1
        )

        # When: classifying its kind
        kind = layout.classify_fixture_kind(fixture)

        # Then: kind reflects the hardware, not the slot it happens to occupy
        assert kind == "moving_head"


class TestGenerateLayout:
    def test_should_produce_one_entry_per_fixture(self) -> None:
        # Given: 3 fixtures
        fixtures = [
            a_fixture_model(fixture_id=1),
            a_fixture_model(fixture_id=2),
            a_fixture_model(fixture_id=3),
        ]

        # When: generating a layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: exactly one entry per fixture, matching ids
        assert len(result.entries) == 3
        assert {e.fixture_id for e in result.entries} == {1, 2, 3}

    def test_should_normalize_positions_between_zero_and_one(self) -> None:
        # Given: several fixtures
        fixtures = [a_fixture_model(fixture_id=i) for i in range(1, 8)]

        # When: generating a layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: every position is within [0, 1] on both axes
        for entry in result.entries:
            assert 0.0 <= entry.x <= 1.0
            assert 0.0 <= entry.y <= 1.0

    def test_should_label_each_entry_with_the_fixture_name(self) -> None:
        # Given: a fixture with a specific name
        fixtures = [a_fixture_model(fixture_id=1, name="LM70S #1")]

        # When: generating a layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: the entry's label is the fixture's human name
        assert result.entries[0].label == "LM70S #1"

    def test_should_classify_kind_from_the_fixture_itself(self) -> None:
        # Given: a known-hardware fixture
        fixtures = [a_fixture_model(fixture_id=1, fixture_master_id=PAR_MASTER_ID)]

        # When: generating a layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: kind matches the standalone classifier
        assert result.entries[0].kind == "par"

    def test_should_be_deterministic_for_identical_input(self) -> None:
        # Given: the same fixture list
        fixtures = [a_fixture_model(fixture_id=i) for i in range(1, 5)]

        # When: generating twice
        first = layout.generate_layout(venue_id=2, fixtures=fixtures)
        second = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: identical output
        assert first == second

    def test_should_return_empty_entries_for_a_venue_with_no_fixtures(self) -> None:
        # Given: no fixtures at all
        # When: generating a layout
        result = layout.generate_layout(venue_id=2, fixtures=[])

        # Then: no crash, an empty layout
        assert result.entries == ()
        assert result.venue_id == 2


class TestLoadLayout:
    def test_should_return_none_when_no_file_exists(self, tmp_path: Path) -> None:
        # Given: a path with no layout file
        path = tmp_path / "layout_venue_2.json"

        # When: loading it
        result = layout.load_layout(path)

        # Then: None, not an error
        assert result is None

    def test_should_round_trip_through_save_and_load(self, tmp_path: Path) -> None:
        # Given: a layout with real entries
        original = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=16, x=0.12, y=0.30, label="LM70S #1", kind="moving_head"
                ),
            ),
        )
        path = tmp_path / "layout_venue_2.json"

        # When: saving then loading
        layout.save_layout(path, original)
        loaded = layout.load_layout(path)

        # Then: identical to the original
        assert loaded == original


class TestSaveLayout:
    def test_should_create_parent_directories_if_missing(self, tmp_path: Path) -> None:
        # Given: a path whose parent directory doesn't exist yet
        path = tmp_path / "nested" / "dir" / "layout_venue_2.json"
        rig_layout = RigLayout(venue_id=2, entries=())

        # When: saving
        layout.save_layout(path, rig_layout)

        # Then: the file exists
        assert path.exists()


class TestEnsureLayout:
    def test_should_generate_a_fresh_layout_when_none_exists(
        self, tmp_path: Path
    ) -> None:
        # Given: no layout file yet, and 2 fixtures
        path = tmp_path / "layout_venue_2.json"
        fixtures = [a_fixture_model(fixture_id=1), a_fixture_model(fixture_id=2)]

        # When: ensuring a layout
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: an entry for every fixture, no orphans, and it's persisted
        assert {e.fixture_id for e in result.layout.entries} == {1, 2}
        assert result.orphan_fixture_ids == ()
        assert path.exists()

    def test_should_preserve_user_adjusted_positions_on_regenerate(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout where the user moved fixture 1
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1, x=0.91, y=0.05, label="LM70S #1", kind="moving_head"
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures = [a_fixture_model(fixture_id=1)]

        # When: regenerating against the same fixture list
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: the user's adjusted position is untouched
        entry = next(e for e in result.layout.entries if e.fixture_id == 1)
        assert entry.x == 0.91
        assert entry.y == 0.05

    def test_should_only_add_entries_for_fixtures_missing_from_the_existing_layout(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout covering fixture 1 only
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1, x=0.5, y=0.5, label="LM70S #1", kind="moving_head"
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures = [a_fixture_model(fixture_id=1), a_fixture_model(fixture_id=2)]

        # When: regenerating with a new fixture (id=2) added to the venue
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: fixture 1's entry is untouched, fixture 2 gets a new entry
        entries_by_id = {e.fixture_id: e for e in result.layout.entries}
        assert entries_by_id[1].x == 0.5
        assert entries_by_id[1].y == 0.5
        assert 2 in entries_by_id

    def test_should_report_orphan_entries_without_silently_dropping_them(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout referencing a fixture that has since
        # been removed from the venue's patch
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=999, x=0.5, y=0.5, label="Removed Fixture", kind="par"
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures: list = []  # fixture 999 no longer exists in the venue

        # When: regenerating
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: the orphan is reported, not silently dropped from knowledge
        assert result.orphan_fixture_ids == (999,)
        # ...but it's also not left in the renderable layout, since it has
        # no corresponding real fixture to draw.
        assert all(e.fixture_id != 999 for e in result.layout.entries)


# ---------------------------------------------------------------------------
# Arch geometry — the real 5-segment truss shape (task requirement:
# "The real truss shape"). Pure geometry, no fixtures involved.
# ---------------------------------------------------------------------------


class TestArchOutline:
    def test_should_return_six_vertices_for_the_five_segments(self) -> None:
        # Given/When: the real truss outline
        points = layout.arch_outline_cm()

        # Then: 5 segments need 6 vertices
        assert len(points) == 6

    def test_should_have_segments_matching_the_documented_real_world_lengths(
        self,
    ) -> None:
        # Given: the outline's 6 vertices
        points = layout.arch_outline_cm()

        # When: measuring each of the 5 segments
        lengths = [
            math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
            for i in range(5)
        ]

        # Then: 150cm vertical, 100cm diagonal, 100cm top, 100cm diagonal,
        # 150cm vertical — left to right, as described by the user
        assert lengths[0] == pytest.approx(layout.VERTICAL_SEGMENT_LENGTH_CM)
        assert lengths[1] == pytest.approx(layout.DIAGONAL_SEGMENT_LENGTH_CM)
        assert lengths[2] == pytest.approx(layout.TOP_SEGMENT_LENGTH_CM)
        assert lengths[3] == pytest.approx(layout.DIAGONAL_SEGMENT_LENGTH_CM)
        assert lengths[4] == pytest.approx(layout.VERTICAL_SEGMENT_LENGTH_CM)

    def test_should_travel_up_across_and_down_in_the_described_directions(self) -> None:
        # Given: the outline's 6 vertices, left to right
        p0, p1, p2, p3, p4, p5 = layout.arch_outline_cm()

        # Then: segment 1 rises straight up (no horizontal drift)
        assert p1[0] == pytest.approx(p0[0])
        assert p1[1] > p0[1]
        # segment 2 rises up and to the right
        assert p2[0] > p1[0]
        assert p2[1] > p1[1]
        # segment 3 crosses horizontally to the right, same height
        assert p3[0] > p2[0]
        assert p3[1] == pytest.approx(p2[1])
        # segment 4 descends down and to the right
        assert p4[0] > p3[0]
        assert p4[1] < p3[1]
        # segment 5 descends straight down to the ground
        assert p5[0] == pytest.approx(p4[0])
        assert p5[1] < p4[1]

    def test_should_have_two_verticals_of_equal_height(self) -> None:
        # Given: the outline's 6 vertices
        p0, p1, _p2, _p3, p4, p5 = layout.arch_outline_cm()

        # When: measuring each vertical segment's height
        left_height = p1[1] - p0[1]
        right_height = p4[1] - p5[1]

        # Then: identical, matching the documented 150cm
        assert left_height == pytest.approx(layout.VERTICAL_SEGMENT_LENGTH_CM)
        assert right_height == pytest.approx(left_height)

    def test_should_have_diagonals_that_are_mirror_images_at_forty_five_degrees(
        self,
    ) -> None:
        # Given: the outline's 6 vertices
        _p0, p1, p2, p3, p4, _p5 = layout.arch_outline_cm()

        # When: measuring each diagonal's angle from horizontal
        left_angle = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        right_angle = math.degrees(math.atan2(p4[1] - p3[1], p4[0] - p3[0]))

        # Then: +45 going up-right, -45 going down-right — mirror images
        assert left_angle == pytest.approx(45.0)
        assert right_angle == pytest.approx(-45.0)
        assert left_angle == pytest.approx(-right_angle)

    def test_should_be_symmetric_about_its_vertical_centre_line(self) -> None:
        # Given: the outline's 6 vertices
        points = layout.arch_outline_cm()
        xs = [p[0] for p in points]
        mid_x = (min(xs) + max(xs)) / 2

        # When/Then: every point has a mirror partner across the centre
        # line, at the same height
        for left_point, right_point in zip(points, reversed(points)):
            assert left_point[0] + right_point[0] == pytest.approx(2 * mid_x)
            assert left_point[1] == pytest.approx(right_point[1])

    def test_should_have_a_bounding_box_matching_the_real_segment_proportions(
        self,
    ) -> None:
        # Given: the outline's 6 vertices
        points = layout.arch_outline_cm()
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]

        # When: measuring the overall bounding box
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)

        # Then: roughly 241cm wide by 221cm tall, as the segment lengths imply
        assert width == pytest.approx(241.4, abs=1.0)
        assert height == pytest.approx(220.7, abs=1.0)


# ---------------------------------------------------------------------------
# Rotation (task requirement: "Rotation")
# ---------------------------------------------------------------------------


class TestNormalizeRotation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (0.0, 0.0),
            (45.0, 45.0),
            (359.0, 359.0),
            (360.0, 0.0),
            (-45.0, 315.0),
            (400.0, 40.0),
            (725.0, 5.0),
            (-1.0, 359.0),
        ],
    )
    def test_should_wrap_any_degree_value_into_the_zero_to_360_range(
        self, raw: float, expected: float
    ) -> None:
        # Given: a raw rotation value, possibly outside 0-360
        # When: normalizing it
        result = layout.normalize_rotation(raw)

        # Then: it's wrapped, never rejected
        assert result == pytest.approx(expected)


class TestLayoutEntryRotation:
    def test_should_default_rotation_to_zero(self) -> None:
        # Given/When: an entry built without specifying rotation
        entry = LayoutEntry(fixture_id=1, x=0.5, y=0.5, label="X", kind="par")

        # Then: rotation defaults to zero
        assert entry.rotation == 0.0

    @pytest.mark.parametrize(
        "raw,expected", [(-45.0, 315.0), (400.0, 40.0), (360.0, 0.0), (725.0, 5.0)]
    )
    def test_should_normalize_out_of_range_rotation_instead_of_rejecting_it(
        self, raw: float, expected: float
    ) -> None:
        # Given: a rotation value outside 0-360
        # When: constructing an entry with it
        entry = LayoutEntry(
            fixture_id=1, x=0.5, y=0.5, label="X", kind="par", rotation=raw
        )

        # Then: normalized, not rejected/raised
        assert entry.rotation == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Arch mounting (task requirements: "Where fixtures sit on it",
# "Normalization and output"). Uses the real 27-fixture venue composition.
# ---------------------------------------------------------------------------


class TestGenerateLayoutArchMounting:
    def test_should_mount_bar_cells_vertically_with_constant_x_and_varying_y(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: each bar's 9 cells share one horizontal position, distinct
        # from the other bar's, but vary in height
        bar1_cells = [_by_label(result, f"Bar 1 Cell {i}") for i in range(1, 10)]
        bar2_cells = [_by_label(result, f"Bar 2 Cell {i}") for i in range(1, 10)]

        bar1_xs = {round(e.x, 6) for e in bar1_cells}
        bar2_xs = {round(e.x, 6) for e in bar2_cells}
        assert len(bar1_xs) == 1
        assert len(bar2_xs) == 1
        assert bar1_xs != bar2_xs

        bar1_ys = {round(e.y, 6) for e in bar1_cells}
        assert len(bar1_ys) == 9

    def test_should_distribute_a_bars_nine_cells_evenly_along_its_height(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: consecutive cells are equally spaced along the bar
        ys = [_by_label(result, f"Bar 1 Cell {i}").y for i in range(1, 10)]
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        assert gaps[0] != pytest.approx(0.0)
        for gap in gaps[1:]:
            assert gap == pytest.approx(gaps[0], abs=1e-6)

    def test_should_co_locate_each_bars_tilt_block_with_its_bar(self) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: each tilt block sits at the same horizontal position as
        # its own bar's cells, within that bar's vertical extent
        bar1_ys = [_by_label(result, f"Bar 1 Cell {i}").y for i in range(1, 10)]
        bar2_ys = [_by_label(result, f"Bar 2 Cell {i}").y for i in range(1, 10)]
        bar1_x = _by_label(result, "Bar 1 Cell 1").x
        bar2_x = _by_label(result, "Bar 2 Cell 1").x

        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")

        assert tilt1.x == pytest.approx(bar1_x)
        assert min(bar1_ys) <= tilt1.y <= max(bar1_ys)

        assert tilt2.x == pytest.approx(bar2_x)
        assert min(bar2_ys) <= tilt2.y <= max(bar2_ys)

    def test_should_reverse_cell_order_producing_mirrored_positions_only(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating with default and reversed cell ordering
        default_result = layout.generate_layout(venue_id=2, fixtures=fixtures)
        reversed_result = layout.generate_layout(
            venue_id=2, fixtures=fixtures, reverse_cell_order=True
        )

        # Then: bar 1's cell heights are exactly mirrored end-to-end
        default_ys = [
            _by_label(default_result, f"Bar 1 Cell {i}").y for i in range(1, 10)
        ]
        reversed_ys = [
            _by_label(reversed_result, f"Bar 1 Cell {i}").y for i in range(1, 10)
        ]
        assert reversed_ys == list(reversed(default_ys))

        # ...and nothing else about those cells changes
        for i in range(1, 10):
            default_entry = _by_label(default_result, f"Bar 1 Cell {i}")
            reversed_entry = _by_label(reversed_result, f"Bar 1 Cell {i}")
            assert reversed_entry.x == pytest.approx(default_entry.x)
            assert reversed_entry.label == default_entry.label
            assert reversed_entry.kind == default_entry.kind

        # ...nor does any non-bar-cell fixture's entry change at all
        for fixture in fixtures:
            if "Cell" in fixture.name:
                continue
            default_entry = next(
                e for e in default_result.entries if e.fixture_id == fixture.id
            )
            reversed_entry = next(
                e for e in reversed_result.entries if e.fixture_id == fixture.id
            )
            assert reversed_entry == default_entry

    def test_should_mount_one_moving_head_on_each_diagonal_with_the_segments_angle(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: the first two moving heads (patch order) sit on the two
        # diagonals, with rotation defaulting to the segment's own angle,
        # mirrored left vs right
        left = _by_label(result, "LM70S #1")
        right = _by_label(result, "LM70S #2")

        assert left.rotation == pytest.approx(
            layout.normalize_rotation(layout.DIAGONAL_ANGLE_DEG)
        )
        assert right.rotation == pytest.approx(
            layout.normalize_rotation(-layout.DIAGONAL_ANGLE_DEG)
        )
        assert left.rotation != right.rotation
        assert left.x != right.x

    def test_should_space_two_top_heads_evenly_between_the_verticals_with_no_rotation(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: the remaining two moving heads sit on the horizontal top,
        # between the two verticals, level with each other, unrotated
        bar1_x = _by_label(result, "Bar 1 Cell 1").x
        bar2_x = _by_label(result, "Bar 2 Cell 1").x
        low_x, high_x = sorted((bar1_x, bar2_x))

        top_a = _by_label(result, "LM70S #3")
        top_b = _by_label(result, "LM70S #4")

        assert low_x < top_a.x < high_x
        assert low_x < top_b.x < high_x
        assert top_a.x != top_b.x
        assert top_a.y == pytest.approx(top_b.y)
        assert top_a.rotation == 0.0
        assert top_b.rotation == 0.0

    def test_should_default_rotation_to_zero_for_fixtures_with_no_default_mounting_rotation(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: only the two diagonal-mounted heads and the tilt blocks
        # (vertical bar mounting rotation — see
        # TestGenerateLayoutTiltBlockMountingRotation) get a non-zero
        # default; every other kind (top heads, bar cells, pars) stays
        # at zero
        diagonal_labels = {"LM70S #1", "LM70S #2"}
        for entry in result.entries:
            if entry.label in diagonal_labels or entry.kind == "tilt_block":
                continue
            assert entry.rotation == 0.0

    def test_should_stand_pars_on_the_ground_outside_the_arch_split_left_and_right(
        self,
    ) -> None:
        # Given: the real venue's fixture composition (3 patched pars)
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        pars = [_by_label(result, f"LPC008S #{i}") for i in range(1, 4)]
        non_par_entries = [e for e in result.entries if e.kind != "par"]
        min_non_par_x = min(e.x for e in non_par_entries)
        max_non_par_x = max(e.x for e in non_par_entries)

        # Then: every par sits outside the arch's horizontal footprint,
        # split across both sides
        left_pars = [p for p in pars if p.x < min_non_par_x]
        right_pars = [p for p in pars if p.x > max_non_par_x]
        assert len(left_pars) + len(right_pars) == 3
        assert left_pars
        assert right_pars

        # ...and each par has a distinct position, even on the same side
        assert len({(round(p.x, 6), round(p.y, 6)) for p in pars}) == 3

    def test_should_produce_exactly_one_entry_per_patched_fixture(self) -> None:
        # Given: the real 27-fixture venue composition — no smoke-machine
        # fixture row exists (it has no DMX fixture presence)
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: exactly 27 entries, never an invented extra one
        assert len(result.entries) == len(fixtures) == 27
        assert {e.fixture_id for e in result.entries} == {f.id for f in fixtures}

    def test_should_be_deterministic_for_the_full_arc_composition(self) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating twice
        first = layout.generate_layout(venue_id=2, fixtures=fixtures)
        second = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: identical output
        assert first == second


# ---------------------------------------------------------------------------
# Regression: bar/cell grouping must be by DMX ADDRESS, not list position.
#
# Bug: generate_layout used to walk the fixture list assuming the
# sequence `tilt, its 9 cells, tilt, its 9 cells`. The real repository
# returns `tilt_block x2, moving_head x4, bar_cell x18, par x3` — both
# tilt blocks arrive before any cell. One bar's 9 cells collapsed onto
# the other bar's pending slot count, and the remaining 9 fell through
# to the centre of the arch. Correct rule: each L1015 bar's tilt block
# owns the cell addresses in its 43-channel range, up to the start of the
# next bar's range — independent of list order.
# ---------------------------------------------------------------------------


class TestGenerateLayoutAddressBasedBarGrouping:
    def test_should_group_each_bars_cells_by_dmx_address_in_the_real_repository_order(
        self,
    ) -> None:
        # Given: fixtures in the REAL repository order — both tilt blocks
        # first, then all 4 heads, then all 18 cells, then the 3 pars
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: bar 1's tilt (ch501) groups with exactly the 9 cells whose
        # addresses fall in its range (ch507-542); bar 2's tilt (ch544)
        # groups with the 9 cells in its range (ch550-585) — never the
        # other bar's
        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")
        bar1_cells = [_by_label(result, f"Bar 1 Cell {i}") for i in range(1, 10)]
        bar2_cells = [_by_label(result, f"Bar 2 Cell {i}") for i in range(1, 10)]

        for cell in bar1_cells:
            assert cell.x == pytest.approx(tilt1.x)
        for cell in bar2_cells:
            assert cell.x == pytest.approx(tilt2.x)
        assert tilt1.x != pytest.approx(tilt2.x)

    def test_should_never_collapse_multiple_cells_onto_the_same_stacked_point(
        self,
    ) -> None:
        # Given: fixtures in the REAL repository order
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: all 18 cells occupy 18 distinct positions — never 9 cells
        # stacked on one identical dead-centre point, the exact visible
        # symptom of the original bug. This can never recur.
        all_cells = [
            _by_label(result, f"Bar {bar} Cell {i}")
            for bar in (1, 2)
            for i in range(1, 10)
        ]
        distinct_positions = {(round(c.x, 6), round(c.y, 6)) for c in all_cells}
        assert len(distinct_positions) == 18

    def test_should_place_the_two_bars_on_opposite_legs_with_no_cross_contamination(
        self,
    ) -> None:
        # Given: fixtures in the REAL repository order
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: bar 1's leg x and bar 2's leg x are distinct, every one of
        # bar 1's cells and its own tilt share bar 1's leg, and every one
        # of bar 2's cells and its own tilt share bar 2's leg — no cell
        # from one bar is ever positioned on the other bar's leg
        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")
        bar1_cells = [_by_label(result, f"Bar 1 Cell {i}") for i in range(1, 10)]
        bar2_cells = [_by_label(result, f"Bar 2 Cell {i}") for i in range(1, 10)]

        bar1_x = round(bar1_cells[0].x, 6)
        bar2_x = round(bar2_cells[0].x, 6)
        assert bar1_x != bar2_x

        assert all(round(c.x, 6) == bar1_x for c in bar1_cells)
        assert all(round(c.x, 6) == bar2_x for c in bar2_cells)
        assert round(tilt1.x, 6) == bar1_x
        assert round(tilt2.x, 6) == bar2_x

    def test_should_produce_the_same_fixture_to_position_mapping_regardless_of_input_order(
        self,
    ) -> None:
        # Given: fixtures in the REAL repository order, and the same
        # fixtures shuffled into an arbitrary order
        fixtures = a_full_arc_fixture_list()
        shuffled = list(fixtures)
        random.Random(42).shuffle(shuffled)

        # When: generating a layout from each ordering
        ordered_result = layout.generate_layout(venue_id=2, fixtures=fixtures)
        shuffled_result = layout.generate_layout(venue_id=2, fixtures=shuffled)

        # Then: identical fixture-id -> (x, y, rotation, kind) mapping —
        # grouping depends only on DMX address, never on list order
        def _mapping(
            rig_layout: RigLayout,
        ) -> dict[int, tuple[float, float, float, str]]:
            return {
                e.fixture_id: (round(e.x, 6), round(e.y, 6), e.rotation, e.kind)
                for e in rig_layout.entries
            }

        assert _mapping(ordered_result) == _mapping(shuffled_result)

    def test_should_group_by_address_even_when_the_higher_address_tilt_is_listed_first(
        self,
    ) -> None:
        # Given: bar 2's tilt (ch544, the HIGHER address) is listed
        # first, followed by one of bar 1's cells (ch507, belonging to the
        # LOWER-address tilt) BEFORE bar 1's own tilt (ch501) appears at
        # all — list position cannot be used to infer grouping here
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 2 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_2_TILT_ADDR,
            ),
            a_fixture_model(
                fixture_id=2,
                name="Bar 1 Cell 1",
                fixture_master_id=PIXEL_CELL_MASTER_ID,
                start_addr=BAR_1_CELL_ADDRS[0],
            ),
            a_fixture_model(
                fixture_id=3,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            ),
            a_fixture_model(
                fixture_id=4,
                name="Bar 2 Cell 1",
                fixture_master_id=PIXEL_CELL_MASTER_ID,
                start_addr=BAR_2_CELL_ADDRS[0],
            ),
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: bar 1's cell still groups with bar 1's tilt by address,
        # never with bar 2's — regardless of list order or which tilt has
        # the higher address
        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")
        bar1_cell = _by_label(result, "Bar 1 Cell 1")
        bar2_cell = _by_label(result, "Bar 2 Cell 1")

        assert bar1_cell.x == pytest.approx(tilt1.x)
        assert bar1_cell.x != pytest.approx(tilt2.x)
        assert bar2_cell.x == pytest.approx(tilt2.x)
        assert bar2_cell.x != pytest.approx(tilt1.x)

    def test_should_report_an_out_of_range_cell_without_crashing_or_mispositioning_it(
        self,
    ) -> None:
        # Given: fixtures in the REAL repository order, plus one stray
        # cell whose address (ch200) falls outside both bars' channel
        # ranges (bar 1's is 507-542, bar 2's is 550-585)
        fixtures = a_full_arc_fixture_list() + [
            a_fixture_model(
                fixture_id=999,
                name="Stray Cell",
                fixture_master_id=PIXEL_CELL_MASTER_ID,
                start_addr=200,
            )
        ]

        # When: generating the layout (must not raise)
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: it is reported as unmapped, not silently merged onto
        # either bar's leg
        assert result.unmapped_cell_ids == (999,)

        stray_entry = next(e for e in result.entries if e.fixture_id == 999)
        bar1_x = round(_by_label(result, "Bar 1 Cell 1").x, 6)
        bar2_x = round(_by_label(result, "Bar 2 Cell 1").x, 6)
        assert round(stray_entry.x, 6) not in (bar1_x, bar2_x)

    def test_should_position_a_tilt_block_with_no_cells_in_its_range(self) -> None:
        # Given: a single tilt block, with no bar_cell fixtures at all
        # patched into its channel range
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            ),
            a_fixture_model(
                fixture_id=2,
                name="LM70S #1",
                fixture_master_id=LM70S_MASTER_ID,
                start_addr=HEAD_ADDRS[0],
            ),
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: no crash, the tilt still gets a valid position
        tilt = _by_label(result, "Bar 1 Tilt")
        assert 0.0 < tilt.x < 1.0
        assert 0.0 < tilt.y < 1.0

    def test_should_group_correctly_when_exactly_one_bar_is_present(self) -> None:
        # Given: exactly one bar (tilt + its 9 cells) — no second bar at
        # all in the venue's patch
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            ),
        ] + [
            a_fixture_model(
                fixture_id=2 + i,
                name=f"Bar 1 Cell {i + 1}",
                fixture_master_id=PIXEL_CELL_MASTER_ID,
                start_addr=addr,
            )
            for i, addr in enumerate(BAR_1_CELL_ADDRS)
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: all 9 cells group with the single tilt block, sharing its
        # horizontal position, at 9 distinct heights
        tilt = _by_label(result, "Bar 1 Tilt")
        cells = [_by_label(result, f"Bar 1 Cell {i}") for i in range(1, 10)]
        for cell in cells:
            assert cell.x == pytest.approx(tilt.x)
        assert len({round(c.y, 6) for c in cells}) == 9

    def test_should_still_lay_out_a_venue_with_no_bars_at_all(self) -> None:
        # Given: moving heads and pars only — no tilt blocks, no bar
        # cells, in the venue's patch at all
        fixtures = [
            a_fixture_model(
                fixture_id=i,
                name=f"LM70S #{i}",
                fixture_master_id=LM70S_MASTER_ID,
                start_addr=addr,
            )
            for i, addr in enumerate(HEAD_ADDRS, start=1)
        ] + [
            a_fixture_model(
                fixture_id=10 + i,
                name=f"LPC008S #{i}",
                fixture_master_id=PAR_MASTER_ID,
                start_addr=addr,
            )
            for i, addr in enumerate(PAR_ADDRS, start=1)
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: no crash, one entry per fixture, and no bar_cell/
        # tilt_block kind ever appears
        assert len(result.entries) == len(fixtures)
        assert {e.kind for e in result.entries} == {"moving_head", "par"}


# ---------------------------------------------------------------------------
# Regression: tilt-block MOUNTING rotation, not fixture-model rotation.
#
# Bug: generate_layout hardcoded rotation=0 for tilt_block fixtures, so
# the renderer swung the L1015 bars' tilt vertically. Both bars are
# mounted VERTICALLY on the inside of the arch's legs (physical-rig-
# profile skill, "Where each fixture physically mounts") — mounting the
# bar on its end rotates its tilt axis 90 degrees, so the same tilt
# motor sweeps the beam fan HORIZONTALLY, left-right across the room.
# User's report: "The only thing I can't see is the tilt of the bars.
# they should sweep from left to right, right?" — they are correct.
# Same class of defect as the address-based bar/cell grouping bug above:
# the fixture was modelled, but not how it is physically MOUNTED.
# ---------------------------------------------------------------------------


class TestGenerateLayoutTiltBlockMountingRotation:
    def test_should_default_a_tilt_blocks_rotation_to_the_mounting_rotation(
        self,
    ) -> None:
        # Given: the real venue's fixture composition (two vertically
        # mounted L1015 tilt blocks among it)
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: each tilt block gets the mounting rotation (bar mounted
        # on its end), not the vertical-mount default of 0
        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")
        expected = layout.normalize_rotation(layout.DEFAULT_TILT_BLOCK_ROTATION_DEGREES)
        assert tilt1.rotation == pytest.approx(expected)
        assert tilt2.rotation == pytest.approx(expected)

    def test_should_never_give_the_two_tilt_blocks_opposing_mounting_rotations(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: both bars' tilt blocks share the SAME mounting rotation.
        # The mirrored left/right sweep the user sees comes from the
        # fixture's own tilt_reversal flag in the rekordbox data, never
        # from giving the two bars opposite mounting rotations here —
        # double-mirroring is exactly the bug this guards against.
        tilt1 = _by_label(result, "Bar 1 Tilt")
        tilt2 = _by_label(result, "Bar 2 Tilt")
        assert tilt1.rotation == pytest.approx(tilt2.rotation)
        assert tilt1.rotation != pytest.approx(
            layout.normalize_rotation(-layout.DEFAULT_TILT_BLOCK_ROTATION_DEGREES)
        )

    def test_should_apply_the_mounting_rotation_even_with_no_bar_cells_present(
        self,
    ) -> None:
        # Given: a venue with a tilt block but no bar_cell fixtures at all
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            )
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: it still gets the mounting rotation default
        tilt = _by_label(result, "Bar 1 Tilt")
        assert tilt.rotation == pytest.approx(
            layout.normalize_rotation(layout.DEFAULT_TILT_BLOCK_ROTATION_DEGREES)
        )

    def test_should_leave_moving_heads_bar_cells_and_pars_unaffected(self) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: the two diagonal-mounted heads keep their segment angle
        left = _by_label(result, "LM70S #1")
        right = _by_label(result, "LM70S #2")
        assert left.rotation == pytest.approx(
            layout.normalize_rotation(layout.DIAGONAL_ANGLE_DEG)
        )
        assert right.rotation == pytest.approx(
            layout.normalize_rotation(-layout.DIAGONAL_ANGLE_DEG)
        )

        # ...the top-mounted heads keep zero
        top_a = _by_label(result, "LM70S #3")
        top_b = _by_label(result, "LM70S #4")
        assert top_a.rotation == 0.0
        assert top_b.rotation == 0.0

        # ...and fixture kinds with no movement capability (bar cells,
        # pars) keep rotation zero — only tilt_block picks up the new
        # mounting default
        for entry in result.entries:
            if entry.kind in ("bar_cell", "par"):
                assert entry.rotation == 0.0

    def test_should_survive_regeneration_when_the_user_adjusts_a_tilt_blocks_rotation(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout where the user adjusted a tilt
        # block's rotation away from the mounting default
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.2,
                    y=0.3,
                    label="Bar 1 Tilt",
                    kind="tilt_block",
                    rotation=200.0,
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            )
        ]

        # When: regenerating against the same fixture list
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: the user's adjusted rotation survives, exactly as for
        # any other fixture kind — it is not reset to the mounting default
        entry = next(e for e in result.layout.entries if e.fixture_id == 1)
        assert entry.rotation == pytest.approx(200.0)


class TestEnsureLayoutTiltBlockMountingRotationDefault:
    """Edge case: a layout file recorded before this change, where a
    tilt block has rotation 0 explicitly recorded, must NOT be silently
    rewritten to the new mounting default — a recorded value (even 0) is
    a user value. Only a fixture with NO existing entry gets the new
    default.
    """

    def test_should_not_rewrite_a_pre_existing_zero_rotation_to_the_new_default(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout recorded by the pre-fix tool, where
        # tilt block #1's rotation was explicitly written as 0 (the old,
        # buggy default) — and a SECOND tilt block, #2, that has no
        # existing entry in the file at all
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.1,
                    y=0.5,
                    label="Bar 1 Tilt",
                    kind="tilt_block",
                    rotation=0.0,
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures = [
            a_fixture_model(
                fixture_id=1,
                name="Bar 1 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_1_TILT_ADDR,
            ),
            a_fixture_model(
                fixture_id=2,
                name="Bar 2 Tilt",
                fixture_master_id=TILT_BLOCK_MASTER_ID,
                start_addr=BAR_2_TILT_ADDR,
            ),
        ]

        # When: regenerating
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: fixture 1's recorded 0 survives untouched (a recorded
        # value is a user value, even if it happens to equal the old
        # buggy default) — but fixture 2, which had no existing entry at
        # all, gets the new mounting-rotation default
        entries_by_id = {e.fixture_id: e for e in result.layout.entries}
        assert entries_by_id[1].rotation == 0.0
        assert entries_by_id[2].rotation == pytest.approx(
            layout.normalize_rotation(layout.DEFAULT_TILT_BLOCK_ROTATION_DEGREES)
        )


class TestGenerateLayoutNormalization:
    def test_should_keep_every_position_strictly_within_the_margin(self) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: nothing sits exactly on the 0/1 edge — a small margin
        # keeps the arch from being clipped
        for entry in result.entries:
            assert 0.0 < entry.x < 1.0
            assert 0.0 < entry.y < 1.0

    def test_should_order_fixtures_vertically_from_ground_pars_up_to_the_apex(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        par_y = _by_label(result, "LPC008S #1").y
        bar_cell_ys = [_by_label(result, f"Bar 1 Cell {i}").y for i in range(1, 10)]
        diagonal_y = _by_label(result, "LM70S #1").y
        top_y = _by_label(result, "LM70S #3").y

        # Then: ground (largest y, GROUND_Y) up to the apex (smallest y):
        # pars below every bar cell, below the diagonal heads, below the
        # top heads — the vertical axis is unambiguous.
        assert par_y > max(bar_cell_ys)
        assert min(bar_cell_ys) > diagonal_y
        assert diagonal_y > top_y


class TestGroundAxisConvention:
    def test_should_expose_an_explicit_ground_end_of_the_normalized_range(
        self,
    ) -> None:
        # Given/When/Then: the ground is the larger end of [0, 1] — a
        # fixture on the floor must never render near the top of screen
        assert layout.GROUND_Y == 1.0
        assert layout.SKY_Y == 0.0

    def test_should_never_render_a_floor_standing_par_near_the_top_of_the_screen(
        self,
    ) -> None:
        # Given: the real venue's fixture composition
        fixtures = a_full_arc_fixture_list()

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: every ground-standing par sits in the ground half of the
        # normalized range
        pars = [e for e in result.entries if e.kind == "par"]
        assert pars
        for par in pars:
            assert par.y > 0.5


class TestGenerateLayoutArchEdgeCases:
    def test_should_lay_out_a_venue_with_no_bars_or_moving_heads(self) -> None:
        # Given: a venue patching only pars — no bars, no moving heads
        fixtures = [
            a_fixture_model(
                fixture_id=1, name="LPC008S #1", fixture_master_id=PAR_MASTER_ID
            ),
            a_fixture_model(
                fixture_id=2, name="LPC008S #2", fixture_master_id=PAR_MASTER_ID
            ),
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: no crash, both fixtures still get a valid position
        assert len(result.entries) == 2
        for entry in result.entries:
            assert 0.0 < entry.x < 1.0
            assert 0.0 < entry.y < 1.0

    def test_should_give_distinct_positions_to_two_fixtures_sharing_a_macro_slot(
        self,
    ) -> None:
        # Given: two physically distinct moving heads sharing one macro slot
        fixtures = [
            a_fixture_model(fixture_id=1, name="LM70S #1", macro_fixture_id=16),
            a_fixture_model(fixture_id=2, name="LM70S #2", macro_fixture_id=16),
        ]

        # When: generating the layout
        result = layout.generate_layout(venue_id=2, fixtures=fixtures)

        # Then: they still get distinct positions
        first = next(e for e in result.entries if e.fixture_id == 1)
        second = next(e for e in result.entries if e.fixture_id == 2)
        assert (first.x, first.y) != (second.x, second.y)


# ---------------------------------------------------------------------------
# Preserving user edits across regeneration (task requirement: "Preserving
# user edits") — extends the existing ensure_layout coverage with rotation.
# ---------------------------------------------------------------------------


class TestEnsureLayoutRotationPreservation:
    def test_should_preserve_user_adjusted_rotation_on_regenerate(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing layout where the user rotated fixture 1
        path = tmp_path / "layout_venue_2.json"
        existing = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.2,
                    y=0.3,
                    label="LM70S #1",
                    kind="moving_head",
                    rotation=123.0,
                ),
            ),
        )
        layout.save_layout(path, existing)
        fixtures = [a_fixture_model(fixture_id=1, name="LM70S #1")]

        # When: regenerating against the same fixture list
        result = layout.ensure_layout(path, venue_id=2, fixtures=fixtures)

        # Then: the user's adjusted rotation is untouched
        entry = next(e for e in result.layout.entries if e.fixture_id == 1)
        assert entry.rotation == pytest.approx(123.0)


class TestSaveLoadRoundTripWithRotation:
    def test_should_round_trip_rotation_alongside_position_label_and_kind(
        self, tmp_path: Path
    ) -> None:
        # Given: a layout with real, non-default rotations
        original = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.11,
                    y=0.22,
                    label="LM70S #1",
                    kind="moving_head",
                    rotation=45.0,
                ),
                LayoutEntry(
                    fixture_id=2,
                    x=0.88,
                    y=0.77,
                    label="LM70S #2",
                    kind="moving_head",
                    rotation=315.0,
                ),
            ),
        )
        path = tmp_path / "layout_venue_2.json"

        # When: saving then loading
        layout.save_layout(path, original)
        loaded = layout.load_layout(path)

        # Then: identical to the original, rotations included
        assert loaded == original


class TestLoadLayoutMissingRotationField:
    def test_should_default_rotation_to_zero_when_the_field_is_absent(
        self, tmp_path: Path
    ) -> None:
        # Given: a layout file written by the pre-rotation version of this
        # tool — no "rotation" key at all
        path = tmp_path / "layout_venue_2.json"
        legacy_payload = {
            "venue_id": 2,
            "entries": [
                {
                    "fixture_id": 1,
                    "x": 0.5,
                    "y": 0.5,
                    "label": "LM70S #1",
                    "kind": "moving_head",
                }
            ],
        }
        path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        # When: loading it
        loaded = layout.load_layout(path)

        # Then: rotation defaults to zero rather than failing
        assert loaded is not None
        assert loaded.entries[0].rotation == 0.0


# ---------------------------------------------------------------------------
# Atomic save (task requirement: "Saving is atomic")
# ---------------------------------------------------------------------------


class TestSaveLayoutAtomicity:
    def test_should_not_corrupt_an_existing_file_when_the_save_is_interrupted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a previously saved, valid layout file
        path = tmp_path / "layout_venue_2.json"
        original = RigLayout(
            venue_id=2,
            entries=(LayoutEntry(fixture_id=1, x=0.1, y=0.2, label="A", kind="par"),),
        )
        layout.save_layout(path, original)
        original_bytes = path.read_bytes()

        # simulate a crash during the atomic rename step of the next save
        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated crash during save")

        monkeypatch.setattr("os.replace", _boom)
        new_layout = RigLayout(
            venue_id=2,
            entries=(LayoutEntry(fixture_id=1, x=0.9, y=0.9, label="A", kind="par"),),
        )

        # When: saving is interrupted mid-write
        with pytest.raises(OSError):
            layout.save_layout(path, new_layout)

        # Then: the original file is completely untouched — no truncation,
        # no partial write
        assert path.read_bytes() == original_bytes

    def test_should_leave_no_file_at_the_target_path_when_the_first_save_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: no layout file exists yet
        path = tmp_path / "layout_venue_2.json"
        assert not path.exists()

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated crash during save")

        monkeypatch.setattr("os.replace", _boom)
        rig_layout = RigLayout(venue_id=2, entries=())

        # When: the very first save is interrupted before the atomic swap
        with pytest.raises(OSError):
            layout.save_layout(path, rig_layout)

        # Then: no truncated/corrupt file was left at the final path
        assert not path.exists()


# ---------------------------------------------------------------------------
# Pure layout-comparison helper (task requirement: "Pure layout-comparison
# helper") — the diff engine behind `rbxlight layout regenerate`'s dry-run
# report. No filesystem or database involvement; tested directly here,
# independent of the CLI.
# ---------------------------------------------------------------------------


class TestDiffLayouts:
    def test_should_report_no_differences_for_two_identical_layouts(self) -> None:
        # Given: two structurally identical layouts
        entries = (
            LayoutEntry(fixture_id=1, x=0.2, y=0.3, label="Head 1", kind="moving_head"),
            LayoutEntry(fixture_id=2, x=0.5, y=0.5, label="Par 1", kind="par"),
        )
        old = RigLayout(venue_id=2, entries=entries)
        new = RigLayout(venue_id=2, entries=entries)

        # When: diffing
        result = layout.diff_layouts(old, new)

        # Then: no differences at all
        assert result == ()

    def test_should_report_an_entry_that_moved(self) -> None:
        # Given: the same fixture at two different positions
        old = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1, x=0.2, y=0.3, label="Head 1", kind="moving_head"
                ),
            ),
        )
        new = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1, x=0.8, y=0.9, label="Head 1", kind="moving_head"
                ),
            ),
        )

        # When: diffing
        result = layout.diff_layouts(old, new)

        # Then: exactly one differing entry, identified by label, with both
        # old and new positions reported
        assert len(result) == 1
        entry = result[0]
        assert entry.fixture_id == 1
        assert entry.label == "Head 1"
        assert entry.old_x == 0.2
        assert entry.old_y == 0.3
        assert entry.new_x == 0.8
        assert entry.new_y == 0.9

    def test_should_report_an_entry_that_only_rotated(self) -> None:
        # Given: the same position, different rotation
        old = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.2,
                    y=0.3,
                    label="Head 1",
                    kind="moving_head",
                    rotation=0.0,
                ),
            ),
        )
        new = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1,
                    x=0.2,
                    y=0.3,
                    label="Head 1",
                    kind="moving_head",
                    rotation=45.0,
                ),
            ),
        )

        # When: diffing
        result = layout.diff_layouts(old, new)

        # Then: reported, with unchanged position and a differing rotation
        assert len(result) == 1
        entry = result[0]
        assert entry.old_x == entry.new_x == 0.2
        assert entry.old_y == entry.new_y == 0.3
        assert entry.old_rotation == 0.0
        assert entry.new_rotation == 45.0

    def test_should_report_an_entry_present_only_in_the_old_layout(self) -> None:
        # Given: a fixture that existed in the saved layout but not the fresh one
        old = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(
                    fixture_id=1, x=0.2, y=0.3, label="Removed Head", kind="moving_head"
                ),
            ),
        )
        new = RigLayout(venue_id=2, entries=())

        # When: diffing
        result = layout.diff_layouts(old, new)

        # Then: reported by label, with no "new" side
        assert len(result) == 1
        entry = result[0]
        assert entry.fixture_id == 1
        assert entry.label == "Removed Head"
        assert entry.new_x is None
        assert entry.new_y is None
        assert entry.new_rotation is None

    def test_should_report_an_entry_present_only_in_the_new_layout(self) -> None:
        # Given: a fixture that's newly patched, absent from the saved layout
        old = RigLayout(venue_id=2, entries=())
        new = RigLayout(
            venue_id=2,
            entries=(
                LayoutEntry(fixture_id=2, x=0.6, y=0.1, label="New Par", kind="par"),
            ),
        )

        # When: diffing
        result = layout.diff_layouts(old, new)

        # Then: reported by label, with no "old" side
        assert len(result) == 1
        entry = result[0]
        assert entry.fixture_id == 2
        assert entry.label == "New Par"
        assert entry.old_x is None
        assert entry.old_y is None
        assert entry.old_rotation is None

    def test_should_produce_the_same_ordered_result_regardless_of_entry_order(
        self,
    ) -> None:
        # Given: the same two logical layouts, but entries listed in
        # different orders within each
        moved_old = LayoutEntry(
            fixture_id=1, x=0.2, y=0.3, label="Head 1", kind="moving_head"
        )
        moved_new = LayoutEntry(
            fixture_id=1, x=0.9, y=0.9, label="Head 1", kind="moving_head"
        )
        unchanged = LayoutEntry(fixture_id=2, x=0.5, y=0.5, label="Par 1", kind="par")
        removed_only_old = LayoutEntry(
            fixture_id=3, x=0.1, y=0.1, label="Gone", kind="par"
        )

        old_forward = RigLayout(
            venue_id=2, entries=(moved_old, unchanged, removed_only_old)
        )
        old_shuffled = RigLayout(
            venue_id=2, entries=(removed_only_old, unchanged, moved_old)
        )
        new_forward = RigLayout(venue_id=2, entries=(moved_new, unchanged))
        new_shuffled = RigLayout(venue_id=2, entries=(unchanged, moved_new))

        # When: diffing both orderings
        result_forward = layout.diff_layouts(old_forward, new_forward)
        result_shuffled = layout.diff_layouts(old_shuffled, new_shuffled)

        # Then: identical ordered results regardless of input entry order
        assert result_forward == result_shuffled
        assert [e.fixture_id for e in result_forward] == [1, 3]
