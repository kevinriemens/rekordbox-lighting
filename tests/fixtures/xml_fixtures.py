"""LightingEditModel XML test data: the golden round-trip corpus plus
synthetic edge-case payloads (malformed input, empty payload).

Golden files under tests/fixtures/golden/ were captured from the live
database (see manifest.json) — never re-captured or regenerated here.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"
MANIFEST_PATH = GOLDEN_DIR / "manifest.json"


@dataclass(frozen=True)
class GoldenFixture:
    """One golden-corpus entry: file name + its manifest metadata."""

    file: str
    macro_id: int
    macro_fixture_id: int
    fixture_type_id: int
    sections_with_content: tuple[str, ...]
    bytes: int
    sha256: str

    @property
    def path(self) -> Path:
        return GOLDEN_DIR / self.file

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")


def golden_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def all_golden_fixtures() -> list[GoldenFixture]:
    """Every captured golden payload (37 files covering every combination
    of programming sections across every fixture type)."""
    manifest = golden_manifest()
    return [
        GoldenFixture(
            file=entry["file"],
            macro_id=entry["macro_id"],
            macro_fixture_id=entry["macro_fixture_id"],
            fixture_type_id=entry["fixture_type_id"],
            sections_with_content=tuple(entry["sections_with_content"]),
            bytes=entry["bytes"],
            sha256=entry["sha256"],
        )
        for entry in manifest["files"]
    ]


def golden_fixture_ids() -> list[str]:
    """pytest.mark.parametrize `ids=` for all_golden_fixtures()."""
    return [g.file for g in all_golden_fixtures()]


# ---------------------------------------------------------------------------
# Synthetic edge cases — NOT from real data (real data never has malformed
# or truncated XML; every non-empty payload in the corpus parses cleanly).
# ---------------------------------------------------------------------------


def an_empty_payload() -> str:
    """A macro_data.data value of "" — 114 such rows exist in real data.
    Legitimate value meaning "this fixture does nothing in this macro"."""
    return ""


def a_malformed_xml_payload() -> str:
    """Synthetic: unclosed tag. Must be reported as invalid, not crash."""
    return '<LightingEditModel ver="1.0"><Brightness>'


def a_non_xml_payload() -> str:
    """Synthetic: not XML at all."""
    return "not xml at all, just text"


def a_truncated_xml_payload() -> str:
    """Synthetic: valid-looking prefix, cut off mid-attribute."""
    return '<?xml version="1.0" encoding="UTF-8"?>\n<LightingEditModel ver="1.'


def top_level_section_names(xml_payload: str) -> list[str]:
    """The ordered list of direct child element tag names of
    <LightingEditModel> — e.g. ["Brightness", "Colour", "Strobe"]."""
    root = ET.fromstring(xml_payload)
    return [child.tag for child in root]
