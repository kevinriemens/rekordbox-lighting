"""Preview: read-only with respect to the databases — prompts for a
macro and venue id, generates the preview HTML, reports the output
path, and offers to open it.
"""

from __future__ import annotations

import webbrowser

from rbxlight import db, orchestration
from rbxlight.menu import actions
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer


def run(prompter: Prompter, renderer: Renderer) -> None:
    macro_raw = prompter.text("Macro id:")
    venue_raw = prompter.text("Venue id:")
    try:
        macro_id = int(macro_raw)
    except ValueError:
        renderer.error(f"'{macro_raw}' is not a valid macro id.")
        return
    try:
        venue_id = int(venue_raw)
    except ValueError:
        renderer.error(f"'{venue_raw}' is not a valid venue id.")
        return

    try:
        output_path = actions.generate_preview_for_menu(macro_id, venue_id)
    except db.WorkingCopyMissingError as exc:
        renderer.error(
            f"Working copy not found at {exc.path}. Run `rbxlight pull` first."
        )
        return
    except orchestration.VenueNotFoundError as exc:
        renderer.error(f"Venue not found: no venue with id {exc.venue_id}.")
        return
    except orchestration.NoActiveVenueError:
        renderer.error(
            "No venue given and no active venue is set. Pick a venue explicitly."
        )
        return
    except orchestration.StaleActiveVenueError as exc:
        renderer.error(f"Active venue (id={exc.stale_venue_id}) no longer exists.")
        return
    except LookupError as exc:
        renderer.error(str(exc))
        return

    renderer.line(f"Preview written to {output_path}")

    if prompter.confirm("Open it now?", default=False):
        webbrowser.open(str(output_path))
