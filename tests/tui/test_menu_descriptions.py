"""Contract: menu items carry a short, per-menu description alongside
their label.

The prompting seam (`Prompter.select`) gained an optional keyword-only
`descriptions` mapping (choice label -> one-line description). The
choice VALUES the menu logic selects on and compares against are
completely unchanged — `test_menu_content.py`'s assertions about which
choices are offered keep passing unmodified (verified by running the
full tests/tui/ suite unmodified alongside this file).

Every menu level (top-level, Macros, Layout, Sync, Backups) must supply
a description for each of its own items, and must supply them itself —
not resolve them from a single global label lookup, because the same
label ("List", "Back") means something different at each level.
"""

from __future__ import annotations

from rbxlight.menu.app import run_menu
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


def _select_calls(prompter: ScriptedPrompter) -> list[tuple]:
    return [call for call in prompter.calls if call[0] == "select"]


def _descriptions_for(prompter: ScriptedPrompter, call_index: int) -> dict[str, str]:
    descriptions = _select_calls(prompter)[call_index][3]
    assert descriptions is not None, (
        f"select() call #{call_index} was not given any descriptions"
    )
    return descriptions


class TestTopLevelMenuDescriptions:
    def test_should_supply_a_description_for_every_top_level_item(self) -> None:
        # Given: a prompter scripted to exit immediately
        prompter = ScriptedPrompter(answers=["Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: every top-level choice has a non-empty description, and
        # the choice VALUES are untouched
        select_calls = _select_calls(prompter)
        choices = select_calls[0][2]
        descriptions = _descriptions_for(prompter, 0)
        assert choices == (
            "Macros",
            "Preview",
            "Layout",
            "Venues",
            "Sync",
            "Backups",
            "Exit",
        )
        for label in choices:
            assert descriptions.get(label), f"no description for top-level {label!r}"


class TestMacrosSubmenuDescriptions:
    def test_should_supply_a_description_for_every_macros_item(self) -> None:
        # Given: navigate into Macros, then straight back out, then exit
        prompter = ScriptedPrompter(answers=["Macros", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: every Macros choice has a description
        select_calls = _select_calls(prompter)
        choices = select_calls[1][2]
        descriptions = _descriptions_for(prompter, 1)
        assert choices == ("List", "Search", "Show", "Create", "Delete", "Back")
        for label in choices:
            assert descriptions.get(label), f"no description for Macros {label!r}"


class TestLayoutSubmenuDescriptions:
    def test_should_supply_a_description_for_every_layout_item(self) -> None:
        # Given: navigate into Layout, then back out, then exit
        prompter = ScriptedPrompter(answers=["Layout", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: every Layout choice has a description
        select_calls = _select_calls(prompter)
        choices = select_calls[1][2]
        descriptions = _descriptions_for(prompter, 1)
        assert choices == ("Regenerate", "Install", "Back")
        for label in choices:
            assert descriptions.get(label), f"no description for Layout {label!r}"


class TestSyncSubmenuDescriptions:
    def test_should_supply_a_description_for_every_sync_item(self) -> None:
        # Given: navigate into Sync, then back out, then exit
        prompter = ScriptedPrompter(answers=["Sync", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: every Sync choice has a description
        select_calls = _select_calls(prompter)
        choices = select_calls[1][2]
        descriptions = _descriptions_for(prompter, 1)
        assert choices == ("Pull", "Push", "Back")
        for label in choices:
            assert descriptions.get(label), f"no description for Sync {label!r}"


class TestBackupsSubmenuDescriptions:
    def test_should_supply_a_description_for_every_backups_item(self) -> None:
        # Given: navigate into Backups, then back out, then exit
        prompter = ScriptedPrompter(answers=["Backups", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: every Backups choice has a description
        select_calls = _select_calls(prompter)
        choices = select_calls[1][2]
        descriptions = _descriptions_for(prompter, 1)
        assert choices == ("List", "Restore", "Back")
        for label in choices:
            assert descriptions.get(label), f"no description for Backups {label!r}"


class TestDescriptionsAreSuppliedPerMenuNotGlobally:
    def test_should_give_the_shared_label_list_a_different_description_per_menu(
        self,
    ) -> None:
        """ "List" appears under Macros and Backups with a different
        meaning at each level. A single global label -> description
        mapping cannot satisfy both at once, so if an implementation
        resolves descriptions from one shared dict keyed only by
        label, this test fails (both menus would show the identical
        text for "List", or the dict would only have room for one
        meaning of "List").
        """
        # Given: navigate into Macros then back, then into Backups then
        # back, then exit — both submenus offer a "List" choice
        prompter = ScriptedPrompter(
            answers=["Macros", "Back", "Backups", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: "List" has a description at each level, and those two
        # descriptions are NOT identical — proving each menu supplied
        # its own, not a shared global lookup
        macros_descriptions = _descriptions_for(prompter, 1)
        backups_descriptions = _descriptions_for(prompter, 3)
        macros_list_description = macros_descriptions["List"]
        backups_list_description = backups_descriptions["List"]
        assert macros_list_description
        assert backups_list_description
        assert macros_list_description != backups_list_description

    def test_should_give_back_a_description_at_every_level_independently(
        self,
    ) -> None:
        """ "Back" appears at every submenu level. Each level must
        supply its own description for it (even if the text happens to
        coincide), never depend on a single shared lookup being present
        for the menu to function.
        """
        # Given: touch every submenu's Back, then exit
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
        run_menu(prompter, renderer)

        # Then: every submenu's select() call independently carried a
        # non-empty description for "Back"
        select_calls = _select_calls(prompter)
        submenu_call_indices = [1, 3, 5, 7]
        for index in submenu_call_indices:
            descriptions = select_calls[index][3]
            assert descriptions is not None
            assert descriptions.get("Back"), (
                f"select() call #{index} missing a description for 'Back'"
            )


class TestSelectingAChoiceIsUnaffectedByDescriptions:
    def test_should_return_the_plain_label_never_the_label_plus_description(
        self,
    ) -> None:
        # Given: a full run through Macros -> Back -> Exit
        prompter = ScriptedPrompter(answers=["Macros", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: the menu behaved identically to the description-less
        # contract — clean exit, every scripted answer consumed, no
        # plan/error/danger ever rendered from a value comparison gone
        # wrong (e.g. comparing "Macros" against "Macros - description")
        assert exit_code == 0
        assert prompter.fully_consumed
        assert renderer.errors == []
