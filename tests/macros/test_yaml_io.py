"""Tests for rbxlight.macros.yaml_io — macro <-> YAML export/import.

Contract: task requirements ("YAML export/import") + rekordbox-lightingdb-
schema skill (fixture-type capability matrix).

TDD: these tests define the expected pretty-print / canonicalize behaviour.
They MUST FAIL against the current implementation (which stores compact XML
verbatim in YAML and does not normalize on import).
"""

from __future__ import annotations

import sqlite3

import pytest
import yaml as pyyaml

from rbxlight import lightingxml
from rbxlight.macros import repo, yaml_io
from rbxlight.macros.yaml_io import FixtureCapabilityError
from tests.fixtures.macro_fixtures import ALL_25_SLOT_IDS, a_valid_slot_payload

# ---------------------------------------------------------------------------
# Compact payloads: single-line XML (the format the DB stores).  These are
# what the export must pretty-print from, and what the import must
# canonicalize to.
# ---------------------------------------------------------------------------

# Full payload for Moving Head slots (11-14, fixture_type_id=3) which
# support ALL sections including Gobo.
_COMPACT_PAYLOAD = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<LightingEditModel ver="1.0">'
    "<Brightness>"
    '<PointBlock xleft="0.0" xright="32.0">'
    '<Point x="0.0" y="0.0" type="1"/>'
    '<Point x="3.98" y="1.0" type="2"/>'
    '<Point x="32.0" y="1.0" type="3"/>'
    "</PointBlock>"
    "</Brightness>"
    "<Colour/>"
    "<Strobe/>"
    "<Position>"
    '<MovementBlock xleft="0.0" xright="32.0" pattern="Circle" width="0.5" '
    'height="0.5" offset_x="0.5" offset_y="0.5" round_angle="0.0" '
    'offset_angle="0.0" start_angle="0.0" period_time="20000.0" '
    'frequency_x="2.0" frequency_y="3.0" phase_x="90.0" phase_y="0.0" '
    'type="Loop" direction="Forward" relative="0.0"/>'
    "</Position>"
    "<Rotate/>"
    "<Gobo/>"
    "</LightingEditModel>"
)

# The same payload pretty-printed with 2-space indentation (what export
# should produce).  The XML declaration is the first line, then each
# nesting level adds 2 spaces.
_INDENTED_PAYLOAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<LightingEditModel ver="1.0">\n'
    "  <Brightness>\n"
    '    <PointBlock xleft="0.0" xright="32.0">\n'
    '      <Point x="0.0" y="0.0" type="1"/>\n'
    '      <Point x="3.98" y="1.0" type="2"/>\n'
    '      <Point x="32.0" y="1.0" type="3"/>\n'
    "    </PointBlock>\n"
    "  </Brightness>\n"
    "  <Colour/>\n"
    "  <Strobe/>\n"
    "  <Position>\n"
    '    <MovementBlock xleft="0.0" xright="32.0" pattern="Circle" '
    'width="0.5" height="0.5" offset_x="0.5" offset_y="0.5" '
    'round_angle="0.0" offset_angle="0.0" start_angle="0.0" '
    'period_time="20000.0" frequency_x="2.0" frequency_y="3.0" '
    'phase_x="90.0" phase_y="0.0" type="Loop" direction="Forward" '
    'relative="0.0"/>\n'
    "  </Position>\n"
    "  <Rotate/>\n"
    "  <Gobo/>\n"
    "</LightingEditModel>"
)

# Compact payload WITHOUT Gobo — suitable for Par/Bar/Strobe/Effect/Laser
# slots (fixture_type_id 1,2,4,5,8,9) which do NOT support Gobo.
_COMPACT_PAYLOAD_NO_GOBO = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<LightingEditModel ver="1.0">'
    "<Brightness>"
    '<PointBlock xleft="0.0" xright="32.0">'
    '<Point x="0.0" y="0.0" type="1"/>'
    '<Point x="3.98" y="1.0" type="2"/>'
    '<Point x="32.0" y="1.0" type="3"/>'
    "</PointBlock>"
    "</Brightness>"
    "<Colour/>"
    "<Strobe/>"
    "<Position>"
    '<MovementBlock xleft="0.0" xright="32.0" pattern="Circle" width="0.5" '
    'height="0.5" offset_x="0.5" offset_y="0.5" round_angle="0.0" '
    'offset_angle="0.0" start_angle="0.0" period_time="20000.0" '
    'frequency_x="2.0" frequency_y="3.0" phase_x="90.0" phase_y="0.0" '
    'type="Loop" direction="Forward" relative="0.0"/>'
    "</Position>"
    "<Rotate/>"
    "</LightingEditModel>"
)

