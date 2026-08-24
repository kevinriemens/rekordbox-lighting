"""Two tiers, visibly different.

Working-copy actions (macro create/delete, layout regenerate/install) use
an ordinary yes/no confirmation defaulting to No. Live-database actions
(Sync -> Push, Backups -> Restore) additionally: use the renderer's
`danger` presentation, state which live files will be overwritten, state
the backup that will be taken, show the exact restore command, and
require a stronger typed confirmation — "y"/wrong-word/empty must never
be accepted, and a live write is unreachable without passing that gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rbxlight import safety, sync
from rbxlight.menu.app import run_menu
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


@pytest.fixture
def pulled_work_copy(
    work_dir: Path, live_dir: Path, rekordbox_not_running: None
) -> None:
    """A working copy freshly pulled from live — matching sha256s, so
    `push` is never refused for staleness in these tests (staleness is
    covered by test_sync.py already)."""
    (live_dir / "macro.db3").write_bytes(b"macro-content")
    (live_dir / "user.db3").write_bytes(b"user-content")
    sync.pull(live_dir, work_dir)


class TestWorkingCopyTierUsesOrdinaryConfirm:
    def test_should_use_the_ordinary_confirm_not_danger_presentation(
        self, work_macro_db: Path
    ) -> None:
        # Given: a working-copy mutation (macro create)
        prompter = ScriptedPrompter(
            answers=["Macros", "Create", "NEW MACRO", "32", False, "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: an ordinary confirm was used, never confirm_typed, and
        # the danger presentation was never invoked
        assert any(call[0] == "confirm" for call in prompter.calls)
        assert not any(call[0] == "confirm_typed" for call in prompter.calls)
        assert renderer.dangers == []


class TestLiveTierUsesDangerPresentationAndTypedConfirm:
    def test_should_show_danger_overwritten_files_backup_and_restore_command(
        self, pulled_work_copy: None
    ) -> None:
        # Given: navigating to Sync -> Push and declining the typed gate
        prompter = ScriptedPrompter(
            answers=["Sync", "Push", "no thanks", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the danger presentation fired, naming overwritten files,
        # a backup note, and the exact restore command
        assert renderer.dangers != []
        assert "macro.db3" in renderer.all_text
        assert "user.db3" in renderer.all_text
        assert "backup" in renderer.all_text.lower()
        assert "restore" in renderer.all_text.lower()

    def test_should_use_confirm_typed_not_the_ordinary_confirm(
        self, pulled_work_copy: None
    ) -> None:
        # Given: navigating to Sync -> Push and declining
        prompter = ScriptedPrompter(
            answers=["Sync", "Push", "no thanks", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: confirm_typed was used for the live gate, never a plain
        # yes/no confirm
        assert any(call[0] == "confirm_typed" for call in prompter.calls)
        typed_call = next(call for call in prompter.calls if call[0] == "confirm_typed")
        assert typed_call[2] == "PUSH"

    @pytest.mark.parametrize(
        "typed_answer", ["y", "yes", "push", "Yes-but-wrong-word", ""]
    )
    def test_should_refuse_the_write_for_any_answer_that_is_not_the_exact_word(
        self, pulled_work_copy: None, live_dir: Path, typed_answer: str
    ) -> None:
        # Given: live content before the attempt
        original_macro = (live_dir / "macro.db3").read_bytes()
        original_user = (live_dir / "user.db3").read_bytes()

        # When: typing anything other than the exact confirmation word
        prompter = ScriptedPrompter(
            answers=["Sync", "Push", typed_answer, "Back", "Exit"]
        )
        renderer = RecordingRenderer()
        run_menu(prompter, renderer)

        # Then: live files are untouched — no write happened
        assert (live_dir / "macro.db3").read_bytes() == original_macro
        assert (live_dir / "user.db3").read_bytes() == original_user

    def test_should_write_to_live_only_when_the_exact_word_is_typed(
        self, pulled_work_copy: None, live_dir: Path
    ) -> None:
        # Given: navigating to Sync -> Push and typing the exact word
        prompter = ScriptedPrompter(answers=["Sync", "Push", "PUSH", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: live now matches the working copy — the write happened
        assert (live_dir / "macro.db3").read_bytes() == b"macro-content"


class TestLiveWriteUnreachableWithoutTheStrongerGate:
    def test_should_never_reach_backup_or_write_before_the_typed_gate_passes(
        self, pulled_work_copy: None, live_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: a spy on backup_live_databases
        backup_calls: list[str] = []
        original = safety.backup_live_databases

        def _spy(lightingdb_dir, backup_root, trigger_command):
            backup_calls.append(trigger_command)
            return original(lightingdb_dir, backup_root, trigger_command)

        monkeypatch.setattr(safety, "backup_live_databases", _spy)

        # When: declining the typed confirmation
        prompter = ScriptedPrompter(answers=["Sync", "Push", "n", "Back", "Exit"])
        renderer = RecordingRenderer()
        run_menu(prompter, renderer)

        # Then: no backup was ever taken — the write path was never
        # reached without the stronger gate passing
        assert backup_calls == []


class TestRestoreUsesTheSameLiveTierContract:
    def test_should_require_typed_confirmation_for_restore_too(
        self, backup_root: Path, live_dir: Path, rekordbox_not_running: None
    ) -> None:
        # Given: an existing backup to restore from
        (live_dir / "macro.db3").write_bytes(b"live-macro")
        (live_dir / "user.db3").write_bytes(b"live-user")
        backup_dir = safety.backup_all("seed")
        original_live = (live_dir / "macro.db3").read_bytes()

        # When: navigating to Backups -> Restore and typing the wrong word
        prompter = ScriptedPrompter(
            answers=["Backups", "Restore", backup_dir.name, "y", "Back", "Exit"]
        )
        renderer = RecordingRenderer()
        run_menu(prompter, renderer)

        # Then: live is untouched, and confirm_typed (not confirm) gated it
        assert (live_dir / "macro.db3").read_bytes() == original_live
        assert any(call[0] == "confirm_typed" for call in prompter.calls)
