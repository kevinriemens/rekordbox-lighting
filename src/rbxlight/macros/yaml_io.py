"""macro <-> YAML export/import.

Document shape (human-editable, `ruamel.yaml` round-trip):

    name: HIGH DROP1
    beats: 32
    fixtures:
      1: ""                     # empty — fixture does nothing
      5: |
        <?xml version="1.0" encoding="UTF-8"?>
        <LightingEditModel ver="1.0">...</LightingEditModel>

`fixtures` is keyed by macro_fixture_id. A slot omitted entirely from the
document is treated identically to an explicit empty string on import.

Exported XML payloads are pretty-printed with 2-space indentation (matching
rekordbox's own style) for human readability.  On import, payloads are
canonicalized via ``lightingxml.parse`` + ``lightingxml.serialize`` so stored
bytes are always the tool's compact form regardless of how the YAML formatted
the XML.
"""

from __future__ import annotations

import io
import re
import sqlite3
import xml.etree.ElementTree as ET

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

from rbxlight import lightingxml
from rbxlight.macros import repo
from rbxlight.models import FIXTURE_SLOT_TYPES, FIXTURE_TYPE_CAPABILITIES, Macro

#: Round-trip dumper — preserves key order, uses block style for multi-line
#: XML payloads so the document stays human-editable.
_DUMPER = YAML()
_DUMPER.default_flow_style = False

#: Plain-value loader — a hand-edited document is ordinary YAML, no
#: round-trip metadata needed on the way back in.
_LOADER = YAML(typ="safe")

#: LightingEditModel section name -> FIXTURE_TYPE_CAPABILITIES key.
_MOVEMENT_SECTIONS: tuple[str, ...] = ("position", "rotate", "gobo")


class FixtureCapabilityError(ValueError):
    """Raised when a document programs a fixture slot with an XML section
    that slot's fixture_type_id does not support (see
    rbxlight.models.FIXTURE_TYPE_CAPABILITIES).
    """


def export_macro_yaml(conn: sqlite3.Connection, macro_id: int) -> str:
    """Render a macro's name, beats, and per-fixture-slot XML payloads as a
    YAML document string.

    Non-empty XML payloads are pretty-printed with 2-space indentation
    (rekordbox's own style).  Empty slots stay empty strings.  Corrupt
    (non-parseable) payloads pass through unchanged.  This path is
    read-only — the database is never written.
    """
    macro = repo.get_macro(conn, macro_id)
    rows = repo.list_macro_data(conn, macro_id)

    fixtures = {
        row.macro_fixture_id: _as_scalar(_pretty_print_xml(row.xml))
        for row in sorted(rows, key=lambda r: r.macro_fixture_id)
    }
    document = {"name": macro.name, "beats": macro.beats, "fixtures": fixtures}

    stream = io.StringIO()
    _DUMPER.dump(document, stream)
    return stream.getvalue()


def import_macro_yaml(conn: sqlite3.Connection, yaml_text: str) -> Macro:
    """Create a new macro from a YAML document produced by
    export_macro_yaml (or hand-edited in the same shape).

    Slots omitted from ``fixtures`` are stored as empty payloads.
    Non-empty payloads are canonicalized via ``lightingxml.parse`` +
    ``lightingxml.serialize`` so stored bytes are always the tool's compact
    form regardless of how the YAML formatted the XML.

    Raises FixtureCapabilityError if any fixture's payload uses a section its
    fixture_type_id doesn't support, before any row is written.
    """
    document = _LOADER.load(yaml_text) or {}
    name = document["name"]
    beats = document["beats"]
    raw_fixtures = document.get("fixtures") or {}
    payloads = {int(slot_id): xml for slot_id, xml in raw_fixtures.items()}

    for slot_id, xml in payloads.items():
        _validate_capability(slot_id, xml)

    canonicalized = {
        slot_id: _canonicalize_payload(xml) for slot_id, xml in payloads.items()
    }
    return repo.create_macro(conn, name=name, beats=beats, payloads=canonicalized)


def _as_scalar(xml: str) -> str:
    if xml == "" or "\n" not in xml:
        return xml
    return LiteralScalarString(xml)


_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


def _pretty_print_xml(xml: str) -> str:
    """Pretty-print a LightingEditModel payload with 2-space indentation.

    Returns the original string unchanged if it is empty or fails to parse
    as XML, so export never raises on corrupt slot data.
    """
    if xml == "":
        return xml
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return xml
    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode")
    # ElementTree emits self-closing tags as `` />``; rekordbox's own style
    # uses ``/>`` (no space).  Strip the space for consistency.
    body = re.sub(r" />", "/>", body)
    return f"{_XML_DECLARATION}\n{body}"


def _canonicalize_payload(xml: str) -> str:
    """Canonicalize a payload to the tool's compact form via parse + serialize.

    Empty strings pass through unchanged.
    """
    if xml == "":
        return xml
    model = lightingxml.parse(xml)
    return lightingxml.serialize(model)


def _validate_capability(slot_id: int, xml: str) -> None:
    if xml == "":
        return
    fixture_type_id = FIXTURE_SLOT_TYPES.get(slot_id)
    if fixture_type_id is None:
        return
    capabilities = FIXTURE_TYPE_CAPABILITIES.get(fixture_type_id, frozenset())

    model = lightingxml.parse(xml)
    if model is None:
        return

    used_sections = {
        "position": model.position is not None,
        "rotate": model.rotate is not None,
        "gobo": model.gobo_present is not None,
    }
    for section in _MOVEMENT_SECTIONS:
        if used_sections[section] and section not in capabilities:
            raise FixtureCapabilityError(
                f"fixture slot {slot_id} (fixture_type_id={fixture_type_id}) does not "
                f"support {section!r} programming"
            )