# Pretty-printed version of _COMPACT_PAYLOAD_NO_GOBO (for export tests
# using slot 1).
_INDENTED_PAYLOAD_NO_GOBO = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<LightingEditModel ver="1.0">\n'
    "  <Brightness>\n"
    '    <PointBlock xleft="0.0" xright="32.0">\n'
    '      <Point x="0.0" y="0.0" type="1"/>\n'
    '      <Point x="3.98" y="1.0" type="2"/>\n'
    '      <Point x="32.0" y="1.0" type="3"/>\n'
    "    </PointBlock>\n"
    "  </Brightness>\n"
    "  <Colour/>\n"
    "  <Strobe/>\n"
    "  <Position>\n"
    '    <MovementBlock xleft="0.0" xright="32.0" pattern="Circle" '
    'width="0.5" height="0.5" offset_x="0.5" offset_y="0.5" '
    'round_angle="0.0" offset_angle="0.0" start_angle="0.0" '
    'period_time="20000.0" frequency_x="2.0" frequency_y="3.0" '
    'phase_x="90.0" phase_y="0.0" type="Loop" direction="Forward" '
    'relative="0.0"/>\n'
    "  </Position>\n"
    "  <Rotate/>\n"
    "</LightingEditModel>"
)

#: A payload using a section slot 101 (fixture_type_id=101, Simple Par)
#: does NOT support — Simple Par/Bar slots have no pan/tilt hardware.
_UNSUPPORTED_POSITION_PAYLOAD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<LightingEditModel ver="1.0">\n'
    "  <Brightness>\n"
    '    <PointBlock xleft="0" xright="32">\n'
    '      <Point x="0" y="0" type="1"/>\n'
    '      <Point x="32" y="0" type="3"/>\n'
    "    </PointBlock>\n"
    "  </Brightness>\n"
    "  <Colour/>\n"
    "  <Strobe/>\n"
    "  <Position>\n"
    '    <MovementBlock xleft="0" xright="32" pattern="Circle" width="0.5" height="0.5" '
    'offset_x="0.5" offset_y="0.5" round_angle="0" offset_angle="0" period_time="20000" '
    'frequency_x="2" frequency_y="3" phase_x="90" phase_y="0" type="Loop" direction="Forward"/>\n'
    "  </Position>\n"
    "</LightingEditModel>"
)

#: Corrupt (non-XML) string — must pass through export unchanged, never crash.
_CORRUPT_PAYLOAD = "<<<NOT XML>>>"

#: Moving Head slot id (fixture_type_id=3, supports all sections including Gobo).
_SLOT_MOVING_HEAD = 11

#: Par Light slot id (fixture_type_id=1, no Gobo support).
_SLOT_PAR = 1


