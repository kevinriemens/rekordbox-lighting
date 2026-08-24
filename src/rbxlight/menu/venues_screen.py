"""Venues: a single read-only listing (with fixture counts), not a
submenu — there is nothing to navigate into beyond viewing it.
"""

from __future__ import annotations

from rbxlight import db
from rbxlight.menu import actions
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer


def run(prompter: Prompter, renderer: Renderer) -> None:
    try:
        entries, active_id = actions.list_venues()
    except db.WorkingCopyMissingError as exc:
        renderer.error(
            f"Working copy not found at {exc.path}. Run `rbxlight pull` first."
        )
        prompter.select("Venues", ["Back"])
        return

    if not entries:
        renderer.line("No venues found.")
    else:
        renderer.line("Venues:")
        for entry in entries:
            marker = " (active)" if entry.venue.id == active_id else ""
            renderer.line(
                f"  {entry.venue.id}: {entry.venue.name} "
                f"({entry.fixture_count} fixture(s)){marker}"
            )

    prompter.select("Venues", ["Back"])
