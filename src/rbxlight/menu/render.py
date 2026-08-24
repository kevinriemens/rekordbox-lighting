"""The showing seam: `Renderer` is the Protocol every menu screen shows
output through. Tests inject `tests.tui.doubles.RecordingRenderer`
instead of this real, rich-backed implementation.
"""

from __future__ import annotations

from typing import Protocol


class Renderer(Protocol):
    """Shows output to the user. Never raises, never blocks."""

    def line(self, text: str) -> None:
        """Show a plain line of text."""
        ...

    def plan(self, plan: object) -> None:
        """Show a dry-run plan (any plan dataclass) before a
        confirmation is asked for it."""
        ...

    def error(self, message: str) -> None:
        """Show a clean, human error message — never a traceback."""
        ...

    def danger(self, message: str) -> None:
        """Show a live-database danger warning — visibly distinct from
        an ordinary error, used only for the live-write confirmation
        tier (Sync -> Push, Backups -> Restore)."""
        ...


class RichRenderer:
    """Real terminal-backed `Renderer`, using `rich`."""

    def __init__(self) -> None:
        from rich.console import Console

        self._console = Console()

    def line(self, text: str) -> None:
        self._console.print(text)

    def plan(self, plan: object) -> None:
        self._console.print(plan)

    def error(self, message: str) -> None:
        self._console.print(f"[red]{message}[/red]")

    def danger(self, message: str) -> None:
        self._console.print(f"[bold red]{message}[/bold red]")
