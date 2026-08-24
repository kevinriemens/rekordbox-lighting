"""Layout submenu: Regenerate, Install — both working-copy tier
mutations (they only ever write the disposable layout JSON file, never
a database, per `orchestration.LayoutRegeneratePlan`/`LayoutInstallPlan`
having `touches_live=False`).
"""

from __future__ import annotations

from pathlib import Path

from rbxlight import db, orchestration
from rbxlight.menu import actions
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer
from rbxlight.preview import layout as preview_layout

_CHOICES = ("Regenerate", "Install", "Back")


def _render_venue_error(renderer: Renderer, exc: Exception) -> None:
    if isinstance(exc, orchestration.VenueNotFoundError):
        renderer.error(f"Venue not found: no venue with id {exc.venue_id}.")
    elif isinstance(exc, orchestration.StaleActiveVenueError):
        renderer.error(f"Active venue (id={exc.stale_venue_id}) no longer exists.")
    elif isinstance(exc, orchestration.NoActiveVenueError):
        renderer.error("No venue given and no active venue is set.")
    else:
        renderer.error(str(exc))


def _resolve_venue_or_none(
    prompter: Prompter, renderer: Renderer
) -> orchestration.VenueResolution | None:
    """Prompt for a venue id (blank = active), resolve it, and render a
    clean message on failure. Returns None (having already rendered the
    error) if there is nothing to resolve — including the "no venues at
    all, no active pointer either" case, which is reported WITHOUT
    prompting for an id at all.
    """
    try:
        entries, active_id = actions.list_venues()
    except db.WorkingCopyMissingError as exc:
        renderer.error(
            f"Working copy not found at {exc.path}. Run `rbxlight pull` first."
        )
        return None

    if not entries and active_id is None:
        renderer.error("No venues found. Nothing to regenerate/install.")
        return None

    raw = prompter.text("Venue id (blank = active venue):")
    venue_id = None
    if raw.strip():
        try:
            venue_id = int(raw)
        except ValueError:
            renderer.error(f"'{raw}' is not a valid venue id.")
            return None

    try:
        return actions.resolve_venue(venue_id)
    except (
        orchestration.VenueNotFoundError,
        orchestration.NoActiveVenueError,
        orchestration.StaleActiveVenueError,
    ) as exc:
        _render_venue_error(renderer, exc)
        return None


def _regenerate(prompter: Prompter, renderer: Renderer) -> None:
    result = _resolve_venue_or_none(prompter, renderer)
    if result is None:
        return

    reset_structure = prompter.confirm(
        "Reset structure to the default arch?", default=False
    )
    layout_dir = orchestration.default_layout_dir()
    plan = orchestration.build_layout_regenerate_plan(
        result.venue.id, result.fixtures, layout_dir, reset_structure=reset_structure
    )
    renderer.plan(plan)
    renderer.line(
        f"Plan: regenerate layout for venue {result.venue.id} in the working "
        f"copy ({plan.structure_status} structure, {len(plan.diffs)} diff(s), "
        f"{plan.unchanged_count} unchanged)."
    )

    if not prompter.confirm("Save this layout?", default=False):
        return

    orchestration.apply_layout_regenerate(
        result.venue.id, result.fixtures, layout_dir, reset_structure=reset_structure
    )
    renderer.line(f"Saved layout for venue {result.venue.id}.")


def _install(prompter: Prompter, renderer: Renderer) -> None:
    result = _resolve_venue_or_none(prompter, renderer)
    if result is None:
        return

    path_raw = prompter.text("Incoming layout file path:")
    layout_dir = orchestration.default_layout_dir()

    try:
        plan = orchestration.build_layout_install_plan(
            Path(path_raw), result.venue.id, result.fixtures, layout_dir
        )
    except orchestration.LayoutVenueMismatchError as exc:
        renderer.error(f"Refused: {exc}")
        return
    except (
        preview_layout.InvalidSavedLayoutError,
        preview_layout.DegenerateStructureError,
        FileNotFoundError,
    ) as exc:
        renderer.error(f"Refused: {exc}")
        return

    renderer.plan(plan)
    renderer.line(
        f"Plan: install layout for venue {result.venue.id} in the working copy."
    )

    if not prompter.confirm("Install this layout?", default=False):
        return

    orchestration.apply_layout_install(plan, layout_dir)
    renderer.line(f"Saved layout for venue {result.venue.id}.")


def run(prompter: Prompter, renderer: Renderer) -> None:
    while True:
        choice = prompter.select("Layout", list(_CHOICES))
        if choice == "Back":
            return
        if choice == "Regenerate":
            _regenerate(prompter, renderer)
        elif choice == "Install":
            _install(prompter, renderer)
        else:
            return
