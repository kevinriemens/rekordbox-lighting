"""The menu's entry point: `run_menu` drives the top-level select loop
and dispatches into each intent's screen module; `main` is the real,
TTY-checked entrypoint `cli.py` wires up (deferred import only).
"""

from __future__ import annotations

import sys

from rbxlight.menu import (
    backups_screen,
    layout_screen,
    macros_screen,
    preview_screen,
    sync_screen,
    tty,
    venues_screen,
)
from rbxlight.menu.prompts import Prompter, QuestionaryPrompter
from rbxlight.menu.render import Renderer, RichRenderer

_TOP_LEVEL_CHOICES = (
    "Macros",
    "Preview",
    "Layout",
    "Venues",
    "Sync",
    "Backups",
    "Exit",
)


def run_menu(prompter: Prompter, renderer: Renderer) -> int:
    """Drive the top-level menu loop until "Exit" is chosen. Returns 0 on
    a clean exit, 130 if a `KeyboardInterrupt` (Ctrl-C) is raised at any
    prompt, matching the shell's conventional SIGINT exit status.
    """
    try:
        while True:
            choice = prompter.select(
                "What do you want to do?", list(_TOP_LEVEL_CHOICES)
            )
            if choice == "Exit":
                return 0
            if choice == "Macros":
                macros_screen.run(prompter, renderer)
            elif choice == "Preview":
                preview_screen.run(prompter, renderer)
            elif choice == "Layout":
                layout_screen.run(prompter, renderer)
            elif choice == "Venues":
                venues_screen.run(prompter, renderer)
            elif choice == "Sync":
                sync_screen.run(prompter, renderer)
            elif choice == "Backups":
                backups_screen.run(prompter, renderer)
    except KeyboardInterrupt:
        return 130


def main() -> int:
    """The real entrypoint: checks stdin/stdout are an interactive TTY,
    then runs the menu with the real questionary/rich-backed
    implementations. Never called from tests — see
    `rbxlight.menu.tty.require_interactive_tty` for the guard tests
    monkeypatch instead.
    """
    tty.require_interactive_tty(sys.stdin, sys.stdout)
    return run_menu(QuestionaryPrompter(), RichRenderer())
