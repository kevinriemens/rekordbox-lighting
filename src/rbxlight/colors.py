"""Signed int32 ARGB <-> component conversion.

Colours in `LightingEditModel` XML are signed int32, Java style
(two's-complement, alpha implicitly 0xFF). See rekordbox-lightingdb-schema
skill, "Colour encoding".
"""

from __future__ import annotations


def argb_to_signed(a: int, r: int, g: int, b: int) -> int:
    """Pack 4 8-bit channels into a signed (two's-complement) int32."""
    val = (a << 24) | (r << 16) | (g << 8) | b
    return val - 0x100000000 if val >= 0x80000000 else val


def signed_to_argb(value: int) -> tuple[int, int, int, int]:
    """Unpack a signed int32 into (a, r, g, b) 8-bit channels."""
    unsigned = value & 0xFFFFFFFF
    a = (unsigned >> 24) & 0xFF
    r = (unsigned >> 16) & 0xFF
    g = (unsigned >> 8) & 0xFF
    b = unsigned & 0xFF
    return (a, r, g, b)
