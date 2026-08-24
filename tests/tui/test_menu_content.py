"""Menu content contract: what's offered at each level, and that
choosing back/escape returns up a level executing no action. Organised
by user intent (Macros/Preview/Layout/Venues/Sync/Backups/Exit), not by
CLI command-group structure.
"""

from __future__ import annotations

from rbxlight.menu.app import run_menu
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


def _select_calls(prompter: ScriptedPrompter) -> list[tuple]:
    return [call for call in prompter.calls if call[0] == "select"]


class TestTopLevelMenuContent:
    def test_should_offer_the_seven_top_level_intents(self) -> None:
        # Given: a prompter scripted to exit immediately
        prompter = ScriptedPrompter(answers=["Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: the top-level choices offered are exactly the seven intents
        select_calls = _select_calls(prompter)
        assert select_calls[0][2] == (
            "Macros",
            "Preview",
            "Layout",
            "Venues",
            "Sync",
            "Backups",
            "Exit",
        )
        assert exit_code == 0
        assert prompter.fully_consumed


class TestMacrosSubmenuContent:
    def test_should_offer_list_search_show_create_delete_back(self) -> None:
        # Given: navigate into Macros, then straight back out, then exit
        prompter = ScriptedPrompter(answers=["Macros", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the Macros submenu offered exactly these six choices
        select_calls = _select_calls(prompter)
        assert select_calls[1][2] == (
            "List",
            "Search",
            "Show",
            "Create",
            "Delete",
            "Back",
        )


class TestLayoutSubmenuContent:
    def test_should_offer_regenerate_install_back(self) -> None:
        # Given: navigate into Layout, then back out, then exit
        prompter = ScriptedPrompter(answers=["Layout", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the Layout submenu offered exactly these three choices
        select_calls = _select_calls(prompter)
        assert select_calls[1][2] == ("Regenerate", "Install", "Back")


class TestSyncSubmenuContent:
    def test_should_offer_pull_push_back(self) -> None:
        # Given: navigate into Sync, then back out, then exit
        prompter = ScriptedPrompter(answers=["Sync", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the Sync submenu offered exactly these three choices
        select_calls = _select_calls(prompter)
        assert select_calls[1][2] == ("Pull", "Push", "Back")


class TestBackupsSubmenuContent:
    def test_should_offer_list_restore_back(self) -> None:
        # Given: navigate into Backups, then back out, then exit
        prompter = ScriptedPrompter(answers=["Backups", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the Backups submenu offered exactly these three choices
        select_calls = _select_calls(prompter)
        assert select_calls[1][2] == ("List", "Restore", "Back")


class TestBackNavigationExecutesNoAction:
    def test_should_return_to_top_level_and_take_no_action_when_back_chosen(
        self,
    ) -> None:
        # Given: entering every submenu and immediately backing out of
        # each, ending with Exit
        prompter = ScriptedPrompter(
            answers=[
                "Macros",
                "Back",
                "Layout",
                "Back",
                "Sync",
                "Back",
                "Backups",
                "Back",
                "Exit",
            ]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: no plan was ever rendered and no danger/error surfaced —
        # backing out took no action at any level
        assert renderer.plans == []
        assert renderer.errors == []
        assert renderer.dangers == []
        assert exit_code == 0
        assert prompter.fully_consumed
