"""typer entrypoint. Every mutating command defaults to a dry run — see
rekordbox-lighting-architecture skill, "typer command shape — dry-run by
default".

Normal commands work against the WORKING COPY only (`db.resolve_path`,
default `live=False`) — never live. The only path to live is `rbxlight
pull`/`push` in `sync.py`.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer

from rbxlight import db, safety, sync
from rbxlight.macros import repo
from rbxlight.preview import document as preview_document
from rbxlight.preview import layout as preview_layout
from rbxlight.preview import payload as preview_payload
from rbxlight.venues import repo as venues_repo

app = typer.Typer(help="rbxlight — rekordbox 6 LightingDB CLI")

macro_app = typer.Typer(help="Macro authoring commands")
app.add_typer(macro_app, name="macro")

layout_app = typer.Typer(help="Rig layout description commands")
app.add_typer(layout_app, name="layout")

venue_app = typer.Typer(help="Venue discovery commands")
app.add_typer(venue_app, name="venue")

_MACRO_DB_NAME = "macro.db3"
_USER_DB_NAME = "user.db3"


@contextmanager
def _working_copy_write(db_name: str) -> Iterator[sqlite3.Connection]:
    """BEGIN -> yield conn -> commit, or rollback + re-raise. Working-copy
    only — unlike safety.write_transaction, no guard/backup (never live).
    """
    conn = sqlite3.connect(db.resolve_path(db_name))
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _require_working_copy(path: Path) -> None:
    """Guard shared by every venue-aware/working-copy-reading command.

    Raises a clean typer.Exit pointing the user at `pull` instead of
    letting a missing working copy surface as a raw sqlite driver error.
    """
    if not path.exists():
        typer.echo(f"Working copy not found at {path}. Run `rbxlight pull` first.")
        raise typer.Exit(code=1)


@contextmanager
def _readonly_working_copy(db_name: str) -> Iterator[sqlite3.Connection]:
    """Resolve db_name in the working copy, require it exists, open it
    read-only, and guarantee close. Shared by every read-only
    working-copy command (`preview`, `layout regenerate`, `venue list`).
    """
    path = db.resolve_path(db_name)
    _require_working_copy(path)
    conn = db.connect_readonly(path)
    try:
        yield conn
    finally:
        conn.close()


def _announce_venue_selection(venue: venues_repo.Venue, source: str) -> None:
    typer.echo(f"Venue: {venue.id} ({venue.name}) — selected via {source}.")


def _format_venue_line(
    entry: venues_repo.VenueWithFixtureCount, *, active_id: int | None = None
) -> str:
    marker = " (active)" if entry.venue.id == active_id else ""
    return f"  {entry.venue.id}: {entry.venue.name} ({entry.fixture_count} fixture(s)){marker}"


def _venue_listing_text(user_conn: sqlite3.Connection) -> str:
    """The "valid venues" enumeration shared by every venue-not-found /
    stale-active-venue error message, built from the same repository
    function `venue list` uses — so the two can never drift apart.
    """
    entries = venues_repo.list_venues_with_fixture_counts(user_conn)
    if not entries:
        return "  (no venues)"
    return "\n".join(_format_venue_line(entry) for entry in entries)


def _resolve_venue_and_fixtures(
    user_conn: sqlite3.Connection, venue: int | None
) -> tuple[venues_repo.Venue, list[venues_repo.Fixture], str]:
    """Resolve + validate the venue (explicit id, else the active
    lighting_property.ExecVenueId) and list its patched fixtures.

    Returns (venue, fixtures, source) where source is "explicit" when
    `venue` was given, else "active venue". Exits cleanly (code 1) when:
    - no venue given and no active venue is set
    - the active venue pointer is stale (points at a venue that no
      longer exists)
    - an explicit or active venue id does not exist
    In every not-found case, the message enumerates the currently valid
    venues so the user can retry immediately.
    """
    venue_id: int | None
    if venue is not None:
        venue_id = venue
        source = "explicit"
    else:
        venue_id = venues_repo.get_exec_venue_id(user_conn)
        if venue_id is None:
            typer.echo(
                "No venue given and no active venue "
                "(lighting_property.ExecVenueId) is set. Pass --venue to "
                "select one explicitly."
            )
            raise typer.Exit(code=1)
        source = "active venue"

    try:
        venue_obj = venues_repo.get_venue(user_conn, venue_id)
    except LookupError:
        listing = _venue_listing_text(user_conn)
        if source == "explicit":
            typer.echo(
                f"Venue not found: no venue with id {venue_id}.\n"
                f"Valid venues:\n{listing}"
            )
        else:
            typer.echo(
                f"Active venue (lighting_property.ExecVenueId={venue_id}) is "
                f"stale — that venue no longer exists.\n"
                f"Valid venues:\n{listing}"
            )
        raise typer.Exit(code=1) from None

    return venue_obj, venues_repo.list_fixtures(user_conn, venue_id), source


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

    with _working_copy_write(_MACRO_DB_NAME) as conn:
        macro = repo.create_macro(conn, name=name, beats=beats, payloads={})

    typer.echo(f"Created macro '{macro.name}' (id={macro.id}).")


@macro_app.command("delete")
def macro_delete(
    macro_id: int,
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Delete a user macro from the working copy. Prints the macro's
    identifying details; only writes with --write. Refuses factory
    content (preset=1, including the sentinel ids).
    """
    path = db.resolve_path(_MACRO_DB_NAME)
    read_conn = db.connect_readonly(path)
    try:
        macro = repo.get_macro(read_conn, macro_id)
    except LookupError as exc:
        typer.echo(f"Macro not found: {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        read_conn.close()

    typer.echo(
        f"Plan: delete macro '{macro.name}' (id={macro.id}, beats={macro.beats})."
    )

    if not write:
        typer.echo("This is a dry run — nothing was changed. Pass --write to apply.")
        return

    try:
        with _working_copy_write(_MACRO_DB_NAME) as conn:
            repo.delete_macro(conn, macro_id)
    except repo.FactoryMacroImmutableError as exc:
        typer.echo(f"Refused: {exc}")
        raise typer.Exit(code=1) from exc

    typer.echo(f"Deleted macro '{macro.name}' (id={macro.id}).")


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
    try:
        with (
            _readonly_working_copy(_MACRO_DB_NAME) as macro_conn,
            _readonly_working_copy(_USER_DB_NAME) as user_conn,
        ):
            venue_obj, fixtures, source = _resolve_venue_and_fixtures(user_conn, venue)
            venue_id = venue_obj.id
            _announce_venue_selection(venue_obj, source)
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

    html = preview_document.render_preview_document(result)

    output_path = Path(output) if output else Path(f"preview_{macro_id}.html")
    output_path.write_text(html, encoding="utf-8")
    typer.echo(f"Preview written to {output_path}")


# ---------------------------------------------------------------------------
# pull / push / restore — the only commands permitted to resolve live
# paths. See rekordbox-data-safety skill, "Working copy model".
# ---------------------------------------------------------------------------


@app.command("pull")
def pull() -> None:
    """Copy live LightingDB into the working copy. Applies immediately —
    only ever writes the disposable working area, so there is no
    dry-run gate. Requires rekordbox to be closed.
    """
    try:
        sync.pull(db.LIGHTINGDB, db.WORK_DIR)
    except safety.RekordboxRunningError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    names = ", ".join(sync.SYNCED_DB_NAMES)
    typer.echo(f"Pulled {names} from {db.LIGHTINGDB} into {db.WORK_DIR}.")


@app.command("push")
def push(
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass the staleness check only. Still guards rekordbox, still backs up.",
    ),
) -> None:
    """Copy the working copy over live LightingDB. Dry run by default —
    refuses a stale working copy (live changed since the last pull)
    unless --force is given.
    """
    if not write:
        names = ", ".join(sync.SYNCED_DB_NAMES)
        typer.echo(f"Plan: push {names} from {db.WORK_DIR} to {db.LIGHTINGDB}.")
        typer.echo("This is a dry run — nothing was changed. Pass --write to apply.")
        return

    trigger_command = "rbxlight push --write" + (" --force" if force else "")
    try:
        backup_dir = sync.push(
            db.LIGHTINGDB,
            db.WORK_DIR,
            safety.BACKUP_ROOT,
            trigger_command,
            force=force,
        )
    except safety.RekordboxRunningError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except sync.StaleWorkingCopyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except FileNotFoundError as exc:
        typer.echo(
            f"Push failed: {exc}. Has the working copy ever been pulled? "
            "Run `rbxlight pull` first."
        )
        raise typer.Exit(code=1) from exc

    typer.echo(f"Pushed to live. Backup saved at:\n  {backup_dir}")


