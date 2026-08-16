"""Preview payload construction: macro + venue + rig layout -> the single
JSON-serializable dict the (separately built) renderer consumes.

`macro_conn` and `user_conn` must both be read-only connections — this
module never writes to either database. See rekordbox-data-safety skill
and rekordbox-lighting-architecture skill ("The Flow That Must Not Break").
"""

from __future__ import annotations

import sqlite3

from rbxlight.macros import repo as macros_repo
from rbxlight.preview.extract import build_fixture_program
from rbxlight.preview.layout import RigLayout, normalized_structure
from rbxlight.venues import repo as venues_repo

#: Static default tempo used for every preview — rekordbox macros carry no
#: intrinsic BPM of their own (that lives on the track, not the macro).
DEFAULT_BPM: int = 128


class MacroNotFoundError(LookupError):
    """Raised when build_preview_payload is given a macro_id that doesn't
    exist in macro_conn."""


class VenueNotFoundError(LookupError):
    """Raised when build_preview_payload is given a venue_id that doesn't
    exist in user_conn."""


class MissingLayoutEntryError(LookupError):
    """Raised when `layout` has no LayoutEntry for one of the venue's
    current fixtures — the caller must run preview.layout.ensure_layout
    first."""


def _fetch_slot_info(macro_conn: sqlite3.Connection, slot_id: int) -> tuple[str, int]:
    row = macro_conn.execute(
        "SELECT name, fixture_type_id FROM macro_fixture WHERE id = ?",
        (slot_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"macro_fixture slot {slot_id} not found")
    return row[0], row[1]


def build_preview_payload(
    macro_conn: sqlite3.Connection,
    user_conn: sqlite3.Connection,
    macro_id: int,
    venue_id: int,
    layout: RigLayout,
    *,
    bpm: int = DEFAULT_BPM,
) -> dict:
    """Build the full preview payload dict.

    Shape (must match the renderer's agreed JSON contract exactly):

        {
          "macro":  {"id": int, "name": str, "beats": int},
        "venue":  {"id": int, "name": str},
        "bpm": int,
        "truss": [[x, y], ...],  # normalized structure, see layout.py
        "fixtures": [
            {
              "id": int, "label": str, "kind": str,
              "x": float, "y": float, "rotation": float,
              "slot_id": int, "slot_name": str, "fixture_type_id": int,
              "program": {...},   # see rbxlight.preview.extract
              "pan_limits": {"min": int, "max": int},
              "tilt_limits": {"min": int, "max": int},
              "tilt_reversal": bool,
              "pan_degrees": float, "tilt_degrees": float,
            },
            ...
          ],
        }

    Raises MacroNotFoundError / VenueNotFoundError for an unknown id.
    Raises MissingLayoutEntryError if `layout` doesn't cover every fixture
    currently patched into the venue.
    """
    try:
        macro = macros_repo.get_macro(macro_conn, macro_id)
    except LookupError as exc:
        raise MacroNotFoundError(f"macro {macro_id} not found") from exc

    try:
        venue = venues_repo.get_venue(user_conn, venue_id)
    except LookupError as exc:
        raise VenueNotFoundError(f"venue {venue_id} not found") from exc

    fixtures = venues_repo.list_fixtures(user_conn, venue_id)
    layout_by_fixture_id = {entry.fixture_id: entry for entry in layout.entries}
    missing_fixture_ids = [
        fixture.id for fixture in fixtures if fixture.id not in layout_by_fixture_id
    ]
    if missing_fixture_ids:
        raise MissingLayoutEntryError(
            f"layout for venue {venue_id} is missing entries for fixture ids: "
            f"{missing_fixture_ids}"
        )

    payload_by_slot_id = {
        row.macro_fixture_id: row.xml
        for row in macros_repo.list_macro_data(macro_conn, macro_id)
    }

    slot_info_cache: dict[int, tuple[str, int]] = {}
    program_cache: dict[int, dict] = {}
    fixtures_out = []

    for fixture in fixtures:
        slot_id = fixture.macro_fixture_id
        if slot_id not in slot_info_cache:
            slot_info_cache[slot_id] = _fetch_slot_info(macro_conn, slot_id)
        slot_name, fixture_type_id = slot_info_cache[slot_id]

        if slot_id not in program_cache:
            xml_payload = payload_by_slot_id.get(slot_id, "")
            program_cache[slot_id] = build_fixture_program(
                xml_payload, fixture_type_id, float(macro.beats)
            )
        program = program_cache[slot_id]

        entry = layout_by_fixture_id[fixture.id]
        fixtures_out.append(
            {
                "id": fixture.id,
                "label": entry.label,
                "kind": entry.kind,
                "x": entry.x,
                "y": entry.y,
                "rotation": entry.rotation,
                "slot_id": slot_id,
                "slot_name": slot_name,
                "fixture_type_id": fixture_type_id,
                "program": program,
                "pan_limits": {
                    "min": fixture.limit_min_x,
                    "max": fixture.limit_max_x,
                },
                "tilt_limits": {
                    "min": fixture.limit_min_y,
                    "max": fixture.limit_max_y,
                },
                "tilt_reversal": bool(fixture.tilt_reversal),
                "pan_degrees": entry.pan_degrees,
                "tilt_degrees": entry.tilt_degrees,
            }
        )

    return {
        "macro": {"id": macro.id, "name": macro.name, "beats": macro.beats},
        "venue": {"id": venue.id, "name": venue.name},
        "bpm": bpm,
        "truss": normalized_structure(layout),
        "fixtures": fixtures_out,
    }
