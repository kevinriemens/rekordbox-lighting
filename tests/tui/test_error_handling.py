"""General error-handling contract: any domain exception raised anywhere
in the menu renders as a clean human message and returns to the menu —
no traceback ever surfaces. Also covers Ctrl-C pressed mid-flow, before
any confirmation is reached.
"""

from __future__ import annotations

from pathlib import Path

from rbxlight.menu.app import run_menu
from tests.tui.doubles import CTRL_C, RecordingRenderer, ScriptedPrompter


class TestDomainExceptionsNeverSurfaceAsTracebacks:
    def test_should_render_a_clean_message_for_an_unparseable_macro_id(
        self, work_macro_db: Path
    ) -> None:
        # Given: text input that isn't a valid integer macro id
        prompter = ScriptedPrompter(
            answers=["Macros", "Show", "not-a-number", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: a clean error, no traceback, menu keeps running
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert exit_code == 0


class TestCtrlCMidFlowBeforeConfirmation:
    def test_should_exit_cleanly_when_interrupted_before_any_confirmation(
        self, work_macro_db: Path
    ) -> None:
        # Given: Ctrl-C pressed on the second prompt of a multi-prompt
        # flow (name given, then interrupted on beats), before the plan
        # is ever confirmed
        original_bytes = work_macro_db.read_bytes()
        prompter = ScriptedPrompter(answers=["Macros", "Create", "NEW", CTRL_C])
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: clean exit, conventional interrupt status, nothing written
        assert exit_code == 130
        assert "Traceback" not in renderer.all_text
        assert work_macro_db.read_bytes() == original_bytes

    def test_should_exit_cleanly_when_interrupted_at_the_top_level_select(
        self,
    ) -> None:
        # Given: Ctrl-C at the very first prompt
        prompter = ScriptedPrompter(answers=[CTRL_C])
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: clean exit, conventional interrupt status
        assert exit_code == 130
        assert "Traceback" not in renderer.all_text
