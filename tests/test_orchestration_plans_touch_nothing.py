"""Cross-cutting tests for the four new plan objects (pull, restore,
layout regenerate, layout install): each proves, with the byte-identical
comparison idiom already established in this suite (test_sync_plans.py's
PushPlan tests) — never mocking, never hashing — that BUILDING a plan
performs zero I/O: no database file, no layout file, and no backup
directory is created or modified. Also asserts each plan's touches_live
flag follows the convention pull/restore already set.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from rbxlight import orchestration, safety, sync
from rbxlight.preview import layout as preview_layout
from rbxlight.venues import repo as venues_repo
from tests.fixtures.venue_fixtures import a_small_full_arc_venue


class TestPullPlanTouchesNothing:
    def test_should_leave_filesystem_untouched_after_building(
        self, tmp_path: Path
    ) -> None:
        # Given: live db content, no work dir
        live_dir = tmp_path / "LightingDB"
        live_dir.mkdir()
        for name in sync.SYNCED_DB_NAMES:
            (live_dir / name).write_bytes(b"live")
        work_dir = tmp_path / "work"
        original_snapshot = {
            name: (live_dir / name).read_bytes() for name in sync.SYNCED_DB_NAMES
        }

        # When: building a pull plan only
        plan = sync.build_pull_plan(live_dir, work_dir)

        # Then: live bytes unchanged, work dir never created
        for name in sync.SYNCED_DB_NAMES:
            assert (live_dir / name).read_bytes() == original_snapshot[name]
        assert not work_dir.exists()
        assert plan.touches_live is False


class TestRestorePlanTouchesNothing:
    def test_should_leave_filesystem_untouched_after_building(
        self, tmp_path: Path
    ) -> None:
        # Given: a backup dir and a live dir with its own content
        backup_dir = tmp_path / "backups" / "2026-08-14T193000Z"
        backup_dir.mkdir(parents=True)
        manifest = {
            "timestamp": "2026-08-14T193000Z",
            "trigger_command": "x",
            "files": {
                "macro.db3": {"source": "s", "sha256": "a" * 64, "bytes": 1},
                "user.db3": {"source": "s", "sha256": "b" * 64, "bytes": 1},
            },
        }
        (backup_dir / "manifest.json").write_text(json.dumps(manifest))

        live_dir = tmp_path / "LightingDB"
        live_dir.mkdir()
        (live_dir / "macro.db3").write_bytes(b"live-macro")
        (live_dir / "user.db3").write_bytes(b"live-user")
        original_macro = (live_dir / "macro.db3").read_bytes()
        original_user = (live_dir / "user.db3").read_bytes()
        original_backup_manifest = (backup_dir / "manifest.json").read_bytes()

        # When: building a restore plan only
        plan = safety.build_restore_plan(backup_dir, live_dir)

        # Then: live bytes unchanged, backup manifest unchanged
        assert (live_dir / "macro.db3").read_bytes() == original_macro
        assert (live_dir / "user.db3").read_bytes() == original_user
        assert (backup_dir / "manifest.json").read_bytes() == original_backup_manifest
        assert plan.touches_live is True


class TestLayoutRegeneratePlanTouchesNothing:
    def test_should_leave_filesystem_untouched_after_building(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a venue with an existing saved layout
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = venues_repo.list_fixtures(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
        preview_layout.save_layout(
            layout_path, preview_layout.generate_layout(venue_id, fixtures)
        )
        original_bytes = layout_path.read_bytes()

        # When: building a regenerate plan only
        plan = orchestration.build_layout_regenerate_plan(
            venue_id, fixtures, layout_dir
        )

        # Then: the saved layout file is unchanged, and the plan reports
        # it never touches live databases (it only ever touches the
        # disposable working-copy layout file, and only on apply)
        assert layout_path.read_bytes() == original_bytes
        assert plan.touches_live is False


class TestLayoutInstallPlanTouchesNothing:
    def test_should_leave_filesystem_untouched_after_building(
        self, user_db_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Given: a venue with an existing saved layout, and an incoming
        # layout file to install
        venue_id = a_small_full_arc_venue(user_db_conn)
        fixtures = venues_repo.list_fixtures(user_db_conn, venue_id)
        layout_dir = tmp_path / "layouts"
        layout_path = preview_layout.layout_path_for_venue(venue_id, layout_dir)
        existing_layout = preview_layout.generate_layout(venue_id, fixtures)
        preview_layout.save_layout(layout_path, existing_layout)
        original_bytes = layout_path.read_bytes()

        incoming_path = tmp_path / "exported.json"
        preview_layout.save_layout(incoming_path, existing_layout)

        # When: building an install plan only
        plan = orchestration.build_layout_install_plan(
            incoming_path, venue_id, fixtures, layout_dir
        )

        # Then: the saved layout file is unchanged, and the plan reports
        # it never touches live databases
        assert layout_path.read_bytes() == original_bytes
        assert plan.touches_live is False
