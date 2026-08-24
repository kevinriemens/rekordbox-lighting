"""Entry & lifecycle contract for the interactive menu.

Requirements covered: no-args opens the menu; `rbxlight tui` opens the
same menu; existing commands are never intercepted; `--help` still
prints help; non-TTY refuses to start (no control codes, never blocks);
Ctrl-C exits cleanly; "Exit" exits 0; back/escape returns up a level
with no action executed.

cli.py is expected to import `rbxlight.menu.app.run_menu` only inside
its entrypoint wiring (deferred import), reading it at call time — same
pattern orchestration.py already uses for module-level location globals
— so monkeypatching `rbxlight.menu.app.run_menu` takes effect regardless
of whether cli.py did `from rbxlight.menu.app import run_menu` at call
time or `menu_app.run_menu(...)`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from rbxlight import cli, db
from tests.conftest import make_macro_db

runner = CliRunner()


@pytest.fixture
def fake_run_menu(monkeypatch: pytest.MonkeyPatch):
    calls: list[tuple] = []

    def _fake(prompter: object, renderer: object) -> int:
        calls.append((prompter, renderer))
        return 0

    import rbxlight.menu.app as menu_app

    monkeypatch.setattr(menu_app, "run_menu", _fake)
    return calls


@pytest.fixture
def tty_stdin_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate the process's real stdin/stdout being a TTY — CliRunner's
    captured streams never report isatty() True, so the CLI's TTY guard
    (which must check the REAL streams, not click's captured ones) is
    monkeypatched directly rather than faked through the runner.
    """
    from rbxlight.menu import tty

    monkeypatch.setattr(tty, "require_interactive_tty", lambda *a, **k: None)


class TestNoArgsOpensMenu:
    def test_should_invoke_the_menu_when_invoked_with_no_arguments(
        self, fake_run_menu: list[tuple], tty_stdin_stdout: None
    ) -> None:
        # Given: a TTY-simulated environment and a faked run_menu
        # When: invoking rbxlight with no arguments
        result = runner.invoke(cli.app, [])

        # Then: the menu was invoked exactly once
        assert len(fake_run_menu) == 1
        assert result.exit_code == 0


class TestTuiCommandOpensMenu:
    def test_should_invoke_the_menu_identically_to_no_args(
        self, fake_run_menu: list[tuple], tty_stdin_stdout: None
    ) -> None:
        # Given: a TTY-simulated environment
        # When: invoking `rbxlight tui`
        result = runner.invoke(cli.app, ["tui"])

        # Then: the menu was invoked exactly once, same as no-args
        assert len(fake_run_menu) == 1
        assert result.exit_code == 0


class TestExistingCommandsNeverIntercepted:
    def test_should_run_macro_list_as_before_without_touching_the_menu(
        self,
        fake_run_menu: list[tuple],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: an existing command with its normal working copy
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        make_macro_db(work_dir / "macro.db3")
        monkeypatch.setattr(db, "WORK_DIR", work_dir)

        # When: invoking an existing subcommand
        result = runner.invoke(cli.app, ["macro", "list"])

        # Then: the menu is never invoked, command behaves as before
        assert len(fake_run_menu) == 0
        assert result.exit_code == 0


class TestHelpStillPrintsHelp:
    def test_should_print_help_text_not_the_menu(
        self, fake_run_menu: list[tuple]
    ) -> None:
        # Given: nothing special
        # When: invoking --help
        result = runner.invoke(cli.app, ["--help"])

        # Then: help text is printed, the menu is never invoked
        assert result.exit_code == 0
        assert "Usage" in result.stdout
        assert len(fake_run_menu) == 0


class TestNonTtyRefusesToStart:
    def test_should_refuse_and_print_guidance_when_not_a_tty(
        self, fake_run_menu: list[tuple]
    ) -> None:
        # Given: CliRunner's captured stdin/stdout, which never report
        # isatty() True — the default, un-simulated environment
        # When: invoking rbxlight with no arguments
        result = runner.invoke(cli.app, [])

        # Then: the menu is never invoked, no control codes leak into
        # the pipe, and clear guidance points at the CLI
        assert len(fake_run_menu) == 0
        assert "\x1b" not in result.stdout
        assert "rbxlight" in result.stdout.lower() or "cli" in result.stdout.lower()

    def test_should_never_block_waiting_for_input_when_not_a_tty(
        self, fake_run_menu: list[tuple]
    ) -> None:
        # Given: no stdin input supplied at all
        # When: invoking rbxlight with no arguments and no input
        result = runner.invoke(cli.app, [], input="")

        # Then: the command completes (does not hang waiting on stdin)
        assert result.exit_code != 0
        assert len(fake_run_menu) == 0


class TestCtrlCExitsCleanly:
    def test_should_exit_with_conventional_interrupt_status_and_no_traceback(
        self, tty_stdin_stdout: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: run_menu raising KeyboardInterrupt as if Ctrl-C were
        # pressed at a prompt
        import rbxlight.menu.app as menu_app

        def _raise_interrupt(prompter: object, renderer: object) -> int:
            raise KeyboardInterrupt

        monkeypatch.setattr(menu_app, "run_menu", _raise_interrupt)

        # When: invoking rbxlight with no arguments
        result = runner.invoke(cli.app, [])

        # Then: no traceback surfaces, exit code is the conventional 130
        assert result.exit_code == 130
        assert "Traceback" not in result.output


class TestExitSelectionExitsCleanly:
    def test_should_return_zero_when_run_menu_reports_a_clean_exit(
        self, tty_stdin_stdout: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: run_menu returning 0, as it does when "Exit" is chosen
        import rbxlight.menu.app as menu_app

        monkeypatch.setattr(menu_app, "run_menu", lambda *a, **k: 0)

        # When: invoking rbxlight with no arguments
        result = runner.invoke(cli.app, [])

        # Then: exit status is 0
        assert result.exit_code == 0
