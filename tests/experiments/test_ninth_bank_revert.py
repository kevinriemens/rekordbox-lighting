"""Tests for rbxlight.experiments.ninth_bank.revert_ninth_bank — undoing an
applied ninth-bank change: the new bank row and its phase assignments are
removed, and the track's original macro_pattern_id is restored, exactly.

On "byte-identical": raw SQLite file bytes are NOT a reliable equality
check across an INSERT-then-DELETE round trip — verified empirically,
SQLite's own freelist/page-reuse bookkeeping can leave the file's raw
bytes (and even its size) different from the pre-write state even when
every row is logically identical afterwards, with no corruption involved.
A full logical dump (`sqlite3.Connection.iterdump()`) comparison is the
non-flaky equivalent that still catches ANY discrepancy in ANY row or
column across the whole database, so that is what these tests assert
instead of raw `read_bytes()` for the round-trip cases. Tests that assert
NOTHING was written at all (revert with no outstanding change) still use
plain byte comparison, since a true no-op is trivially byte-identical.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight.experiments import ninth_bank
from rbxlight.macros import patterns
from rbxlight.phrases import repo as phrases_repo


def _dump(path: Path) -> str:
    conn = sqlite3.connect(path)
    text = "\n".join(conn.iterdump())
    conn.close()
    return text


def _build_and_apply(
    work_dir_info: dict, state_path: Path, **overrides: object
) -> ninth_bank.NinthBankApplyPlan:
    macro_path = Path(work_dir_info["macro_path"])
    user_path = Path(work_dir_info["user_path"])
    macro_conn = sqlite3.connect(macro_path)
    macro_conn.row_factory = sqlite3.Row
    user_conn = sqlite3.connect(user_path)
    user_conn.row_factory = sqlite3.Row
    try:
        plan = ninth_bank.build_apply_plan(
            macro_conn,
            user_conn,
            source_pattern_id=overrides.get(
                "source_pattern_id", work_dir_info["source_pattern_id"]
            ),
            content_id=overrides.get("content_id", work_dir_info["content_id"]),
            macro_db_path=macro_path,
            user_db_path=user_path,
        )
    finally:
        macro_conn.close()
        user_conn.close()
    ninth_bank.apply_ninth_bank(plan, state_path=state_path)
    return plan


class TestRevertNinthBank:
    def test_should_restore_both_databases_to_their_exact_pre_apply_state(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: the pre-apply logical content of both databases
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_dump_before = _dump(macro_path)
        user_dump_before = _dump(user_path)

        state_path = tmp_path / "state.json"
        plan = _build_and_apply(ninth_bank_work_dir, state_path)

        # When: reverting — using ONLY the persisted state file, exactly
        # as a separate `revert` invocation would (no in-memory plan
        # object carried over from apply)
        revert_plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # Then: the new bank row is gone
        macro_conn = sqlite3.connect(macro_path)
        macro_conn.row_factory = sqlite3.Row
        with pytest.raises(LookupError):
            patterns.get_macro_pattern(macro_conn, plan.new_pattern_id)

        # And: its phase-assignment rows are gone
        assert patterns.list_macro_assign(macro_conn, plan.new_pattern_id) == []
        macro_conn.close()

        # And: the track's original bank-pattern reference is restored
        # to the exact prior value
        user_conn = sqlite3.connect(user_path)
        user_conn.row_factory = sqlite3.Row
        restored = phrases_repo.get_content(user_conn, plan.content_id)
        user_conn.close()
        assert restored.macro_pattern_id == plan.original_macro_pattern_id == 1

        # And: both databases are back to their exact pre-apply logical
        # state (see module docstring on why this is a dump comparison,
        # not a raw byte comparison)
        assert _dump(macro_path) == macro_dump_before
        assert _dump(user_path) == user_dump_before

        # And: the undo state file itself is cleaned up
        assert not state_path.exists()

    def test_should_be_a_no_op_when_nothing_was_ever_applied(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: no state file — nothing was ever applied
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_bytes_before = macro_path.read_bytes()
        user_bytes_before = user_path.read_bytes()
        state_path = tmp_path / "never-applied.json"

        # When: reverting anyway
        plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(plan, state_path=state_path)

        # Then: no exception, and nothing changed — a true no-op
        assert macro_path.read_bytes() == macro_bytes_before
        assert user_path.read_bytes() == user_bytes_before

    def test_should_raise_and_write_nothing_when_state_file_is_corrupt(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a malformed state file
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        user_path = Path(ninth_bank_work_dir["user_path"])
        macro_bytes_before = macro_path.read_bytes()
        user_bytes_before = user_path.read_bytes()
        state_path = tmp_path / "state.json"
        state_path.write_text("{ not valid json")

        # When / Then: fails loudly rather than silently doing the wrong
        # thing
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            ninth_bank.build_revert_plan(state_path)

        # And: nothing was written to either database, and the corrupt
        # file itself is left in place (not silently deleted)
        assert macro_path.read_bytes() == macro_bytes_before
        assert user_path.read_bytes() == user_bytes_before
        assert state_path.exists()

    def test_should_allow_applying_again_after_a_successful_revert(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a full apply -> revert cycle
        state_path = tmp_path / "state.json"
        _build_and_apply(ninth_bank_work_dir, state_path)
        revert_plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # When: applying again — the guard must not be permanently stuck
        second_plan = _build_and_apply(ninth_bank_work_dir, state_path)

        # Then: succeeds, with a freshly allocated bank id
        assert ninth_bank.load_ninth_bank_state(state_path) is not None
        assert second_plan.new_pattern_id >= 1