class TestExportMacroYaml:
    """Export: macro -> YAML document with 2-space-indented XML payloads."""

    def test_should_capture_name_beats_and_fixture_programming(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """UPDATED existing test: after the pretty-print feature, the exported
        fixture payload is 2-space-indented (not compact).  The assertion now
        checks that the exported payload is the indented equivalent of the
        compact stored bytes — i.e. it parses to the same model."""
        # Given: a macro with one programmed slot (compact stored bytes)
        macro = repo.create_macro(
            macro_db_conn,
            name="HIGH DROP1",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported to YAML
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: name, beats, and per-fixture programming are all present,
        # and the payload is the 2-space-indented equivalent
        assert parsed["name"] == "HIGH DROP1"
        assert parsed["beats"] == 32
        exported_xml = parsed["fixtures"][_SLOT_MOVING_HEAD]
        # The exported payload must parse to the same model as the compact original
        model_from_exported = lightingxml.parse(exported_xml)
        model_from_compact = lightingxml.parse(_COMPACT_PAYLOAD)
        assert model_from_exported == model_from_compact
        # The exported payload is pretty-printed (multi-line), not compact
        assert "\n" in exported_xml

    def test_should_pretty_print_fixture_payloads_with_two_space_indent(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 1: each fixture-slot XML payload in the exported YAML
        is pretty-printed with 2-space indentation, matching Pioneer
        rekordbox's own XML output style, instead of a compact single line."""
        # Given: a macro whose slot payload is compact single-line XML
        macro = repo.create_macro(
            macro_db_conn,
            name="INDENT TEST",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported to YAML
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: the payload is pretty-printed with 2-space indentation
        exported_xml = parsed["fixtures"][_SLOT_MOVING_HEAD]
        lines = exported_xml.split("\n")
        # First line is the XML declaration
        assert lines[0] == '<?xml version="1.0" encoding="UTF-8"?>'
        # Second line is the root element (no indent)
        assert lines[1] == '<LightingEditModel ver="1.0">'
        # Child elements are indented 2 spaces
        assert lines[2] == "  <Brightness>"
        # Deeper nesting adds 2 more spaces
        assert lines[3] == '    <PointBlock xleft="0.0" xright="32.0">'
        assert lines[4] == '      <Point x="0.0" y="0.0" type="1"/>'

    def test_should_preserve_xml_declaration_as_first_line(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 2: the XML declaration line survives intact as the
        first line of each indented payload."""
        # Given: a macro with a payload that has an XML declaration
        macro = repo.create_macro(
            macro_db_conn,
            name="DECL TEST",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: the exported payload starts with the XML declaration
        exported_xml = parsed["fixtures"][_SLOT_MOVING_HEAD]
        assert exported_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_should_keep_empty_slots_as_empty_strings(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 3: empty fixture slots remain empty strings in the
        export — they must NOT become an indented empty document."""
        # Given: a macro with only slot 11 programmed (all others empty)
        macro = repo.create_macro(
            macro_db_conn,
            name="EMPTY SLOTS",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: slot 11 has the pretty-printed payload, all others are ""
        assert parsed["fixtures"][_SLOT_MOVING_HEAD] != ""
        for slot_id in ALL_25_SLOT_IDS:
            if slot_id == _SLOT_MOVING_HEAD:
                continue
            assert parsed["fixtures"][slot_id] == ""

    def test_should_pass_through_corrupt_xml_without_crashing(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 4: a payload that fails to parse as XML is emitted
        into the YAML unchanged (raw string) rather than raising; the
        export completes successfully despite the corrupt slot."""
        # Given: a macro with a corrupt (non-XML) payload in slot 11
        macro = repo.create_macro(
            macro_db_conn,
            name="CORRUPT SLOT",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _CORRUPT_PAYLOAD},
        )

        # When: exported — must NOT raise
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: the corrupt payload passes through unchanged (not indented)
        assert parsed["fixtures"][_SLOT_MOVING_HEAD] == _CORRUPT_PAYLOAD

    def test_should_export_valid_yaml_parseable_by_standard_parser(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 5: the exported document is valid YAML parseable by
        a standard parser; extracting any indented payload from it and
        parsing that XML yields a model equal to parsing the original
        compact payload (indentation is lossless)."""
        # Given: a macro with a compact payload
        macro = repo.create_macro(
            macro_db_conn,
            name="ROUNDTRIP TEST",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported and parsed as YAML
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: the YAML is valid and the parsed XML yields the same model
        exported_xml = parsed["fixtures"][_SLOT_MOVING_HEAD]
        model_from_compact = lightingxml.parse(_COMPACT_PAYLOAD)
        model_from_exported = lightingxml.parse(exported_xml)
        assert model_from_exported == model_from_compact

    def test_should_not_modify_database_on_export(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 6: export remains read-only with respect to the
        database — stored bytes must be unchanged after export."""
        # Given: a macro with a compact payload
        macro = repo.create_macro(
            macro_db_conn,
            name="READONLY TEST",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported
        yaml_io.export_macro_yaml(macro_db_conn, macro.id)

        # Then: the stored payload is still the original compact form
        rows = repo.list_macro_data(macro_db_conn, macro.id)
        slot_data = next(r for r in rows if r.macro_fixture_id == _SLOT_MOVING_HEAD)
        assert slot_data.xml == _COMPACT_PAYLOAD

    def test_should_pretty_print_multi_section_payload_at_every_depth(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Edge case: payload with declaration + multiple nested sections
        (Brightness, Colour, Strobe, Position, Rotate, Gobo) indents
        correctly at every depth."""
        # Given: a macro with a payload containing all sections
        macro = repo.create_macro(
            macro_db_conn,
            name="ALL SECTIONS",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: each nesting level is indented by exactly 2 spaces
        exported_xml = parsed["fixtures"][_SLOT_MOVING_HEAD]
        lines = exported_xml.split("\n")
        # Verify indentation increments at each nesting level
        assert lines[0] == '<?xml version="1.0" encoding="UTF-8"?>'
        assert lines[1] == '<LightingEditModel ver="1.0">'  # 0 indent
        assert lines[2] == "  <Brightness>"  # 2 indent
        assert lines[3] == '    <PointBlock xleft="0.0" xright="32.0">'  # 4 indent
        assert lines[4] == '      <Point x="0.0" y="0.0" type="1"/>'  # 6 indent
        assert lines[5] == '      <Point x="3.98" y="1.0" type="2"/>'  # 6 indent
        assert lines[6] == '      <Point x="32.0" y="1.0" type="3"/>'  # 6 indent
        assert lines[7] == "    </PointBlock>"  # 4 indent
        assert lines[8] == "  </Brightness>"  # 2 indent
        assert lines[9] == "  <Colour/>"  # 2 indent
        assert lines[10] == "  <Strobe/>"  # 2 indent
        assert lines[11] == "  <Position>"  # 2 indent
        assert lines[12].startswith("    <MovementBlock")  # 4 indent
        assert lines[13] == "  </Position>"  # 2 indent
        assert lines[14] == "  <Rotate/>"  # 2 indent
        assert lines[15] == "  <Gobo/>"  # 2 indent
        assert lines[16] == "</LightingEditModel>"  # 0 indent

    def test_should_pretty_print_payload_without_gobo_on_par_slot(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Edge case: Par Light slot (no Gobo) still gets proper
        2-space indentation for the sections it does have."""
        # Given: a macro with a no-Gobo payload in slot 1 (Par Light)
        macro = repo.create_macro(
            macro_db_conn,
            name="PAR INDENT",
            beats=32,
            payloads={_SLOT_PAR: _COMPACT_PAYLOAD_NO_GOBO},
        )

        # When: exported
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: the payload is pretty-printed with correct indentation
        exported_xml = parsed["fixtures"][_SLOT_PAR]
        lines = exported_xml.split("\n")
        assert lines[0] == '<?xml version="1.0" encoding="UTF-8"?>'
        assert lines[2] == "  <Brightness>"
        # No Gobo line present
        assert not any("<Gobo" in line for line in lines)


class TestImportMacroYaml:
    """Import: YAML document -> macro with compact canonical stored bytes."""

    def test_should_store_compact_canonical_bytes_from_indented_yaml(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 7: importing a YAML document whose payloads are
        2-space-indented stores COMPACT canonical bytes — identical to
        what the tool's own serializer produces for the same model.
        Storage must be insensitive to how the YAML formatted the XML."""
        # Given: a YAML document with indented XML payloads on a Moving Head
        # slot (which supports all sections including Gobo)
        document = pyyaml.safe_dump(
            {
                "name": "INDENTED IMPORT",
                "beats": 32,
                "fixtures": {_SLOT_MOVING_HEAD: _INDENTED_PAYLOAD},
            }
        )

        # When: imported
        macro = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: the stored payload is the compact canonical form
        rows = repo.list_macro_data(macro_db_conn, macro.id)
        slot_data = next(r for r in rows if r.macro_fixture_id == _SLOT_MOVING_HEAD)
        model_from_stored = lightingxml.parse(slot_data.xml)
        model_from_compact = lightingxml.parse(_COMPACT_PAYLOAD)
        assert model_from_stored == model_from_compact
        # The stored bytes should be compact (no leading whitespace per line)
        assert "\n  " not in slot_data.xml

    def test_should_fill_omitted_fixtures_with_empty_payload(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 8 (part 1): omitted/empty fixtures fill all 25 slots
        with empty strings (never NULL)."""
        # Given: a hand-written document that only programs one fixture
        document = 'name: PARTIAL IMPORT\nbeats: 32\nfixtures:\n  1: ""\n'

        # When: imported
        macro = yaml_io.import_macro_yaml(macro_db_conn, document)
        rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, macro.id)
        }

        # Then: the macro is complete (25 rows) with every omitted slot empty
        assert len(rows) == 25
        for slot_id in ALL_25_SLOT_IDS:
            if slot_id == 1:
                continue
            assert rows[slot_id] == ""

    def test_should_reject_document_programming_unsupported_capability_for_fixture_type(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Requirement 8 (part 2): documents programming a section unsupported
        by the fixture's type are rejected before anything is written."""
        # Given: a document assigning Position programming to slot 101
        # (fixture_type_id 101 = Par Light (Simple) — no pan/tilt hardware)
        document = pyyaml.safe_dump(
            {
                "name": "INVALID IMPORT",
                "beats": 32,
                "fixtures": {101: _UNSUPPORTED_POSITION_PAYLOAD},
            }
        )

        # When / Then: import is rejected, and rejects before writing anything
        with pytest.raises(FixtureCapabilityError):
            yaml_io.import_macro_yaml(macro_db_conn, document)

        assert macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0] == 0

    def test_should_round_trip_export_import_stored_bytes_equal_canonical(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Edge case: export → re-import → stored bytes equal the tool's
        canonical compact serialization."""
        # Given: a macro with compact payloads on Moving Head slots
        original = repo.create_macro(
            macro_db_conn,
            name="ROUNDTRIP CANONICAL",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _COMPACT_PAYLOAD},
        )

        # When: exported to YAML and re-imported
        document = yaml_io.export_macro_yaml(macro_db_conn, original.id)
        imported = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: the imported payload is the canonical compact serialization
        canonical_payload = lightingxml.serialize(lightingxml.parse(_COMPACT_PAYLOAD))
        imported_rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, imported.id)
        }
        assert imported_rows[_SLOT_MOVING_HEAD] == canonical_payload
        # All other slots are empty
        for slot_id in ALL_25_SLOT_IDS:
            if slot_id == _SLOT_MOVING_HEAD:
                continue
            assert imported_rows[slot_id] == ""

    def test_should_reproduce_equivalent_stored_payloads(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Existing guarantee: import produces stored payloads in canonical
        compact form, regardless of how the YAML formatted the XML."""
        # Given: an exported macro's YAML document
        original = repo.create_macro(
            macro_db_conn,
            name="MID CHORUS COOL",
            beats=64,
            payloads={1: a_valid_slot_payload(), 11: a_valid_slot_payload()},
        )
        document = yaml_io.export_macro_yaml(macro_db_conn, original.id)

        # When: imported back in
        imported = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: the imported macro's stored payloads are canonical compact form
        imported_rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, imported.id)
        }
        canonical_slot1 = lightingxml.serialize(
            lightingxml.parse(a_valid_slot_payload())
        )
        canonical_slot11 = lightingxml.serialize(
            lightingxml.parse(a_valid_slot_payload())
        )
        assert imported_rows[1] == canonical_slot1
        assert imported_rows[11] == canonical_slot11

    def test_empty_slot_vs_corrupt_slot_behave_differently(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Edge case: empty-string slot stays empty on export; corrupt-string
        slot passes through raw on export."""
        # Given: a macro with slot 11 = corrupt, slot 1 = omitted (empty)
        macro = repo.create_macro(
            macro_db_conn,
            name="EMPTY VS CORRUPT",
            beats=32,
            payloads={_SLOT_MOVING_HEAD: _CORRUPT_PAYLOAD},
        )

        # When: exported
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: empty stays empty, corrupt passes through raw
        assert parsed["fixtures"][1] == ""
        assert parsed["fixtures"][_SLOT_MOVING_HEAD] == _CORRUPT_PAYLOAD

    def test_should_store_compact_when_importing_hand_crafted_indented_document(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Hand-crafted YAML with indented payloads is stored as compact
        canonical bytes, matching the tool's own serializer output."""
        # Given: a hand-crafted YAML document with 2-space-indented payloads
        # on a Moving Head slot (supports all sections including Gobo)
        document = pyyaml.safe_dump(
            {
                "name": "HANDCRAFTED",
                "beats": 32,
                "fixtures": {_SLOT_MOVING_HEAD: _INDENTED_PAYLOAD},
            }
        )

        # When: imported
        macro = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: stored payload is compact canonical form
        rows = repo.list_macro_data(macro_db_conn, macro.id)
        slot_data = next(r for r in rows if r.macro_fixture_id == _SLOT_MOVING_HEAD)
        model_from_stored = lightingxml.parse(slot_data.xml)
        model_from_compact = lightingxml.parse(_COMPACT_PAYLOAD)
        assert model_from_stored == model_from_compact

    def test_should_accept_empty_string_payloads_in_import(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Explicit empty strings in the fixtures map are stored as empty
        strings (not NULL, not indented empty document)."""
        # Given: a document with explicit empty strings
        document = pyyaml.safe_dump(
            {
                "name": "EMPTY EXPLICIT",
                "beats": 32,
                "fixtures": {1: "", 11: ""},
            }
        )

        # When: imported
        macro = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: both slots are empty strings
        rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, macro.id)
        }
        assert rows[1] == ""
        assert rows[11] == ""

    def test_should_reject_unsupported_gobo_on_non_moving_head(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Edge case: Gobo section is only supported by fixture_type_id 3
        (Moving Head) and 103 (Moving Head Simple). Slot 1 (Par Light,
        fixture_type_id=1) does not support Gobo."""
        # Given: a document with a Gobo-containing payload on slot 1
        # (Par Light — no gobo wheel)
        gobo_payload = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<LightingEditModel ver="1.0">'
            "<Brightness>"
            '<PointBlock xleft="0" xright="32">'
            '<Point x="0" y="0" type="1"/>'
            '<Point x="32" y="0" type="3"/>'
            "</PointBlock>"
            "</Brightness>"
            "<Colour/>"
            "<Strobe/>"
            "<Gobo/>"
            "</LightingEditModel>"
        )
        document = pyyaml.safe_dump(
            {
                "name": "GOBO ON PAR",
                "beats": 32,
                "fixtures": {1: gobo_payload},
            }
        )

        # When / Then: import is rejected
        with pytest.raises(FixtureCapabilityError, match="gobo"):
            yaml_io.import_macro_yaml(macro_db_conn, document)

        assert macro_db_conn.execute("SELECT COUNT(*) FROM macro").fetchone()[0] == 0

    def test_should_normalize_indented_payload_on_par_slot_without_gobo(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        """Import on a non-Gobo slot with indented payload: stored bytes
        must be compact canonical form."""
        # Given: indented payload without Gobo on slot 1 (Par Light)
        document = pyyaml.safe_dump(
            {
                "name": "PAR NORMALIZE",
                "beats": 32,
                "fixtures": {_SLOT_PAR: _INDENTED_PAYLOAD_NO_GOBO},
            }
        )

        # When: imported
        macro = yaml_io.import_macro_yaml(macro_db_conn, document)

        # Then: stored payload is compact canonical form
        rows = repo.list_macro_data(macro_db_conn, macro.id)
        slot_data = next(r for r in rows if r.macro_fixture_id == _SLOT_PAR)
        model_from_stored = lightingxml.parse(slot_data.xml)
        model_from_compact = lightingxml.parse(_COMPACT_PAYLOAD_NO_GOBO)
        assert model_from_stored == model_from_compact
        assert "\n  " not in slot_data.xml
