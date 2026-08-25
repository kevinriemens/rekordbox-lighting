"""Tests for rbxlight.cli — dry-run-by-default contract for mutating
commands, plus the read-only `preview` command. Contract:
rekordbox-data-safety skill (rule 7, "DRY-RUN BY DEFAULT") and
rekordbox-lighting-architecture skill ("typer command shape").
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from rbxlight import cli, db, safety
from rbxlight.experiments import ninth_bank
from rbxlight.macros import yaml_io
from rbxlight.preview import layout as preview_layout
from rbxlight.venues import repo as venues_repo
from tests.conftest import make_macro_db, make_user_db
from tests.fixtures.content_fixtures import a_track
from tests.fixtures.macro_fixtures import (
    ALL_25_SLOT_IDS,
    a_factory_macro,
    a_user_macro,
    a_valid_slot_payload,
    insert_macro_data_row,
    insert_macro_row,
    sentinel_macro_rows,
)
from tests.fixtures.pattern_fixtures import a_high_energy_bank
from tests.fixtures.venue_fixtures import (
    ACTIVE_VENUE_NAME,
    a_multi_venue_database,
    a_par_fixture,
    a_small_full_arc_venue,
    a_venue,
    set_lighting_property,
)

runner = CliRunner()


def assert_no_unhandled_exception(result: Result) -> None:
    """Assert a refusal was a clean, handled exit — not a crash.

    CliRunner.invoke (typer's runner wraps click's) unconditionally sets
    ``result.exception`` to the ``SystemExit`` it caught whenever the exit
    code is nonzero, whether that ``SystemExit`` came from a deliberate
    ``typer.Exit`` or from click itself. So for any refused command,
    ``exception is None`` is unreachable — ``exit_code != 0`` and
    ``exception is None`` can never both be true. The real signal that the
    command didn't crash is that the *only* exception CliRunner saw was that
    interpreter-level ``SystemExit``, not some other unhandled error.
    """
    assert isinstance(result.exception, SystemExit), (
        f"expected a clean SystemExit, got {result.exception!r}"
    )


@pytest.fixture
def rekordbox_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        returncode = 1

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


@pytest.fixture
def rekordbox_running(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        returncode = 0

    monkeypatch.setattr(safety.subprocess, "run", lambda *a, **k: _Result())


@pytest.fixture
def work_macro_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    db_path = make_macro_db(work_dir / "macro.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)
    return db_path


class TestMacroCreateDryRun:
    def test_should_change_nothing_without_the_write_flag(
        self, work_macro_db: Path
    ) -> None:
        # Given: the current (unwritten-to) working-copy macro.db3
        original_bytes = work_macro_db.read_bytes()

        # When: running the mutating command without --write
        result = runner.invoke(cli.app, ["macro", "create", "NEW MACRO", "32"])

        # Then: the database is byte-for-byte unchanged
        assert work_macro_db.read_bytes() == original_bytes
        assert result.exit_code == 0

    def test_should_report_a_dry_run_without_the_write_flag(
        self, work_macro_db: Path
    ) -> None:
        # Given: no --write flag
        # When: running the mutating command
        result = runner.invoke(cli.app, ["macro", "create", "NEW MACRO", "32"])

        # Then: the output tells the user this was a preview, not a write
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout

    def test_should_apply_the_change_when_write_flag_is_given(
        self, work_macro_db: Path
    ) -> None:
        # Given: the current (empty) working-copy macro.db3
        # When: running the mutating command with --write
        result = runner.invoke(
            cli.app, ["macro", "create", "NEW MACRO", "32", "--write"]
        )

        # Then: the database now contains the new macro
        assert result.exit_code == 0
        conn = sqlite3.connect(work_macro_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM macro WHERE name = 'NEW MACRO'"
        ).fetchone()[0]
        conn.close()
        assert count == 1


@pytest.fixture
def work_preview_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """A working copy with one macro + one venue seeded, wired up as the
    CLI's default (WORK_DIR) resolution target."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    macro_path = make_macro_db(work_dir / "macro.db3")
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    macro_conn = sqlite3.connect(macro_path)
    macro_id = a_user_macro(macro_conn, macro_id=10008, name="AI TEST SWEEP", beats=32)
    macro_conn.close()

    user_conn = sqlite3.connect(user_path)
    venue_id = a_small_full_arc_venue(user_conn)
    set_lighting_property(user_conn, "ExecVenueId", str(venue_id))
    user_conn.close()

    return {
        "work_dir": work_dir,
        "macro_path": macro_path,
        "user_path": user_path,
        "macro_id": macro_id,
        "venue_id": venue_id,
    }