@app.command("restore")
def restore(
    from_: str = typer.Option(
        None,
        "--from",
        help="Backup directory name to restore. Omit to list available backups.",
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """The panic-button command. With no --from, lists backups newest
    first and changes nothing. With --from, guards + verifies the backup,
    shows what will be overwritten, confirms (unless --yes), then
    restores live from it.
    """
    if from_ is None:
        backups = safety.list_backups()
        if not backups:
            typer.echo(f"No backups found under {safety.BACKUP_ROOT}.")
            return
        typer.echo("Available backups (newest first):")
        for info in backups:
            typer.echo(f"  {info.name}  ({info.trigger_command})")
        return

    backup_dir = safety.BACKUP_ROOT / from_
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        typer.echo(
            f"No backup named '{from_}' found under {safety.BACKUP_ROOT}. "
            "Run `rbxlight restore` with no arguments to list available backups."
        )
        raise typer.Exit(code=1)

    try:
        safety.guard_rekordbox_not_running()
        safety.verify_backup_integrity(backup_dir)
    except safety.RekordboxRunningError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except safety.BackupCorruptedError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    manifest = json.loads(manifest_path.read_text())
    file_names = [name for name in manifest["files"] if not name.endswith(".meta")]
    typer.echo(f"This will overwrite the following live files from backup '{from_}':")
    for name in file_names:
        typer.echo(f"  {name}")

    if not yes and not typer.confirm("Proceed with restore?"):
        typer.echo("Restore cancelled — nothing changed.")
        return

    safety.restore_from_backup(backup_dir)
    typer.echo(f"Restored live data from backup '{from_}'.")


# ---------------------------------------------------------------------------
# layout regenerate — the supported cure for stale, algorithm-generated
# layout positions. Never wipes user pan/tilt calibration on apply.
# ---------------------------------------------------------------------------


@layout_app.command("regenerate")
def layout_regenerate(
    venue: int = typer.Option(
        None,
        "--venue",
        help="Venue id. Defaults to the active venue (lighting_property.ExecVenueId).",
    ),
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Regenerate a venue's rig layout from the current algorithm and diff
    it against the saved layout. Position, rotation, label, and kind
    always come from the fresh generation; pan/tilt sweep calibration is
    preserved for every fixture that still exists. Dry run by default —
    never writes the saved layout file unless --write is given.
    """
    with _readonly_working_copy(_USER_DB_NAME) as user_conn:
        venue_obj, fixtures, source = _resolve_venue_and_fixtures(user_conn, venue)

    venue_id = venue_obj.id
    _announce_venue_selection(venue_obj, source)

    fixture_ids = {fixture.id for fixture in fixtures}
    layout_path = preview_layout.layout_path_for_venue(
        venue_id, db.WORK_DIR / "layouts"
    )

    # NOTE: load_layout() only reads — never use ensure_layout() here, it
    # writes the file as a side effect of loading, which would break the
    # dry-run guarantee below.
    existing = preview_layout.load_layout(layout_path)
    fresh = preview_layout.generate_layout(venue_id, fixtures)

    existing_entries = existing.entries if existing is not None else ()
    old_present_entries = tuple(
        entry for entry in existing_entries if entry.fixture_id in fixture_ids
    )
    orphans = tuple(
        entry for entry in existing_entries if entry.fixture_id not in fixture_ids
    )
    for orphan in sorted(orphans, key=lambda entry: entry.fixture_id):
        typer.echo(
            f"No longer in venue {venue_id}'s patch: "
            f"{orphan.label} (id={orphan.fixture_id})."
        )

    old_present = preview_layout.RigLayout(
        venue_id=venue_id, entries=old_present_entries
    )
    diffs = preview_layout.diff_layouts(old_present, fresh)

    for diff in diffs:
        if diff.old_x is None:
            typer.echo(
                f"New: {diff.label} (id={diff.fixture_id}) -> "
                f"({diff.new_x:.3f}, {diff.new_y:.3f}) @ {diff.new_rotation:.3f}."
            )
        else:
            typer.echo(
                f"{diff.label} (id={diff.fixture_id}): "
                f"({diff.old_x:.3f}, {diff.old_y:.3f}) @ {diff.old_rotation:.3f} -> "
                f"({diff.new_x:.3f}, {diff.new_y:.3f}) @ {diff.new_rotation:.3f}"
            )

    unchanged_count = len(fixture_ids) - len(diffs)
    typer.echo(f"{unchanged_count} fixture(s) unchanged.")

    if not write:
        typer.echo("This is a dry run — nothing was changed. Pass --write to apply.")
        return

    old_present_by_id = {entry.fixture_id: entry for entry in old_present_entries}
    merged_entries = tuple(
        preview_layout.LayoutEntry(
            fixture_id=entry.fixture_id,
            x=entry.x,
            y=entry.y,
            label=entry.label,
            kind=entry.kind,
            rotation=entry.rotation,
            pan_degrees=prior.pan_degrees,
            tilt_degrees=prior.tilt_degrees,
        )
        if (prior := old_present_by_id.get(entry.fixture_id)) is not None
        else entry
        for entry in fresh.entries
    )
    merged_layout = preview_layout.RigLayout(venue_id=venue_id, entries=merged_entries)
    preview_layout.save_layout(layout_path, merged_layout)
    typer.echo(f"Saved layout for venue {venue_id} to {layout_path}.")


# ---------------------------------------------------------------------------
# venue list — read-only venue discovery. Never mutates a database; never
# hides a venue (zero-fixture, or when the active pointer is stale).
# ---------------------------------------------------------------------------


@venue_app.command("list")
def venue_list() -> None:
    """List every venue in the working copy, with its fixture count. The
    active venue (lighting_property.ExecVenueId) is marked, if it still
    resolves to a real venue. Read-only, never writes anything.
    """
    with _readonly_working_copy(_USER_DB_NAME) as user_conn:
        entries = venues_repo.list_venues_with_fixture_counts(user_conn)
        active_id = venues_repo.get_exec_venue_id(user_conn)

    if not entries:
        typer.echo("No venues found.")
        return

    typer.echo("Venues:")
    for entry in entries:
        typer.echo(_format_venue_line(entry, active_id=active_id))
