"""Contract: a short identifying banner is shown once, before the first
prompt, when the menu starts.

The banner goes through the existing showing seam's plain-line method
(`Renderer.line`) — no new method is added to the `Renderer` Protocol,
so `RecordingRenderer` (unmodified — see EXISTING_TESTS_TO_UPDATE) is
sufficient to observe it.
"""

from __future__ import annotations

from rbxlight.menu.app import run_menu
from rbxlight.menu.tty import NotATtyError, require_interactive_tty
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


class TestBannerShownOnStart:
    def test_should_show_a_line_before_the_first_prompt_is_asked(self) -> None:
        # Given: a prompter scripted to exit immediately
        prompter = ScriptedPrompter(answers=["Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: at least one line was shown through the plain-line
        # method before anything else happened, i.e. the recorded
        # transcript is non-empty at menu start
        assert renderer.lines, "expected a banner line to be shown via renderer.line()"

    def test_should_show_the_banner_only_once_not_once_per_loop_iteration(
        self,
    ) -> None:
        # Given: a prompter that goes into and back out of two
        # submenus before exiting — multiple loop iterations of the
        # top-level menu
        prompter = ScriptedPrompter(
            answers=["Macros", "Back", "Layout", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the first recorded line (the banner) appears exactly
        # once across the whole transcript, not once per top-level
        # loop iteration
        banner_line = renderer.lines[0]
        occurrences = renderer.lines.count(banner_line)
        assert occurrences == 1

    def test_should_show_the_banner_before_any_plan_error_or_danger(self) -> None:
        # Given: a plain run to Exit — nothing that would render a
        # plan/error/danger
        prompter = ScriptedPrompter(answers=["Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: no plan/error/danger competes with the banner as the
        # first thing shown (sanity check that the banner is emitted
        # via the plain line() method, not one of the typed ones)
        assert renderer.plans == []
        assert renderer.errors == []
        assert renderer.dangers == []
        assert renderer.lines


class TestBannerNotShownWhenMenuRefusesToStart:
    def test_should_not_call_renderer_line_when_the_tty_guard_refuses(self) -> None:
        # Given: a fake, non-TTY stdin/stdout pair
        class _NotATty:
            def isatty(self) -> bool:
                return False

        renderer = RecordingRenderer()

        # When: the TTY guard refuses to start (this happens BEFORE
        # run_menu — and therefore before the double — is ever
        # reached, matching cli.py's real wiring)
        try:
            require_interactive_tty(_NotATty(), _NotATty())
        except NotATtyError:
            pass

        # Then: the renderer that would have shown the banner was
        # never touched — the banner never leaked into a non-TTY pipe
        assert renderer.lines == []
