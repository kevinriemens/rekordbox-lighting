"""The asking seam: `Prompter` is the Protocol every menu screen asks
questions through. Tests inject `tests.tui.doubles.ScriptedPrompter`
instead of this real, questionary-backed implementation — see that
module for the contract this Protocol must satisfy.
"""

from __future__ import annotations

from typing import Protocol


class Prompter(Protocol):
    """Asks the user questions. Every method returns the user's answer;
    a real implementation raises `KeyboardInterrupt` on Ctrl-C at any
    prompt, matching `ScriptedPrompter`'s `CTRL_C` sentinel behaviour.
    """

    def select(
        self,
        message: str,
        choices: list[str],
        *,
        descriptions: dict[str, str] | None = None,
    ) -> str:
        """Ask the user to pick one of `choices`, return the choice.
        `descriptions` optionally maps each label to a one-line
        description shown alongside it; the returned value is always
        the plain label, never a display string.
        """
        ...

    def text(self, message: str, *, default: str | None = None) -> str:
        """Ask for free-form text, return what was typed."""
        ...

    def confirm(self, message: str, *, default: bool = False) -> bool:
        """Ask an ordinary yes/no question."""
        ...

    def confirm_typed(self, message: str, *, expected_word: str) -> bool:
        """Ask the user to type an exact word to confirm a dangerous
        action. Returns whether the typed text matched `expected_word`
        exactly — used for the live-database "danger" tier, where a
        casual "y" must never be accepted.
        """
        ...


class QuestionaryPrompter:
    """Real terminal-backed `Prompter`, using `questionary`. A `None`
    answer from questionary (Ctrl-C / Ctrl-D at the prompt) is
    normalized to `KeyboardInterrupt`, matching `ScriptedPrompter`'s
    `CTRL_C` sentinel.
    """

    def select(
        self,
        message: str,
        choices: list[str],
        *,
        descriptions: dict[str, str] | None = None,
    ) -> str:
        import questionary

        descriptions = descriptions or {}
        width = max((len(label) for label in choices), default=0)
        style = questionary.Style(
            [
                ("label", ""),
                ("description", "fg:#7f7f7f"),
                ("pointer", "fg:#5f87ff bold"),
            ]
        )
        display_choices = [
            questionary.Choice(
                title=[
                    ("class:label", f"{label:<{width}}"),
                    ("class:description", f"      {descriptions[label]}"),
                ]
                if label in descriptions
                else [("class:label", label)],
                value=label,
            )
            for label in choices
        ]
        answer = questionary.select(
            message,
            choices=display_choices,
            pointer="\u2192",
            instruction="(\u2191/\u2193 to move, Enter to select)",
            style=style,
        ).ask()
        if answer is None:
            raise KeyboardInterrupt
        return str(answer)

    def text(self, message: str, *, default: str | None = None) -> str:
        import questionary

        answer = questionary.text(message, default=default or "").ask()
        if answer is None:
            raise KeyboardInterrupt
        return str(answer)

    def confirm(self, message: str, *, default: bool = False) -> bool:
        import questionary

        answer = questionary.confirm(message, default=default).ask()
        if answer is None:
            raise KeyboardInterrupt
        return bool(answer)

    def confirm_typed(self, message: str, *, expected_word: str) -> bool:
        import questionary

        typed = questionary.text(f'{message} (type "{expected_word}" to confirm)').ask()
        if typed is None:
            raise KeyboardInterrupt
        return str(typed) == expected_word
