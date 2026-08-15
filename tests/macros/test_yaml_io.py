"""Tests for rbxlight.macros.yaml_io — macro <-> YAML export/import.
Contract: task requirements ("YAML export/import") + rekordbox-lightingdb-
schema skill (fixture-type capability matrix).
"""

from __future__ import annotations

import sqlite3

import pytest
import yaml as pyyaml

from rbxlight.macros import repo, yaml_io
from rbxlight.macros.yaml_io import FixtureCapabilityError
from tests.fixtures.macro_fixtures import ALL_25_SLOT_IDS, a_valid_slot_payload

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


class TestExportMacroYaml:
    def test_should_capture_name_beats_and_fixture_programming(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
        # Given: a macro with one programmed slot
        macro = repo.create_macro(
            macro_db_conn,
            name="HIGH DROP1",
            beats=32,
            payloads={1: a_valid_slot_payload()},
        )

        # When: exported to YAML
        document = yaml_io.export_macro_yaml(macro_db_conn, macro.id)
        parsed = pyyaml.safe_load(document)

        # Then: name, beats, and per-fixture programming are all present
        assert parsed["name"] == "HIGH DROP1"
        assert parsed["beats"] == 32
        assert parsed["fixtures"][1] == a_valid_slot_payload()


class TestImportMacroYaml:
    def test_should_reproduce_equivalent_stored_payloads(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
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

        # Then: the new macro's stored payloads match the original's
        original_rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, original.id)
        }
        imported_rows = {
            r.macro_fixture_id: r.xml
            for r in repo.list_macro_data(macro_db_conn, imported.id)
        }
        assert imported_rows == original_rows

    def test_should_fill_omitted_fixtures_with_empty_payload(
        self, macro_db_conn: sqlite3.Connection
    ) -> None:
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
