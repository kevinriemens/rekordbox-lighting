"""`rbxlight experiment ninth-bank` — a bounded, fully reversible experiment
that provisionally adds a ninth lighting "bank" (a macro_pattern row whose
`pattern` value is the "unknown" 9 — the real library only ever has 1..8
plus 99/INTERLUDE) and repoints one throwaway track at it, so the user can
observe by hand whether rekordbox honours it.

Disposable orchestration built on top of the permanent
rbxlight.macros.patterns / rbxlight.phrases.repo modules — deliberately
isolated so the whole experiment can be deleted in one commit once it
concludes. See rekordbox-lighting-architecture skill on repo-vs-
orchestration placement.

Hard rules for this module (enforced by tests):
- No typer/click import, no print, no sys.exit — typed exceptions and
  return values only. cli.py translates these into user-facing messages
  and exit codes.
- Every `build_*_plan` function performs zero I/O: no write, no backup, no
  guard, no transaction. Plans are pure values.
- Every write goes through safety.working_copy_write — this experiment
  never touches live, and never opens a database read-write any other way.
- Each database file (macro.db3, user.db3) is written inside its OWN
  transaction. There is deliberately NO cross-file atomic write (no ATTACH
  tricks) — a partial failure (e.g. macro.db3 succeeds, user.db3 fails) is
  recoverable because the working copy is regenerable via `pull`.
- `db.WORK_DIR` is read at CALL time (via safety.working_copy_write and
  default_state_path()), never bound at import time, so test monkeypatches
  of that constant take effect for every call.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from rbxlight import db, safety
from rbxlight.macros import patterns
from rbxlight.phrases import repo as phrases_repo

#: The "unknown" pattern value this experiment provisionally adds — the
#: real library only ever has 1..8 (named banks) plus 99 (INTERLUDE).
NEW_PATTERN_VALUE: int = 9

_MACRO_DB_NAME = "macro.db3"
_USER_DB_NAME = "user.db3"

#: Default undo-state filename, under db.WORK_DIR.
_STATE_FILENAME = "ninth_bank_state.json"


class NoSourceBankError(LookupError):
    """Raised when the given source_pattern_id has no matching
    macro_pattern row — apply refuses before writing anything."""


class NoTargetTrackError(LookupError):
    """Raised when a SUPPLIED content_id has no matching content row —
    apply refuses before writing anything. Never raised when content_id
    is omitted (the bank-only default) — there is no target to be
    missing."""


class NinthBankAlreadyAppliedError(RuntimeError):
    """Raised when apply is attempted while a change is already
    outstanding (undo state exists on disk). A second apply would
    overwrite the record of the original value and make undo impossible.
    """


class CorruptNinthBankStateError(RuntimeError):
    """Raised when the on-disk undo-state file exists but cannot be
    parsed as a valid NinthBankState. A raw JSONDecodeError/KeyError must
    never reach the caller — this is the one typed error wrapping every
    corrupt-file failure mode.
    """


# ---------------------------------------------------------------------------
# Undo state — a small on-disk record of the track's original
# macro_pattern_id, written by apply() and read back by revert(),
# potentially in a separate process invocation. Mirrors the defensive JSON
# house style of preview/layout_io.py: separate to_dict/from_dict, atomic
# write via tempfile.mkstemp + os.replace, None for "nothing applied yet".
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NinthBankState:
    """The exact facts revert() needs to undo an applied ninth-bank
    change. `content_id` / `original_macro_pattern_id` are both `None`
    when the apply was bank-only (no track repointed) — they are always
    both present or both absent, never just one.
    """

    new_pattern_id: int
    content_id: int | None = None
    original_macro_pattern_id: int | None = None


def _state_to_dict(state: NinthBankState) -> dict[str, int | None]:
    return {
        "new_pattern_id": state.new_pattern_id,
        "content_id": state.content_id,
        "original_macro_pattern_id": state.original_macro_pattern_id,
    }


def _state_from_dict(data: dict[str, object]) -> NinthBankState:
    new_pattern_id = data["new_pattern_id"]
    content_id = data.get("content_id")
    original_macro_pattern_id = data.get("original_macro_pattern_id")

    if (content_id is None) != (original_macro_pattern_id is None):
        raise ValueError(
            "content_id and original_macro_pattern_id must be both present "
            "or both absent — got a partial track record "
            f"(content_id={content_id!r}, "
            f"original_macro_pattern_id={original_macro_pattern_id!r})"
        )

    return NinthBankState(
        new_pattern_id=new_pattern_id,  # type: ignore[arg-type]
        content_id=content_id,  # type: ignore[arg-type]
        original_macro_pattern_id=original_macro_pattern_id,  # type: ignore[arg-type]
    )


def save_ninth_bank_state(path: Path, state: NinthBankState) -> None:
    """Write `state` to `path` as JSON, atomically: write to a temp file
    in the same directory, then `os.replace` it into place, so an
    interrupted save can never leave a truncated/corrupt file at `path`.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(_state_to_dict(state), indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(data)
        os.replace(tmp_name, str(path))
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise


def load_ninth_bank_state(path: Path) -> NinthBankState | None:
    """Read the undo state from `path`. Returns None if the file does not
    exist — the normal "nothing has ever been applied" case, not an
    error. Raises CorruptNinthBankStateError (never a raw
    JSONDecodeError/KeyError/TypeError) for anything malformed.
    """
    if not path.exists():
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CorruptNinthBankStateError(f"could not read {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorruptNinthBankStateError(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise CorruptNinthBankStateError(
            f"{path} must contain a JSON object describing ninth-bank undo "
            f"state, got {type(data).__name__}."
        )

    try:
        return _state_from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise CorruptNinthBankStateError(
            f"{path} is not a valid ninth-bank undo state: {exc}"
        ) from exc


def default_state_path() -> Path:
    """The on-disk location for this experiment's undo state, derived
    from the CURRENT value of `db.WORK_DIR` (read at call time, never
    bound at import time — an import-time binding would silently defeat
    test monkeypatches and point this at the user's real rekordbox data).
    """
    return db.WORK_DIR / _STATE_FILENAME


# ---------------------------------------------------------------------------
# Apply — plan (zero I/O) + write.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NinthBankApplyPlan:
    """A typed, immutable description of what `experiment ninth-bank
    apply` WOULD do — built with zero writes. `content_id` and
    `original_macro_pattern_id` are both `None` together on the
    bank-only (default) path, and both populated together when a target
    track was supplied — never just one.
    """

    new_pattern_id: int
    new_pattern_value: int
    source_energy: int
    phase_count: int
    source_pattern_id: int
    macro_db_path: Path
    user_db_path: Path
    content_id: int | None = None
    original_macro_pattern_id: int | None = None
    touches_live: bool = False


def build_apply_plan(
    macro_conn: sqlite3.Connection,
    user_conn: sqlite3.Connection | None = None,
    *,
    source_pattern_id: int,
    content_id: int | None = None,
    macro_db_path: Path,
    user_db_path: Path,
) -> NinthBankApplyPlan:
    """Build a NinthBankApplyPlan: resolve the source bank and, only if
    `content_id` is supplied, the target track — reporting exactly what
    would change (the new bank's id, one past the current max; the phase
    count, copied from the source; and, if supplied, which single track
    would be repointed). Performs zero writes.

    Omitting `content_id` (the default) is the bank-only path: `user_conn`
    is never even touched, and the returned plan carries `content_id`
    and `original_macro_pattern_id` both `None`.

    Raises NoSourceBankError if source_pattern_id has no matching
    macro_pattern row. Raises NoTargetTrackError only when `content_id`
    IS supplied and has no matching content row — never when it is
    omitted. Either way, nothing is written.
    """
    try:
        source = patterns.get_macro_pattern(macro_conn, source_pattern_id)
    except LookupError as exc:
        raise NoSourceBankError(
            f"source bank (macro_pattern {source_pattern_id}) not found"
        ) from exc

    original_macro_pattern_id: int | None = None
    if content_id is not None:
        assert user_conn is not None
        try:
            content = phrases_repo.get_content(user_conn, content_id)
        except LookupError as exc:
            raise NoTargetTrackError(
                f"target track (content {content_id}) not found"
            ) from exc
        original_macro_pattern_id = content.macro_pattern_id

    phase_count = len(patterns.list_macro_assign(macro_conn, source_pattern_id))
    new_pattern_id = patterns.next_macro_pattern_id(macro_conn)

    return NinthBankApplyPlan(
        new_pattern_id=new_pattern_id,
        new_pattern_value=NEW_PATTERN_VALUE,
        source_energy=source.energy,
        phase_count=phase_count,
        source_pattern_id=source_pattern_id,
        content_id=content_id,
        original_macro_pattern_id=original_macro_pattern_id,
        macro_db_path=macro_db_path,
        user_db_path=user_db_path,
    )


def apply_ninth_bank(plan: NinthBankApplyPlan, *, state_path: Path) -> None:
    """Apply a NinthBankApplyPlan: create the new bank and clone its
    phase assignments in macro.db3 (always). ONLY if `plan.content_id`
    is not None does it also repoint the target track in user.db3 (a
    separate transaction) — the bank-only (default) path never opens a
    transaction against user.db3 at all. Undo state is then persisted.

    Refuses with NinthBankAlreadyAppliedError if a change is already
    outstanding (state_path already holds a record) — checked BEFORE any
    write, so a refused second apply never touches either database or
    overwrites the existing undo record.

    No cross-file atomicity is attempted: macro.db3 and user.db3 are each
    written inside their own `safety.working_copy_write` transaction. The
    working copy is regenerable via `pull`, so a failure partway between
    the two file writes is recoverable, not catastrophic.
    """
    if load_ninth_bank_state(state_path) is not None:
        raise NinthBankAlreadyAppliedError(
            "a ninth-bank change is already outstanding — run "
            "`experiment ninth-bank revert` before applying again"
        )

    with safety.working_copy_write(_MACRO_DB_NAME) as macro_conn:
        created_pattern = patterns.create_macro_pattern(
            macro_conn, energy=plan.source_energy, pattern=plan.new_pattern_value
        )
        patterns.clone_macro_assign(
            macro_conn,
            source_pattern_id=plan.source_pattern_id,
            target_pattern_id=created_pattern.id,
        )

    if plan.content_id is not None:
        with safety.working_copy_write(_USER_DB_NAME) as user_conn:
            phrases_repo.update_content_macro_pattern_id(
                user_conn, plan.content_id, created_pattern.id
            )

    save_ninth_bank_state(
        state_path,
        NinthBankState(
            new_pattern_id=created_pattern.id,
            content_id=plan.content_id,
            original_macro_pattern_id=plan.original_macro_pattern_id,
        ),
    )


# ---------------------------------------------------------------------------
# Revert — plan (zero I/O) + write.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NinthBankRevertPlan:
    """A typed, immutable description of what `experiment ninth-bank
    revert` WOULD do — built with zero writes. `nothing_to_revert` is
    True when no undo state exists (nothing was ever applied, or a prior
    revert already ran).
    """

    nothing_to_revert: bool
    new_pattern_id: int | None
    content_id: int | None
    original_macro_pattern_id: int | None
    touches_live: bool = False


def build_revert_plan(state_path: Path) -> NinthBankRevertPlan:
    """Build a NinthBankRevertPlan from the on-disk undo state. Performs
    zero writes. Raises CorruptNinthBankStateError if the state file
    exists but is malformed — a corrupt file is never silently treated as
    "nothing to revert".
    """
    state = load_ninth_bank_state(state_path)
    if state is None:
        return NinthBankRevertPlan(
            nothing_to_revert=True,
            new_pattern_id=None,
            content_id=None,
            original_macro_pattern_id=None,
        )

    return NinthBankRevertPlan(
        nothing_to_revert=False,
        new_pattern_id=state.new_pattern_id,
        content_id=state.content_id,
        original_macro_pattern_id=state.original_macro_pattern_id,
    )


def revert_ninth_bank(plan: NinthBankRevertPlan, *, state_path: Path) -> None:
    """Apply a NinthBankRevertPlan: remove the provisional bank and its
    phase assignments from macro.db3 (one transaction). ONLY if
    `plan.content_id` is not None does it also restore the track's
    original macro_pattern_id in user.db3 (a separate transaction) — a
    bank-only apply's revert never opens a transaction against user.db3
    at all. Then deletes the undo-state file.

    A true no-op (no writes at all) when `plan.nothing_to_revert` is True
    — reverting when nothing was ever applied is always safe. This is
    independent of whether a track was recorded: a bank-only apply still
    has something outstanding to revert (the bank itself).
    """
    if plan.nothing_to_revert:
        return

    assert plan.new_pattern_id is not None

    with safety.working_copy_write(_MACRO_DB_NAME) as macro_conn:
        patterns.delete_macro_assign(macro_conn, plan.new_pattern_id)
        patterns.delete_macro_pattern(macro_conn, plan.new_pattern_id)

    if plan.content_id is not None:
        assert plan.original_macro_pattern_id is not None
        with safety.working_copy_write(_USER_DB_NAME) as user_conn:
            phrases_repo.update_content_macro_pattern_id(
                user_conn, plan.content_id, plan.original_macro_pattern_id
            )

    state_path.unlink(missing_ok=True)
