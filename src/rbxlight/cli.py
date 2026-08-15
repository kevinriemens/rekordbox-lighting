"""typer entrypoint. Every mutating command defaults to a dry run — see
rekordbox-lighting-architecture skill, "typer command shape — dry-run by
default".

Normal commands work against the WORKING COPY only (`db.resolve_path`,
default `live=False`) — never live. The only path to live is `rbxlight
pull`/`push` in `sync.py`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import typer

from rbxlight import db
from rbxlight.macros import repo
from rbxlight.preview import document as preview_document
from rbxlight.preview import layout as preview_layout
from rbxlight.preview import payload as preview_payload
from rbxlight.venues import repo as venues_repo

app = typer.Typer(help="rbxlight — rekordbox 6 LightingDB CLI")

macro_app = typer.Typer(help="Macro authoring commands")
app.add_typer(macro_app, name="macro")

_MACRO_DB_NAME = "macro.db3"
_USER_DB_NAME = "user.db3"


@macro_app.command("create")
def macro_create(
    name: str,
    beats: int,
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Create a new user macro. Prints the plan; only writes with --write."""
    typer.echo(
        f"Plan: create macro '{name}' ({beats} beats), all 25 fixture slots empty."
    )

    if not write:
        typer.echo("This is a dry run — nothing was changed. Pass --write to apply.")
        return

    path = db.resolve_path(_MACRO_DB_NAME)
    conn = sqlite3.connect(path)
    try:
        conn.execute("BEGIN")
        macro = repo.create_macro(conn, name=name, beats=beats, payloads={})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    typer.echo(f"Created macro '{macro.name}' (id={macro.id}).")


@app.command("preview")
def preview(
    macro_id: int,
    venue: int = typer.Option(
        None,
        "--venue",
        help="Venue id. Defaults to the active venue (lighting_property.ExecVenueId).",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output HTML path. Defaults to preview_<macro_id>.html in the "
        "current directory.",
    ),
) -> None:
    """Render a self-contained HTML preview of a macro against a venue's
    fixture layout. Read-only, nothing to confirm; never touches live data.
    """
    macro_path = db.resolve_path(_MACRO_DB_NAME)
    user_path = db.resolve_path(_USER_DB_NAME)

    macro_conn = db.connect_readonly(macro_path)
    user_conn = db.connect_readonly(user_path)
    try:
        venue_id = venue
        if venue_id is None:
            venue_id = venues_repo.get_exec_venue_id(user_conn)
            if venue_id is None:
                typer.echo(
                    "No venue given and no active venue "
                    "(lighting_property.ExecVenueId) is set."
                )
                raise typer.Exit(code=1)

        fixtures = venues_repo.list_fixtures(user_conn, venue_id)
        layout_path = preview_layout.layout_path_for_venue(
            venue_id, db.WORK_DIR / "layouts"
        )
        merge_result = preview_layout.ensure_layout(layout_path, venue_id, fixtures)

        result = preview_payload.build_preview_payload(
            macro_conn, user_conn, macro_id, venue_id, merge_result.layout
        )
    except preview_payload.MacroNotFoundError as exc:
        typer.echo(f"Macro not found: {exc}")
        raise typer.Exit(code=1) from exc
    except preview_payload.VenueNotFoundError as exc:
        typer.echo(f"Venue not found: {exc}")
        raise typer.Exit(code=1) from exc
    except preview_payload.MissingLayoutEntryError as exc:
        typer.echo(f"Layout incomplete: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        macro_conn.close()
        user_conn.close()

    html = preview_document.render_preview_document(result)

    output_path = Path(output) if output else Path(f"preview_{macro_id}.html")
    output_path.write_text(html, encoding="utf-8")
    typer.echo(f"Preview written to {output_path}")
