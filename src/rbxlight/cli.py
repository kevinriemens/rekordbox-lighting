"""typer entrypoint. Every mutating command defaults to a dry run — see
rekordbox-lighting-architecture skill, "typer command shape — dry-run by
default".

Normal commands work against the WORKING COPY only (`db.resolve_path`,
default `live=False`) — never live. The only path to live is `rbxlight
pull`/`push` in `sync.py`.

Command bodies here are thin: parse flags -> call rbxlight.orchestration
-> render the result. All venue resolution, layout regenerate/install
orchestration, and preview pipeline logic lives in `orchestration.py` so a
future front-end can drive the same operations without importing typer.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, NoReturn

import typer

from rbxlight import db, orchestration, safety, sync
from rbxlight.experiments import ninth_bank
from rbxlight.macros import repo
from rbxlight.preview import layout as preview_layout
from rbxlight.venues import repo as venues_repo

app = typer.Typer(
    help="rbxlight — rekordbox 6 LightingDB CLI", invoke_without_command=True
)

macro_app = typer.Typer(help="Macro authoring commands")
app.add_typer(macro_app, name="macro")

layout_app = typer.Typer(help="Rig layout description commands")
app.add_typer(layout_app, name="layout")

venue_app = typer.Typer(help="Venue discovery commands")
app.add_typer(venue_app, name="venue")

experiment_app = typer.Typer(help="One-off, disposable experiments")
app.add_typer(experiment_app, name="experiment")

ninth_bank_app = typer.Typer(
    help="Provisionally add a ninth lighting bank (pattern=9) and repoint "
    "one track at it — fully reversible, working copy only."
)
experiment_app.add_typer(ninth_bank_app, name="ninth-bank")

_MACRO_DB_NAME = "macro.db3"
_USER_DB_NAME = "user.db3"


def _launch_menu() -> int:
    """Real, TTY-checked entrypoint into the interactive menu. Imports
    `rbxlight.menu` at FUNCTION scope only — see
    `tests/tui/test_structural_boundaries.py`, which asserts this module
    never imports `rbxlight.menu` at module scope.
    """
    import sys

    from rbxlight.menu import app as menu_app
    from rbxlight.menu import tty as menu_tty
    from rbxlight.menu.prompts import QuestionaryPrompter
    from rbxlight.menu.render import RichRenderer

    try:
        menu_tty.require_interactive_tty(sys.stdin, sys.stdout)
    except menu_tty.NotATtyError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc

    try:
        return menu_app.run_menu(QuestionaryPrompter(), RichRenderer())
    except KeyboardInterrupt:
        return 130


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """With no subcommand, launch the interactive menu instead of
    printing help.
    """
    if ctx.invoked_subcommand is not None:
        return
    raise typer.Exit(code=_launch_menu())


@app.command("tui")
def tui() -> None:
    """Launch the interactive menu — identical to running rbxlight with
    no arguments.
    """
    raise typer.Exit(code=_launch_menu())


class _NegativeSafeCommand(typer.core.TyperCommand):
    """A TyperCommand that accepts negative integer arguments (e.g. -1).

    Standard click/typer treats ``-1`` as an option flag, refusing it as a
    positional argument.  Setting ``ignore_unknown_options`` on the command's
    context lets the parser pass ``-1`` through as the argument value.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.context_settings = {"ignore_unknown_options": True}


def _fail(message: str, *, cause: BaseException | None = None) -> NoReturn:
    """Echo `message` and exit with code 1, chaining `cause` if given.

    Shared exception-to-exit translation for every command that reports a
    clean error instead of letting a raw exception surface.
    """
    typer.echo(message)
    raise typer.Exit(code=1) from cause


def _fail_missing_working_copy(exc: FileNotFoundError) -> NoReturn:
    """Shared `push` error: a working-copy file the plan/apply needed
    doesn't exist. Identical whether the miss happens during the dry-run
    plan or the actual write.
    """
    _fail(
        f"Push failed: {exc}. Has the working copy ever been pulled? "
        "Run `rbxlight pull` first.",
        cause=exc,
    )


