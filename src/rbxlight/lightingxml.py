"""LightingEditModel XML parse/serialize. Round-trip exactness is the
project's most important invariant — see rekordbox-lightingdb-schema skill.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from rbxlight.models import (
    ColourBlock,
    LightingEditModel,
    MovementBlock,
    Point,
    PointBlock,
    RotateBlock,
    StrobeBlock,
)

#: Fixed, non-negotiable section emission order.
SECTION_ORDER: tuple[str, ...] = (
    "Brightness",
    "Colour",
    "Strobe",
    "Position",
    "Rotate",
    "Gobo",
)


class InvalidLightingXMLError(ValueError):
    """Raised by parse() when given a payload that is not valid XML."""


def parse(payload: str) -> LightingEditModel | None:
    """Parse a macro_data.data payload string.

    Returns None for the empty-string payload ("this fixture does nothing
    in this macro"). Raises InvalidLightingXMLError for a non-empty string
    that is not valid XML. Never raises for any real captured payload.
    """
    if payload == "":
        return None

    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise InvalidLightingXMLError(str(exc)) from exc

    brightness = _parse_brightness(root)
    colour = _parse_colour(root)
    strobe = _parse_strobe(root)
    position = _parse_position(root)
    rotate = _parse_rotate(root)
    gobo_present = False if root.find("Gobo") is not None else None

    return LightingEditModel(
        brightness=brightness,
        colour=colour,
        strobe=strobe,
        position=position,
        rotate=rotate,
        gobo_present=gobo_present,
    )


def serialize(model: LightingEditModel | None) -> str:
    """Serialize a model back to a LightingEditModel XML string.

    serialize(None) == "" (empty payload round-trips as empty).
    Section order is always Brightness, Colour, Strobe, Position, Rotate,
    Gobo; a section that was absent from the parsed source stays absent,
    a section parsed as present-but-empty stays present as an empty tag.
    """
    if model is None:
        return ""

    root = ET.Element("LightingEditModel", {"ver": "1.0"})

    brightness_el = ET.SubElement(root, "Brightness")
    pb = model.brightness
    pb_el = ET.SubElement(
        brightness_el,
        "PointBlock",
        {"xleft": _fmt(pb.xleft), "xright": _fmt(pb.xright)},
    )
    for point in pb.points:
        ET.SubElement(
            pb_el,
            "Point",
            {"x": _fmt(point.x), "y": _fmt(point.y), "type": str(point.type)},
        )

    colour_el = ET.SubElement(root, "Colour")
    for colour_block in model.colour:
        ET.SubElement(
            colour_el,
            "ColourBlock",
            {
                "xleft": _fmt(colour_block.xleft),
                "colourleft": str(colour_block.colourleft),
                "xright": _fmt(colour_block.xright),
                "colourright": str(colour_block.colourright),
            },
        )

    strobe_el = ET.SubElement(root, "Strobe")
    for strobe_block in model.strobe:
        ET.SubElement(
            strobe_el,
            "StrobeBlock",
            {
                "xleft": _fmt(strobe_block.xleft),
                "strobeleft": _fmt(strobe_block.strobeleft),
                "xright": _fmt(strobe_block.xright),
                "stroberight": _fmt(strobe_block.stroberight),
            },
        )

    if model.position is not None:
        position_el = ET.SubElement(root, "Position")
        for movement_block in model.position:
            ET.SubElement(position_el, "MovementBlock", _movement_attrs(movement_block))

    if model.rotate is not None:
        rotate_el = ET.SubElement(root, "Rotate")
        for rotate_block in model.rotate:
            ET.SubElement(
                rotate_el,
                "RotateBlock",
                {
                    "xleft": _fmt(rotate_block.xleft),
                    "rotateleft": _fmt(rotate_block.rotateleft),
                    "xright": _fmt(rotate_block.xright),
                    "rotateright": _fmt(rotate_block.rotateright),
                },
            )

    if model.gobo_present is not None:
        ET.SubElement(root, "Gobo")

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )


def _fmt(value: float) -> str:
    """Format a float so it re-parses to the exact same value."""
    return repr(value)


def _movement_attrs(block: MovementBlock) -> dict[str, str]:
    attrs = {
        "xleft": _fmt(block.xleft),
        "xright": _fmt(block.xright),
        "pattern": block.pattern,
        "width": _fmt(block.width),
        "height": _fmt(block.height),
        "offset_x": _fmt(block.offset_x),
        "offset_y": _fmt(block.offset_y),
        "round_angle": _fmt(block.round_angle),
        "offset_angle": _fmt(block.offset_angle),
    }
    if block.start_angle is not None:
        attrs["start_angle"] = _fmt(block.start_angle)
    attrs.update(
        {
            "period_time": _fmt(block.period_time),
            "frequency_x": _fmt(block.frequency_x),
            "frequency_y": _fmt(block.frequency_y),
            "phase_x": _fmt(block.phase_x),
            "phase_y": _fmt(block.phase_y),
            "type": block.type,
            "direction": block.direction,
        }
    )
    if block.relative is not None:
        attrs["relative"] = _fmt(block.relative)
    return attrs


def _parse_brightness(root: ET.Element) -> PointBlock:
    brightness_el = root.find("Brightness")
    if brightness_el is None:
        raise InvalidLightingXMLError("missing required <Brightness> section")
    pb_el = brightness_el.find("PointBlock")
    if pb_el is None:
        raise InvalidLightingXMLError("<Brightness> missing required <PointBlock>")
    points = tuple(
        Point(
            x=float(p.attrib["x"]), y=float(p.attrib["y"]), type=int(p.attrib["type"])
        )
        for p in pb_el.findall("Point")
    )
    return PointBlock(
        xleft=float(pb_el.attrib["xleft"]),
        xright=float(pb_el.attrib["xright"]),
        points=points,
    )


def _parse_colour(root: ET.Element) -> tuple[ColourBlock, ...]:
    colour_el = root.find("Colour")
    if colour_el is None:
        raise InvalidLightingXMLError("missing required <Colour> section")
    return tuple(
        ColourBlock(
            xleft=float(cb.attrib["xleft"]),
            colourleft=int(cb.attrib["colourleft"]),
            xright=float(cb.attrib["xright"]),
            colourright=int(cb.attrib["colourright"]),
        )
        for cb in colour_el.findall("ColourBlock")
    )


def _parse_strobe(root: ET.Element) -> tuple[StrobeBlock, ...]:
    strobe_el = root.find("Strobe")
    if strobe_el is None:
        raise InvalidLightingXMLError("missing required <Strobe> section")
    return tuple(
        StrobeBlock(
            xleft=float(sb.attrib["xleft"]),
            strobeleft=float(sb.attrib["strobeleft"]),
            xright=float(sb.attrib["xright"]),
            stroberight=float(sb.attrib["stroberight"]),
        )
        for sb in strobe_el.findall("StrobeBlock")
    )


def _parse_position(root: ET.Element) -> tuple[MovementBlock, ...] | None:
    position_el = root.find("Position")
    if position_el is None:
        return None
    return tuple(
        MovementBlock(
            xleft=float(mb.attrib["xleft"]),
            xright=float(mb.attrib["xright"]),
            pattern=mb.attrib["pattern"],
            width=float(mb.attrib["width"]),
            height=float(mb.attrib["height"]),
            offset_x=float(mb.attrib["offset_x"]),
            offset_y=float(mb.attrib["offset_y"]),
            round_angle=float(mb.attrib["round_angle"]),
            offset_angle=float(mb.attrib["offset_angle"]),
            period_time=float(mb.attrib["period_time"]),
            frequency_x=float(mb.attrib["frequency_x"]),
            frequency_y=float(mb.attrib["frequency_y"]),
            phase_x=float(mb.attrib["phase_x"]),
            phase_y=float(mb.attrib["phase_y"]),
            type=mb.attrib["type"],
            direction=mb.attrib["direction"],
            start_angle=_opt_float(mb.get("start_angle")),
            relative=_opt_float(mb.get("relative")),
        )
        for mb in position_el.findall("MovementBlock")
    )


def _parse_rotate(root: ET.Element) -> tuple[RotateBlock, ...] | None:
    rotate_el = root.find("Rotate")
    if rotate_el is None:
        return None
    return tuple(
        RotateBlock(
            xleft=float(rb.attrib["xleft"]),
            rotateleft=float(rb.attrib["rotateleft"]),
            xright=float(rb.attrib["xright"]),
            rotateright=float(rb.attrib["rotateright"]),
        )
        for rb in rotate_el.findall("RotateBlock")
    )


def _opt_float(value: str | None) -> float | None:
    return float(value) if value is not None else None
