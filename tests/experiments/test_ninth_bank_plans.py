"""Tests for the ninth-bank experiment's dry-run plan objects
(NinthBankApplyPlan / NinthBankRevertPlan): typed, immutable descriptions
of what `experiment ninth-bank apply`/`revert` WOULD do, built with zero
writes.

Contract: rekordbox-lighting-architecture ("dry-run by default", typed
frozen plan objects) + rekordbox-data-safety (rule 7, "DRY-RUN BY
DEFAULT"). Follows the exact idiom already established for macro
create/delete plans (tests/macros/test_plans.py) and extended
cross-cuttingly for pull/restore/layout plans
(tests/test_orchestration_plans_touch_nothing.py): building a plan must
never create, open for writing, or modify any file — proven here by byte-
identical comparison of both macro.db3 and user.db3 before/after building,
plus (for revert) the state file itself.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from rbxlight.experiments import ninth_bank


def _open(macro_path: Path, user_path: Path) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    macro_conn = sqlite3.connect(macro_path)
    macro_conn.row_factory = sqlite3.Row
    user_conn = sqlite3.connect(user_path)
    user_conn.row_factory = sqlite3.Row
    return macro_conn, user_conn


class TestBuildApplyPlan:
    def test_should_report_the_true_blast_radius(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: a HIGH-energy (11-phase) source bank and a target track
        macro_conn, user_conn = _open(
            ninth_bank_work_dir["macro_path"], ninth_bank_work_dir["user_path"]
        )

        # When: building an apply plan
        plan = ninth_bank.build_apply_plan(
            macro_conn,
            user_conn,
            source_pattern_id=ninth_bank_work_dir["source_pattern_id"],
            content_id=ninth_bank_work_dir["content_id"],
            macro_db_path=ninth_bank_work_dir["macro_path"],
            user_db_path=ninth_bank_work_dir["user_path"],
        )
        macro_conn.close()
        user_conn.close()

        # Then: it describes exactly what would change — the new bank's
        # id (one past the current max, here 1 -> 2), the "unknown"
        # pattern value 9, how many phase rows would be created (11, from
        # the source), and which single track would be repointed
        assert plan.new_pattern_id == 2
        assert plan.new_pattern_value == 9
        assert plan.phase_count == 11
        assert plan.content_id == ninth_bank_work_dir["content_id"]
        assert plan.source_pattern_id == ninth_bank_work_dir["source_pattern_id"]
        assert plan.original_macro_pattern_id == 1
        assert plan.touches_live is False

    def test_should_perform_no_write_when_building(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: current bytes of both working-copy databases
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_bytes_before = macro_path.read_bytes()
        user_bytes_before = user_path.read_bytes()

        macro_conn, user_conn = _open(macro_path, user_path)

        # When: building a plan only
        ninth_bank.build_apply_plan(
            macro_conn,
            user_conn,
            source_pattern_id=ninth_bank_work_dir["source_pattern_id"],
            content_id=ninth_bank_work_dir["content_id"],
            macro_db_path=macro_path,
            user_db_path=user_path,
        )
        macro_conn.close()
        user_conn.close()

        # Then: both files byte-for-byte unchanged
        assert macro_path.read_bytes() == macro_bytes_before
        assert user_path.read_bytes() == user_bytes_before

    def test_should_be_immutable(self, ninth_bank_work_dir: dict) -> None:
        # Given: a built apply plan
        macro_conn, user_conn = _open(
            ninth_bank_work_dir["macro_path"], ninth_bank_work_dir["user_path"]
        )
        plan = ninth_bank.build_apply_plan(
            macro_conn,
            user_conn,
            source_pattern_id=ninth_bank_work_dir["source_pattern_id"],
            content_id=ninth_bank_work_dir["content_id"],
            macro_db_path=ninth_bank_work_dir["macro_path"],
            user_db_path=ninth_bank_work_dir["user_path"],
        )
        macro_conn.close()
        user_conn.close()

        # When / Then: mutating any field raises
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.new_pattern_id = 999  # type: ignore[misc]

    def test_should_raise_no_source_bank_error_when_source_pattern_missing(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: a source_pattern_id with no matching macro_pattern row
        macro_conn, user_conn = _open(
            ninth_bank_work_dir["macro_path"], ninth_bank_work_dir["user_path"]
        )

        # When / Then: a clear, typed failure — never a generic KeyError
        with pytest.raises(ninth_bank.NoSourceBankError):
            ninth_bank.build_apply_plan(
                macro_conn,
                user_conn,
                source_pattern_id=99999,
                content_id=ninth_bank_work_dir["content_id"],
                macro_db_path=ninth_bank_work_dir["macro_path"],
                user_db_path=ninth_bank_work_dir["user_path"],
            )
        macro_conn.close()
        user_conn.close()

    def test_should_write_nothing_when_source_bank_missing(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: both files' current bytes
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_bytes_before = macro_path.read_bytes()
        user_bytes_before = user_path.read_bytes()
        macro_conn, user_conn = _open(macro_path, user_path)

        # When: attempting to build a plan for a nonexistent source bank
        with pytest.raises(ninth_bank.NoSourceBankError):
            ninth_bank.build_apply_plan(
                macro_conn,
                user_conn,
                source_pattern_id=99999,
                content_id=ninth_bank_work_dir["content_id"],
                macro_db_path=macro_path,
                user_db_path=user_path,
            )
        macro_conn.close()
        user_conn.close()

        # Then: nothing written
        assert macro_path.read_bytes() == macro_bytes_before
        assert user_path.read_bytes() == user_bytes_before

    def test_should_raise_no_target_track_error_when_content_missing(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: a content_id with no matching content row
        macro_conn, user_conn = _open(
            ninth_bank_work_dir["macro_path"], ninth_bank_work_dir["user_path"]
        )

        # When / Then: a clear, typed failure
        with pytest.raises(ninth_bank.NoTargetTrackError):
            ninth_bank.build_apply_plan(
                macro_conn,
                user_conn,
                source_pattern_id=ninth_bank_work_dir["source_pattern_id"],
                content_id=99999,
                macro_db_path=ninth_bank_work_dir["macro_path"],
                user_db_path=ninth_bank_work_dir["user_path"],
            )
        macro_conn.close()
        user_conn.close()

    def test_should_write_nothing_when_target_track_missing(
        self, ninth_bank_work_dir: dict
    ) -> None:
        # Given: both files' current bytes
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_bytes_before = macro_path.read_bytes()
        user_bytes_before = user_path.read_bytes()
        macro_conn, user_conn = _open(macro_path, user_path)

        # When: attempting to build a plan for a nonexistent target track
        with pytest.raises(ninth_bank.NoTargetTrackError):
            ninth_bank.build_apply_plan(
                macro_conn,
                user_conn,
                source_pattern_id=ninth_bank_work_dir["source_pattern_id"],
                content_id=99999,
                macro_db_path=macro_path,
                user_db_path=user_path,
            )
        macro_conn.close()
        user_conn.close()

        # Then: nothing written
        assert macro_path.read_bytes() == macro_bytes_before
        assert user_path.read_bytes() == user_bytes_before


class TestBuildRevertPlan:
    def test_should_report_nothing_to_revert_when_state_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        # Given: a state path that was never written
        state_path = tmp_path / "never-applied.json"

        # When: building a revert plan
        plan = ninth_bank.build_revert_plan(state_path)

        # Then: reports "nothing to revert" rather than crashing
        assert plan.nothing_to_revert is True
        assert plan.touches_live is False

    def test_should_report_the_outstanding_change_when_state_exists(
        self, tmp_path: Path
    ) -> None:
        # Given: a persisted outstanding change
        state_path = tmp_path / "state.json"
        ninth_bank.save_ninth_bank_state(
            state_path,
            ninth_bank.NinthBankState(
                new_pattern_id=28, content_id=5, original_macro_pattern_id=3
            ),
        )

        # When: building a revert plan
        plan = ninth_bank.build_revert_plan(state_path)

        # Then: it carries the exact facts needed to undo it
        assert plan.nothing_to_revert is False
        assert plan.new_pattern_id == 28
        assert plan.content_id == 5
        assert plan.original_macro_pattern_id == 3
        assert plan.touches_live is False

    def test_should_raise_a_clear_error_for_a_corrupt_state_file(
        self, tmp_path: Path
    ) -> None:
        # Given: a malformed state file
        state_path = tmp_path / "state.json"
        state_path.write_text("{not valid json")

        # When / Then: fails loudly with a typed, actionable error
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            ninth_bank.build_revert_plan(state_path)

    def test_should_perform_no_write_when_building_with_state_present(
        self, tmp_path: Path
    ) -> None:
        # Given: an existing state file
        state_path = tmp_path / "state.json"
        ninth_bank.save_ninth_bank_state(
            state_path,
            ninth_bank.NinthBankState(
                new_pattern_id=28, content_id=5, original_macro_pattern_id=3
            ),
        )
        original_bytes = state_path.read_bytes()

        # When: building a revert plan only
        ninth_bank.build_revert_plan(state_path)

        # Then: the state file itself is unchanged
        assert state_path.read_bytes() == original_bytes

    def test_should_perform_no_write_when_building_with_state_absent(
        self, tmp_path: Path
    ) -> None:
        # Given: no state file
        state_path = tmp_path / "never-applied.json"

        # When: building a revert plan only
        ninth_bank.build_revert_plan(state_path)

        # Then: still absent — building a plan creates nothing
        assert not state_path.exists()