class TestPreviewCommand:
    def test_should_have_no_write_flag(self) -> None:
        # Given: the preview command's help text
        result = runner.invoke(cli.app, ["preview", "--help"])

        # Then: unlike mutating commands, there is no --write option to gate it
        assert "--write" not in result.stdout

    def test_should_succeed_without_any_special_flag(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a seeded working copy, no flags beyond the macro id
        output_path = tmp_path / "out.html"

        # When: running preview with only the required macro id
        result = runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--output",
                str(output_path),
            ],
        )

        # Then: it succeeds — read-only commands need no confirmation flag
        assert result.exit_code == 0
        assert output_path.exists()

    def test_should_embed_the_payload_in_the_output_file(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a seeded working copy
        output_path = tmp_path / "out.html"

        # When: running preview
        runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--output",
                str(output_path),
            ],
        )

        # Then: the macro's identity appears in the rendered document
        content = output_path.read_text(encoding="utf-8")
        assert "AI TEST SWEEP" in content

    def test_should_resolve_the_active_venue_when_venue_is_omitted(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: no --venue flag, but lighting_property.ExecVenueId is set
        output_path = tmp_path / "out.html"

        # When: running preview without --venue
        result = runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--output",
                str(output_path),
            ],
        )

        # Then: it succeeds by resolving the active venue automatically
        assert result.exit_code == 0
        # And: the output confirms which venue was used, by id and name,
        # and that it came from the active-venue fallback (not an
        # explicit --venue choice)
        assert str(work_preview_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout
        assert "active venue" in result.stdout.lower()

    def test_should_confirm_the_explicit_venue_used_by_id_and_name(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a second venue that is NOT the active one
        output_path = tmp_path / "out.html"
        user_conn = sqlite3.connect(work_preview_dbs["user_path"])
        other_venue_id = a_venue(user_conn, venue_id=55, name="Second Room")
        user_conn.close()

        # When: running preview with an explicit --venue different from
        # the active one
        result = runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--venue",
                str(other_venue_id),
                "--output",
                str(output_path),
            ],
        )

        # Then: it succeeds and confirms the EXPLICIT venue was used, by
        # id and name, distinguishable from the active-venue-fallback case
        assert result.exit_code == 0
        assert str(other_venue_id) in result.stdout
        assert "Second Room" in result.stdout
        assert "explicit" in result.stdout.lower()

    def test_should_fail_clearly_when_no_venue_given_and_none_is_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with a macro but no ExecVenueId set
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        macro_conn = sqlite3.connect(macro_path)
        macro_id = a_user_macro(
            macro_conn, macro_id=10008, name="NO VENUE TEST", beats=32
        )
        macro_conn.close()

        # When: running preview with no --venue
        result = runner.invoke(cli.app, ["preview", str(macro_id)])

        # Then: a clear, handled failure — not an unhandled traceback —
        # explaining no active venue is set and how to proceed
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "no active venue" in result.stdout.lower()
        assert "--venue" in result.stdout

    def test_should_fail_clearly_when_the_active_venue_pointer_is_stale(
        self, work_preview_dbs: dict
    ) -> None:
        # Given: ExecVenueId is overwritten to point at a venue that no
        # longer exists (the real venue from work_preview_dbs still does)
        user_conn = sqlite3.connect(work_preview_dbs["user_path"])
        set_lighting_property(user_conn, "ExecVenueId", "999999")
        user_conn.close()

        # When: running preview with no --venue
        result = runner.invoke(cli.app, ["preview", str(work_preview_dbs["macro_id"])])

        # Then: a distinct, clean failure from the "no active venue set"
        # case — naming the stale id and enumerating the still-valid venues
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "999999" in result.stdout
        assert (
            "no longer exist" in result.stdout.lower()
            or "stale" in result.stdout.lower()
        )
        assert str(work_preview_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout

    def test_should_default_the_output_path_when_omitted(
        self, work_preview_dbs: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: no --output flag, running from a known cwd
        monkeypatch.chdir(tmp_path)

        # When: running preview with no output path
        result = runner.invoke(cli.app, ["preview", str(work_preview_dbs["macro_id"])])

        # Then: it succeeds and writes a file somewhere discoverable under cwd
        assert result.exit_code == 0
        assert any(tmp_path.glob("*.html"))

    def test_should_error_clearly_for_an_unknown_macro(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a macro id that doesn't exist
        output_path = tmp_path / "out.html"

        # When: running preview
        result = runner.invoke(
            cli.app, ["preview", "999999", "--output", str(output_path)]
        )

        # Then: it fails with a non-zero exit, a message naming the problem
        # (not a bare traceback/generic exception), and no silent output
        assert result.exit_code != 0
        assert "999999" in result.stdout or (
            result.exception is not None and "999999" in str(result.exception)
        )
        assert not output_path.exists()

    def test_should_error_clearly_for_an_unknown_venue(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an explicit venue id that doesn't exist
        output_path = tmp_path / "out.html"

        # When: running preview against that venue
        result = runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--venue",
                "999999",
                "--output",
                str(output_path),
            ],
        )

        # Then: it fails with a message naming the problem, not silently
        assert result.exit_code != 0
        assert "999999" in result.stdout or (
            result.exception is not None and "999999" in str(result.exception)
        )
        assert not output_path.exists()
        # And: the error enumerates the valid venues so the user can retry
        assert str(work_preview_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout

    def test_should_never_modify_the_source_databases(
        self, work_preview_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: the current (seeded) working-copy databases
        macro_bytes_before = Path(work_preview_dbs["macro_path"]).read_bytes()
        user_bytes_before = Path(work_preview_dbs["user_path"]).read_bytes()
        output_path = tmp_path / "out.html"

        # When: running preview
        runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--output",
                str(output_path),
            ],
        )

        # Then: both databases are byte-for-byte unchanged
        assert Path(work_preview_dbs["macro_path"]).read_bytes() == macro_bytes_before
        assert Path(work_preview_dbs["user_path"]).read_bytes() == user_bytes_before

    def test_should_never_touch_the_live_lightingdb_directory(
        self,
        work_preview_dbs: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a live directory that does not even exist
        nonexistent_live_dir = tmp_path / "never-created-live-dir"
        monkeypatch.setattr(db, "LIGHTINGDB", nonexistent_live_dir)
        output_path = tmp_path / "out.html"

        # When: running preview
        result = runner.invoke(
            cli.app,
            [
                "preview",
                str(work_preview_dbs["macro_id"]),
                "--output",
                str(output_path),
            ],
        )

        # Then: it succeeds anyway — proof it never resolved a live path
        assert result.exit_code == 0
        assert not nonexistent_live_dir.exists()


# ---------------------------------------------------------------------------
# `rbxlight pull` — live -> working copy. Applies immediately, no dry-run
# gate (rekordbox-data-safety skill, "Working copy model"). Only ever
# writes to the disposable working area.
# ---------------------------------------------------------------------------


@pytest.fixture
def live_lightingdb_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    live_dir = tmp_path / "live-lightingdb"
    live_dir.mkdir()
    (live_dir / "macro.db3").write_bytes(b"macro-live-v1")
    (live_dir / "user.db3").write_bytes(b"user-live-v1")
    monkeypatch.setattr(db, "LIGHTINGDB", live_dir)
    return live_dir


@pytest.fixture
def cli_work_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    work_dir = tmp_path / "work"
    monkeypatch.setattr(db, "WORK_DIR", work_dir)
    return work_dir


@pytest.fixture
def cli_backup_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    backup_root = tmp_path / "backups"
    monkeypatch.setattr(safety, "BACKUP_ROOT", backup_root)
    return backup_root


class TestPullCommand:
    def test_should_copy_databases_into_the_working_area(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a live LightingDB dir and an empty working area
        # When: running pull
        result = runner.invoke(cli.app, ["pull"])

        # Then: it succeeds and both databases now exist in the working copy
        assert result.exit_code == 0
        assert (cli_work_dir / "macro.db3").read_bytes() == b"macro-live-v1"
        assert (cli_work_dir / "user.db3").read_bytes() == b"user-live-v1"

    def test_should_report_which_files_it_copied_and_where(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given/When: running pull
        result = runner.invoke(cli.app, ["pull"])

        # Then: the user is told what landed where
        assert "macro.db3" in result.stdout
        assert "user.db3" in result.stdout
        assert str(cli_work_dir) in result.stdout

    def test_should_refuse_when_rekordbox_is_running(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        rekordbox_running: None,
    ) -> None:
        # Given: rekordbox is running
        # When: running pull
        result = runner.invoke(cli.app, ["pull"])

        # Then: it refuses cleanly, and nothing is created in the working area
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not cli_work_dir.exists() or not any(cli_work_dir.iterdir())


# ---------------------------------------------------------------------------
# `rbxlight push` — working copy -> live. Dry run by default; the apply
# flag is stale-write protected; `--force` bypasses ONLY that staleness
# check (rekordbox-data-safety skill, rule 10).
# ---------------------------------------------------------------------------


class TestPushCommand:
    def test_should_default_to_a_dry_run_that_changes_nothing(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pulled working copy
        runner.invoke(cli.app, ["pull"])
        live_macro_bytes = (live_lightingdb_dir / "macro.db3").read_bytes()

        # When: running push without --write
        result = runner.invoke(cli.app, ["push"])

        # Then: nothing changed — no backup, live untouched, told it's a dry run
        assert result.exit_code == 0
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout
        assert (live_lightingdb_dir / "macro.db3").read_bytes() == live_macro_bytes
        assert not cli_backup_root.exists() or list(cli_backup_root.glob("*")) == []

    def test_should_push_and_report_backup_location_when_write_flag_given(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pulled, then locally edited working copy
        runner.invoke(cli.app, ["pull"])
        (cli_work_dir / "macro.db3").write_bytes(b"edited-locally")

        # When: pushing with --write
        result = runner.invoke(cli.app, ["push", "--write"])

        # Then: live reflects the change, and the backup location is reported
        assert result.exit_code == 0
        assert (live_lightingdb_dir / "macro.db3").read_bytes() == b"edited-locally"
        backup_dirs = list(cli_backup_root.glob("*"))
        assert len(backup_dirs) == 1
        assert backup_dirs[0].name in result.stdout

    def test_should_refuse_when_rekordbox_is_running_even_with_write(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_running: None,
    ) -> None:
        # Given: rekordbox is running
        # When: pushing with --write
        result = runner.invoke(cli.app, ["push", "--write"])

        # Then: refused cleanly, non-zero exit, no backup taken
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not cli_backup_root.exists() or list(cli_backup_root.glob("*")) == []

    def test_should_refuse_a_stale_working_copy_and_tell_the_user_to_pull_again(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pull, then live drifting before push (rekordbox or
        # something else touched it)
        runner.invoke(cli.app, ["pull"])
        (live_lightingdb_dir / "macro.db3").write_bytes(b"drifted-on-live")

        # When: pushing with --write, no --force
        result = runner.invoke(cli.app, ["push", "--write"])

        # Then: refused non-zero, told to pull again, live untouched
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "pull" in result.stdout.lower()
        assert (live_lightingdb_dir / "macro.db3").read_bytes() == b"drifted-on-live"

    def test_should_not_take_a_backup_when_refusing_a_stale_push(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a stale working copy
        runner.invoke(cli.app, ["pull"])
        (live_lightingdb_dir / "user.db3").write_bytes(b"drifted-on-live")

        # When: pushing with --write, refused
        runner.invoke(cli.app, ["push", "--write"])

        # Then: no backup was taken for a refused push
        assert not cli_backup_root.exists() or list(cli_backup_root.glob("*")) == []

    def test_should_bypass_only_staleness_with_force_and_still_take_a_backup(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a pull, then live drifting, then a local working-copy edit
        runner.invoke(cli.app, ["pull"])
        (live_lightingdb_dir / "macro.db3").write_bytes(b"drifted-on-live")
        (cli_work_dir / "macro.db3").write_bytes(b"edited-locally")

        # When: pushing with --write --force
        result = runner.invoke(cli.app, ["push", "--write", "--force"])

        # Then: the push proceeds despite the drift, and a backup was still taken
        assert result.exit_code == 0
        assert (live_lightingdb_dir / "macro.db3").read_bytes() == b"edited-locally"
        assert len(list(cli_backup_root.glob("*"))) == 1

    def test_should_still_refuse_when_rekordbox_is_running_even_with_force(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_running: None,
    ) -> None:
        # Given: rekordbox running, --force given
        # When: pushing with --write --force
        result = runner.invoke(cli.app, ["push", "--write", "--force"])

        # Then: still refused — force bypasses ONLY the staleness check
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_not_blow_up_when_working_copy_was_never_pulled(
        self,
        live_lightingdb_dir: Path,
        cli_work_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a working area with databases but no .pull-state.json
        # (never pulled)
        cli_work_dir.mkdir(parents=True, exist_ok=True)
        (cli_work_dir / "macro.db3").write_bytes(b"never-pulled")
        (cli_work_dir / "user.db3").write_bytes(b"never-pulled")

        # When: pushing with --write
        result = runner.invoke(cli.app, ["push", "--write"])

        # Then: a clear, handled failure — not an unhandled traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)


# ---------------------------------------------------------------------------
# `rbxlight restore` — the panic-button command. No identifier lists
# backups; a given identifier guards, verifies, confirms, then restores.
# ---------------------------------------------------------------------------


class TestRestoreCommand:
    @pytest.fixture
    def restore_live_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        live_dir = tmp_path / "live-lightingdb"
        live_dir.mkdir()
        (live_dir / "macro.db3").write_bytes(b"macro-live-current")
        (live_dir / "user.db3").write_bytes(b"user-live-current")
        monkeypatch.setattr(safety, "LIGHTINGDB", live_dir)
        return live_dir

    def test_should_list_backups_newest_first_and_change_nothing_when_no_id_given(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: two existing backups
        first = safety.backup_all("trigger one")
        second = safety.backup_all("trigger two")
        live_bytes_before = (restore_live_dir / "macro.db3").read_bytes()

        # When: running restore with no backup id
        result = runner.invoke(cli.app, ["restore"])

        # Then: lists both, newest first, restores nothing, exits zero
        assert result.exit_code == 0
        assert result.stdout.index(second.name) < result.stdout.index(first.name)
        assert (restore_live_dir / "macro.db3").read_bytes() == live_bytes_before

    def test_should_say_plainly_when_there_are_no_backups(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: no backups at all (backup root doesn't even exist)
        assert not cli_backup_root.exists()

        # When: running restore with no backup id
        result = runner.invoke(cli.app, ["restore"])

        # Then: it says so plainly rather than crashing, and exits zero
        assert result.exit_code == 0
        assert "no backup" in result.stdout.lower()

    def test_should_refuse_when_rekordbox_is_running(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_running: None,
    ) -> None:
        # Given: a valid backup, but rekordbox is running
        backup_dir = safety.backup_all("trigger")

        # When: restoring it
        result = runner.invoke(cli.app, ["restore", "--from", backup_dir.name, "--yes"])

        # Then: refused cleanly, live untouched
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert (restore_live_dir / "macro.db3").read_bytes() == b"macro-live-current"

    def test_should_refuse_a_corrupted_backup_before_overwriting_anything(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a backup whose recorded checksum no longer matches its contents
        backup_dir = safety.backup_all("trigger")
        (backup_dir / "macro.db3").write_bytes(b"TAMPERED")

        # When: restoring it, even with --yes
        result = runner.invoke(cli.app, ["restore", "--from", backup_dir.name, "--yes"])

        # Then: refused non-zero, live untouched by the refused restore, no traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert (restore_live_dir / "macro.db3").read_bytes() == b"macro-live-current"

    def test_should_refuse_an_unknown_backup_identifier(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: no backup named this
        # When: restoring a nonexistent identifier
        result = runner.invoke(
            cli.app, ["restore", "--from", "does-not-exist", "--yes"]
        )

        # Then: refused non-zero, no traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_restore_nothing_when_the_user_declines_confirmation(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a valid backup, then a live change since
        backup_dir = safety.backup_all("trigger")
        (restore_live_dir / "macro.db3").write_bytes(b"changed-since-backup")

        # When: restoring interactively and declining
        result = runner.invoke(
            cli.app, ["restore", "--from", backup_dir.name], input="n\n"
        )

        # Then: exits without error, nothing restored
        assert result.exit_code == 0
        assert (restore_live_dir / "macro.db3").read_bytes() == b"changed-since-backup"

    def test_should_show_what_will_be_overwritten_before_confirming(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a valid backup
        backup_dir = safety.backup_all("trigger")

        # When: restoring interactively (declining, to inspect only the prompt)
        result = runner.invoke(
            cli.app, ["restore", "--from", backup_dir.name], input="n\n"
        )

        # Then: the user was shown what would be overwritten before confirming
        assert "macro.db3" in result.stdout

    def test_should_restore_live_data_when_confirmed(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a valid backup of the original state, then a live change
        backup_dir = safety.backup_all("trigger")
        (restore_live_dir / "macro.db3").write_bytes(b"changed-since-backup")

        # When: restoring and confirming
        result = runner.invoke(
            cli.app, ["restore", "--from", backup_dir.name], input="y\n"
        )

        # Then: live is back to exactly the backed-up state
        assert result.exit_code == 0
        assert (restore_live_dir / "macro.db3").read_bytes() == b"macro-live-current"

    def test_should_skip_the_prompt_with_yes_flag(
        self,
        restore_live_dir: Path,
        cli_backup_root: Path,
        rekordbox_not_running: None,
    ) -> None:
        # Given: a valid backup, then a live change
        backup_dir = safety.backup_all("trigger")
        (restore_live_dir / "macro.db3").write_bytes(b"changed-since-backup")

        # When: restoring with --yes and no input available at all
        result = runner.invoke(cli.app, ["restore", "--from", backup_dir.name, "--yes"])

        # Then: it proceeds without prompting
        assert result.exit_code == 0
        assert (restore_live_dir / "macro.db3").read_bytes() == b"macro-live-current"


# ---------------------------------------------------------------------------
# `rbxlight macro delete <macro_id>` — dry run by default; operates on the
# working copy only; refuses factory content (preset=1, including the
# sentinel ids).
# ---------------------------------------------------------------------------


class TestMacroDeleteCommand:
    def test_should_print_the_macro_name_and_change_nothing_by_default(
        self, work_macro_db: Path
    ) -> None:
        # Given: a user macro in the working copy
        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10005, name="DELETE ME", beats=32)
        conn.close()
        original_bytes = work_macro_db.read_bytes()

        # When: running macro delete without --write
        result = runner.invoke(cli.app, ["macro", "delete", "10005"])

        # Then: the macro's name is shown, and nothing changed
        assert result.exit_code == 0
        assert "DELETE ME" in result.stdout
        assert work_macro_db.read_bytes() == original_bytes

    def test_should_delete_the_macro_and_all_its_data_rows_when_write_flag_given(
        self, work_macro_db: Path
    ) -> None:
        # Given: a user macro with its full 25-row macro_data set
        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10005, name="DELETE ME", beats=32)
        conn.close()

        # When: running macro delete with --write
        result = runner.invoke(cli.app, ["macro", "delete", "10005", "--write"])

        # Then: both the macro row and every one of its macro_data rows are gone
        assert result.exit_code == 0
        conn = sqlite3.connect(work_macro_db)
        macro_count = conn.execute(
            "SELECT COUNT(*) FROM macro WHERE id = 10005"
        ).fetchone()[0]
        data_count = conn.execute(
            "SELECT COUNT(*) FROM macro_data WHERE macro_id = 10005"
        ).fetchone()[0]
        conn.close()
        assert macro_count == 0
        assert data_count == 0

    def test_should_refuse_to_delete_an_ordinary_factory_macro(
        self, work_macro_db: Path
    ) -> None:
        # Given: an ordinary factory (preset=1) macro
        conn = sqlite3.connect(work_macro_db)
        a_factory_macro(conn, macro_id=61, name="FACTORY MACRO")
        conn.close()
        original_bytes = work_macro_db.read_bytes()

        # When: attempting to delete it, even with --write
        result = runner.invoke(cli.app, ["macro", "delete", "61", "--write"])

        # Then: refused, non-zero exit, naming the reason, nothing changed
        assert result.exit_code != 0
        assert "factory" in result.stdout.lower()
        assert work_macro_db.read_bytes() == original_bytes

    @pytest.mark.parametrize("sentinel_id", [-1, 10000])
    def test_should_refuse_to_delete_sentinel_macro_ids(
        self, work_macro_db: Path, sentinel_id: int
    ) -> None:
        # Given: the sentinel rows (id=-1 factory, id=10000 SEPARATOR)
        conn = sqlite3.connect(work_macro_db)
        sentinel_macro_rows(conn)
        conn.close()
        original_bytes = work_macro_db.read_bytes()

        # When: attempting to delete a sentinel id, even with --write
        result = runner.invoke(
            cli.app, ["macro", "delete", str(sentinel_id), "--write"]
        )

        # Then: refused, non-zero exit, nothing changed
        assert result.exit_code != 0
        assert work_macro_db.read_bytes() == original_bytes

    def test_should_allow_deleting_the_lowest_legitimate_user_macro_id(
        self, work_macro_db: Path
    ) -> None:
        # Given: a user macro at the lowest legal user id (10001)
        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10001, name="LOWEST USER MACRO")
        conn.close()

        # When: deleting it with --write
        result = runner.invoke(cli.app, ["macro", "delete", "10001", "--write"])

        # Then: it succeeds — this id is user-owned, not factory
        assert result.exit_code == 0
        conn = sqlite3.connect(work_macro_db)
        count = conn.execute("SELECT COUNT(*) FROM macro WHERE id = 10001").fetchone()[
            0
        ]
        conn.close()
        assert count == 0

    def test_should_error_clearly_for_a_nonexistent_macro_id(
        self, work_macro_db: Path
    ) -> None:
        # Given: no macro with this id
        # When: attempting to delete it
        result = runner.invoke(cli.app, ["macro", "delete", "555555"])

        # Then: a clear, handled failure — not an unhandled traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_never_touch_the_live_lightingdb_directory(
        self, work_macro_db: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: a live directory that does not even exist
        nonexistent_live_dir = tmp_path / "never-created-live-dir"
        monkeypatch.setattr(db, "LIGHTINGDB", nonexistent_live_dir)
        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10005, name="DELETE ME")
        conn.close()

        # When: deleting on the working copy
        result = runner.invoke(cli.app, ["macro", "delete", "10005", "--write"])

        # Then: succeeds anyway — proof it never resolved a live path
        assert result.exit_code == 0
        assert not nonexistent_live_dir.exists()


# ---------------------------------------------------------------------------
# `rbxlight layout regenerate` — the supported cure for stale, algorithm-
# preserved layout positions. Dry run by default; must NEVER wipe user
# pan/tilt calibration on apply.
# ---------------------------------------------------------------------------


@pytest.fixture
def work_layout_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    user_conn = sqlite3.connect(user_path)
    venue_id = a_small_full_arc_venue(user_conn)
    set_lighting_property(user_conn, "ExecVenueId", str(venue_id))
    user_conn.close()

    return {"work_dir": work_dir, "user_path": user_path, "venue_id": venue_id}


class TestLayoutRegenerateCommand:
    def test_should_not_create_a_layout_file_on_first_dry_run(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: no layout file has ever been generated for this venue
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        assert not layout_path.exists()

        # When: running regenerate without --write
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: it succeeds, and still no file was created
        assert result.exit_code == 0
        assert not layout_path.exists()

    def test_should_report_a_dry_run_by_default(self, work_layout_dbs: dict) -> None:
        # Given: no --write flag
        # When: running regenerate
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: told this was a preview
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout

    def test_should_leave_the_saved_layout_byte_for_byte_unchanged_on_dry_run(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a layout already generated once
        first = runner.invoke(cli.app, ["layout", "regenerate", "--write"])
        assert first.exit_code == 0
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        original_bytes = layout_path.read_bytes()

        # When: running regenerate again without --write
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: it succeeds, and the saved file is untouched
        assert result.exit_code == 0
        assert layout_path.read_bytes() == original_bytes

    def test_should_overwrite_the_saved_layout_when_write_flag_given(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: an existing saved layout, hand-adjusted by the user to a
        # position the current algorithm would never itself produce
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        existing = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=1, x=0.99, y=0.99, label="LM70S #1", kind="moving_head"
                ),
            ),
        )
        preview_layout.save_layout(layout_path, existing)

        # When: regenerating with --write
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: the saved layout now reflects the freshly generated position
        assert result.exit_code == 0
        regenerated = preview_layout.load_layout(layout_path)
        entry = next(e for e in regenerated.entries if e.fixture_id == 1)
        assert (entry.x, entry.y) != (0.99, 0.99)

    def test_should_preserve_pan_and_tilt_calibration_across_regeneration(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved layout with hand-calibrated pan/tilt sweep values
        # that don't match the algorithm's defaults
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        existing = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=1,
                    x=0.5,
                    y=0.5,
                    label="LM70S #1",
                    kind="moving_head",
                    rotation=10.0,
                    pan_degrees=123.0,
                    tilt_degrees=45.0,
                ),
            ),
        )
        preview_layout.save_layout(layout_path, existing)

        # When: regenerating with --write (algorithm output for position/
        # rotation is reset — calibration must not be)
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: this fixture's pan/tilt calibration survived regeneration
        assert result.exit_code == 0
        regenerated = preview_layout.load_layout(layout_path)
        entry = next(e for e in regenerated.entries if e.fixture_id == 1)
        assert entry.pan_degrees == 123.0
        assert entry.tilt_degrees == 45.0

    def test_should_regenerate_without_crashing_when_calibration_was_never_saved(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a layout file written before sweep-calibration existed —
        # pan_degrees/tilt_degrees are simply absent from the JSON
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_payload = {
            "venue_id": work_layout_dbs["venue_id"],
            "entries": [
                {
                    "fixture_id": 1,
                    "x": 0.5,
                    "y": 0.5,
                    "label": "LM70S #1",
                    "kind": "moving_head",
                }
            ],
        }
        layout_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

        # When: regenerating with --write
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: it succeeds rather than crashing on the missing keys
        assert result.exit_code == 0

    def test_should_report_a_fixture_removed_from_the_patch_rather_than_silently_dropping_it(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved layout entry for a fixture no longer patched into the venue
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        existing = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=999, x=0.5, y=0.5, label="Removed Fixture", kind="par"
                ),
            ),
        )
        preview_layout.save_layout(layout_path, existing)

        # When: regenerating (dry run is enough — this is a reporting concern)
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: the orphan is named, not silently discarded
        assert result.exit_code == 0
        assert "999" in result.stdout or "Removed Fixture" in result.stdout

    def test_should_use_the_explicit_venue_when_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a venue that is not the active one
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        user_path = make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        user_conn = sqlite3.connect(user_path)
        a_venue(user_conn, venue_id=7, name="Explicit Venue")
        a_par_fixture(user_conn, fixture_id=1, venue_id=7)
        user_conn.close()

        # When: regenerating with an explicit --venue, no ExecVenueId set
        result = runner.invoke(cli.app, ["layout", "regenerate", "--venue", "7"])

        # Then: it succeeds against the explicitly named venue
        assert result.exit_code == 0
        # And: the output confirms the venue used, by id and name, and
        # that it came from the explicit selection (not a fallback)
        assert "7" in result.stdout
        assert "Explicit Venue" in result.stdout
        assert "explicit" in result.stdout.lower()

    def test_should_confirm_the_active_venue_used_when_venue_is_omitted(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: no --venue flag, but lighting_property.ExecVenueId is set
        # (work_layout_dbs)
        # When: regenerating without --venue
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: it succeeds and confirms which venue was used, by id and
        # name, attributed to the active-venue fallback (not explicit)
        assert result.exit_code == 0
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout
        assert "active venue" in result.stdout.lower()

    def test_should_error_clearly_for_an_unknown_venue(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: an explicit venue id that doesn't exist. NOTE: this is
        # the fixed defect — layout regenerate used to silently succeed
        # here, treating the unknown id as a venue with no fixtures
        # instead of failing.
        # When: regenerating against it
        result = runner.invoke(cli.app, ["layout", "regenerate", "--venue", "999999"])

        # Then: it now fails cleanly, names the id, and enumerates the
        # valid venues so the user can retry immediately
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "999999" in result.stdout
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout

    def test_should_fail_clearly_when_the_active_venue_pointer_is_stale(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: ExecVenueId is overwritten to point at a venue that no
        # longer exists (the real venue from work_layout_dbs still does)
        user_conn = sqlite3.connect(work_layout_dbs["user_path"])
        set_lighting_property(user_conn, "ExecVenueId", "999999")
        user_conn.close()

        # When: regenerating with no --venue
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: a distinct, clean failure from the "no active venue set"
        # case — naming the stale id and enumerating the still-valid venues
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "999999" in result.stdout
        assert (
            "no longer exist" in result.stdout.lower()
            or "stale" in result.stdout.lower()
        )
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout

    def test_should_fail_clearly_when_no_venue_given_and_none_is_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with no ExecVenueId set
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: regenerating with no --venue
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: a clear, handled failure — not an unhandled traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_handle_a_venue_with_no_fixtures_at_all(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a venue with zero patched fixtures
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        user_path = make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        user_conn = sqlite3.connect(user_path)
        a_venue(user_conn, venue_id=9, name="Empty Venue")
        user_conn.close()

        # When: regenerating against it, applying the (empty) result
        result = runner.invoke(
            cli.app, ["layout", "regenerate", "--venue", "9", "--write"]
        )

        # Then: it succeeds without crashing, producing an empty layout
        assert result.exit_code == 0

    def test_should_report_the_old_and_new_rotation_when_only_rotation_changes(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved layout whose position already matches what the
        # algorithm currently generates, but whose rotation was hand-
        # adjusted away from the algorithm's current output — so the only
        # real difference for this fixture is rotation
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        first = runner.invoke(cli.app, ["layout", "regenerate", "--write"])
        assert first.exit_code == 0
        fresh = preview_layout.load_layout(layout_path)
        assert fresh is not None
        fresh_entry = next(e for e in fresh.entries if e.fixture_id == 1)
        new_rotation = fresh_entry.rotation
        old_rotation = (new_rotation + 90.0) % 360.0

        rotated_entries = tuple(
            preview_layout.LayoutEntry(
                fixture_id=entry.fixture_id,
                x=entry.x,
                y=entry.y,
                label=entry.label,
                kind=entry.kind,
                rotation=old_rotation if entry.fixture_id == 1 else entry.rotation,
                pan_degrees=entry.pan_degrees,
                tilt_degrees=entry.tilt_degrees,
            )
            for entry in fresh.entries
        )
        preview_layout.save_layout(
            layout_path,
            preview_layout.RigLayout(
                venue_id=work_layout_dbs["venue_id"], entries=rotated_entries
            ),
        )

        # When: regenerating without --write (position is unchanged for
        # this fixture, only rotation would change)
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: the report for this fixture shows both the old and the
        # new rotation value, not just an identical-looking position
        assert result.exit_code == 0
        fixture_line = next(
            line for line in result.stdout.splitlines() if "LM70S #1" in line
        )
        assert f"{old_rotation:.3f}" in fixture_line, (
            f"old rotation {old_rotation} missing from: {fixture_line!r}"
        )
        assert f"{new_rotation:.3f}" in fixture_line, (
            f"new rotation {new_rotation} missing from: {fixture_line!r}"
        )

    # -----------------------------------------------------------------
    # Structure geometry is user-owned (task requirement 6). Regeneration
    # must preserve the saved structure unchanged by default — the same
    # category as pan/tilt calibration, never the algorithm-owned
    # position/rotation/label/kind — and only reset it to the default
    # arch when the user explicitly opts in.
    # -----------------------------------------------------------------

    def test_should_preserve_a_custom_saved_structure_by_default(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved layout with a custom, non-default structure —
        # user-owned geometry, same category as pan/tilt calibration
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        custom_structure = ((0.0, 0.0), (600.0, 0.0))
        preview_layout.save_layout(
            layout_path,
            preview_layout.RigLayout(
                venue_id=work_layout_dbs["venue_id"],
                entries=(),
                structure_cm=custom_structure,
            ),
        )

        # When: regenerating with --write, no reset flag
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: the custom structure survives exactly — never silently
        # reset to the default arch
        assert result.exit_code == 0
        regenerated = preview_layout.load_layout(layout_path)
        assert regenerated is not None
        assert regenerated.structure_cm == custom_structure
        assert "preserved" in result.stdout.lower()

    def test_should_never_reset_the_structure_without_the_explicit_flag(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved custom structure
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        custom_structure = ((0.0, 0.0), (600.0, 0.0))
        preview_layout.save_layout(
            layout_path,
            preview_layout.RigLayout(
                venue_id=work_layout_dbs["venue_id"],
                entries=(),
                structure_cm=custom_structure,
            ),
        )

        # When: regenerating repeatedly with --write, never passing the
        # reset flag
        runner.invoke(cli.app, ["layout", "regenerate", "--write"])
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: still the custom shape, never the default arch
        assert result.exit_code == 0
        regenerated = preview_layout.load_layout(layout_path)
        assert regenerated is not None
        assert regenerated.structure_cm == custom_structure
        assert regenerated.structure_cm != preview_layout.arch_outline_cm()

    def test_should_reset_the_structure_to_the_default_arch_when_the_flag_is_given(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved custom structure
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        custom_structure = ((0.0, 0.0), (600.0, 0.0))
        preview_layout.save_layout(
            layout_path,
            preview_layout.RigLayout(
                venue_id=work_layout_dbs["venue_id"],
                entries=(),
                structure_cm=custom_structure,
            ),
        )

        # When: regenerating with the explicit reset flag
        result = runner.invoke(
            cli.app, ["layout", "regenerate", "--reset-structure", "--write"]
        )

        # Then: the structure is now the standard default arch, and the
        # output clearly, distinguishably reports the reset
        assert result.exit_code == 0
        regenerated = preview_layout.load_layout(layout_path)
        assert regenerated is not None
        assert regenerated.structure_cm == preview_layout.arch_outline_cm()
        assert "regenerated" in result.stdout.lower()
        assert "default" in result.stdout.lower()

    def test_should_not_reset_the_structure_on_a_dry_run_even_with_the_flag(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: a saved custom structure
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        custom_structure = ((0.0, 0.0), (600.0, 0.0))
        preview_layout.save_layout(
            layout_path,
            preview_layout.RigLayout(
                venue_id=work_layout_dbs["venue_id"],
                entries=(),
                structure_cm=custom_structure,
            ),
        )
        original_bytes = layout_path.read_bytes()

        # When: passing --reset-structure WITHOUT --write
        result = runner.invoke(cli.app, ["layout", "regenerate", "--reset-structure"])

        # Then: still a dry run — nothing on disk changes regardless of
        # the reset flag
        assert result.exit_code == 0
        assert layout_path.read_bytes() == original_bytes

    def test_should_report_structure_status_on_a_fresh_first_regeneration(
        self, work_layout_dbs: dict
    ) -> None:
        # Given: no layout file has ever been generated for this venue
        layout_path = preview_layout.layout_path_for_venue(
            work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
        )
        assert not layout_path.exists()

        # When: regenerating for the first time
        result = runner.invoke(cli.app, ["layout", "regenerate", "--write"])

        # Then: it succeeds and clearly reports the structure's status
        assert result.exit_code == 0
        assert "structure" in result.stdout.lower()

    def test_should_never_leak_one_venues_structure_into_another_venues_saved_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: two venues, each with its own saved custom structure
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        user_path = make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        user_conn = sqlite3.connect(user_path)
        venue_a = a_venue(user_conn, venue_id=2, name="Venue A")
        a_par_fixture(user_conn, fixture_id=1, venue_id=venue_a)
        venue_b = a_venue(user_conn, venue_id=3, name="Venue B")
        a_par_fixture(user_conn, fixture_id=2, venue_id=venue_b, macro_fixture_id=2)
        user_conn.close()

        layouts_dir = work_dir / "layouts"
        layout_path_a = preview_layout.layout_path_for_venue(venue_a, layouts_dir)
        layout_path_b = preview_layout.layout_path_for_venue(venue_b, layouts_dir)

        custom_a = ((0.0, 0.0), (300.0, 0.0))
        custom_b = ((0.0, 0.0), (0.0, 150.0), (200.0, 150.0), (200.0, 0.0))
        preview_layout.save_layout(
            layout_path_a,
            preview_layout.RigLayout(
                venue_id=venue_a, entries=(), structure_cm=custom_a
            ),
        )
        preview_layout.save_layout(
            layout_path_b,
            preview_layout.RigLayout(
                venue_id=venue_b, entries=(), structure_cm=custom_b
            ),
        )
        b_original_bytes = layout_path_b.read_bytes()

        # When: regenerating venue A only
        result = runner.invoke(
            cli.app, ["layout", "regenerate", "--venue", str(venue_a), "--write"]
        )

        # Then: venue A's own structure survives untouched, and venue B's
        # saved file is byte-for-byte untouched — no leakage between venues
        assert result.exit_code == 0
        reloaded_a = preview_layout.load_layout(layout_path_a)
        assert reloaded_a is not None
        assert reloaded_a.structure_cm == custom_a
        assert layout_path_b.read_bytes() == b_original_bytes


# ---------------------------------------------------------------------------
# `rbxlight venue list` — read-only venue discovery. Never mutates a
# database; must never hide a venue (zero-fixture, or an active pointer
# that no longer resolves). See requirement A.
# ---------------------------------------------------------------------------


@pytest.fixture
def work_venues_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """A working copy seeded with the multi-venue edge-case database:
    one populated venue, one with zero fixtures, and a same-name pair."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    user_conn = sqlite3.connect(user_path)
    venue_ids = a_multi_venue_database(user_conn)
    user_conn.close()

    return {"work_dir": work_dir, "user_path": user_path, "venue_ids": venue_ids}


class TestVenueListCommand:
    def test_should_list_every_venue_with_its_id_name_and_fixture_count(
        self, work_venues_db: dict
    ) -> None:
        # Given: a database with a populated venue (2 fixtures seeded)
        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it succeeds, and the populated venue's line shows its id,
        # name, and correct fixture count
        assert result.exit_code == 0
        venue_ids = work_venues_db["venue_ids"]
        populated_line = next(
            line
            for line in result.stdout.splitlines()
            if str(venue_ids["populated"]) in line
        )
        assert "Main Room" in populated_line
        assert "2" in populated_line

    def test_should_show_a_venue_with_zero_fixtures_not_hide_it(
        self, work_venues_db: dict
    ) -> None:
        # Given: "Empty Room" has zero patched fixtures
        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it still appears, with a count of zero — never omitted or
        # special-cased
        assert result.exit_code == 0
        empty_id = work_venues_db["venue_ids"]["empty"]
        empty_line = next(
            line for line in result.stdout.splitlines() if str(empty_id) in line
        )
        assert "0" in empty_line

    def test_should_distinguish_identically_named_venues_by_id(
        self, work_venues_db: dict
    ) -> None:
        # Given: two venues sharing the exact same name, different ids
        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: both ids are present in the output so the user can tell
        # them apart even though the names alone can't
        assert result.exit_code == 0
        assert str(work_venues_db["venue_ids"]["dup_a"]) in result.stdout
        assert str(work_venues_db["venue_ids"]["dup_b"]) in result.stdout

    def test_should_mark_the_active_venue(self, work_venues_db: dict) -> None:
        # Given: ExecVenueId points at the populated venue
        user_conn = sqlite3.connect(work_venues_db["user_path"])
        set_lighting_property(
            user_conn, "ExecVenueId", str(work_venues_db["venue_ids"]["populated"])
        )
        user_conn.close()

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: exactly one line is visually marked active, and it's the
        # right one
        assert result.exit_code == 0
        lines = result.stdout.splitlines()
        active_lines = [line for line in lines if "(active)" in line]
        assert len(active_lines) == 1
        assert str(work_venues_db["venue_ids"]["populated"]) in active_lines[0]

    def test_should_not_mark_non_active_venues(self, work_venues_db: dict) -> None:
        # Given: ExecVenueId points at the populated venue only
        user_conn = sqlite3.connect(work_venues_db["user_path"])
        set_lighting_property(
            user_conn, "ExecVenueId", str(work_venues_db["venue_ids"]["populated"])
        )
        user_conn.close()

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: the empty venue's line carries no active marker
        assert result.exit_code == 0
        empty_id = work_venues_db["venue_ids"]["empty"]
        empty_line = next(
            line for line in result.stdout.splitlines() if str(empty_id) in line
        )
        assert "(active)" not in empty_line

    def test_should_mark_no_venue_active_when_none_is_set(
        self, work_venues_db: dict
    ) -> None:
        # Given: no lighting_property row at all (never set)
        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it succeeds, and no venue is marked active
        assert result.exit_code == 0
        assert "(active)" not in result.stdout

    def test_should_show_every_real_venue_and_mark_none_active_when_pointer_is_stale(
        self, work_venues_db: dict
    ) -> None:
        # Given: ExecVenueId points at a venue id that doesn't exist
        user_conn = sqlite3.connect(work_venues_db["user_path"])
        set_lighting_property(user_conn, "ExecVenueId", "999999")
        user_conn.close()

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it doesn't crash or hide any real venue, and marks none active
        assert result.exit_code == 0
        assert "(active)" not in result.stdout
        for venue_id in work_venues_db["venue_ids"].values():
            assert str(venue_id) in result.stdout

    def test_should_say_plainly_when_there_are_no_venues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy whose user.db3 has no venue rows at all
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it says so plainly rather than printing an empty list
        # silently
        assert result.exit_code == 0
        assert "no venues" in result.stdout.lower()

    def test_should_never_modify_the_database(self, work_venues_db: dict) -> None:
        # Given: the current (seeded) working-copy user.db3
        before = Path(work_venues_db["user_path"]).read_bytes()

        # When: listing venues
        runner.invoke(cli.app, ["venue", "list"])

        # Then: byte-for-byte unchanged — this command only reads
        after = Path(work_venues_db["user_path"]).read_bytes()
        assert before == after

    def test_should_never_touch_the_live_lightingdb_directory(
        self,
        work_venues_db: dict,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Given: a live directory that does not even exist
        nonexistent_live_dir = tmp_path / "never-created-live-dir"
        monkeypatch.setattr(db, "LIGHTINGDB", nonexistent_live_dir)

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: it succeeds anyway — proof it never resolved a live path
        assert result.exit_code == 0
        assert not nonexistent_live_dir.exists()

    def test_should_error_cleanly_when_the_working_copy_does_not_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: listing venues
        result = runner.invoke(cli.app, ["venue", "list"])

        # Then: a clean, actionable error — not a raw traceback or a bare
        # database driver error — pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "pull" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Missing working copy — venue-aware commands must fail cleanly, not with
# a raw traceback or bare database driver error. See requirement D.
# ---------------------------------------------------------------------------


class TestMissingWorkingCopyForVenueAwareCommands:
    def test_preview_should_error_cleanly_when_the_working_copy_does_not_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: running preview
        result = runner.invoke(cli.app, ["preview", "1"])

        # Then: a clean, handled failure pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "pull" in result.stdout.lower()

    def test_layout_regenerate_should_error_cleanly_when_the_working_copy_does_not_exist(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: running layout regenerate
        result = runner.invoke(cli.app, ["layout", "regenerate"])

        # Then: a clean, handled failure pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "pull" in result.stdout.lower()


# ---------------------------------------------------------------------------
# `rbxlight layout install <path>` — installs a layout file exported by the
# offline visualizer's export/download button into a venue's saved-layout
# location. Dry run by default; refuses invalid/mismatched/degenerate
# files with an actionable message; reports BOTH fixture and stage/truss
# changes; prompts before installing over fixtures no longer patched into
# the target venue; atomic write, same venue-resolution and missing-
# working-copy conventions as every other venue-aware command.
# ---------------------------------------------------------------------------


def _install_target_path(work_layout_dbs: dict) -> Path:
    return preview_layout.layout_path_for_venue(
        work_layout_dbs["venue_id"], work_layout_dbs["work_dir"] / "layouts"
    )


def _current_fixtures(work_layout_dbs: dict) -> list[venues_repo.Fixture]:
    conn = sqlite3.connect(work_layout_dbs["user_path"])
    try:
        return venues_repo.list_fixtures(conn, work_layout_dbs["venue_id"])
    finally:
        conn.close()


def _moved_entries(
    entries: tuple[preview_layout.LayoutEntry, ...], *, moved_fixture_id: int
) -> tuple[preview_layout.LayoutEntry, ...]:
    """Same entries, except `moved_fixture_id`'s position is nudged —
    used to build an incoming export that differs from an existing saved
    layout in exactly one fixture's position, nothing else."""
    return tuple(
        preview_layout.LayoutEntry(
            fixture_id=entry.fixture_id,
            x=0.02 if entry.fixture_id == moved_fixture_id else entry.x,
            y=0.02 if entry.fixture_id == moved_fixture_id else entry.y,
            label=entry.label,
            kind=entry.kind,
            rotation=entry.rotation,
            pan_degrees=entry.pan_degrees,
            tilt_degrees=entry.tilt_degrees,
        )
        for entry in entries
    )


class TestLayoutInstallCommand:
    # -----------------------------------------------------------------
    # Requirement 1: refuse a file that is not a valid saved layout.
    # -----------------------------------------------------------------

    def test_should_refuse_an_empty_file(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a completely empty exported file
        export_path = tmp_path / "export.json"
        export_path.write_text("", encoding="utf-8")
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused, non-zero exit, an actionable message, nothing written
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not target_path.exists()

    def test_should_refuse_a_file_that_is_not_valid_json(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a file that isn't parseable JSON at all
        export_path = tmp_path / "export.json"
        export_path.write_text("not json at all{", encoding="utf-8")
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused clearly, non-zero exit, nothing written
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not target_path.exists()

    def test_should_refuse_valid_json_missing_the_fields_a_saved_layout_requires(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: valid JSON, but not shaped like a saved layout at all
        export_path = tmp_path / "export.json"
        export_path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused clearly, non-zero exit, nothing written
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not target_path.exists()

    def test_should_refuse_a_file_with_the_right_shape_but_wrong_types(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: "entries" present, but not a list of entry objects at all
        export_path = tmp_path / "export.json"
        export_path.write_text(
            json.dumps({"venue_id": work_layout_dbs["venue_id"], "entries": "nope"}),
            encoding="utf-8",
        )
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused clearly, non-zero exit, nothing written
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert not target_path.exists()

    # -----------------------------------------------------------------
    # Requirement 2: refuse a venue mismatch, naming both venues.
    # -----------------------------------------------------------------

    def test_should_refuse_a_venue_mismatch_naming_both_venues(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an exported layout built for a different venue than the
        # one being installed into
        other_venue_id = 999999
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path,
            preview_layout.RigLayout(venue_id=other_venue_id, entries=()),
        )
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it into the real target venue
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused, naming BOTH the file's venue and the target venue
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert str(other_venue_id) in result.stdout
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout
        assert not target_path.exists()

    # -----------------------------------------------------------------
    # Requirement 3: degenerate stage/truss geometry surfaces as an
    # actionable message, not a traceback (existing loading-layer
    # validation, just surfaced cleanly by this command).
    # -----------------------------------------------------------------

    def test_should_refuse_a_degenerate_truss_shape_with_an_actionable_message(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a file for the right venue, but a stage structure with
        # only one vertex — cannot describe a polyline
        export_path = tmp_path / "export.json"
        export_path.write_text(
            json.dumps(
                {
                    "venue_id": work_layout_dbs["venue_id"],
                    "entries": [],
                    "structure_cm": [[10.0, 20.0]],
                }
            ),
            encoding="utf-8",
        )
        target_path = _install_target_path(work_layout_dbs)

        # When: installing it
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: refused with a clear, actionable message — not a traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "vertex" in result.stdout.lower() or "vertices" in result.stdout.lower()
        assert not target_path.exists()

    # -----------------------------------------------------------------
    # Requirement 4: dry run by default.
    # -----------------------------------------------------------------

    def test_should_default_to_a_dry_run_and_explain_how_to_apply(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a valid export matching the target venue
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing without --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: told this was a preview, and how to apply
        assert result.exit_code == 0
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout

    def test_should_not_create_a_file_on_dry_run_first_time_install(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: no existing saved layout for this venue
        target_path = _install_target_path(work_layout_dbs)
        assert not target_path.exists()
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing without --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: still no file created
        assert result.exit_code == 0
        assert not target_path.exists()

    def test_should_leave_an_existing_saved_layout_byte_for_byte_identical_on_dry_run(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout for this venue
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)
        original_bytes = target_path.read_bytes()

        # And: an incoming export that DIFFERS (fixture 1 moved)
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=_moved_entries(existing.entries, moved_fixture_id=1),
            structure_cm=existing.structure_cm,
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing without --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: the saved layout on disk is completely untouched
        assert result.exit_code == 0
        assert target_path.read_bytes() == original_bytes

    # -----------------------------------------------------------------
    # Requirement 5: apply with --write.
    # -----------------------------------------------------------------

    def test_should_install_and_confirm_what_was_saved_and_where(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a valid export matching the target venue
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)
        target_path = _install_target_path(work_layout_dbs)

        # When: installing with --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
        )

        # Then: it succeeds, the file now exists, and the user is told
        # what was saved and where
        assert result.exit_code == 0
        assert target_path.exists()
        assert str(target_path) in result.stdout
        assert preview_layout.load_layout(target_path) == incoming

    # -----------------------------------------------------------------
    # Requirement 6: report BOTH fixture and stage/truss changes.
    # -----------------------------------------------------------------

    def test_should_report_a_fixture_only_change(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)

        # And: an incoming export with the SAME truss but fixture 1 moved
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=_moved_entries(existing.entries, moved_fixture_id=1),
            structure_cm=existing.structure_cm,
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing (dry run is enough — this is a reporting concern)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: the changed fixture is named, and this is NOT "no changes"
        assert result.exit_code == 0
        assert "LM70S #1" in result.stdout
        assert "no changes" not in result.stdout.lower()

    def test_should_report_a_truss_only_change_even_when_every_fixture_is_identical(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout with the default arch structure
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)

        # And: an incoming export with IDENTICAL fixtures but a different
        # stage/truss shape
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=existing.entries,
            structure_cm=((0.0, 0.0), (500.0, 0.0)),
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing (dry run)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: a truss/stage-shape change is reported — this must NOT be
        # treated as "nothing changed" just because every fixture matches
        assert result.exit_code == 0
        assert "no changes" not in result.stdout.lower()
        assert (
            "truss" in result.stdout.lower()
            or "structure" in result.stdout.lower()
            or "stage" in result.stdout.lower()
        )

    def test_should_report_both_fixture_and_truss_changes_together(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)

        # And: an incoming export with BOTH a moved fixture AND a
        # different truss shape
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=_moved_entries(existing.entries, moved_fixture_id=1),
            structure_cm=((0.0, 0.0), (500.0, 0.0)),
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing (dry run)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: both kinds of change are surfaced
        assert result.exit_code == 0
        assert "LM70S #1" in result.stdout
        assert (
            "truss" in result.stdout.lower()
            or "structure" in result.stdout.lower()
            or "stage" in result.stdout.lower()
        )

    def test_should_report_no_changes_when_incoming_matches_the_saved_layout_exactly(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)

        # And: an incoming export that is IDENTICAL in every way
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, existing)

        # When: installing (dry run)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: clearly reported as no changes
        assert result.exit_code == 0
        assert "no changes" in result.stdout.lower()

    def test_should_apply_harmlessly_when_incoming_is_identical_to_the_saved_layout(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an existing saved layout, and an identical incoming export
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, existing)
        original_bytes = target_path.read_bytes()

        # When: applying with --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
        )

        # Then: harmless — succeeds, and the file's content is unchanged
        assert result.exit_code == 0
        assert target_path.read_bytes() == original_bytes

    # -----------------------------------------------------------------
    # Requirement 7: first-time install is reported as new, not an edit.
    # -----------------------------------------------------------------

    def test_should_make_clear_a_first_time_install_is_a_new_file_not_an_edit(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: no existing saved layout for this venue
        target_path = _install_target_path(work_layout_dbs)
        assert not target_path.exists()
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing (dry run is enough — this is a reporting concern)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: distinctly reported as new, never as "no changes"
        assert result.exit_code == 0
        assert "no changes" not in result.stdout.lower()
        assert "new" in result.stdout.lower()

    def test_should_install_successfully_on_first_time_with_write_flag(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: no existing saved layout, and the --write flag
        target_path = _install_target_path(work_layout_dbs)
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing with --write
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
        )

        # Then: the new file now exists, matching the incoming layout
        assert result.exit_code == 0
        assert target_path.exists()
        assert preview_layout.load_layout(target_path) == incoming

    # -----------------------------------------------------------------
    # Requirement 8: prompt when the incoming layout references fixtures
    # no longer patched into the target venue; skippable non-interactively.
    # -----------------------------------------------------------------

    def test_should_prompt_when_incoming_references_fixtures_no_longer_patched(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an incoming export referencing a fixture id that no
        # longer exists in the venue's current patch
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=999, x=0.5, y=0.5, label="Ghost Fixture", kind="par"
                ),
            ),
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)
        target_path = _install_target_path(work_layout_dbs)

        # When: installing with --write, declining the prompt
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
            input="n\n",
        )

        # Then: the missing fixture is named, nothing was written, and
        # this is a clean exit — cancelling is not an error
        assert result.exit_code == 0
        assert "999" in result.stdout or "Ghost Fixture" in result.stdout
        assert not target_path.exists()

    def test_should_proceed_when_the_missing_fixture_prompt_is_confirmed(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: the same missing-fixture scenario
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=999, x=0.5, y=0.5, label="Ghost Fixture", kind="par"
                ),
            ),
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)
        target_path = _install_target_path(work_layout_dbs)

        # When: installing with --write, confirming the prompt
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
            input="y\n",
        )

        # Then: it proceeds and writes the file
        assert result.exit_code == 0
        assert target_path.exists()

    def test_should_skip_the_missing_fixture_prompt_with_the_yes_flag(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: the same missing-fixture scenario
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=(
                preview_layout.LayoutEntry(
                    fixture_id=999, x=0.5, y=0.5, label="Ghost Fixture", kind="par"
                ),
            ),
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)
        target_path = _install_target_path(work_layout_dbs)

        # When: installing with --write --yes, and NO input available at all
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
                "--yes",
            ],
        )

        # Then: it proceeds without prompting
        assert result.exit_code == 0
        assert target_path.exists()

    # -----------------------------------------------------------------
    # Requirement 9: venue resolution follows the same rules as every
    # other venue-aware command.
    # -----------------------------------------------------------------

    def test_should_use_the_explicit_venue_when_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a venue that is not the active one
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        user_path = make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        user_conn = sqlite3.connect(user_path)
        a_venue(user_conn, venue_id=7, name="Explicit Venue")
        a_par_fixture(user_conn, fixture_id=1, venue_id=7)
        user_conn.close()

        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path, preview_layout.RigLayout(venue_id=7, entries=())
        )

        # When: installing with an explicit --venue, no ExecVenueId set
        result = runner.invoke(
            cli.app, ["layout", "install", str(export_path), "--venue", "7"]
        )

        # Then: it succeeds against the explicitly named venue
        assert result.exit_code == 0
        assert "7" in result.stdout
        assert "Explicit Venue" in result.stdout
        assert "explicit" in result.stdout.lower()

    def test_should_confirm_the_active_venue_used_when_venue_is_omitted(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: no --venue flag, but lighting_property.ExecVenueId is set
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        # When: installing without --venue
        result = runner.invoke(cli.app, ["layout", "install", str(export_path)])

        # Then: it succeeds and confirms the active-venue fallback was used
        assert result.exit_code == 0
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout
        assert "active venue" in result.stdout.lower()

    def test_should_fail_clearly_when_no_venue_given_and_none_is_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with no ExecVenueId set
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        make_user_db(work_dir / "user.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path, preview_layout.RigLayout(venue_id=1, entries=())
        )

        # When: installing with no --venue
        result = runner.invoke(cli.app, ["layout", "install", str(export_path)])

        # Then: a clear, handled failure
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "no active venue" in result.stdout.lower()
        assert "--venue" in result.stdout

    def test_should_fail_clearly_when_the_active_venue_pointer_is_stale(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: ExecVenueId is overwritten to point at a venue that no
        # longer exists (the real venue from work_layout_dbs still does)
        user_conn = sqlite3.connect(work_layout_dbs["user_path"])
        set_lighting_property(user_conn, "ExecVenueId", "999999")
        user_conn.close()
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path, preview_layout.RigLayout(venue_id=999999, entries=())
        )

        # When: installing with no --venue
        result = runner.invoke(cli.app, ["layout", "install", str(export_path)])

        # Then: a distinct, clean failure naming the stale id and
        # enumerating the still-valid venues
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "999999" in result.stdout
        assert (
            "no longer exist" in result.stdout.lower()
            or "stale" in result.stdout.lower()
        )
        assert str(work_layout_dbs["venue_id"]) in result.stdout
        assert ACTIVE_VENUE_NAME in result.stdout

    # -----------------------------------------------------------------
    # Requirement 10: missing working copy points at `pull`, not a raw
    # database error.
    # -----------------------------------------------------------------

    def test_should_tell_the_user_to_pull_first_when_the_working_copy_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: WORK_DIR points at a directory with no user.db3 at all
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path, preview_layout.RigLayout(venue_id=1, entries=())
        )

        # When: installing
        result = runner.invoke(
            cli.app, ["layout", "install", str(export_path), "--venue", "1"]
        )

        # Then: a clear, handled failure telling the user to pull first
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "pull" in result.stdout.lower()

    # -----------------------------------------------------------------
    # Requirement 11: the write is atomic.
    # -----------------------------------------------------------------

    def test_should_leave_the_existing_saved_layout_untouched_when_write_is_interrupted(
        self, work_layout_dbs: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: an existing saved layout
        existing = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        target_path = _install_target_path(work_layout_dbs)
        preview_layout.save_layout(target_path, existing)
        original_bytes = target_path.read_bytes()

        # And: an incoming export that differs
        incoming = preview_layout.RigLayout(
            venue_id=work_layout_dbs["venue_id"],
            entries=_moved_entries(existing.entries, moved_fixture_id=1),
            structure_cm=existing.structure_cm,
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated crash during install write")

        monkeypatch.setattr("os.replace", _boom)

        # When: installing with --write, interrupted mid-write
        runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
        )

        # Then: the previously saved layout is completely untouched
        assert target_path.read_bytes() == original_bytes

    def test_should_leave_no_file_behind_when_a_first_time_install_write_is_interrupted(
        self, work_layout_dbs: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: no existing saved layout for this venue at all
        target_path = _install_target_path(work_layout_dbs)
        assert not target_path.exists()
        incoming = preview_layout.generate_layout(
            work_layout_dbs["venue_id"], _current_fixtures(work_layout_dbs)
        )
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(export_path, incoming)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated crash during install write")

        monkeypatch.setattr("os.replace", _boom)

        # When: the very first install is interrupted mid-write
        runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
                "--write",
            ],
        )

        # Then: no truncated/corrupt file was left behind
        assert not target_path.exists()

    # -----------------------------------------------------------------
    # Other edge cases.
    # -----------------------------------------------------------------

    def test_should_handle_a_file_with_zero_fixture_entries(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: a valid export for the right venue with no fixture entries
        export_path = tmp_path / "export.json"
        preview_layout.save_layout(
            export_path,
            preview_layout.RigLayout(venue_id=work_layout_dbs["venue_id"], entries=()),
        )

        # When: installing (dry run)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: no crash
        assert result.exit_code == 0

    def test_should_load_safely_when_the_export_omits_stage_geometry_entirely(
        self, work_layout_dbs: dict, tmp_path: Path
    ) -> None:
        # Given: an older-format export with no "structure_cm" key at all
        export_path = tmp_path / "export.json"
        export_path.write_text(
            json.dumps({"venue_id": work_layout_dbs["venue_id"], "entries": []}),
            encoding="utf-8",
        )

        # When: installing (dry run)
        result = runner.invoke(
            cli.app,
            [
                "layout",
                "install",
                str(export_path),
                "--venue",
                str(work_layout_dbs["venue_id"]),
            ],
        )

        # Then: it loads safely via the existing defaulting, no crash
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# `rbxlight macro list` — read-only listing of macros in the working copy.
# Default scope is user-only (preset=0); --all and --factory override.
# ---------------------------------------------------------------------------


@pytest.fixture
def work_macro_list_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """A working copy seeded with user and factory macros for list/search/show."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    macro_path = make_macro_db(work_dir / "macro.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    conn = sqlite3.connect(macro_path)
    a_user_macro(conn, macro_id=10006, name="HIGH DROP1", beats=32)
    a_user_macro(conn, macro_id=10001, name="MID CHORUS COOL", beats=64)
    a_factory_macro(conn, macro_id=61, name="FACTORY BEAT")
    sentinel_macro_rows(conn)
    conn.close()

    return {"work_dir": work_dir, "macro_path": macro_path}


class TestMacroListCommand:
    def test_should_print_header_and_indented_lines_for_user_macros(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a working copy with user macros seeded
        # When: running macro list
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: header "Macros:" followed by 2-space-indented macro lines
        assert result.exit_code == 0
        lines = result.stdout.strip().splitlines()
        assert lines[0] == "Macros:"
        macro_lines = [line for line in lines[1:] if line.strip()]
        assert len(macro_lines) == 2
        for line in macro_lines:
            assert line.startswith("  ")

    def test_should_format_macro_line_as_id_name_beats(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a user macro "HIGH DROP1" with id=10006, beats=32
        # When: running macro list
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: the line is exactly "  10006: HIGH DROP1 (32 beats)"
        assert "10006: HIGH DROP1 (32 beats)" in result.stdout

    def test_should_order_by_id_ascending(self, work_macro_list_db: dict) -> None:
        # Given: macros with ids 10001 and 10006
        # When: running macro list
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: id 10001 appears before id 10006 in the output
        pos_10001 = result.stdout.index("10001:")
        pos_10006 = result.stdout.index("10006:")
        assert pos_10001 < pos_10006

    def test_should_exclude_factory_macros_by_default(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a factory macro "FACTORY BEAT" exists
        # When: running macro list (default scope = user)
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: factory macros are not shown
        assert "FACTORY BEAT" not in result.stdout
        assert "61:" not in result.stdout

    def test_should_include_factory_macros_with_all_flag(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: both user and factory macros exist
        # When: running macro list --all
        result = runner.invoke(cli.app, ["macro", "list", "--all"])

        # Then: both user and factory macros appear
        assert "HIGH DROP1" in result.stdout
        assert "FACTORY BEAT" in result.stdout
        assert "10006:" in result.stdout
        assert "61:" in result.stdout

    def test_should_show_factory_macros_only_with_factory_flag(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: both user and factory macros exist
        # When: running macro list --factory
        result = runner.invoke(cli.app, ["macro", "list", "--factory"])

        # Then: only factory macros appear
        assert "FACTORY BEAT" in result.stdout
        assert "61:" in result.stdout
        assert "HIGH DROP1" not in result.stdout
        assert "10006:" not in result.stdout

    def test_should_print_no_macros_found_when_no_user_macros(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with only factory macros
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        a_factory_macro(conn, macro_id=61, name="FACTORY ONLY")
        conn.close()

        # When: running macro list (default = user only)
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: "No macros found." message, exit 0
        assert result.exit_code == 0
        assert "No macros found." in result.stdout

    def test_should_be_read_only(self, work_macro_list_db: dict) -> None:
        # Given: the current macro.db3 bytes
        original_bytes = Path(work_macro_list_db["macro_path"]).read_bytes()

        # When: running macro list
        runner.invoke(cli.app, ["macro", "list"])

        # Then: the database is byte-for-byte unchanged
        assert Path(work_macro_list_db["macro_path"]).read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# `rbxlight macro search TERM` — case-insensitive substring search.
# ---------------------------------------------------------------------------


class TestMacroSearchCommand:
    def test_should_print_header_and_matching_lines(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a factory macro containing "BEAT"
        # When: searching for "BEAT" (default scope = factory)
        result = runner.invoke(cli.app, ["macro", "search", "BEAT"])

        # Then: header "Search results:" followed by matching lines
        assert result.exit_code == 0
        assert "Search results:" in result.stdout
        assert "FACTORY BEAT" in result.stdout

    def test_should_match_case_insensitively(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a factory macro named "FACTORY beat"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        a_factory_macro(conn, macro_id=61, name="FACTORY beat")
        conn.close()

        # When: searching with uppercase term
        result = runner.invoke(cli.app, ["macro", "search", "BEAT"])

        # Then: it matches case-insensitively
        assert "FACTORY beat" in result.stdout
        assert result.exit_code == 0

    def test_should_search_factory_macros_by_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with a factory macro containing "DROP" and
        # a user macro also containing "DROP"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        a_factory_macro(conn, macro_id=61, name="FACTORY DROP")
        a_user_macro(conn, macro_id=10001, name="USER DROP")
        conn.close()

        # When: searching for "DROP" with no scope flag
        result = runner.invoke(cli.app, ["macro", "search", "DROP"])

        # Then: only factory macros are returned by default
        assert "FACTORY DROP" in result.stdout
        assert "USER DROP" not in result.stdout

    def test_should_search_user_macros_with_user_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working copy with a factory macro containing "DROP" and
        # a user macro also containing "DROP"
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        a_factory_macro(conn, macro_id=61, name="FACTORY DROP")
        a_user_macro(conn, macro_id=10001, name="USER DROP")
        conn.close()

        # When: searching for "DROP" with --user flag
        result = runner.invoke(cli.app, ["macro", "search", "DROP", "--user"])

        # Then: only user macros are returned
        assert "USER DROP" in result.stdout
        assert "FACTORY DROP" not in result.stdout

    def test_should_search_all_macros_with_all_flag(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: both user and factory macros
        # When: searching all scope for "FACTORY"
        result = runner.invoke(cli.app, ["macro", "search", "FACTORY", "--all"])

        # Then: factory macros are included
        assert "FACTORY BEAT" in result.stdout
        assert "61:" in result.stdout

    def test_should_print_no_macros_found_when_no_matches(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: macros exist but none match the search term
        # When: searching for a non-existent term
        result = runner.invoke(cli.app, ["macro", "search", "NONEXISTENT"])

        # Then: "No macros found." message, exit 0
        assert result.exit_code == 0
        assert "No macros found." in result.stdout

    def test_should_treat_percent_as_literal_not_wildcard(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: macros exist in the working copy
        # When: searching for "100%" — no macro contains this literal
        result = runner.invoke(cli.app, ["macro", "search", "100%"])

        # Then: no match (percent treated as literal, not wildcard)
        assert result.exit_code == 0
        assert "No macros found." in result.stdout

    def test_should_treat_underscore_as_literal_not_wildcard(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: macros exist in the working copy
        # When: searching for "DROP_" — no macro contains this literal
        result = runner.invoke(cli.app, ["macro", "search", "DROP_"])

        # Then: no match (underscore treated as literal, not wildcard)
        assert result.exit_code == 0
        assert "No macros found." in result.stdout

    def test_should_order_results_by_id_ascending(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: macros 10001 "MID CHORUS COOL" and 10006 "HIGH DROP1"
        # When: searching user macros for "COOL" which only matches 10001
        result = runner.invoke(cli.app, ["macro", "search", "COOL", "--user"])

        # Then: only 10001 is returned
        assert "10001:" in result.stdout
        assert "10006:" not in result.stdout

    def test_should_be_read_only(self, work_macro_list_db: dict) -> None:
        # Given: the current macro.db3 bytes
        original_bytes = Path(work_macro_list_db["macro_path"]).read_bytes()

        # When: running macro search
        runner.invoke(cli.app, ["macro", "search", "CHORUS"])

        # Then: the database is byte-for-byte unchanged
        assert Path(work_macro_list_db["macro_path"]).read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# `rbxlight macro show <id>` — detailed metadata for one macro.
# ---------------------------------------------------------------------------


class TestMacroShowCommand:
    def test_should_print_metadata_block_for_user_macro(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a user macro with id=10006
        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "10006"])

        # Then: metadata block with id, name, beats, preset, enabled
        assert result.exit_code == 0
        assert "Macro 10006: HIGH DROP1" in result.stdout
        assert "Beats: 32" in result.stdout
        assert "Preset: user (0)" in result.stdout
        assert "Enabled: yes (1)" in result.stdout

    def test_should_print_all_25_fixture_slots(self, work_macro_list_db: dict) -> None:
        # Given: a user macro with id=10006 (all slots empty)
        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "10006"])

        # Then: "Fixture slots:" section with exactly 25 entries
        assert "Fixture slots:" in result.stdout
        lines = result.stdout.strip().splitlines()
        slot_lines = [line.strip() for line in lines if line.strip().startswith(())]
        # Count lines that look like "N: programmed" or "N: empty"
        slot_lines = [
            line.strip()
            for line in lines
            if line.strip() and ": programmed" in line or ": empty" in line
        ]
        assert len(slot_lines) == 25

    def test_should_show_empty_for_all_empty_slots(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a macro with all slots empty (the default fixture)
        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "10006"])

        # Then: all 25 slots are marked "empty"
        lines = result.stdout.strip().splitlines()
        empty_lines = [line.strip() for line in lines if "empty" in line]
        assert len(empty_lines) == 25

    def test_should_show_programmed_for_nonempty_slots(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a macro with some slots programmed
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        a_user_macro(conn, macro_id=10001, name="PARTIAL")
        # Program slot 1 and slot 11
        insert_macro_data_row(
            conn,
            macro_id=10001,
            macro_fixture_id=1,
            data=a_valid_slot_payload(),
        )
        insert_macro_data_row(
            conn,
            macro_id=10001,
            macro_fixture_id=11,
            data=a_valid_slot_payload(),
        )
        # Note: the macro already has 25 rows from a_user_macro (all empty).
        # We just overwrote slots 1 and 11 via UPDATE (the fixture writes
        # empty rows; we need to UPDATE them, not INSERT).
        conn.execute(
            "UPDATE macro_data SET data = ? WHERE macro_id = 10001 AND macro_fixture_id = 1",
            (a_valid_slot_payload(),),
        )
        conn.execute(
            "UPDATE macro_data SET data = ? WHERE macro_id = 10001 AND macro_fixture_id = 11",
            (a_valid_slot_payload(),),
        )
        conn.close()

        # When: showing the macro
        result = runner.invoke(cli.app, ["macro", "show", "10001"])

        # Then: slots 1 and 11 are "programmed", the other 23 are "empty"
        lines = result.stdout.strip().splitlines()
        programmed_lines = [line.strip() for line in lines if "programmed" in line]
        empty_lines = [line.strip() for line in lines if "empty" in line]
        assert len(programmed_lines) == 2
        assert len(empty_lines) == 23

    def test_should_show_factory_macro_as_preset_factory(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a factory macro with id=61
        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "61"])

        # Then: shows as factory preset
        assert "Preset: factory (1)" in result.stdout
        assert "FACTORY BEAT" in result.stdout

    def test_should_show_disabled_macro(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a disabled user macro
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        macro_path = make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        conn = sqlite3.connect(macro_path)
        insert_macro_row(
            conn,
            macro_id=10001,
            name="DISABLED MACRO",
            beats=32,
            preset=0,
            enabled=0,
        )
        for slot_id in ALL_25_SLOT_IDS:
            insert_macro_data_row(
                conn, macro_id=10001, macro_fixture_id=slot_id, data=""
            )
        conn.close()

        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "10001"])

        # Then: enabled is "no (0)"
        assert "Enabled: no (0)" in result.stdout

    @pytest.mark.parametrize("sentinel_id", [-1, 10000])
    def test_should_not_crash_on_sentinel_ids(
        self, work_macro_list_db: dict, sentinel_id: int
    ) -> None:
        # Given: sentinel rows exist in the DB
        # When: showing a sentinel id
        result = runner.invoke(cli.app, ["macro", "show", str(sentinel_id)])

        # Then: no crash, shows the sentinel's metadata
        assert result.exit_code == 0
        assert f"Macro {sentinel_id}:" in result.stdout

    def test_should_print_not_found_for_nonexistent_id(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: no macro with id 99999
        # When: showing it
        result = runner.invoke(cli.app, ["macro", "show", "99999"])

        # Then: "not found" message, exit 1, no Python traceback
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()
        assert_no_unhandled_exception(result)

    def test_should_output_yaml_when_yaml_flag_given(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a macro seeded in the working copy
        # When: showing it with --yaml
        result = runner.invoke(cli.app, ["macro", "show", "10006", "--yaml"])

        # Then: output is valid YAML containing the macro's name and beats
        assert result.exit_code == 0
        assert "name:" in result.stdout
        assert "HIGH DROP1" in result.stdout
        assert "beats:" in result.stdout
        assert "32" in result.stdout
        assert "fixtures:" in result.stdout

    def test_should_produce_yaml_identical_to_export_macro_yaml(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: a macro seeded in the working copy
        macro_path = Path(work_macro_list_db["macro_path"])
        conn = sqlite3.connect(macro_path)
        expected_yaml = yaml_io.export_macro_yaml(conn, 10006)
        conn.close()

        # When: showing it with --yaml
        result = runner.invoke(cli.app, ["macro", "show", "10006", "--yaml"])

        # Then: output matches the existing export function exactly
        assert result.exit_code == 0
        assert result.stdout == expected_yaml

    def test_should_be_read_only(self, work_macro_list_db: dict) -> None:
        # Given: the current macro.db3 bytes
        original_bytes = Path(work_macro_list_db["macro_path"]).read_bytes()

        # When: running macro show
        runner.invoke(cli.app, ["macro", "show", "10006"])

        # Then: the database is byte-for-byte unchanged
        assert Path(work_macro_list_db["macro_path"]).read_bytes() == original_bytes


# ---------------------------------------------------------------------------
# Missing working copy for the three macro discovery commands.
# ---------------------------------------------------------------------------


class TestMissingWorkingCopyForMacroDiscoveryCommands:
    def test_macro_list_should_error_when_working_copy_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: running macro list
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: a clean, handled failure pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "Working copy not found at" in result.stdout
        assert "Run `rbxlight pull` first." in result.stdout

    def test_macro_search_should_error_when_working_copy_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: running macro search
        result = runner.invoke(cli.app, ["macro", "search", "TERM"])

        # Then: a clean, handled failure pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "Working copy not found at" in result.stdout
        assert "Run `rbxlight pull` first." in result.stdout

    def test_macro_show_should_error_when_working_copy_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a working-copy directory that was never pulled
        work_dir = tmp_path / "work-never-pulled"
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: running macro show
        result = runner.invoke(cli.app, ["macro", "show", "10006"])

        # Then: a clean, handled failure pointing at the pull step
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)
        assert "Working copy not found at" in result.stdout
        assert "Run `rbxlight pull` first." in result.stdout


# ---------------------------------------------------------------------------
# Conflicting flags are rejected cleanly.
# ---------------------------------------------------------------------------


class TestConflictingFlags:
    def test_macro_list_rejects_all_and_factory_together(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: conflicting --all and --factory flags
        # When: running macro list with both
        result = runner.invoke(cli.app, ["macro", "list", "--all", "--factory"])

        # Then: refused cleanly, non-zero exit, no traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_macro_search_rejects_user_and_all_together(
        self, work_macro_list_db: dict
    ) -> None:
        # Given: conflicting --user and --all flags
        # When: running macro search with both
        result = runner.invoke(cli.app, ["macro", "search", "TERM", "--user", "--all"])

        # Then: refused cleanly, non-zero exit, no traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)


# ---------------------------------------------------------------------------
# `rbxlight experiment ninth-bank` — the one-off, fully-undoable experiment:
# provisionally add a ninth bank (macro_pattern row, pattern=9) and point one
# throwaway track at it. Dry run by default, spans macro.db3 + user.db3,
# never touches live. See rbxlight.experiments.ninth_bank.
# ---------------------------------------------------------------------------


@pytest.fixture
def work_ninth_bank_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    """A working copy with a HIGH-energy (11-phase) source bank and one
    target track, wired up as db.WORK_DIR."""
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    macro_path = make_macro_db(work_dir / "macro.db3")
    user_path = make_user_db(work_dir / "user.db3")
    monkeypatch.setattr(db, "WORK_DIR", work_dir)

    macro_conn = sqlite3.connect(macro_path)
    source_pattern_id = a_high_energy_bank(macro_conn, pattern_id=1)
    macro_conn.close()

    user_conn = sqlite3.connect(user_path)
    content_id = a_track(user_conn, content_id=1, macro_pattern_id=1)
    user_conn.close()

    return {
        "work_dir": work_dir,
        "macro_path": macro_path,
        "user_path": user_path,
        "source_pattern_id": source_pattern_id,
        "content_id": content_id,
    }


def _apply_args(dbs: dict, *, write: bool = False) -> list[str]:
    args = [
        "experiment",
        "ninth-bank",
        "apply",
        str(dbs["source_pattern_id"]),
        str(dbs["content_id"]),
    ]
    if write:
        args.append("--write")
    return args


class TestExperimentNinthBankApplyDryRun:
    def test_should_change_nothing_without_the_write_flag(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: the current (unwritten-to) working-copy databases
        macro_bytes_before = Path(work_ninth_bank_dbs["macro_path"]).read_bytes()
        user_bytes_before = Path(work_ninth_bank_dbs["user_path"]).read_bytes()

        # When: running the mutating command without --write
        result = runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs))

        # Then: both databases are byte-for-byte unchanged
        assert result.exit_code == 0
        assert Path(work_ninth_bank_dbs["macro_path"]).read_bytes() == macro_bytes_before
        assert Path(work_ninth_bank_dbs["user_path"]).read_bytes() == user_bytes_before

    def test_should_report_the_true_blast_radius_and_how_to_apply(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: no --write flag
        # When: running the command
        result = runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs))

        # Then: told this was a preview, and shown the plan's facts: the
        # phase-assignment row count (11, from the source bank) and the
        # target track id
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout
        assert "11" in result.stdout
        assert str(work_ninth_bank_dbs["content_id"]) in result.stdout

    def test_should_not_create_a_state_file_on_dry_run(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: no --write flag
        # When: running the command
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs))

        # Then: no undo-state file was created
        assert not ninth_bank.default_state_path().exists()

    def test_should_error_clearly_for_a_nonexistent_source_bank(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: a source_pattern_id that doesn't exist
        # When: running the command
        result = runner.invoke(
            cli.app, ["experiment", "ninth-bank", "apply", "99999", "1"]
        )

        # Then: a clean, handled failure — not an unhandled traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_error_clearly_for_a_nonexistent_target_track(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: a content_id that doesn't exist
        # When: running the command
        result = runner.invoke(
            cli.app,
            [
                "experiment",
                "ninth-bank",
                "apply",
                str(work_ninth_bank_dbs["source_pattern_id"]),
                "99999",
            ],
        )

        # Then: a clean, handled failure
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)


class TestExperimentNinthBankApplyWrite:
    def test_should_create_the_new_bank_and_repoint_the_track(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # When: applying with --write
        result = runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # Then: succeeds, and the new bank (pattern=9) now exists
        assert result.exit_code == 0
        macro_conn = sqlite3.connect(work_ninth_bank_dbs["macro_path"])
        pattern_9_count = macro_conn.execute(
            "SELECT COUNT(*) FROM macro_pattern WHERE pattern = 9"
        ).fetchone()[0]
        macro_conn.close()
        assert pattern_9_count == 1

    def test_should_persist_undo_state_so_revert_can_run_later(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # When: applying with --write
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # Then: an undo-state file now exists on disk
        assert ninth_bank.default_state_path().exists()

    def test_should_refuse_a_second_apply_while_one_is_outstanding(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: an already-applied, un-reverted change
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # When: applying again
        result = runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # Then: refused cleanly, not a crash
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_never_touch_the_live_lightingdb_directory(
        self,
        work_ninth_bank_dbs: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a live directory that does not even exist
        nonexistent_live_dir = tmp_path / "never-created-live-dir"
        monkeypatch.setattr(db, "LIGHTINGDB", nonexistent_live_dir)

        # When: applying with --write
        result = runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # Then: succeeds anyway — proof it never resolved a live path
        assert result.exit_code == 0
        assert not nonexistent_live_dir.exists()


class TestExperimentNinthBankRevert:
    def test_should_change_nothing_without_the_write_flag(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: an applied change
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))
        macro_bytes_before = Path(work_ninth_bank_dbs["macro_path"]).read_bytes()
        user_bytes_before = Path(work_ninth_bank_dbs["user_path"]).read_bytes()

        # When: running revert without --write
        result = runner.invoke(cli.app, ["experiment", "ninth-bank", "revert"])

        # Then: both databases are byte-for-byte unchanged
        assert result.exit_code == 0
        assert Path(work_ninth_bank_dbs["macro_path"]).read_bytes() == macro_bytes_before
        assert Path(work_ninth_bank_dbs["user_path"]).read_bytes() == user_bytes_before

    def test_should_report_a_dry_run_by_default(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: an applied change
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # When: running revert without --write
        result = runner.invoke(cli.app, ["experiment", "ninth-bank", "revert"])

        # Then: told this was a preview
        assert "dry run" in result.stdout.lower()
        assert "--write" in result.stdout

    def test_should_restore_the_track_and_remove_the_new_bank_when_write_given(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: an applied change
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))

        # When: reverting with --write
        result = runner.invoke(
            cli.app, ["experiment", "ninth-bank", "revert", "--write"]
        )

        # Then: succeeds, the track is back to its original bank, and no
        # pattern=9 bank remains
        assert result.exit_code == 0
        user_conn = sqlite3.connect(work_ninth_bank_dbs["user_path"])
        macro_pattern_id = user_conn.execute(
            "SELECT macro_pattern_id FROM content WHERE id = ?",
            (work_ninth_bank_dbs["content_id"],),
        ).fetchone()[0]
        user_conn.close()
        assert macro_pattern_id == 1

        macro_conn = sqlite3.connect(work_ninth_bank_dbs["macro_path"])
        pattern_9_count = macro_conn.execute(
            "SELECT COUNT(*) FROM macro_pattern WHERE pattern = 9"
        ).fetchone()[0]
        macro_conn.close()
        assert pattern_9_count == 0

    def test_should_report_nothing_to_revert_when_no_change_is_outstanding(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: no prior apply
        # When: reverting with --write
        result = runner.invoke(
            cli.app, ["experiment", "ninth-bank", "revert", "--write"]
        )

        # Then: a clean, non-crashing "nothing to revert" message
        assert result.exit_code == 0
        assert "nothing to revert" in result.stdout.lower()

    def test_should_error_clearly_for_a_corrupt_state_file(
        self, work_ninth_bank_dbs: dict
    ) -> None:
        # Given: a malformed undo-state file
        state_path = ninth_bank.default_state_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text("{ not valid json")

        # When: reverting
        result = runner.invoke(
            cli.app, ["experiment", "ninth-bank", "revert", "--write"]
        )

        # Then: a clean, handled failure — not an unhandled traceback
        assert result.exit_code != 0
        assert_no_unhandled_exception(result)

    def test_should_never_touch_the_live_lightingdb_directory(
        self,
        work_ninth_bank_dbs: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: an applied change, and a live directory that does not
        # even exist
        runner.invoke(cli.app, _apply_args(work_ninth_bank_dbs, write=True))
        nonexistent_live_dir = tmp_path / "never-created-live-dir"
        monkeypatch.setattr(db, "LIGHTINGDB", nonexistent_live_dir)

        # When: reverting with --write
        result = runner.invoke(
            cli.app, ["experiment", "ninth-bank", "revert", "--write"]
        )

        # Then: succeeds anyway — proof it never resolved a live path
        assert result.exit_code == 0
        assert not nonexistent_live_dir.exists()
