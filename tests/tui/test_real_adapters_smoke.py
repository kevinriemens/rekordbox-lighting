"""Smoke tests for the REAL (non-double) menu adapters.

Every other test in tests/tui/ injects `ScriptedPrompter` /
`RecordingRenderer` from doubles.py, so nothing in the suite ever
imports `questionary` or constructs `QuestionaryPrompter` /
`RichRenderer` for real. That let the suite pass green while the
package's actual runtime dependency was missing entirely, and the gap
only surfaced when a human ran `rbxlight` against a real terminal.

These tests import the real libraries, construct the real adapters,
and check they still satisfy the `Prompter` / `Renderer` Protocols the
doubles are built against — without ever driving a real TTY or calling
an interactive `.ask()`.
"""

from __future__ import annotations

import inspect
from typing import Protocol

from rbxlight.menu.prompts import Prompter, QuestionaryPrompter
from rbxlight.menu.render import Renderer, RichRenderer


def _protocol_methods(protocol: type[Protocol]) -> list[str]:
    return [
        name
        for name in vars(protocol)
        if not name.startswith("_") and callable(getattr(protocol, name, None))
    ]


def _assert_satisfies_protocol(instance: object, protocol: type[Protocol]) -> None:
    for name in _protocol_methods(protocol):
        protocol_method = getattr(protocol, name)
        instance_method = getattr(instance, name, None)
        assert instance_method is not None, (
            f"{type(instance).__name__} is missing {name}, required by {protocol.__name__}"
        )
        protocol_params = list(inspect.signature(protocol_method).parameters)[1:]
        instance_params = list(inspect.signature(instance_method).parameters)
        assert instance_params == protocol_params, (
            f"{type(instance).__name__}.{name} signature {instance_params} "
            f"does not match {protocol.__name__}.{name} signature {protocol_params}"
        )


class TestQuestionaryPrompterIsReal:
    def test_should_import_questionary_and_construct_without_error(self) -> None:
        # Given: questionary is a declared runtime dependency
        import questionary  # noqa: F401

        # When: the real prompter is constructed
        prompter = QuestionaryPrompter()

        # Then: construction succeeds without driving a terminal
        assert isinstance(prompter, QuestionaryPrompter)

    def test_should_satisfy_prompter_protocol(self) -> None:
        # Given: the real, questionary-backed prompter
        prompter = QuestionaryPrompter()

        # When/Then: every method the menu calls exists with a
        # compatible signature — protects against doubles.py drifting
        # away from the real adapter
        _assert_satisfies_protocol(prompter, Prompter)


class TestRichRendererIsReal:
    def test_should_import_rich_and_render_a_line_without_tty(self, capsys) -> None:
        # Given: rich is a declared runtime dependency, real renderer
        import rich  # noqa: F401

        renderer = RichRenderer()

        # When: a plain line is rendered
        renderer.line("hello from the real renderer")

        # Then: the text made it out (not asserting on styling/markup)
        captured = capsys.readouterr()
        assert "hello from the real renderer" in captured.out

    def test_should_satisfy_renderer_protocol(self) -> None:
        # Given: the real, rich-backed renderer
        renderer = RichRenderer()

        # When/Then: every method the menu calls exists with a
        # compatible signature — protects against doubles.py drifting
        # away from the real adapter
        _assert_satisfies_protocol(renderer, Renderer)
