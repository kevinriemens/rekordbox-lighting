"""Shared domain/actions layer: venue resolution, layout regenerate/install
orchestration, and the preview pipeline — extracted out of cli.py so a
future front-end (e.g. an interactive TUI) can drive the same operations
without importing typer/click. See rekordbox-lighting-architecture skill
("The Flow That Must Not Break") and rekordbox-data-safety skill
("DRY-RUN BY DEFAULT").

Hard rules for this module (enforced by tests):
- No typer/click import, no print, no sys.exit — typed exceptions and
  return values only. The CLI layer translates these into user-facing
  messages and exit codes.
- Every `build_*_plan` function performs zero I/O: no backup, no guard,
  no transaction, no database mutation, no file write. Plans are pure
  values.
- Module-level location constants (`db.WORK_DIR`, `safety.BACKUP_ROOT`)
  are read via attribute access INSIDE function bodies, never bound at
  import time — so test monkeypatches of those constants take effect for
  every call, not just calls made before a redirect.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from rbxlight import db, safety
from rbxlight.preview import document as preview_document
from rbxlight.preview import layout as preview_layout
from rbxlight.preview import payload as preview_payload
from rbxlight.venues import repo as venues_repo

# ---------------------------------------------------------------------------
# Venue resolution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VenueResolution:
    """The result of resolving a venue id (explicit or via the active
    venue pointer) plus its patched fixtures.
    """

    venue: venues_repo.Venue
    fixtures: list[venues_repo.Fixture]
    source: str  # "explicit" | "active_venue"


class VenueNotFoundError(LookupError):
    """Raised when an explicit venue id does not exist. Carries the list
    of currently valid venues so a caller can offer them to the user.
    """

    def __init__(
        self, venue_id: int, venues: list[venues_repo.VenueWithFixtureCount]
    ) -> None:
        self.venue_id = venue_id
        self.venues = venues
        super().__init__(f"venue {venue_id} not found")


class NoActiveVenueError(LookupError):
    """Raised when no explicit venue id is given and no active venue
    pointer (lighting_property.ExecVenueId) is set at all.
    """

    def __init__(self, venues: list[venues_repo.VenueWithFixtureCount]) -> None:
        self.venues = venues
        super().__init__("no active venue is set")


class StaleActiveVenueError(LookupError):
    """Raised when the active venue pointer is set but points at a venue
    that no longer exists. Deliberately NOT a subclass of
    NoActiveVenueError (and vice versa) — the two failure modes must be
    distinguishable by type alone.
    """

    def __init__(
        self, stale_venue_id: int, venues: list[venues_repo.VenueWithFixtureCount]
    ) -> None:
        self.stale_venue_id = stale_venue_id
        self.venues = venues
        super().__init__(
            f"active venue (ExecVenueId={stale_venue_id}) no longer exists"
        )


def resolve_venue(conn: sqlite3.Connection, venue_id: int | None) -> VenueResolution:
    """Resolve `venue_id` (explicit, else the active venue pointer) and
    list its patched fixtures.

    Raises VenueNotFoundError, NoActiveVenueError, or
    StaleActiveVenueError on failure — never prints, never exits.
    """
    if venue_id is not None:
        try:
            venue = venues_repo.get_venue(conn, venue_id)
        except LookupError as exc:
            venues = venues_repo.list_venues_with_fixture_counts(conn)
            raise VenueNotFoundError(venue_id, venues) from exc
        fixtures = venues_repo.list_fixtures(conn, venue_id)
        return VenueResolution(venue=venue, fixtures=fixtures, source="explicit")

    active_id = venues_repo.get_exec_venue_id(conn)
    if active_id is None:
        venues = venues_repo.list_venues_with_fixture_counts(conn)
        raise NoActiveVenueError(venues)

    try:
        venue = venues_repo.get_venue(conn, active_id)
    except LookupError as exc:
        venues = venues_repo.list_venues_with_fixture_counts(conn)
        raise StaleActiveVenueError(active_id, venues) from exc

    fixtures = venues_repo.list_fixtures(conn, active_id)
    return VenueResolution(venue=venue, fixtures=fixtures, source="active_venue")


# ---------------------------------------------------------------------------
# Layout regenerate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayoutRegeneratePlan:
    """A pure description of what `layout regenerate` WOULD do — built
    with zero writes. `touches_live` is always False: regenerate only
    ever touches the disposable working-copy layout file, and only on
    apply.
    """

    venue_id: int
    fresh: preview_layout.RigLayout
    old_present_entries: tuple[preview_layout.LayoutEntry, ...]
    orphans: tuple[preview_layout.LayoutEntry, ...]
    diffs: tuple[preview_layout.LayoutDiffEntry, ...]
    unchanged_count: int
    structure_status: str  # "reset" | "preserved" | "no_previous"
    touches_live: bool = False


def build_layout_regenerate_plan(
    venue_id: int,
    fixtures: list[venues_repo.Fixture],
    layout_dir: Path,
    *,
    structure_cm: tuple[tuple[float, float], ...] | None = None,
    reset_structure: bool = False,
) -> LayoutRegeneratePlan:
    """Build a LayoutRegeneratePlan: resolve the target structure,
    generate a fresh layout, and diff it against any saved layout.
    Performs zero writes — uses `load_layout`, never `ensure_layout`
    (which always writes as a side effect of loading and would silently
    break this function's dry-run guarantee).
    """
    fixture_ids = {fixture.id for fixture in fixtures}
    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
    existing = preview_layout.load_layout(layout_path)

    if structure_cm is not None:
        target_structure = structure_cm
        structure_status = "preserved"
    elif reset_structure:
        target_structure = preview_layout.arch_outline_cm()
        structure_status = "reset"
    elif existing is not None:
        target_structure = existing.structure_cm
        structure_status = "preserved"
    else:
        target_structure = None
        structure_status = "no_previous"

    fresh = preview_layout.generate_layout(venue_id, fixtures, target_structure)

    existing_entries = existing.entries if existing is not None else ()
    old_present_entries = tuple(
        entry for entry in existing_entries if entry.fixture_id in fixture_ids
    )
    orphans = tuple(
        entry for entry in existing_entries if entry.fixture_id not in fixture_ids
    )

    old_present = preview_layout.RigLayout(
        venue_id=venue_id, entries=old_present_entries
    )
    diffs = preview_layout.diff_layouts(old_present, fresh)
    unchanged_count = len(fixture_ids) - len(diffs)

    return LayoutRegeneratePlan(
        venue_id=venue_id,
        fresh=fresh,
        old_present_entries=old_present_entries,
        orphans=orphans,
        diffs=diffs,
        unchanged_count=unchanged_count,
        structure_status=structure_status,
    )


def apply_layout_regenerate(
    venue_id: int,
    fixtures: list[venues_repo.Fixture],
    layout_dir: Path,
    *,
    reset_structure: bool = False,
) -> preview_layout.RigLayout:
    """Regenerate venue_id's layout and write it to disk, preserving
    every still-present fixture's prior pan/tilt calibration. This is
    the WRITE side — build_layout_regenerate_plan is the dry-run
    equivalent.
    """
    plan = build_layout_regenerate_plan(
        venue_id, fixtures, layout_dir, reset_structure=reset_structure
    )
    merged_layout = preview_layout.apply_prior_calibration(
        plan.fresh, plan.old_present_entries
    )
    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
    preview_layout.save_layout(layout_path, merged_layout)
    return merged_layout


# ---------------------------------------------------------------------------
# Layout install
# ---------------------------------------------------------------------------


class LayoutVenueMismatchError(ValueError):
    """Raised when an incoming layout file's venue id does not match the
    target venue.
    """

    def __init__(self, incoming_venue_id: int, target_venue_id: int) -> None:
        self.incoming_venue_id = incoming_venue_id
        self.target_venue_id = target_venue_id
        super().__init__(
            f"layout is for venue {incoming_venue_id}, but the target is "
            f"venue {target_venue_id}"
        )


@dataclass(frozen=True)
class LayoutInstallPlan:
    """A pure description of what `layout install` WOULD do — built with
    zero writes. `touches_live` is always False.
    """

    venue_id: int
    incoming: preview_layout.RigLayout
    existing: preview_layout.RigLayout | None
    missing_from_incoming_fixture_ids: tuple[int, ...]
    missing_from_venue_fixture_ids: tuple[int, ...]
    fixture_diffs: tuple[preview_layout.LayoutDiffEntry, ...]
    structure_changed: bool
    touches_live: bool = False


def build_layout_install_plan(
    incoming_path: Path,
    venue_id: int,
    fixtures: list[venues_repo.Fixture],
    layout_dir: Path,
) -> LayoutInstallPlan:
    """Build a LayoutInstallPlan: load the incoming layout file, validate
    its venue id matches, and diff it against any existing saved layout.
    Raises LayoutVenueMismatchError on a venue id mismatch. Performs zero
    writes.
    """
    incoming = preview_layout.load_layout_file(incoming_path)

    if incoming.venue_id != venue_id:
        raise LayoutVenueMismatchError(incoming.venue_id, venue_id)

    incoming_ids = {entry.fixture_id for entry in incoming.entries}
    venue_fixture_ids = {fixture.id for fixture in fixtures}
    missing_from_incoming_fixture_ids = tuple(
        sorted(fixture.id for fixture in fixtures if fixture.id not in incoming_ids)
    )
    missing_from_venue_fixture_ids = tuple(
        sorted(
            fixture_id
            for fixture_id in incoming_ids
            if fixture_id not in venue_fixture_ids
        )
    )

    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
    existing = preview_layout.load_layout(layout_path)

    if existing is None:
        fixture_diffs: tuple[preview_layout.LayoutDiffEntry, ...] = ()
        structure_changed = False
    else:
        fixture_diffs = preview_layout.diff_layouts(existing, incoming)
        structure_changed = existing.structure_cm != incoming.structure_cm

    return LayoutInstallPlan(
        venue_id=venue_id,
        incoming=incoming,
        existing=existing,
        missing_from_incoming_fixture_ids=missing_from_incoming_fixture_ids,
        missing_from_venue_fixture_ids=missing_from_venue_fixture_ids,
        fixture_diffs=fixture_diffs,
        structure_changed=structure_changed,
    )


def apply_layout_install(plan: LayoutInstallPlan, layout_dir: Path) -> None:
    """Write `plan.incoming` to disk as the saved layout for
    `plan.venue_id`. The WRITE side of build_layout_install_plan.
    """
    layout_path = preview_layout.layout_path_for_venue(plan.venue_id, layout_dir)
    preview_layout.save_layout(layout_path, plan.incoming)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


def generate_preview(
    macro_conn: sqlite3.Connection,
    user_conn: sqlite3.Connection,
    macro_id: int,
    venue_id: int,
    fixtures: list[venues_repo.Fixture],
    layout_dir: Path,
    output_path: Path,
) -> Path:
    """Resolve/ensure the venue's layout, build the preview payload,
    render it to HTML, and write it to `output_path`. Uses
    `ensure_layout` deliberately: preview is read-only with respect to
    the databases, but a venue with no saved layout yet must still get
    one generated and persisted so the renderer has something to show —
    this is NOT a dry-run command, unlike layout regenerate/install.
    Returns `output_path`.
    """
    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
    merge_result = preview_layout.ensure_layout(layout_path, venue_id, fixtures)

    payload = preview_payload.build_preview_payload(
        macro_conn, user_conn, macro_id, venue_id, merge_result.layout
    )
    html = preview_document.render_preview_document(payload)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# ---------------------------------------------------------------------------
# Default locations — read module globals at CALL time, never at import
# time, so a test (or future caller) redirecting db.WORK_DIR /
# safety.BACKUP_ROOT after this module was imported still takes effect.
# ---------------------------------------------------------------------------


def default_layout_dir() -> Path:
    """The default on-disk directory for saved layout files, derived from
    the CURRENT value of `db.WORK_DIR`.
    """
    return db.WORK_DIR / "layouts"


def default_backup_root() -> Path:
    """The CURRENT value of `safety.BACKUP_ROOT`."""
    return safety.BACKUP_ROOT
