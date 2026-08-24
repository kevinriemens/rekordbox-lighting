"""TTY guard for the interactive menu — it must never start against a
pipe/redirect, and it must never block waiting for input that can't
arrive.
"""

from __future__ import annotations

from typing import Protocol


class _IsATtyStream(Protocol):
    def isatty(self) -> bool: ...


class NotATtyError(RuntimeError):
    """Raised when stdin/stdout are not an interactive terminal."""


def require_interactive_tty(stdin: _IsATtyStream, stdout: _IsATtyStream) -> None:
    """Raise `NotATtyError` unless both `stdin` and `stdout` report
    `isatty() is True`. Never blocks — `isatty()` is a cheap, immediate
    check, not a read.
    """
    if not stdin.isatty() or not stdout.isatty():
        raise NotATtyError(
            "rbxlight's interactive menu needs a real terminal (TTY) and "
            "can't run here. Use a specific rbxlight CLI command instead, "
            "e.g. `rbxlight macro list`."
        )
