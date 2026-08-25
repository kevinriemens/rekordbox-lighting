"""Tests for rbxlight.experiments.ninth_bank.apply_ninth_bank — the WRITE
side of the ninth-bank experiment: create one new macro_pattern row (the
"unknown" pattern value 9), clone its phase assignments from a source
bank, and — ONLY if a target track was supplied — repoint exactly one
content row and persist that track's original bank for undo.

Disposable, experiment-specific orchestration built on the permanent
rbxlight.macros.patterns / rbxlight.phrases.repo modules (see
rekordbox-lighting-architecture skill on repo-vs-orchestration
placement). Every write goes through safety.working_copy_write — never
live (rekordbox-data-safety, "WORK ON A COPY, NOT ON LIVE").

Core contract of this refactor: repointing a track is OPTIONAL, and
omitting it (bank-only) is the DEFAULT. The user database (content,
phrase_data — ~2966 rows of irreplaceable user work) must not be written
to, or even have a transaction opened against it, on the bank-only path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rbxlight import safety
from rbxlight.experiments import ninth_bank
from rbxlight.macros import patterns
from rbxlight.phrases import repo as phrases_repo
from tests.fixtures.content_fixtures import many_tracks
from tests.fixtures.pattern_fixtures import (
    ENERGY_MID,
    PHASE_COUNT_BY_ENERGY,
    a_mid_energy_bank,
)


def _build_plan(work_dir_info: dict, **overrides: object) -> ninth_bank.NinthBankApplyPlan:
    """Builds a WITH-TRACK plan (content_id supplied)."""
    macro_path = Path(work_dir_info["macro_path"])
    user_path = Path(work_dir_info["user_path"])
    macro_conn = sqlite3.connect(macro_path)
    macro_conn.row_factory = sqlite3.Row
    user_conn = sqlite3.connect(user_path)
    user_conn.row_factory = sqlite3.Row
    try:
        return ninth_bank.build_apply_plan(
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


def _build_bank_only_plan(
    work_dir_info: dict, **overrides: object
) -> ninth_bank.NinthBankApplyPlan:
    """Builds a BANK-ONLY plan (content_id omitted) — never opens a
    connection to user.db3 at all."""
    macro_path = Path(work_dir_info["macro_path"])
    user_path = Path(work_dir_info["user_path"])
    macro_conn = sqlite3.connect(macro_path)
    macro_conn.row_factory = sqlite3.Row
    try:
        return ninth_bank.build_apply_plan(
            macro_conn,
            source_pattern_id=overrides.get(
                "source_pattern_id", work_dir_info["source_pattern_id"]
            ),
            macro_db_path=macro_path,
            user_db_path=user_path,
        )
    finally:
        macro_conn.close()


class TestApplyNinthBankWithTrack:
    def test_should_create_exactly_one_new_bank_pattern_row_with_pattern_value_9(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a valid apply plan
        plan = _build_plan(ninth_bank_work_dir)

        # When: applying it
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: exactly one new macro_pattern row, with the "unknown"
        # pattern value 9
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        created = patterns.get_macro_pattern(macro_conn, plan.new_pattern_id)
        macro_conn.close()
        assert created.pattern == 9

    def test_should_create_phase_assignment_rows_matching_the_source_count(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a valid apply plan (source bank has 11 real phases)
        plan = _build_plan(ninth_bank_work_dir)

        # When: applying it
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: exactly as many phase rows as the source had — never a
        # hardcoded count
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        created_assign = patterns.list_macro_assign(macro_conn, plan.new_pattern_id)
        macro_conn.close()
        assert len(created_assign) == plan.phase_count == 11

    def test_should_repoint_exactly_the_target_track_and_no_other(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: several tracks sharing the source bank, one of which is
        # the apply target
        user_conn = sqlite3.connect(ninth_bank_work_dir["user_path"])
        many_tracks(user_conn, content_ids=(2, 3), macro_pattern_id=1)
        user_conn.close()

        plan = _build_plan(ninth_bank_work_dir)

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: only the target track's macro_pattern_id changed
        user_conn = sqlite3.connect(ninth_bank_work_dir["user_path"])
        user_conn.row_factory = sqlite3.Row
        target = phrases_repo.get_content(user_conn, ninth_bank_work_dir["content_id"])
        other_1 = phrases_repo.get_content(user_conn, 2)
        other_2 = phrases_repo.get_content(user_conn, 3)
        user_conn.close()
        assert target.macro_pattern_id == plan.new_pattern_id
        assert other_1.macro_pattern_id == 1
        assert other_2.macro_pattern_id == 1

    def test_should_persist_undo_state_to_disk_with_the_track_recorded(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a valid apply plan
        plan = _build_plan(ninth_bank_work_dir)
        state_path = tmp_path / "state.json"

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=state_path)

        # Then: state file exists and carries exactly what revert needs
        state = ninth_bank.load_ninth_bank_state(state_path)
        assert state is not None
        assert state.new_pattern_id == plan.new_pattern_id
        assert state.content_id == plan.content_id
        assert state.original_macro_pattern_id == plan.original_macro_pattern_id


class TestApplyNinthBankBankOnly:
    """The new DEFAULT: no target track supplied. Adds the bank and its
    cloned phase assignments; performs NO write whatsoever to user.db3,
    and no transaction is even opened against it.
    """

    def test_should_create_exactly_one_new_bank_pattern_row_with_pattern_value_9(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: a valid bank-only apply plan
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)

        # When: applying it
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: exactly one new macro_pattern row, pattern value 9
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        created = patterns.get_macro_pattern(macro_conn, plan.new_pattern_id)
        macro_conn.close()
        assert created.pattern == 9

    def test_should_create_phase_assignment_rows_matching_the_source_count(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: a valid bank-only apply plan (source bank has 11 real
        # phases)
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)

        # When: applying it
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: exactly as many phase rows as the source had
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        created_assign = patterns.list_macro_assign(macro_conn, plan.new_pattern_id)
        macro_conn.close()
        assert len(created_assign) == plan.phase_count == 11

    def test_should_leave_the_user_database_byte_identical(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: the current bytes of user.db3
        user_path = Path(ninth_bank_work_dir_no_tracks["user_path"])
        user_bytes_before = user_path.read_bytes()
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)

        # When: applying a bank-only plan
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: user.db3 is untouched, byte for byte
        assert user_path.read_bytes() == user_bytes_before

    def test_should_never_open_a_transaction_against_the_user_database(
        self,
        ninth_bank_work_dir_no_tracks: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a spy on safety.working_copy_write recording every
        # db_name it is invoked with
        opened_db_names: list[str] = []
        original_working_copy_write = safety.working_copy_write

        def _spy(db_name: str):
            opened_db_names.append(db_name)
            return original_working_copy_write(db_name)

        monkeypatch.setattr(safety, "working_copy_write", _spy)
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)

        # When: applying a bank-only plan
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: only macro.db3 was ever opened for writing — user.db3
        # never appears, not even once
        assert opened_db_names == ["macro.db3"]

    def test_should_persist_undo_state_with_no_track_recorded(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: a valid bank-only apply plan
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)
        state_path = tmp_path / "state.json"

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=state_path)

        # Then: state file records the new bank but no track
        state = ninth_bank.load_ninth_bank_state(state_path)
        assert state is not None
        assert state.new_pattern_id == plan.new_pattern_id
        assert state.content_id is None
        assert state.original_macro_pattern_id is None


class TestApplyNinthBankPhaseCountFidelity:
    """Requirement: the phase count is copied, never assumed. Covered
    end-to-end (not just at the repo layer) with two source banks of
    different phase counts, in both the with-track and bank-only shapes.
    """

    def test_should_create_11_rows_when_source_bank_is_high_energy(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: the fixture's default HIGH-energy (11-phase) source bank
        plan = _build_plan(ninth_bank_work_dir)

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: 11 phase rows created
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        count = len(patterns.list_macro_assign(macro_conn, plan.new_pattern_id))
        macro_conn.close()
        assert count == 11

    def test_should_create_10_rows_when_source_bank_is_mid_energy(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: a SEPARATE, MID-energy (10-phase) source bank — a
        # different phase count from the HIGH case above
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        mid_pattern_id = a_mid_energy_bank(macro_conn, pattern_id=2)
        macro_conn.close()

        plan = _build_plan(ninth_bank_work_dir, source_pattern_id=mid_pattern_id)
        assert plan.phase_count == PHASE_COUNT_BY_ENERGY[ENERGY_MID] == 10

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: 10 phase rows created — following the source, not the
        # first test's count
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        count = len(patterns.list_macro_assign(macro_conn, plan.new_pattern_id))
        macro_conn.close()
        assert count == 10

    def test_should_create_10_rows_when_source_bank_is_mid_energy_bank_only(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: a MID-energy (10-phase) source bank, bank-only shape —
        # phase count must still be read from the source, not assumed,
        # regardless of whether a track is being repointed
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        mid_pattern_id = a_mid_energy_bank(macro_conn, pattern_id=2)
        macro_conn.close()

        plan = _build_bank_only_plan(
            ninth_bank_work_dir_no_tracks, source_pattern_id=mid_pattern_id
        )
        assert plan.phase_count == PHASE_COUNT_BY_ENERGY[ENERGY_MID] == 10

        # When: applying
        ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: 10 phase rows created
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        count = len(patterns.list_macro_assign(macro_conn, plan.new_pattern_id))
        macro_conn.close()
        assert count == 10


class TestNinthBankDoubleApplyGuard:
    """Requirement: the outstanding-change guard holds in both shapes,
    and across mixed shapes — the guard is keyed on whether ANY undo
    state exists on disk, not on which shape produced it.
    """

    def test_should_refuse_a_second_with_track_apply_while_one_is_outstanding(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: an already-applied, un-reverted with-track change
        state_path = tmp_path / "state.json"
        first_plan = _build_plan(ninth_bank_work_dir)
        ninth_bank.apply_ninth_bank(first_plan, state_path=state_path)

        # When / Then: applying again is refused, not silently overwritten
        second_plan = _build_plan(ninth_bank_work_dir)
        with pytest.raises(ninth_bank.NinthBankAlreadyAppliedError):
            ninth_bank.apply_ninth_bank(second_plan, state_path=state_path)

        # And: no second new bank was created
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        all_patterns = patterns.list_macro_patterns(macro_conn)
        macro_conn.close()
        assert len(all_patterns) == 2  # the original source bank + one new bank

    def test_should_refuse_a_second_bank_only_apply_while_one_is_outstanding(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # Given: an already-applied, un-reverted bank-only change
        state_path = tmp_path / "state.json"
        first_plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)
        ninth_bank.apply_ninth_bank(first_plan, state_path=state_path)

        # When / Then: applying again is refused
        second_plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)
        with pytest.raises(ninth_bank.NinthBankAlreadyAppliedError):
            ninth_bank.apply_ninth_bank(second_plan, state_path=state_path)

        # And: no second new bank was created
        macro_conn = sqlite3.connect(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        all_patterns = patterns.list_macro_patterns(macro_conn)
        macro_conn.close()
        assert len(all_patterns) == 2

    def test_should_refuse_a_with_track_apply_when_a_bank_only_apply_is_outstanding(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: an outstanding BANK-ONLY change
        state_path = tmp_path / "state.json"
        bank_only_plan = _build_bank_only_plan(ninth_bank_work_dir)
        ninth_bank.apply_ninth_bank(bank_only_plan, state_path=state_path)

        # When / Then: a WITH-TRACK apply is refused too — the guard
        # doesn't care which shape produced the outstanding state
        with_track_plan = _build_plan(ninth_bank_work_dir)
        with pytest.raises(ninth_bank.NinthBankAlreadyAppliedError):
            ninth_bank.apply_ninth_bank(with_track_plan, state_path=state_path)

        # And: the target track was never repointed by the refused apply
        user_conn = sqlite3.connect(ninth_bank_work_dir["user_path"])
        user_conn.row_factory = sqlite3.Row
        content = phrases_repo.get_content(user_conn, ninth_bank_work_dir["content_id"])
        user_conn.close()
        assert content.macro_pattern_id == 1

    def test_should_refuse_a_bank_only_apply_when_a_with_track_apply_is_outstanding(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: an outstanding WITH-TRACK change
        state_path = tmp_path / "state.json"
        with_track_plan = _build_plan(ninth_bank_work_dir)
        ninth_bank.apply_ninth_bank(with_track_plan, state_path=state_path)

        # When / Then: a BANK-ONLY apply is refused too
        bank_only_plan = _build_bank_only_plan(ninth_bank_work_dir)
        with pytest.raises(ninth_bank.NinthBankAlreadyAppliedError):
            ninth_bank.apply_ninth_bank(bank_only_plan, state_path=state_path)

        # And: no second new bank was created
        macro_conn = sqlite3.connect(ninth_bank_work_dir["macro_path"])
        macro_conn.row_factory = sqlite3.Row
        all_patterns = patterns.list_macro_patterns(macro_conn)
        macro_conn.close()
        assert len(all_patterns) == 2

    def test_should_not_overwrite_the_existing_undo_state_on_a_refused_double_apply(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # Given: an already-applied change, whose state was recorded
        state_path = tmp_path / "state.json"
        first_plan = _build_plan(ninth_bank_work_dir)
        ninth_bank.apply_ninth_bank(first_plan, state_path=state_path)
        state_before = ninth_bank.load_ninth_bank_state(state_path)

        # When: a second apply is attempted and refused
        second_plan = _build_plan(ninth_bank_work_dir)
        with pytest.raises(ninth_bank.NinthBankAlreadyAppliedError):
            ninth_bank.apply_ninth_bank(second_plan, state_path=state_path)

        # Then: the original undo record is untouched — otherwise undo
        # would be impossible
        state_after = ninth_bank.load_ninth_bank_state(state_path)
        assert state_after == state_before


class TestNinthBankApplyTransactionality:
    """No cross-file atomicity is claimed or tested (macro.db3 and
    user.db3 are written in separate transactions, by design — the
    working copy is regenerable). Each INDIVIDUAL file's write must still
    be transactional: a failure mid-write leaves THAT file unchanged.
    """

    def test_should_leave_macro_db_unchanged_when_its_write_fails_mid_transaction(
        self,
        ninth_bank_work_dir: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a valid plan, and a forced failure partway through the
        # macro.db3 write (after the new bank row was created, during
        # phase-assignment cloning)
        plan = _build_plan(ninth_bank_work_dir)
        macro_path = Path(ninth_bank_work_dir["macro_path"])
        macro_bytes_before = macro_path.read_bytes()

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(patterns, "clone_macro_assign", _boom)

        # When: applying (expected to raise)
        with pytest.raises(RuntimeError, match="boom"):
            ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: macro.db3 rolled back to byte-for-byte unchanged — the new
        # bank row is gone too, not left half-written
        assert macro_path.read_bytes() == macro_bytes_before

    def test_should_leave_macro_db_unchanged_when_bank_only_write_fails_mid_transaction(
        self,
        ninth_bank_work_dir_no_tracks: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a valid bank-only plan, and a forced failure partway
        # through the macro.db3 write
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)
        macro_path = Path(ninth_bank_work_dir_no_tracks["macro_path"])
        macro_bytes_before = macro_path.read_bytes()

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(patterns, "clone_macro_assign", _boom)

        # When: applying (expected to raise)
        with pytest.raises(RuntimeError, match="boom"):
            ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: macro.db3 rolled back to byte-for-byte unchanged
        assert macro_path.read_bytes() == macro_bytes_before

    def test_should_leave_user_db_unchanged_when_its_write_fails_mid_transaction(
        self,
        ninth_bank_work_dir: dict,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: a valid plan, and a forced failure during the user.db3
        # write (the macro.db3 write, in its own separate transaction,
        # has already completed by this point — no cross-file atomicity
        # is claimed)
        plan = _build_plan(ninth_bank_work_dir)
        user_path = Path(ninth_bank_work_dir["user_path"])
        user_bytes_before = user_path.read_bytes()

        def _boom(*args: object, **kwargs: object) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr(phrases_repo, "update_content_macro_pattern_id", _boom)

        # When: applying (expected to raise)
        with pytest.raises(RuntimeError, match="boom"):
            ninth_bank.apply_ninth_bank(plan, state_path=tmp_path / "state.json")

        # Then: user.db3's OWN write rolled back to byte-for-byte unchanged
        assert user_path.read_bytes() == user_bytes_before


class TestNinthBankApplyEdgeCases:
    def test_should_raise_no_source_bank_error_for_a_nonexistent_source_with_track(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # When / Then: building the plan itself refuses — apply never runs
        with pytest.raises(ninth_bank.NoSourceBankError):
            _build_plan(ninth_bank_work_dir, source_pattern_id=99999)

    def test_should_raise_no_source_bank_error_for_a_nonexistent_source_bank_only(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # When / Then: refused before writing anything, bank-only shape
        with pytest.raises(ninth_bank.NoSourceBankError):
            _build_bank_only_plan(
                ninth_bank_work_dir_no_tracks, source_pattern_id=99999
            )

    def test_should_raise_no_target_track_error_for_a_nonexistent_supplied_track(
        self, ninth_bank_work_dir: dict, tmp_path: Path
    ) -> None:
        # When / Then: building the plan itself refuses — apply never runs
        with pytest.raises(ninth_bank.NoTargetTrackError):
            _build_plan(ninth_bank_work_dir, content_id=99999)

    def test_should_not_raise_no_target_track_error_when_no_track_is_supplied(
        self, ninth_bank_work_dir_no_tracks: dict, tmp_path: Path
    ) -> None:
        # When / Then: omitting the target track entirely is the default
        # and never raises NoTargetTrackError
        plan = _build_bank_only_plan(ninth_bank_work_dir_no_tracks)
        assert plan.content_id is None
