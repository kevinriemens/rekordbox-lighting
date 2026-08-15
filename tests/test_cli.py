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
from rbxlight.preview import layout as preview_layout
from tests.conftest import make_macro_db, make_user_db
from tests.fixtures.macro_fixtures import (
    a_factory_macro,
    a_user_macro,
    sentinel_macro_rows,
)
from tests.fixtures.venue_fixtures import (
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
