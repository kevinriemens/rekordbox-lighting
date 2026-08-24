"""Tests for sync.PullPlan / sync.build_pull_plan — the pull side of the
dry-run plan pair (see test_sync_plans.py's PushPlan tests for the
established idiom this mirrors). Contract: rekordbox-data-safety
("WORK ON A COPY, NOT ON LIVE") — pull only ever refreshes the disposable
working copy, and must report that it never touches live.
"""

from __future__ import annotations

from pathlib import Path

from rbxlight import sync


class TestBuildPullPlan:
    def test_should_report_what_would_be_refreshed_and_that_live_is_never_touched(
        self, tmp_path: Path
    ) -> None:
        # Given: a live directory with the synced db files, and a work
        # directory that doesn't exist yet (never pulled before)
        live_dir = tmp_path / "LightingDB"
        live_dir.mkdir()
        for name in sync.SYNCED_DB_NAMES:
            (live_dir / name).write_bytes(b"live-content")
        work_dir = tmp_path / "work"

        # When: building a pull plan
        plan = sync.build_pull_plan(live_dir, work_dir)

        # Then: it reports what would be refreshed, and — critically —
        # that pull only ever overwrites the disposable working copy
        assert set(plan.db_names) == set(sync.SYNCED_DB_NAMES)
        assert plan.lightingdb_dir == live_dir
        assert plan.work_dir == work_dir
        assert plan.touches_live is False

    def test_should_perform_no_write_when_building(self, tmp_path: Path) -> None:
        # Given: a live dir with content, no work dir yet
        live_dir = tmp_path / "LightingDB"
        live_dir.mkdir()
        for name in sync.SYNCED_DB_NAMES:
            (live_dir / name).write_bytes(b"live-content")
        work_dir = tmp_path / "work"

        # When: building the plan (does not pull)
        sync.build_pull_plan(live_dir, work_dir)

        # Then: no work dir was created, nothing was written
        assert not work_dir.exists()