def _echo_macro_listing(
    macros: list[repo.Macro], *, header: str, empty_message: str
) -> None:
    """Render a macro listing shared by `macro list` and `macro search`:
    an empty message when there are no results, else a header followed
    by one formatted line per macro.
    """
    if not macros:
        typer.echo(empty_message)
        return
    typer.echo(header)
    for macro in macros:
        typer.echo(_format_macro_line(macro))


@contextmanager
def _readonly_working_copy(db_name: str) -> Iterator[sqlite3.Connection]:
    """Resolve db_name in the working copy, require it exists, open it
    read-only, and guarantee close. Shared by every read-only
    working-copy command (`preview`, `layout regenerate`, `venue list`).

    Thin typer wrapper around `db.readonly_working_copy`: translates a
    missing working copy into the same clean `_fail` exit this command
    group has always produced.
    """
    try:
        with db.readonly_working_copy(db_name) as conn:
            yield conn
    except db.WorkingCopyMissingError as exc:
        _fail(f"Working copy not found at {exc.path}. Run `rbxlight pull` first.")


def _announce_venue_selection(venue: venues_repo.Venue, source: str) -> None:
    announce_source = "explicit" if source == "explicit" else "active venue"
    typer.echo(f"Venue: {venue.id} ({venue.name}) — selected via {announce_source}.")


def _format_macro_line(macro: repo.Macro) -> str:
    """Format a macro as a 2-space-indented summary line."""
    return f"  {macro.id}: {macro.name} ({macro.beats} beats)"


def _resolve_macro_scope(
    *, all: bool, user: bool = False, factory: bool = False, default: str
) -> str:
    """Resolve conflicting macro-scope CLI flags to a scope string.

    Checks for conflicting flags first, then returns the resolved scope.
    Raises typer.Exit(code=1) on conflict.
    """
    if all and factory:
        _fail("Flags --all and --factory cannot be used together.")
    if user and all:
        _fail("Flags --user and --all cannot be used together.")
    if all:
        return "all"
    if user:
        return "user"
    if factory:
        return "factory"
    return default


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


#: User-facing dry-run gate message — a tested contract, identical across
#: every mutating command.
_DRY_RUN_NOTICE = "This is a dry run — nothing was changed. Pass --write to apply."


def _resolve_venue_and_fixtures(
    user_conn: sqlite3.Connection, venue: int | None
) -> tuple[venues_repo.Venue, list[venues_repo.Fixture], str]:
    """Resolve a venue via orchestration.resolve_venue, translating its
    typed exceptions into the CLI's clean-exit error messages.
    """
    try:
        result = orchestration.resolve_venue(user_conn, venue)
    except orchestration.VenueNotFoundError as exc:
        listing = _venue_listing_text(user_conn)
        _fail(
            f"Venue not found: no venue with id {exc.venue_id}.\n"
            f"Valid venues:\n{listing}"
        )
    except orchestration.NoActiveVenueError:
        _fail(
            "No venue given and no active venue "
            "(lighting_property.ExecVenueId) is set. Pass --venue to "
            "select one explicitly."
        )
    except orchestration.StaleActiveVenueError as exc:
        listing = _venue_listing_text(user_conn)
        _fail(
            f"Active venue (lighting_property.ExecVenueId={exc.stale_venue_id}) is "
            f"stale — that venue no longer exists.\n"
            f"Valid venues:\n{listing}"
        )

    return result.venue, result.fixtures, result.source


def _resolve_and_announce_venue(
    venue: int | None,
) -> tuple[venues_repo.Venue, list[venues_repo.Fixture]]:
    """Resolve venue (see _resolve_venue_and_fixtures) against the
    working copy and announce the selection. Shared by every
    venue-aware layout command.
    """
    with _readonly_working_copy(_USER_DB_NAME) as user_conn:
        venue_obj, fixtures, source = _resolve_venue_and_fixtures(user_conn, venue)
    _announce_venue_selection(venue_obj, source)
    return venue_obj, fixtures


