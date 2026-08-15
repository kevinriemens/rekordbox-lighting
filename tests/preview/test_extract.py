"""Tests for rbxlight.preview.extract — decoding one macro_data.data XML
payload into the JSON-contract-shaped `program` dict. Contract: task
requirements ("Program extraction") + rekordbox-lightingdb-schema skill
(colour encoding, section support matrix).
"""

from __future__ import annotations

import pytest

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
from rbxlight.preview import extract
from rbxlight.preview.extract import EMPTY_PROGRAM
from tests.fixtures.colour_fixtures import REFERENCE_COLOURS, a_reference_colour
from tests.fixtures.xml_fixtures import all_golden_fixtures, golden_fixture_ids

#: Fixture types that support Brightness/Colour/Strobe only (Simple Par/Bar).
_RESTRICTED_TYPE_IDS: tuple[int, ...] = (101, 102)
#: A fixture type with the full section set (Moving Head).
_FULL_TYPE_ID: int = 3


def _movement_block(**overrides: object) -> MovementBlock:
    defaults = {
        "xleft": 0.0,
        "xright": 32.0,
        "pattern": "Circle",
        "width": 0.5,
        "height": 0.5,
        "offset_x": 0.5,
        "offset_y": 0.5,
        "round_angle": 0.0,
        "offset_angle": 0.0,
        "period_time": 20000.0,
        "frequency_x": 2.0,
        "frequency_y": 3.0,
        "phase_x": 90.0,
        "phase_y": 0.0,
        "type": "Loop",
        "direction": "Forward",
    }
    defaults.update(overrides)
    return MovementBlock(**defaults)


class TestEmptyPayload:
    def test_should_return_the_explicit_empty_program_for_an_empty_string(
        self,
    ) -> None:
        # Given: a slot with no programming at all
        # When: building its program
        program = extract.build_fixture_program("", fixture_type_id=1, beats=32.0)

        # Then: the explicit empty shape, not None and not a missing key
        assert program == EMPTY_PROGRAM
        assert program["brightness"] is None
        assert program["colour"] == []
        assert program["strobe"] == []
        assert program["position"] == []
        assert program["rotate"] == []
        assert program["gobo"] is None


class TestBrightnessBeatOrder:
    def test_should_preserve_points_in_ascending_beat_order(self) -> None:
        # Given: a model whose points are stored out of beat order
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0,
                xright=32.0,
                points=(
                    Point(x=32.0, y=0.0, type=3),
                    Point(x=0.0, y=1.0, type=1),
                    Point(x=16.0, y=0.5, type=2),
                ),
            ),
            colour=(),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=32.0)

        # Then: points come back sorted ascending by x
        xs = [p["x"] for p in program["brightness"]["points"]]
        assert xs == sorted(xs)


class TestColourDecoding:
    @pytest.mark.parametrize(
        "colour_name",
        list(REFERENCE_COLOURS.keys()),
        ids=list(REFERENCE_COLOURS.keys()),
    )
    def test_should_decode_signed_colour_into_argb_components(
        self, colour_name: str
    ) -> None:
        # Given: a colour block using a real reference signed int32 value
        signed_value, (a, r, g, b) = a_reference_colour(colour_name)
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(
                ColourBlock(
                    xleft=0.0,
                    colourleft=signed_value,
                    xright=32.0,
                    colourright=signed_value,
                ),
            ),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=32.0)

        # Then: the block's left/right colours are separate 0-255 components
        colour_block = program["colour"][0]
        assert colour_block["left"] == {"a": a, "r": r, "g": g, "b": b}
        assert colour_block["right"] == {"a": a, "r": r, "g": g, "b": b}
        for component in colour_block["left"].values():
            assert 0 <= component <= 255


class TestStrobeBlocks:
    def test_should_include_strobe_blocks_verbatim(self) -> None:
        # Given: a model with one strobe block
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(
                StrobeBlock(xleft=4.0, strobeleft=1.0, xright=8.0, stroberight=1.0),
            ),
        )
        xml = lightingxml.serialize(model)

        # When: building the program
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=32.0)

        # Then: the strobe block's beat window and values are present
        assert program["strobe"] == [
            {"xleft": 4.0, "xright": 8.0, "left": 1.0, "right": 1.0}
        ]


