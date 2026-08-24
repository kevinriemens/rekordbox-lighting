"""Tests for the push dry-run plan object: a typed, immutable description
of what a `push` WOULD do, built with zero writes. Contract:
rekordbox-lighting-architecture ("dry-run by default") +
rekordbox-data-safety ("WORK ON A COPY, NOT ON LIVE" / rule 10, "PUSH IS
STALE-WRITE PROTECTED").
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from rbxlight import sync


@pytest.fixture
def work_dir_with_synced_dbs(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    for name in sync.SYNCED_DB_NAMES:
        (work / name).write_bytes(b"working-copy-content")
    return work


@pytest.fixture
def lightingdb_dir(tmp_path: Path) -> Path:
    live = tmp_path / "LightingDB"
    live.mkdir()
    for name in sync.SYNCED_DB_NAMES:
        (live / name).write_bytes(b"live-content")
    return live


class TestBuildPushPlan:
    def test_should_report_db_names_paths_and_that_live_data_would_be_touched(
        self, work_dir_with_synced_dbs: Path, lightingdb_dir: Path
    ) -> None:
        # When: building a push plan
        plan = sync.build_push_plan(work_dir_with_synced_dbs, lightingdb_dir)

        # Then: it carries the facts needed to render it, and — critically
        # — reports that live data would be touched
        assert set(plan.db_names) == set(sync.SYNCED_DB_NAMES)
        assert plan.work_dir == work_dir_with_synced_dbs
        assert plan.lightingdb_dir == lightingdb_dir
        assert plan.touches_live is True

    def test_should_perform_no_write_when_building(
        self, work_dir_with_synced_dbs: Path, lightingdb_dir: Path
    ) -> None:
        # Given: the live files' current bytes
        original_live_bytes = {
            name: (lightingdb_dir / name).read_bytes() for name in sync.SYNCED_DB_NAMES
        }

        # When: building a push plan (does not push)
        sync.build_push_plan(work_dir_with_synced_dbs, lightingdb_dir)

        # Then: live is untouched, byte-for-byte
        for name in sync.SYNCED_DB_NAMES:
            assert (lightingdb_dir / name).read_bytes() == original_live_bytes[name]

    def test_should_raise_file_not_found_when_working_copy_is_missing(
        self, tmp_path: Path, lightingdb_dir: Path
    ) -> None:
        # Given: a work dir that was never pulled into (matches the
        # existing predictable failure mode of sync.push() itself, which
        # raises FileNotFoundError copying from a missing working copy)
        empty_work_dir = tmp_path / "never-pulled"

        # When / Then: building the plan raises, rather than describing a
        # push of nonexistent files
        with pytest.raises(FileNotFoundError):
            sync.build_push_plan(empty_work_dir, lightingdb_dir)

    def test_should_be_immutable(
        self, work_dir_with_synced_dbs: Path, lightingdb_dir: Path
    ) -> None:
        # Given: a built push plan
        plan = sync.build_push_plan(work_dir_with_synced_dbs, lightingdb_dir)

        # When / Then: mutating any field raises
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.touches_live = False  # type: ignore[misc]
