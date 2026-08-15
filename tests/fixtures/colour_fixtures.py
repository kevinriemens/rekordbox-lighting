"""Reference colour values for rbxlight.colors round-trip tests.

Source: rekordbox-lightingdb-schema skill, "Colour encoding" — signed int32
ARGB (two's-complement, alpha implicitly 0xFF), values observed in the
live library.
"""

from __future__ import annotations

#: name -> (signed_int32, (a, r, g, b))
REFERENCE_COLOURS: dict[str, tuple[int, tuple[int, int, int, int]]] = {
    "red": (-65536, (0xFF, 0xFF, 0x00, 0x00)),
    "green": (-16711936, (0xFF, 0x00, 0xFF, 0x00)),
    "blue": (-16776961, (0xFF, 0x00, 0x00, 0xFF)),
    "magenta": (-65281, (0xFF, 0xFF, 0x00, 0xFF)),
    "yellow": (-256, (0xFF, 0xFF, 0xFF, 0x00)),
    "orange": (-32768, (0xFF, 0xFF, 0x80, 0x00)),
    "white": (-1, (0xFF, 0xFF, 0xFF, 0xFF)),
    "black": (-16777216, (0xFF, 0x00, 0x00, 0x00)),
}


def a_reference_colour(name: str) -> tuple[int, tuple[int, int, int, int]]:
    """Factory: (signed_int32, (a, r, g, b)) for a named reference colour."""
    return REFERENCE_COLOURS[name]


#: Boundary/edge signed int32 values worth round-tripping explicitly.
BOUNDARY_SIGNED_VALUES: tuple[int, ...] = (
    0,  # #00000000 — a=0 (never produced by argb_to_signed with a=0xFF, but a valid int32)
    -1,  # all bits set
    -2147483648,  # int32 min
    2147483647,  # int32 max
    -128,
    127,
    -0x80000000,  # sign boundary exact
)