class TestMovementAndRotation:
    def test_should_include_position_blocks_for_a_supporting_fixture_type(
        self,
    ) -> None:
        # Given: a Moving Head model (t3, supports Position) with a movement block
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(),
            position=(_movement_block(),),
        )
        xml = lightingxml.serialize(model)

        # When: building the program for a Moving Head slot
        program = extract.build_fixture_program(
            xml, fixture_type_id=_FULL_TYPE_ID, beats=32.0
        )

        # Then: the movement block is present with the contract's field subset
        assert len(program["position"]) == 1
        block = program["position"][0]
        assert block["pattern"] == "Circle"
        assert block["type"] == "Loop"
        assert block["direction"] == "Forward"
        assert block["xleft"] == 0.0
        assert block["xright"] == 32.0

    def test_should_include_rotate_blocks_for_a_supporting_fixture_type(self) -> None:
        # Given: a Moving Head model with a rotate block
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(),
            rotate=(
                RotateBlock(xleft=0.0, rotateleft=0.0, xright=32.0, rotateright=1.0),
            ),
        )
        xml = lightingxml.serialize(model)

        # When: building the program
        program = extract.build_fixture_program(
            xml, fixture_type_id=_FULL_TYPE_ID, beats=32.0
        )

        # Then: the rotate block is present
        assert program["rotate"] == [
            {"xleft": 0.0, "xright": 32.0, "left": 0.0, "right": 1.0}
        ]

    @pytest.mark.parametrize("restricted_type_id", _RESTRICTED_TYPE_IDS)
    def test_should_never_surface_position_for_a_restricted_fixture_type(
        self, restricted_type_id: int
    ) -> None:
        # Given: a payload that (unusually) carries Position data
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(),
            position=(_movement_block(),),
        )
        xml = lightingxml.serialize(model)

        # When: building the program for a Simple Par/Bar slot (no pan/tilt hw)
        program = extract.build_fixture_program(
            xml, fixture_type_id=restricted_type_id, beats=32.0
        )

        # Then: position is forced empty regardless of what the payload has
        assert program["position"] == []

    @pytest.mark.parametrize("restricted_type_id", _RESTRICTED_TYPE_IDS)
    def test_should_never_surface_rotate_for_a_restricted_fixture_type(
        self, restricted_type_id: int
    ) -> None:
        # Given: a payload that (unusually) carries Rotate data
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(),
            rotate=(
                RotateBlock(xleft=0.0, rotateleft=0.0, xright=32.0, rotateright=1.0),
            ),
        )
        xml = lightingxml.serialize(model)

        # When: building the program for a Simple Par/Bar slot
        program = extract.build_fixture_program(
            xml, fixture_type_id=restricted_type_id, beats=32.0
        )

        # Then: rotate is forced empty
        assert program["rotate"] == []

    def test_should_always_set_gobo_to_none(self) -> None:
        # Given: any non-empty program, even for a gobo-capable type
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=32.0, points=(Point(0.0, 1.0, 1), Point(32.0, 1.0, 3))
            ),
            colour=(),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program for a gobo-capable Moving Head slot
        program = extract.build_fixture_program(
            xml, fixture_type_id=_FULL_TYPE_ID, beats=32.0
        )

        # Then: gobo is never extracted
        assert program["gobo"] is None


class TestBeatClamping:
    def test_should_clamp_block_xright_to_macro_beats(self) -> None:
        # Given: a colour block whose xright overshoots a 10-beat macro
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=10.0, points=(Point(0.0, 1.0, 1), Point(10.0, 1.0, 3))
            ),
            colour=(
                ColourBlock(xleft=0.0, colourleft=-1, xright=32.0, colourright=-1),
            ),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program with beats=10
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=10.0)

        # Then: xright never exceeds the macro's beat length
        assert program["colour"][0]["xright"] <= 10.0

    def test_should_clamp_point_x_to_macro_beats(self) -> None:
        # Given: a brightness point whose x overshoots a 10-beat macro
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0,
                xright=32.0,
                points=(Point(0.0, 1.0, 1), Point(32.0, 0.0, 3)),
            ),
            colour=(),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program with beats=10
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=10.0)

        # Then: no point's x exceeds 10
        assert all(p["x"] <= 10.0 for p in program["brightness"]["points"])

    def test_should_not_raise_zero_division_when_beats_is_zero(self) -> None:
        # Given: a macro with a beat length of zero
        model = LightingEditModel(
            brightness=PointBlock(
                xleft=0.0, xright=0.0, points=(Point(0.0, 0.0, 1), Point(0.0, 0.0, 3))
            ),
            colour=(),
            strobe=(),
        )
        xml = lightingxml.serialize(model)

        # When: building the program with beats=0
        program = extract.build_fixture_program(xml, fixture_type_id=1, beats=0.0)

        # Then: no crash, and nothing exceeds beat 0
        assert program["brightness"]["xright"] <= 0.0


class TestAgainstGoldenCorpus:
    """Broad, cheap coverage: every captured real payload is extracted
    without error, and non-empty sections match the manifest's record of
    which sections that payload actually populates.
    """

    @pytest.mark.parametrize("golden", all_golden_fixtures(), ids=golden_fixture_ids())
    def test_should_extract_without_error_and_match_populated_sections(
        self, golden
    ) -> None:
        # Given: a real captured payload for a known fixture type
        xml = golden.read()

        # When: building its program
        program = extract.build_fixture_program(
            xml, fixture_type_id=golden.fixture_type_id, beats=float(2**16)
        )

        # Then: brightness is always present (every real payload has it)
        assert program["brightness"] is not None
        # And: colour/strobe non-empty iff the manifest says that section
        # has content for this payload.
        assert bool(program["colour"]) == ("Colour" in golden.sections_with_content)
        assert bool(program["strobe"]) == ("Strobe" in golden.sections_with_content)
        # And: position/rotate only ever surface for a fixture type whose
        # capabilities include them — forced empty otherwise, matched to
        # the manifest when the type does support them.
        capabilities = FIXTURE_TYPE_CAPABILITIES.get(
            golden.fixture_type_id, frozenset()
        )
        if "position" not in capabilities:
            assert program["position"] == []
        else:
            assert bool(program["position"]) == (
                "Position" in golden.sections_with_content
            )
        if "rotate" not in capabilities:
            assert program["rotate"] == []
        else:
            assert bool(program["rotate"]) == ("Rotate" in golden.sections_with_content)
