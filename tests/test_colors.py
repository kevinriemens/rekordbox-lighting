"""Tests for rbxlight.colors — signed int32 ARGB <-> component conversion.

Contract: rekordbox-lightingdb-schema skill, "Colour encoding".
"""

from __future__ import annotations

import pytest

from rbxlight import colors
from tests.fixtures.colour_fixtures import (
    BOUNDARY_SIGNED_VALUES,
    REFERENCE_COLOURS,
    a_reference_colour,
)


class TestSignedToArgbToSigned:
    """Round trip: signed_to_argb(argb_to_signed(...)) == original components."""

    @pytest.mark.parametrize(
        "a,r,g,b",
        [
            (0xFF, 0xFF, 0x00, 0x00),
            (0xFF, 0x00, 0xFF, 0x00),
            (0xFF, 0x00, 0x00, 0xFF),
            (0x00, 0x00, 0x00, 0x00),
            (0xFF, 0xFF, 0xFF, 0xFF),
            (0x80, 0x01, 0x02, 0x03),
        ],
        ids=["red", "green", "blue", "all_zero", "all_max", "mixed_sign_boundary"],
    )
    def test_should_round_trip_components_when_converted_both_ways(
        self, a: int, r: int, g: int, b: int
    ) -> None:
        # Given: 4 8-bit ARGB components
        # When: packed to signed int32 and unpacked again
        signed = colors.argb_to_signed(a, r, g, b)
        result = colors.signed_to_argb(signed)

        # Then: the original components are recovered exactly
        assert result == (a, r, g, b)

    @pytest.mark.parametrize("value", BOUNDARY_SIGNED_VALUES)
    def test_should_round_trip_signed_value_when_negative_or_boundary(
        self, value: int
    ) -> None:
        # Given: a signed int32 value, including negative and sign-boundary cases
        # When: unpacked to components and repacked
        a, r, g, b = colors.signed_to_argb(value)
        result = colors.argb_to_signed(a, r, g, b)

        # Then: the original signed value is recovered exactly
        assert result == value

    def test_should_round_trip_when_value_is_negative(self) -> None:
        # Given: a typical negative stored colour (e.g. red, -65536)
        signed = -65536

        # When: unpacked then repacked
        a, r, g, b = colors.signed_to_argb(signed)
        result = colors.argb_to_signed(a, r, g, b)

        # Then: value round-trips exactly
        assert result == signed

    def test_should_round_trip_across_sign_boundary(self) -> None:
        # Given: the exact int32 sign boundary (0x80000000 unsigned)
        boundary_unsigned = 0x80000000
        signed = boundary_unsigned - 0x100000000  # -2147483648

        # When: unpacked then repacked
        a, r, g, b = colors.signed_to_argb(signed)
        result = colors.argb_to_signed(a, r, g, b)

        # Then: value round-trips exactly, still negative
        assert result == signed
        assert result < 0


class TestReferenceColours:
    """Known reference colours (rekordbox-lightingdb-schema skill table)."""

    @pytest.mark.parametrize(
        "name",
        list(REFERENCE_COLOURS.keys()),
    )
    def test_should_convert_signed_to_argb_for_known_reference_colour(
        self, name: str
    ) -> None:
        # Given: a documented reference colour
        signed, expected_argb = a_reference_colour(name)

        # When: converted from signed int32 to components
        result = colors.signed_to_argb(signed)

        # Then: matches the documented (a, r, g, b)
        assert result == expected_argb

    @pytest.mark.parametrize(
        "name",
        list(REFERENCE_COLOURS.keys()),
    )
    def test_should_convert_argb_to_signed_for_known_reference_colour(
        self, name: str
    ) -> None:
        # Given: a documented reference colour's components
        signed, (a, r, g, b) = a_reference_colour(name)

        # When: packed from components to signed int32
        result = colors.argb_to_signed(a, r, g, b)

        # Then: matches the documented signed int32 value
        assert result == signed
