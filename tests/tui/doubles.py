"""Test doubles for the menu's asking/showing seam.

These are the CONTRACT for `rbxlight.menu.prompts.Prompter` and
`rbxlight.menu.render.Renderer` (Protocols the backend-agent implements in
src/). They are real, functioning test infrastructure — not disposable
compile-only stubs — because the menu is designed to take these interfaces
injected, never driving a real terminal in tests (see rekordbox-lighting
menu story: "the prompting library must be replaced by an injected test
double that returns a scripted sequence of answers").

ScriptedPrompter answers select()/text()/confirm()/confirm_typed() calls
from a pre-scripted queue, in order, and raises AssertionError if the
queue runs dry (a test asked for more interaction than it scripted — a
sign the flow diverged from what the test expected). A scripted
`KeyboardInterrupt` sentinel raises that exception instead of returning
an answer, simulating Ctrl-C at that exact prompt.

`select()` additionally accepts an optional `descriptions` mapping
(choice label -> one-line description), recorded verbatim as the 4th
element of its `calls` tuple. This mirrors the real seam: descriptions
are supplied per-call by whichever menu level is asking, never resolved
from a global label lookup. `descriptions` does not affect the choice
VALUES returned/recorded — those remain exactly the plain `choices`
list, unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: Script sentinel: the next prompt call raises KeyboardInterrupt instead
#: of returning a scripted answer.
CTRL_C = object()


@dataclass
class ScriptedPrompter:
    """Answers prompts from `answers`, in order. Every call (select, text,
    confirm, confirm_typed) consumes exactly one scripted answer.
    `calls` records (method_name, message, choices_or_default) tuples in
    the order they were made, so a test can assert on the exact sequence
    of questions asked — and that every scripted answer was consumed.
    """

    answers: list
    calls: list[tuple] = field(default_factory=list)
    _index: int = 0

    def _next(
        self,
        method: str,
        message: str,
        extra: object = None,
        descriptions: dict[str, str] | None = None,
    ) -> object:
        self.calls.append((method, message, extra, descriptions))
        if self._index >= len(self.answers):
            raise AssertionError(
                f"ScriptedPrompter ran out of answers at call #{self._index} "
                f"({method!r}, {message!r}) — script only provided "
                f"{len(self.answers)} answer(s)."
            )
        answer = self.answers[self._index]
        self._index += 1
        if answer is CTRL_C:
            raise KeyboardInterrupt
        return answer

    def select(
        self,
        message: str,
        choices: list[str],
        *,
        descriptions: dict[str, str] | None = None,
    ) -> str:
        return self._next("select", message, tuple(choices), descriptions)

    def text(self, message: str, *, default: str | None = None) -> str:
        return self._next("text", message, default)

    def confirm(self, message: str, *, default: bool = False) -> bool:
        return self._next("confirm", message, default)

    def confirm_typed(self, message: str, *, expected_word: str) -> bool:
        """Consumes one scripted answer, which is the RAW TYPED STRING the
        user entered (not a bool) — the double never itself decides
        whether it matches `expected_word`; that comparison is the
        production Prompter's job (or the real implementation backing
        this Protocol), so tests can script "y", "", or the wrong word
        and assert the caller treats all of them as a refusal.
        """
        typed = self._next("confirm_typed", message, expected_word)
        return typed == expected_word

    @property
    def fully_consumed(self) -> bool:
        return self._index == len(self.answers)


@dataclass
class RecordingRenderer:
    """Records every render call verbatim, in order, so tests can assert
    on what was shown without a terminal. `lines` is the flattened,
    chronological record across all render methods; the typed lists
    (`plans`, `errors`, `dangers`) let a test assert on a specific
    category without string-matching the whole transcript.
    """

    lines: list[str] = field(default_factory=list)
    plans: list[object] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dangers: list[str] = field(default_factory=list)

    def line(self, text: str) -> None:
        self.lines.append(text)

    def plan(self, plan: object) -> None:
        self.plans.append(plan)
        self.lines.append(f"<plan {plan!r}>")

    def error(self, message: str) -> None:
        self.errors.append(message)
        self.lines.append(f"<error {message}>")

    def danger(self, message: str) -> None:
        self.dangers.append(message)
        self.lines.append(f"<danger {message}>")

    @property
    def all_text(self) -> str:
        return "\n".join(self.lines)
