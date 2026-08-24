"""Structural boundary tests, enforced by AST inspection (no runtime
imports required — these must hold even before rbxlight.menu exists,
so they use file/text inspection rather than importing the module,
matching this suite's other "structural" tests).

- The menu package is forbidden from importing the CLI module.
- The CLI module is forbidden from importing the menu module except in
  the single entrypoint wiring (the no-args callback and the `tui`
  command).
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "rbxlight"


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestMenuNeverImportsCli:
    def test_should_find_no_import_of_rbxlight_cli_anywhere_under_menu(self) -> None:
        # Given: every .py file under src/rbxlight/menu (once it exists)
        menu_dir = SRC_ROOT / "menu"
        if not menu_dir.exists():
            import pytest

            pytest.skip("rbxlight.menu package does not exist yet")

        # When: scanning each file's imports
        offending: list[str] = []
        for path in menu_dir.rglob("*.py"):
            names = _imported_module_names(path.read_text())
            if any(name == "rbxlight.cli" or name.endswith(".cli") for name in names):
                offending.append(str(path))

        # Then: none of them import rbxlight.cli
        assert offending == []


class TestCliOnlyImportsMenuInEntrypointWiring:
    def test_should_only_reference_the_menu_module_inside_function_bodies(
        self,
    ) -> None:
        # Given: cli.py's source
        cli_source = (SRC_ROOT / "cli.py").read_text()
        tree = ast.parse(cli_source)

        # When: collecting top-level (module-scope) imports
        top_level_menu_imports = [
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            and (
                (
                    isinstance(node, ast.ImportFrom)
                    and node.module
                    and "menu" in node.module
                )
                or (
                    isinstance(node, ast.Import)
                    and any("menu" in alias.name for alias in node.names)
                )
            )
        ]

        # Then: rbxlight.menu is never imported at module scope — only
        # inside function bodies (deferred import wiring), if imported
        # at all yet
        assert top_level_menu_imports == []
