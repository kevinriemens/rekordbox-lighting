"""Tests for rbxlight.cli — dry-run-by-default contract for mutating
commands, plus the read-only `preview` command. Contract:
rekordbox-data-safety skill (rule 7, "DRY-RUN BY DEFAULT") and
rekordbox-lighting-architecture skill ("typer command shape").
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rbxlight import cli, db
from tests.conftest import make_macro_db, make_user_db
from tests.fixtures.macro_fixtures import a_user_macro
from tests.fixtures.venue_fixtures import (
    a_small_full_arc_venue,
    set_lighting_property,
)

runner = CliRunner()


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
