"""Tests for rbxlight.orchestration.generate_preview — the shared logic
behind the CLI's `preview` command, extracted so a future front-end can
drive the same operation without reimplementing venue/layout/payload
wiring. Contract: rekordbox-lighting-architecture ("Where to Put New
Code" — preview payload/document assembly).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rbxlight import orchestration
from rbxlight.venues import repo as venues_repo
from tests.fixtures.macro_fixtures import a_user_macro
from tests.fixtures.venue_fixtures import a_small_full_arc_venue


class TestGeneratePreview:
    def test_should_write_a_preview_document_and_report_its_path(
        self,
        macro_db_conn: sqlite3.Connection,
        user_db_conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        # Given: a macro and a venue with fixtures
        macro_id = a_user_macro(macro_db_conn, macro_id=10009, name="AI SWEEP")
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = venues_repo.list_fixtures(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        output_path = tmp_path / "preview.html"

        # When: generating a preview
        result_path = orchestration.generate_preview(
            macro_db_conn,
            user_db_conn,
            macro_id,
            venue_id,
            fixtures,
            layout_dir,
            output_path,
        )

        # Then: a preview document is written, and the path is reported
        assert result_path == output_path
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8")

    def test_should_create_a_layout_and_still_succeed_when_venue_has_none_yet(
        self,
        macro_db_conn: sqlite3.Connection,
        user_db_conn: sqlite3.Connection,
        tmp_path: Path,
    ) -> None:
        # Given: a venue that has no layout on disk yet
        macro_id = a_user_macro(macro_db_conn, macro_id=10010, name="AI SWEEP 2")
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = venues_repo.list_fixtures(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        output_path = tmp_path / "preview.html"
        assert not layout_dir.exists()

        # When: generating a preview
        result_path = orchestration.generate_preview(
            macro_db_conn,
            user_db_conn,
            macro_id,
            venue_id,
            fixtures,
            layout_dir,
            output_path,
        )

        # Then: a layout is created for the venue, and the preview still
        # succeeds
        assert layout_dir.exists()
        assert any(layout_dir.iterdir())
        assert result_path.exists()
