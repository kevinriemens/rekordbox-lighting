"""Tests for the ninth-bank experiment's persisted undo state: a small
on-disk record of the track's original macro_pattern_id, written by
`apply` and read back by `revert` — potentially in a SEPARATE process
invocation (requirement: "undo survives a separate invocation"). Mirrors
the on-disk state idiom already used elsewhere in this project
(sync.py's `.pull-state.json`, preview.layout's saved layout files):
plain JSON, `None` for "file absent" (not an error), a dedicated typed
error for anything malformed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rbxlight.experiments import ninth_bank


class TestSaveAndLoadNinthBankState:
    def test_should_round_trip_exactly(self, tmp_path: Path) -> None:
        # Given: a state describing an outstanding change
        state_path = tmp_path / "state.json"
        state = ninth_bank.NinthBankState(
            new_pattern_id=28, content_id=42, original_macro_pattern_id=7
        )

        # When: saving then loading it back
        ninth_bank.save_ninth_bank_state(state_path, state)
        loaded = ninth_bank.load_ninth_bank_state(state_path)

        # Then: identical to what was saved
        assert loaded == state

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

    def test_should_raise_a_clear_error_for_valid_json_missing_required_fields(
        self, tmp_path: Path
    ) -> None:
        # Given: syntactically valid JSON, but missing required keys
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"new_pattern_id": 28}))

        # When / Then: refused, not silently treated as a partial state
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
