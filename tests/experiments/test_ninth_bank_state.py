"""Tests for the ninth-bank experiment's persisted undo state: a small
on-disk record of what apply changed, written by `apply` and read back by
`revert` — potentially in a SEPARATE process invocation (requirement:
"undo survives a separate invocation"). Mirrors the on-disk state idiom
already used elsewhere in this project (sync.py's `.pull-state.json`,
preview.layout's saved layout files): plain JSON, `None` for "file
absent" (not an error), a dedicated typed error for anything malformed.

Two valid shapes, both round-trip faithfully:
- WITH a track: `content_id` and `original_macro_pattern_id` both set —
  the with-track apply repointed a track and recorded its original bank.
- WITHOUT a track (bank-only, the new default): `content_id` and
  `original_macro_pattern_id` both `None` — no track was ever repointed,
  so there is nothing to restore, and that is a VALID, not corrupt, state.

`new_pattern_id` is the only field required in every shape. A state
missing it, or one that records only one of the two track fields (an
internally inconsistent partial track record), is genuinely malformed —
distinguishable from the valid no-track shape, which cleanly omits BOTH
track fields together.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rbxlight.experiments import ninth_bank


class TestSaveAndLoadNinthBankStateWithTrack:
    def test_should_round_trip_exactly(self, tmp_path: Path) -> None:
        # Given: a state describing an outstanding change that repointed
        # a track
        state_path = tmp_path / "state.json"
        state = ninth_bank.NinthBankState(
            new_pattern_id=28, content_id=42, original_macro_pattern_id=7
        )

        # When: saving then loading it back
        ninth_bank.save_ninth_bank_state(state_path, state)
        loaded = ninth_bank.load_ninth_bank_state(state_path)

        # Then: identical to what was saved
        assert loaded == state
        assert loaded.content_id == 42
        assert loaded.original_macro_pattern_id == 7


class TestSaveAndLoadNinthBankStateBankOnly:
    def test_should_round_trip_exactly_with_no_track_recorded(
        self, tmp_path: Path
    ) -> None:
        # Given: a state describing a BANK-ONLY apply — no track was ever
        # repointed, so there is nothing to record for one
        state_path = tmp_path / "state.json"
        state = ninth_bank.NinthBankState(new_pattern_id=28)

        # When: saving then loading it back
        ninth_bank.save_ninth_bank_state(state_path, state)
        loaded = ninth_bank.load_ninth_bank_state(state_path)

        # Then: identical to what was saved — a valid state, not an error
        assert loaded == state
        assert loaded.new_pattern_id == 28
        assert loaded.content_id is None
        assert loaded.original_macro_pattern_id is None

    def test_should_default_track_fields_to_none_when_constructed_bare(self) -> None:
        # Given / When: a state built with only the field every shape
        # requires
        state = ninth_bank.NinthBankState(new_pattern_id=28)

        # Then: the track fields default to None, not a required int
        assert state.content_id is None
        assert state.original_macro_pattern_id is None

    def test_should_be_a_valid_state_when_the_on_disk_json_omits_track_fields(
        self, tmp_path: Path
    ) -> None:
        # Given: a hand-written state file that only carries the one
        # universally-required field — exactly what a bank-only apply
        # persists. This must be treated as VALID, not corrupt.
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"new_pattern_id": 28}))

        # When: loading it
        loaded = ninth_bank.load_ninth_bank_state(state_path)

        # Then: a normal, valid no-track state — no exception
        assert loaded == ninth_bank.NinthBankState(new_pattern_id=28)

    def test_should_be_a_valid_state_when_track_fields_are_explicit_json_null(
        self, tmp_path: Path
    ) -> None:
        # Given: a state file that spells out the track fields as JSON
        # null rather than omitting the keys entirely — both must be
        # accepted as the same valid no-track shape
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "new_pattern_id": 28,
                    "content_id": None,
                    "original_macro_pattern_id": None,
                }
            )
        )

        # When: loading it
        loaded = ninth_bank.load_ninth_bank_state(state_path)

        # Then: valid, identical to the omitted-keys shape
        assert loaded == ninth_bank.NinthBankState(new_pattern_id=28)


class TestNinthBankStateMissingOrCorrupt:
    def test_should_return_none_when_state_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        # Given: a state path that was never written to — the normal
        # "nothing has ever been applied" case, not an error
        missing_path = tmp_path / "never-written.json"

        # When: loading it
        result = ninth_bank.load_ninth_bank_state(missing_path)

        # Then: None, not an exception
        assert result is None

    def test_should_raise_a_clear_error_for_malformed_json(
        self, tmp_path: Path
    ) -> None:
        # Given: a state file that isn't valid JSON at all
        state_path = tmp_path / "state.json"
        state_path.write_text("{ this is not valid json ]")

        # When / Then: a clear, actionable, typed error
        with pytest.raises(ninth_bank.CorruptNinthBankStateError) as exc_info:
            ninth_bank.load_ninth_bank_state(state_path)
        assert str(state_path) in str(exc_info.value)

    def test_should_raise_a_clear_error_when_the_only_universally_required_field_is_missing(
        self, tmp_path: Path
    ) -> None:
        # Given: syntactically valid JSON, but missing `new_pattern_id` —
        # the one field required in EVERY shape (with-track or bank-only)
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"content_id": 5, "original_macro_pattern_id": 3})
        )

        # When / Then: refused, not silently treated as a partial state
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            ninth_bank.load_ninth_bank_state(state_path)

    def test_should_raise_a_clear_error_when_only_content_id_is_present(
        self, tmp_path: Path
    ) -> None:
        # Given: a partial, internally inconsistent track record — a
        # content_id with no recorded original_macro_pattern_id would make
        # restoring that track's original bank impossible. This is
        # DISTINCT from the valid no-track shape, which omits BOTH fields
        # together, never just one.
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"new_pattern_id": 28, "content_id": 5})
        )

        # When / Then: a loud, typed failure — never silently treated as
        # either valid shape
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            ninth_bank.load_ninth_bank_state(state_path)

    def test_should_raise_a_clear_error_when_only_original_macro_pattern_id_is_present(
        self, tmp_path: Path
    ) -> None:
        # Given: the mirror-image partial record — a recorded original
        # bank with no content_id to restore it onto
        state_path = tmp_path / "state.json"
        state_path.write_text(
            json.dumps({"new_pattern_id": 28, "original_macro_pattern_id": 3})
        )

        # When / Then: a loud, typed failure
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            ninth_bank.load_ninth_bank_state(state_path)

    def test_should_not_leak_a_raw_json_decode_error(self, tmp_path: Path) -> None:
        # Given: garbage content
        state_path = tmp_path / "state.json"
        state_path.write_text("not json at all {{{")

        # When / Then: the raw json.JSONDecodeError must never escape —
        # only the typed, actionable error
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            try:
                ninth_bank.load_ninth_bank_state(state_path)
            except json.JSONDecodeError:
                pytest.fail(
                    "raw JSONDecodeError leaked instead of CorruptNinthBankStateError"
                )

    def test_should_not_leak_a_raw_key_error(self, tmp_path: Path) -> None:
        # Given: valid JSON, wrong shape entirely (e.g. a list, not an
        # object with the expected keys)
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps([1, 2, 3]))

        # When / Then: the raw KeyError/TypeError must never escape
        with pytest.raises(ninth_bank.CorruptNinthBankStateError):
            try:
                ninth_bank.load_ninth_bank_state(state_path)
            except (KeyError, TypeError):
                pytest.fail(
                    "raw KeyError/TypeError leaked instead of CorruptNinthBankStateError"
                )
