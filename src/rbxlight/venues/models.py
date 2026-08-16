"""user.db3 domain dataclasses: venue + fixture patch. See
rekordbox-lightingdb-schema skill ("user.db3 tables").

Kept in this subpackage (rather than rbxlight.models) to keep the existing
`rbxlight.models` module untouched — see rekordbox-lighting-architecture
skill for module placement conventions.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Venue:
    id: int
    name: str
    order: int
    enabled: int


@dataclass(frozen=True)
class Fixture:
    """One row of user.db3's `fixture` table — a physical fixture patched
    into a venue. offset_x/offset_y are a rekordbox-stored placeholder
    (always centred, e.g. 127/127) — NEVER a real physical layout
    position; that lives in the preview tool's own layout description
    (see rbxlight.preview.layout), not here.
    """

    id: int
    name: str
    venue_id: int
    fixture_master_id: int
    mode_num: int
    macro_fixture_id: int
    universe_num: int
    start_addr: int
    color_num: int
    order: int
    offset_x: int
    offset_y: int
    limit_min_x: int
    limit_max_x: int
    limit_min_y: int
    limit_max_y: int
    tilt_reversal: int


@dataclass(frozen=True)
class VenueWithFixtureCount:
    """A venue paired with the count of fixtures patched into it — the
    read model behind `rbxlight venue list` and shared venue-resolution
    error messages. See rbxlight.venues.repo.list_venues_with_fixture_counts.
    """

    venue: Venue
    fixture_count: int
