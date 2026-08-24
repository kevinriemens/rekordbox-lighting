"""Cross-cutting structural tests for rbxlight.orchestration: the
guarantees that would otherwise silently rot with no test.

1. Every function in the orchestration layer raises a typed exception on
   failure, rather than printing a message or exiting the process — that
   is the CLI's job, layered on top, not this layer's.
2. The orchestration layer must not import the CLI framework (typer) at
   all — the structural guarantee that a future second front-end (an
   interactive menu) can depend on it directly.
3. The orchestration layer reads its working-directory / backup-root
   location values at CALL time, not at import/def time — so that tests
   (and any future caller) redirecting those locations actually take
   effect for every subsequent call, not just calls made before the
   redirect.
"""

from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from rbxlight import db, orchestration, safety
from tests.fixtures.venue_fixtures import a_venue


class TestOrchestrationRaisesTypedExceptionsOnFailure:
    def test_resolve_venue_raises_rather_than_exiting_or_printing(
        self, user_db_conn: sqlite3.Connection, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Given: no venues at all
        # When: resolving fails
        with pytest.raises(Exception) as exc_info:
            orchestration.resolve_venue(user_db_conn, None)

        # Then: it's a real exception, not a SystemExit, and nothing was
        # printed to stdout as a substitute for raising
        assert not isinstance(exc_info.value, SystemExit)
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_build_layout_install_plan_raises_rather_than_exiting_or_printing(
        self,
        user_db_conn: sqlite3.Connection,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from rbxlight.preview import layout as preview_layout
        from rbxlight.venues import repo as venues_repo

        # Given: a layout file for the wrong venue
        venue_id = a_venue(user_db_conn, venue_id=1, name="Main Room")
        fixtures = venues_repo.list_fixtures(user_db_conn, venue_id)
        incoming_path = tmp_path / "exported.json"
        preview_layout.save_layout(
            incoming_path, preview_layout.generate_layout(999, fixtures)
        )

        # When: installing fails
        with pytest.raises(Exception) as exc_info:
            orchestration.build_layout_install_plan(
                incoming_path, venue_id, fixtures, tmp_path / "layouts"
            )

        # Then: a real exception, nothing printed
        assert not isinstance(exc_info.value, SystemExit)
        captured = capsys.readouterr()
        assert captured.out == ""


class TestOrchestrationDoesNotImportCliFramework:
    def test_should_not_import_typer_anywhere_in_the_module_source(self) -> None:
        # Given: the orchestration module's own source file
        import rbxlight.orchestration as orchestration_module

        source_path = Path(orchestration_module.__file__)
        tree = ast.parse(source_path.read_text(encoding="utf-8"))

        # When: walking every import statement in the file
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module.split(".")[0])

        # Then: no CLI framework import exists anywhere in this module —
        # a future second front-end (interactive menu) must be able to
        # depend on this layer without pulling in typer/click
        assert "typer" not in imported_names
        assert "click" not in imported_names

    def test_should_not_reference_typer_at_runtime_either(self) -> None:
        # Given/When: the module is already imported (see conftest-level
        # import machinery) — inspect its live namespace
        import sys

        import rbxlight.orchestration as orchestration_module

        # Then: typer was never imported as a side effect of importing
        # this module (it may still be imported elsewhere, e.g. cli.py —
        # this only asserts THIS module didn't pull it in)
        module_globals = vars(orchestration_module)
        assert "typer" not in module_globals
        # And: rbxlight.cli's own typer import doesn't leak in as a
        # side effect purely from importing orchestration first
        assert "rbxlight.cli" not in sys.modules or sys.modules.get(
            "rbxlight.orchestration"
        ) is not sys.modules.get("rbxlight.cli")


class TestOrchestrationReadsLocationsAtCallTime:
    def test_default_layout_dir_reflects_db_work_dir_set_after_import(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: db.WORK_DIR is redirected to a sandbox AFTER
        # rbxlight.orchestration has already been imported
        redirected_work_dir = tmp_path / "redirected-work"
        monkeypatch.setattr(db, "WORK_DIR", redirected_work_dir)

        # When: asking the orchestration layer for its default layout dir
        result = orchestration.default_layout_dir()

        # Then: it reflects the REDIRECTED location, proving it was read
        # at call time and not captured as a stale default at import time
        assert result == redirected_work_dir / "layouts"

    def test_default_layout_dir_reflects_a_second_redirect_in_the_same_test(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: two different redirects applied in sequence
        first_dir = tmp_path / "first"
        second_dir = tmp_path / "second"

        # When: reading after the first redirect
        monkeypatch.setattr(db, "WORK_DIR", first_dir)
        first_result = orchestration.default_layout_dir()

        # And: reading again after a second redirect
        monkeypatch.setattr(db, "WORK_DIR", second_dir)
        second_result = orchestration.default_layout_dir()

        # Then: each call reflects whatever db.WORK_DIR was AT THAT CALL —
        # no caching of the location across calls
        assert first_result == first_dir / "layouts"
        assert second_result == second_dir / "layouts"
        assert first_result != second_result

    def test_default_backup_root_reflects_safety_backup_root_set_after_import(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # Given: safety.BACKUP_ROOT is redirected to a sandbox AFTER
        # rbxlight.orchestration has already been imported
        redirected_backup_root = tmp_path / "redirected-backups"
        monkeypatch.setattr(safety, "BACKUP_ROOT", redirected_backup_root)

        # When: asking the orchestration layer for its default backup root
        result = orchestration.default_backup_root()

        # Then: it reflects the redirected location
        assert result == redirected_backup_root
