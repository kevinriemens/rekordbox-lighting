"""Read-only flow contract: macro list/search/show, venue list, backups
list, preview. None of these ever ask for confirmation and none of them
write anything. A missing working copy or an unresolvable id produces a
clean message and returns to the menu — never a traceback.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rbxlight import safety
from rbxlight.menu.app import run_menu
from tests.fixtures.macro_fixtures import a_factory_macro, a_user_macro
from tests.fixtures.venue_fixtures import a_par_fixture, a_venue
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


class TestMacroList:
    def test_should_prompt_for_scope_and_display_matching_macros(
        self, work_macro_db: Path
    ) -> None:
        import sqlite3

        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10001, name="MY MACRO")
        conn.close()

        # Given: navigating to Macros -> List, scope "user"
        prompter = ScriptedPrompter(answers=["Macros", "List", "user", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the macro appears in the rendered output
        assert "MY MACRO" in renderer.all_text
        assert renderer.errors == []

    def test_should_report_an_empty_result_without_a_traceback(
        self, work_macro_db: Path
    ) -> None:
        # Given: an empty working-copy macro.db3, scope "user"
        prompter = ScriptedPrompter(answers=["Macros", "List", "user", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: no traceback, a clean empty-list message is rendered
        assert renderer.errors == []
        assert "no macro" in renderer.all_text.lower()


class TestMacroSearch:
    def test_should_prompt_for_term_and_scope_and_display_matches(
        self, work_macro_db: Path
    ) -> None:
        import sqlite3

        conn = sqlite3.connect(work_macro_db)
        a_factory_macro(conn, macro_id=61, name="HIGH DROP")
        conn.close()

        # Given: navigating to Macros -> Search
        prompter = ScriptedPrompter(
            answers=["Macros", "Search", "DROP", "factory", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the matching macro is displayed
        assert "HIGH DROP" in renderer.all_text

    def test_should_report_no_results_cleanly(self, work_macro_db: Path) -> None:
        # Given: a search term that matches nothing
        prompter = ScriptedPrompter(
            answers=["Macros", "Search", "NOTHING MATCHES", "factory", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: no traceback, a clean no-results message
        assert renderer.errors == []
        assert "no macro" in renderer.all_text.lower()


class TestMacroShow:
    def test_should_display_metadata_and_slot_summary(
        self, work_macro_db: Path
    ) -> None:
        import sqlite3

        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10001, name="SHOW ME")
        conn.close()

        # Given: navigating to Macros -> Show with a valid id
        prompter = ScriptedPrompter(answers=["Macros", "Show", "10001", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the macro's metadata and slot summary appear
        assert "SHOW ME" in renderer.all_text
        assert (
            "empty" in renderer.all_text.lower()
            or "programmed" in renderer.all_text.lower()
        )

    def test_should_report_a_missing_macro_cleanly_and_return_to_the_menu(
        self, work_macro_db: Path
    ) -> None:
        # Given: an id that doesn't exist
        prompter = ScriptedPrompter(
            answers=["Macros", "Show", "999999", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: a clean human message, no traceback, control returns to
        # the menu (the script's later "Back"/"Exit" still get consumed)
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert exit_code == 0
        assert prompter.fully_consumed


class TestVenueList:
    def test_should_display_venues_with_fixture_counts(
        self, work_user_db: Path
    ) -> None:
        import sqlite3

        conn = sqlite3.connect(work_user_db)
        venue_id = a_venue(conn, venue_id=2, name="MAIN ROOM")
        a_par_fixture(conn, fixture_id=1, venue_id=venue_id)
        conn.close()

        # Given: navigating to Venues
        prompter = ScriptedPrompter(answers=["Venues", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the venue and its fixture count are displayed
        assert "MAIN ROOM" in renderer.all_text

    def test_should_report_no_venues_cleanly(self, work_user_db: Path) -> None:
        # Given: an empty working-copy user.db3
        prompter = ScriptedPrompter(answers=["Venues", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: no traceback, a clean "no venues" message
        assert renderer.errors == []
        assert "no venue" in renderer.all_text.lower()


class TestBackupsList:
    def test_should_display_name_timestamp_and_trigger_command(
        self, backup_root: Path, rekordbox_not_running: None
    ) -> None:
        safety.backup_all("rbxlight macro create --write --name X")

        # Given: navigating to Backups -> List
        prompter = ScriptedPrompter(answers=["Backups", "List", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the backup's trigger command appears in the listing
        assert "macro create" in renderer.all_text


class TestMissingWorkingCopyGuidance:
    def test_should_offer_pull_first_guidance_instead_of_raising(
        self, work_dir: Path
    ) -> None:
        # Given: a working copy directory with no macro.db3 in it at all
        # When: navigating to a read flow that needs it
        prompter = ScriptedPrompter(answers=["Macros", "List", "user", "Back", "Exit"])
        renderer = RecordingRenderer()
        run_menu(prompter, renderer)

        # Then: clean guidance mentioning `pull`, no traceback
        assert "pull" in renderer.all_text.lower()
        assert "Traceback" not in renderer.all_text


class TestPreview:
    def test_should_prompt_for_macro_and_venue_report_path_and_offer_to_open(
        self, work_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Given: orchestration.generate_preview is a collaborator — mocked
        # here because its own generation logic is covered by
        # test_orchestration_preview.py; the menu's job is only to ask
        # for the two ids, call it, and report the result.
        from rbxlight.menu import actions

        calls: list[tuple] = []

        def _fake_generate_preview(macro_id: int, venue_id: int) -> Path:
            calls.append((macro_id, venue_id))
            return Path("preview_1.html")

        monkeypatch.setattr(
            actions, "generate_preview_for_menu", _fake_generate_preview
        )

        prompter = ScriptedPrompter(answers=["Preview", "10001", "2", False, "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the collaborator was called with the two given ids, and
        # the output path was reported
        assert calls == [(10001, 2)]
        assert "preview_1.html" in renderer.all_text
