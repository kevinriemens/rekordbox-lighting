"""Tests for rbxlight.experiments.ninth_bank.revert_ninth_bank — undoing an
applied ninth-bank change: the new bank row and its phase assignments are
removed, and — ONLY if a track was actually repointed by the apply being
undone — the track's original macro_pattern_id is restored, exactly.

Reverting a BANK-ONLY apply must remove the bank cleanly and must NOT fail
or no-op merely because no track was ever recorded — "nothing was
repointed" is a different fact from "nothing to revert".

On "byte-identical": raw SQLite file bytes are NOT a reliable equality
check across an INSERT-then-DELETE round trip — verified empirically,
SQLite's own freelist/page-reuse bookkeeping can leave the file's raw
bytes (and even its size) different from the pre-write state even when
every row is logically identical afterwards, with no corruption involved.
A full logical dump (`sqlite3.Connection.iterdump()`) comparison is the
non-flaky equivalent that still catches ANY discrepancy in ANY row or
column across the whole database, so that is what these tests assert
instead of raw `read_bytes()` for the round-trip cases. Tests that assert
NOTHING was written at all (revert with no outstanding change, or the
user.db3 side of a bank-only apply/revert cycle, which is never opened at
all) still use plain byte comparison, since a true no-op is trivially
byte-identical.
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
    """Builds and applies a WITH-TRACK plan."""
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


def _build_and_apply_bank_only(
    work_dir_info: dict, state_path: Path, **overrides: object
) -> ninth_bank.NinthBankApplyPlan:
    """Builds and applies a BANK-ONLY plan — no target track supplied."""
    macro_path = Path(work_dir_info["macro_path"])
    user_path = Path(work_dir_info["user_path"])
    macro_conn = sqlite3.connect(macro_path)
    macro_conn.row_factory = sqlite3.Row
    try:
        plan = ninth_bank.build_apply_plan(
            macro_conn,
            source_pattern_id=overrides.get(
                "source_pattern_id", work_dir_info["source_pattern_id"]
            ),
            macro_db_path=macro_path,
            user_db_path=user_path,
        )
    finally:
        macro_conn.close()
    ninth_bank.apply_ninth_bank(plan, state_path=state_path)
    return plan


class TestRevertNinthBankWithTrack:
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


class TestRevertNinthBankBankOnly:
    """Reverting a BANK-ONLY apply: removes the provisional bank and its
    phase assignments. Restores no track, because none was repointed.
    Must not fail or no-op merely because no track is recorded — the
    bank itself is still outstanding and must still be removed.
    """

    def test_should_remove_the_bank_and_its_phase_assignments(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: a bank-only apply, with no track ever recorded
        macro_path = Path(ninth_bank_work_dir_no_tracks["macro_path"])
        state_path = tmp_path / "state.json"
        plan = _build_and_apply_bank_only(ninth_bank_work_dir_no_tracks, state_path)

        # When: reverting via the persisted state — the revert plan must
        # report there IS something to revert, not "nothing to revert",
        # even though content_id/original_macro_pattern_id are None
        revert_plan = ninth_bank.build_revert_plan(state_path)
        assert revert_plan.nothing_to_revert is False
        assert revert_plan.content_id is None
        assert revert_plan.original_macro_pattern_id is None

        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # Then: the new bank row and its phase assignments are gone
        macro_conn = sqlite3.connect(macro_path)
        macro_conn.row_factory = sqlite3.Row
        with pytest.raises(LookupError):
            patterns.get_macro_pattern(macro_conn, plan.new_pattern_id)
        assert patterns.list_macro_assign(macro_conn, plan.new_pattern_id) == []
        macro_conn.close()

        # And: the undo state file is cleaned up
        assert not state_path.exists()

    def test_should_leave_the_user_database_byte_identical_across_apply_and_revert(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: user.db3's bytes before any of this ran
        user_path = Path(ninth_bank_work_dir_no_tracks["user_path"])
        user_bytes_before = user_path.read_bytes()
        state_path = tmp_path / "state.json"

        # When: a full bank-only apply -> revert cycle
        _build_and_apply_bank_only(ninth_bank_work_dir_no_tracks, state_path)
        revert_plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # Then: user.db3 was never opened at any point — byte-identical
        # (a valid plain-byte comparison here, since it was never written
        # to at all, unlike the macro.db3 insert/delete round trip)
        assert user_path.read_bytes() == user_bytes_before

    def test_should_restore_macro_db_to_its_exact_pre_apply_logical_state(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: the pre-apply logical content of macro.db3
        macro_path = Path(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_dump_before = _dump(macro_path)
        state_path = tmp_path / "state.json"

        # When: a full bank-only apply -> revert cycle
        _build_and_apply_bank_only(ninth_bank_work_dir_no_tracks, state_path)
        revert_plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # Then: macro.db3 is back to its exact pre-apply logical state
        assert _dump(macro_path) == macro_dump_before

    def test_should_allow_a_second_bank_only_apply_after_reverting_the_first(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: bank-only apply -> revert
        state_path = tmp_path / "state.json"
        _build_and_apply_bank_only(ninth_bank_work_dir_no_tracks, state_path)
        revert_plan = ninth_bank.build_revert_plan(state_path)
        ninth_bank.revert_ninth_bank(revert_plan, state_path=state_path)

        # When: applying bank-only again — ids must reallocate cleanly,
        # not collide with the reverted (now-deleted) bank
        second_plan = _build_and_apply_bank_only(
            ninth_bank_work_dir_no_tracks, state_path
        )

        # Then: succeeds, with the bank present under a fresh id
        assert second_plan.new_pattern_id >= 1
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        created = patterns.get_macro_pattern(macro_conn, second_plan.new_pattern_id)
        macro_conn.close()
        assert created.pattern == 9
        assert ninth_bank.load_ninth_bank_state(state_path) is not None
