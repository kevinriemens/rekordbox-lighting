"""Tests for rbxlight.lightingxml — LightingEditModel parse/serialize.

Contract: rekordbox-lightingdb-schema skill ("LightingEditModel XML") and
rekordbox-lighting-architecture skill ("lightingxml round-trip
requirement"). Golden corpus: tests/fixtures/golden/ (captured from the
live DB, never re-captured here).
"""

from __future__ import annotations

import pytest

from rbxlight import lightingxml
from rbxlight.lightingxml import SECTION_ORDER, InvalidLightingXMLError
from tests.fixtures.xml_fixtures import (
    GoldenFixture,
    a_malformed_xml_payload,
    a_non_xml_payload,
    a_truncated_xml_payload,
    all_golden_fixtures,
    an_empty_payload,
    golden_fixture_ids,
    top_level_section_names,
)


class TestGoldenCorpusRoundTrip:
    """parse(serialize(x)) reproduces an equivalent document for every
    captured golden payload — the project's most important invariant."""

    @pytest.mark.parametrize("golden", all_golden_fixtures(), ids=golden_fixture_ids())
    def test_should_round_trip_exactly_when_parsing_and_reserializing_golden_payload(
        self, golden: GoldenFixture
    ) -> None:
        # Given: a real captured LightingEditModel payload
        original_xml = golden.read()

        # When: parsed, serialized, and parsed again
        model = lightingxml.parse(original_xml)
        reserialized_xml = lightingxml.serialize(model)
        reparsed_model = lightingxml.parse(reserialized_xml)

        # Then: the model is unchanged by the round trip (same sections,
        # same order, same attributes, same values)
        assert reparsed_model == model

    @pytest.mark.parametrize("golden", all_golden_fixtures(), ids=golden_fixture_ids())
    def test_should_preserve_section_order_when_round_tripping_golden_payload(
        self, golden: GoldenFixture
    ) -> None:
        # Given: a real captured payload's original top-level section order
        original_xml = golden.read()
        original_order = top_level_section_names(original_xml)

        # When: round-tripped through parse -> serialize
        model = lightingxml.parse(original_xml)
        reserialized_xml = lightingxml.serialize(model)
        new_order = top_level_section_names(reserialized_xml)

        # Then: identical section set, identical order
        assert new_order == original_order

    @pytest.mark.parametrize("golden", all_golden_fixtures(), ids=golden_fixture_ids())
    def test_should_only_use_canonical_section_order_when_serializing_golden_payload(
        self, golden: GoldenFixture
    ) -> None:
        # Given: any real captured payload
        model = lightingxml.parse(golden.read())

        # When: serialized
        reserialized_xml = lightingxml.serialize(model)

        # Then: whatever sections are present appear in the fixed
        # Brightness, Colour, Strobe, Position, Rotate, Gobo order
        present = top_level_section_names(reserialized_xml)
        canonical_positions = [SECTION_ORDER.index(tag) for tag in present]
        assert canonical_positions == sorted(canonical_positions)


class TestSectionOrderConstant:
    def test_should_define_section_order_as_brightness_colour_strobe_position_rotate_gobo(
        self,
    ) -> None:
        # Given/When: the module's canonical section order
        # Then: matches the fixed order rekordbox requires
        assert SECTION_ORDER == (
            "Brightness",
            "Colour",
            "Strobe",
            "Position",
            "Rotate",
            "Gobo",
        )


class TestBrightnessCurveInvariant:
    """Every Brightness PointBlock has exactly one start (type=1) and one
    end (type=3) point, with zero or more interior (type=2) points between."""

    @pytest.mark.parametrize("golden", all_golden_fixtures(), ids=golden_fixture_ids())
    def test_should_have_exactly_one_start_and_one_end_point_when_brightness_is_programmed(
        self, golden: GoldenFixture
    ) -> None:
        # Given: a real captured payload
        model = lightingxml.parse(golden.read())

        # When: inspecting its brightness curve
        points = model.brightness.points

        # Then: exactly one start, one end, any number of interior points
        start_points = [p for p in points if p.type == 1]
        end_points = [p for p in points if p.type == 3]
        interior_points = [p for p in points if p.type == 2]

        assert len(start_points) == 1
        assert len(end_points) == 1
        assert len(interior_points) == len(points) - 2


class TestEmptyPayload:
    """A macro_data.data value of "" is legitimate: "this fixture does
    nothing in this macro" — 114 such rows exist in real data."""

    def test_should_parse_empty_payload_to_none(self) -> None:
        # Given: an empty payload string
        payload = an_empty_payload()

        # When: parsed
        result = lightingxml.parse(payload)

        # Then: represents "no programming", not an error
        assert result is None

    def test_should_serialize_none_back_to_empty_string(self) -> None:
        # Given: the "no programming" sentinel
        model = lightingxml.parse(an_empty_payload())

        # When: serialized
        result = lightingxml.serialize(model)

        # Then: round-trips as the empty string
        assert result == ""


class TestInvalidXml:
    """A payload that is not valid XML must be reported as invalid without
    crashing the caller. Synthetic input only — every non-empty payload in
    the real data parses successfully."""

    @pytest.mark.parametrize(
        "payload",
        [a_malformed_xml_payload(), a_non_xml_payload(), a_truncated_xml_payload()],
        ids=["unclosed_tag", "not_xml_at_all", "truncated_mid_attribute"],
    )
    def test_should_raise_invalid_lighting_xml_error_when_payload_is_not_valid_xml(
        self, payload: str
    ) -> None:
        # Given: a synthetic malformed payload
        # When / Then: parse reports it as invalid via a domain exception,
        # not an uncaught parser crash
        with pytest.raises(InvalidLightingXMLError):
            lightingxml.parse(payload)