def _print_layout_diff_entry(diff: preview_layout.LayoutDiffEntry) -> None:
    """Render one LayoutDiffEntry: new, removed, or changed. Shared by
    `layout regenerate` and `layout install` — the "removed" case never
    fires for regenerate (its diff is always old-present vs fresh, and
    fresh covers every currently patched fixture), but the format is
    identical wherever it does apply.
    """
    if diff.old_x is None:
        typer.echo(
            f"New: {diff.label} (id={diff.fixture_id}) -> "
            f"({diff.new_x:.3f}, {diff.new_y:.3f}) @ {diff.new_rotation:.3f}."
        )
    elif diff.new_x is None:
        typer.echo(f"Removed: {diff.label} (id={diff.fixture_id}).")
    else:
        typer.echo(
            f"{diff.label} (id={diff.fixture_id}): "
            f"({diff.old_x:.3f}, {diff.old_y:.3f}) @ {diff.old_rotation:.3f} -> "
            f"({diff.new_x:.3f}, {diff.new_y:.3f}) @ {diff.new_rotation:.3f}"
        )


@macro_app.command("create")
def macro_create(
    name: str,
    beats: int,
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Create a new user macro. Prints the plan; only writes with --write."""
    plan = repo.build_create_macro_plan(
        name=name, beats=beats, target_path=db.resolve_path(_MACRO_DB_NAME)
    )
    typer.echo(
        f"Plan: create macro '{plan.name}' ({plan.beats} beats), "
        "all 25 fixture slots empty."
    )

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    with safety.working_copy_write(_MACRO_DB_NAME) as conn:
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
        plan = repo.build_delete_macro_plan(
            read_conn, macro_id=macro_id, target_path=path
        )
    except LookupError as exc:
        _fail(f"Macro not found: {exc}", cause=exc)
    finally:
        read_conn.close()

    typer.echo(
        f"Plan: delete macro '{plan.macro_name}' (id={plan.macro_id}, "
        f"beats={plan.beats})."
    )

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    try:
        with safety.working_copy_write(_MACRO_DB_NAME) as conn:
            repo.delete_macro(conn, macro_id)
    except repo.FactoryMacroImmutableError as exc:
        _fail(f"Refused: {exc}", cause=exc)

    typer.echo(f"Deleted macro '{plan.macro_name}' (id={plan.macro_id}).")


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
    output_path = Path(output) if output else Path(f"preview_{macro_id}.html")

    try:
        with (
            _readonly_working_copy(_MACRO_DB_NAME) as macro_conn,
            _readonly_working_copy(_USER_DB_NAME) as user_conn,
        ):
            venue_obj, fixtures, source = _resolve_venue_and_fixtures(user_conn, venue)
            _announce_venue_selection(venue_obj, source)
            orchestration.generate_preview(
                macro_conn,
                user_conn,
                macro_id,
                venue_obj.id,
                fixtures,
                orchestration.default_layout_dir(),
                output_path,
            )
    except orchestration.preview_payload.MacroNotFoundError as exc:
        _fail(f"Macro not found: {exc}", cause=exc)
    except orchestration.preview_payload.VenueNotFoundError as exc:
        _fail(f"Venue not found: {exc}", cause=exc)
    except orchestration.preview_payload.MissingLayoutEntryError as exc:
        _fail(f"Layout incomplete: {exc}", cause=exc)

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
        _fail(str(exc), cause=exc)

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
        try:
            plan = sync.build_push_plan(db.WORK_DIR, db.LIGHTINGDB)
        except FileNotFoundError as exc:
            _fail_missing_working_copy(exc)
        names = ", ".join(plan.db_names)
        typer.echo(f"Plan: push {names} from {plan.work_dir} to {plan.lightingdb_dir}.")
        typer.echo(_DRY_RUN_NOTICE)
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
        _fail(str(exc), cause=exc)
    except sync.StaleWorkingCopyError as exc:
        _fail(str(exc), cause=exc)
    except FileNotFoundError as exc:
        _fail_missing_working_copy(exc)

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
        _fail(
            f"No backup named '{from_}' found under {safety.BACKUP_ROOT}. "
            "Run `rbxlight restore` with no arguments to list available backups."
        )

    try:
        safety.preflight_restore(backup_dir)
    except safety.RekordboxRunningError as exc:
        _fail(str(exc), cause=exc)
    except safety.BackupCorruptedError as exc:
        _fail(str(exc), cause=exc)

    plan = safety.build_restore_plan(backup_dir, safety.LIGHTINGDB)
    typer.echo(f"This will overwrite the following live files from backup '{from_}':")
    for name in plan.file_names:
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
    reset_structure: bool = typer.Option(
        False,
        "--reset-structure",
        help="Reset the saved stage structure back to the default arch. "
        "Without this flag, a saved custom structure is never reset.",
    ),
) -> None:
    """Regenerate a venue's rig layout from the current algorithm and diff
    it against the saved layout. Position, rotation, label, and kind
    always come from the fresh generation; pan/tilt sweep calibration is
    preserved for every fixture that still exists — and so is the saved
    stage structure, unless --reset-structure opts into replacing it with
    the default arch. Dry run by default — never writes the saved layout
    file unless --write is given.
    """
    venue_obj, fixtures = _resolve_and_announce_venue(venue)
    venue_id = venue_obj.id
    layout_dir = orchestration.default_layout_dir()

    plan = orchestration.build_layout_regenerate_plan(
        venue_id, fixtures, layout_dir, reset_structure=reset_structure
    )

    if plan.structure_status == "reset":
        typer.echo("Structure: regenerated to the default arch.")
    elif plan.structure_status == "preserved":
        typer.echo("Structure: preserved (saved shape unchanged).")
    else:
        typer.echo("Structure: no previous layout — using the default arch.")

    for orphan in sorted(plan.orphans, key=lambda entry: entry.fixture_id):
        typer.echo(
            f"No longer in venue {venue_id}'s patch: "
            f"{orphan.label} (id={orphan.fixture_id})."
        )

    for diff in plan.diffs:
        _print_layout_diff_entry(diff)

    typer.echo(f"{plan.unchanged_count} fixture(s) unchanged.")

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
    orchestration.apply_layout_regenerate(
        venue_id, fixtures, layout_dir, reset_structure=reset_structure
    )
    typer.echo(f"Saved layout for venue {venue_id} to {layout_path}.")


# ---------------------------------------------------------------------------
# layout install — install a layout file exported by the offline
# visualizer as the saved layout for a venue. The export shares the
# saved-layout file's exact shape; the normalization frame is carried
# through unchanged, never recomputed (see preview.layout,
# NormalizationFrame).
# ---------------------------------------------------------------------------


@layout_app.command("install")
def layout_install(
    path: Path,
    venue: int = typer.Option(
        None,
        "--venue",
        help="Venue id. Defaults to the active venue (lighting_property.ExecVenueId).",
    ),
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    """Install a layout file exported by the offline visualizer as the
    saved layout for `venue`. Reports both fixture-placement and
    stage/truss changes against any existing saved layout; a first-time
    install is reported distinctly rather than diffed. Dry run by
    default — never writes the saved layout file unless --write is given.
    """
    venue_obj, fixtures = _resolve_and_announce_venue(venue)
    venue_id = venue_obj.id
    layout_dir = orchestration.default_layout_dir()

    try:
        plan = orchestration.build_layout_install_plan(
            path, venue_id, fixtures, layout_dir
        )
    except (
        preview_layout.InvalidSavedLayoutError,
        preview_layout.DegenerateStructureError,
    ) as exc:
        _fail(f"Refused: {exc}", cause=exc)
    except orchestration.LayoutVenueMismatchError as exc:
        _fail(
            f"Refused: {path} is a layout for venue {exc.incoming_venue_id}, but "
            f"the target is venue {exc.target_venue_id} ({venue_obj.name})."
        )

    labels_by_id = {entry.fixture_id: entry.label for entry in plan.incoming.entries}
    orphaned_incoming_ids = plan.missing_from_venue_fixture_ids
    for missing_id in orphaned_incoming_ids:
        typer.echo(
            f"No longer patched into venue {venue_id}: "
            f"{labels_by_id[missing_id]} (id={missing_id})."
        )

    if plan.existing is None:
        typer.echo("New file — no existing saved layout for this venue.")
    else:
        for diff in plan.fixture_diffs:
            _print_layout_diff_entry(diff)

        if plan.structure_changed:
            typer.echo("Structure/truss: changed.")

        if not plan.fixture_diffs and not plan.structure_changed:
            typer.echo("No changes.")

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    if orphaned_incoming_ids and not yes and not typer.confirm("Proceed anyway?"):
        typer.echo("Cancelled — nothing was written.")
        return

    orchestration.apply_layout_install(plan, layout_dir)
    layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
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


# ---------------------------------------------------------------------------
# macro list / macro search / macro show — read-only macro discovery.
# Never mutates a database; no --write flag, no guard, no backup.
# ---------------------------------------------------------------------------


@macro_app.command("list")
def macro_list(
    all: bool = typer.Option(False, "--all", help="Include factory macros."),
    factory: bool = typer.Option(False, "--factory", help="Factory macros only."),
) -> None:
    """List macros in the working copy. Default scope is user-only. Read-only,
    never writes anything.
    """
    scope = _resolve_macro_scope(all=all, factory=factory, default="user")

    with _readonly_working_copy(_MACRO_DB_NAME) as conn:
        macros = repo.list_macros(conn, scope=scope)

    _echo_macro_listing(macros, header="Macros:", empty_message="No macros found.")


@macro_app.command("search")
def macro_search(
    term: str,
    user: bool = typer.Option(False, "--user", help="Search user macros."),
    all: bool = typer.Option(False, "--all", help="Search all macros."),
) -> None:
    """Search macros by name. Default scope is factory — searching by name is
    how users find factory content. Read-only, never writes anything.
    """
    scope = _resolve_macro_scope(all=all, user=user, default="factory")

    with _readonly_working_copy(_MACRO_DB_NAME) as conn:
        results = repo.search_macros(conn, term, scope=scope)

    _echo_macro_listing(
        results, header="Search results:", empty_message="No macros found."
    )


@macro_app.command("show", cls=_NegativeSafeCommand)
def macro_show(
    macro_id: int,
    yaml: bool = typer.Option(False, "--yaml", help="Output as YAML."),
) -> None:
    """Show detailed metadata for a macro. Read-only, never writes anything."""
    with _readonly_working_copy(_MACRO_DB_NAME) as conn:
        try:
            macro = repo.get_macro(conn, macro_id)
        except LookupError as exc:
            _fail(f"Macro {macro_id} not found.", cause=exc)

        if yaml:
            from rbxlight.macros import yaml_io

            typer.echo(yaml_io.export_macro_yaml(conn, macro_id), nl=False)
            return

        slot_statuses = repo.get_slot_statuses(conn, macro_id)

    preset_label = "user" if macro.preset == 0 else "factory"
    enabled_label = "yes" if macro.enabled else "no"

    typer.echo(f"Macro {macro.id}: {macro.name}")
    typer.echo(f"  Beats: {macro.beats}")
    typer.echo(f"  Preset: {preset_label} ({macro.preset})")
    typer.echo(f"  Enabled: {enabled_label} ({macro.enabled})")
    typer.echo("  Fixture slots:")
    for slot in slot_statuses:
        status = "programmed" if slot.programmed else "empty"
        typer.echo(f"    {slot.slot_id}: {status}")


# ---------------------------------------------------------------------------
# experiment ninth-bank apply/revert — see rbxlight.experiments.ninth_bank.
# Deliberately NOT wired into rbxlight.menu — a one-off experimental
# command, not a supported interactive-menu action.
# ---------------------------------------------------------------------------


@ninth_bank_app.command("apply")
def experiment_ninth_bank_apply(
    source_pattern_id: int,
    content_id: int | None = typer.Argument(
        None,
        help="Track (content id) to repoint at the new bank. Optional — "
        "omit to add the bank without repointing any track (the default).",
    ),
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Provisionally create a ninth bank (macro_pattern, pattern=9) cloned
    from an existing bank's phase assignments. Repointing a track at it
    is OPTIONAL — omitting `content_id` (the default) never touches
    user.db3 at all, not even a read connection. Working copy only —
    never touches live. Refused if a prior apply is still outstanding
    (run `experiment ninth-bank revert` first).
    """
    macro_path = db.resolve_path(_MACRO_DB_NAME)
    macro_conn = db.connect_readonly(macro_path)
    user_path = db.resolve_path(_USER_DB_NAME)
    user_conn = db.connect_readonly(user_path) if content_id is not None else None
    try:
        plan = ninth_bank.build_apply_plan(
            macro_conn,
            user_conn,
            source_pattern_id=source_pattern_id,
            content_id=content_id,
            macro_db_path=macro_path,
            user_db_path=user_path,
        )
    except ninth_bank.NoSourceBankError as exc:
        _fail(f"Source bank not found: {exc}", cause=exc)
    except ninth_bank.NoTargetTrackError as exc:
        _fail(f"Target track not found: {exc}", cause=exc)
    finally:
        macro_conn.close()
        if user_conn is not None:
            user_conn.close()

    plan_prefix = (
        f"Plan: add bank pattern={plan.new_pattern_value} (id={plan.new_pattern_id}), "
        f"cloning {plan.phase_count} phase assignment(s) from pattern "
        f"{plan.source_pattern_id}; "
    )
    if plan.content_id is not None:
        typer.echo(
            plan_prefix + f"repoint content {plan.content_id} "
            f"(currently pattern {plan.original_macro_pattern_id})."
        )
    else:
        typer.echo(plan_prefix + "no track will be repointed.")

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    try:
        ninth_bank.apply_ninth_bank(plan, state_path=ninth_bank.default_state_path())
    except ninth_bank.NinthBankAlreadyAppliedError as exc:
        _fail(str(exc), cause=exc)

    applied_suffix = (
        f"content {plan.content_id} repointed."
        if plan.content_id is not None
        else "no track repointed."
    )
    typer.echo(f"Applied: new bank pattern id={plan.new_pattern_id}; " + applied_suffix)


@ninth_bank_app.command("revert")
def experiment_ninth_bank_revert(
    write: bool = typer.Option(
        False, "--write", help="Apply the change. Default is a dry run."
    ),
) -> None:
    """Undo an outstanding `experiment ninth-bank apply`: remove the
    provisional bank and, only if a track was repointed by that apply,
    restore its original macro_pattern_id. Reads undo state from disk —
    works even in a separate invocation from the apply that created it.
    """
    state_path = ninth_bank.default_state_path()
    try:
        plan = ninth_bank.build_revert_plan(state_path)
    except ninth_bank.CorruptNinthBankStateError as exc:
        _fail(str(exc), cause=exc)

    if plan.nothing_to_revert:
        typer.echo("Nothing to revert — no ninth-bank change is outstanding.")
        return

    plan_suffix = (
        f"restore content {plan.content_id} to pattern "
        f"{plan.original_macro_pattern_id}."
        if plan.content_id is not None
        else "no track will be restored (none was repointed)."
    )
    typer.echo(f"Plan: remove bank pattern id={plan.new_pattern_id}; " + plan_suffix)

    if not write:
        typer.echo(_DRY_RUN_NOTICE)
        return

    ninth_bank.revert_ninth_bank(plan, state_path=state_path)
    typer.echo("Reverted.")
