"""E1d — "lighting mode diff". Disposable, READ-ONLY probe, fourth in the
E1/E1b/E1c series.

See docs/experiments/E1d-lighting-mode-row-creation.md for the written
verdict this script exists to produce — that file, not this one, is the
deliverable.

E1c (docs/experiments/E1c-after-full-analysis.md) proved that ordinary
right-click "Analyze Track" (export-mode phrase analysis) does NOT create
`content`/`phrase_data` rows — the `content` table was byte-identical
across a full library re-analysis pass. E1d tests the next hypothesis: are
these rows created when a track is opened in rekordbox's LIGHTING mode
editor? The DJ opened 8 tracks in LIGHTING mode (probably never opened
there before) and changed the bank on exactly 1 of them, then fully quit
rekordbox.

This script diffs a BEFORE snapshot of `user.db3` (taken by the orchestrator
before the DJ's session — passed in via --before, never hard-coded) against
the current, freshly-pulled `work/user.db3` (AFTER), row by row, across
every table in the schema. It also confirms `macro.db3` was not touched
(compared against the live file's own mtime — no BEFORE copy of macro.db3
exists, so mtime is the only available signal, not a byte diff).

Safety (see rekordbox-data-safety skill):
  - `work/master.db` is READ-ONLY, reused via `ensure_master_db_copy`
    (E1's helper) — refreshed by the orchestrator before this probe ran,
    not by this script.
  - `work/user.db3` and `work/macro.db3` (AFTER) and the BEFORE snapshot
    passed via --before are all opened read-only (`open_readonly`).
  - This script writes nothing. It does not call `sync.pull` or touch any
    live path — the AFTER/master refresh already happened before this
    script runs (see the written report's "Refresh procedure").

This module imports shared helpers from `e1_library_join` and
`e1b_real_denominator` — both are disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward).

Requires the optional `experiments` dependency group (same as E1/E1b/E1c):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1d_lighting_mode_diff \\
        --before work/e1d_before_user.db3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    ContentRow,
    ensure_master_db_copy,
    load_master_tracks,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import ENERGY_NAMES

#: Baseline figures from E1c, quoted here only for direct comparison — never
#: used as a substitute for a fresh measurement.
BASELINE_CONTENT_ROWS = 2966
BASELINE_PHRASE_DATA_ROWS = 41742
BASELINE_PHRASE_DATA_DISTINCT_CONTENT = 2905
BASELINE_MPID_ZERO_ORPHANS = 61
BASELINE_PHRASE_OVERRIDES = 36
BASELINE_PHRASE_NULLS = 0
BASELINE_LIGHTING_DATA_ROWS = 264


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_content_dict(user_db3: Path) -> dict[int, ContentRow]:
    """All `content` rows, keyed by `id`."""
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT id, song_id, master_db_id, macro_pattern_id FROM content"
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: ContentRow(*row) for row in rows}


@dataclass(frozen=True)
class PhraseDataRow:
    """One row of `phrase_data`."""

    content_id: int
    phrase_num: int
    macro_id: int | None
    initial_macro_id: int | None


def load_phrase_data_dict(user_db3: Path) -> dict[tuple[int, int], PhraseDataRow]:
    """All `phrase_data` rows, keyed by `(content_id, phrase_num)` (its PK)."""
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT content_id, phrase_num, macro_id, initial_macro_id FROM phrase_data"
        ).fetchall()
    finally:
        conn.close()
    return {(row[0], row[1]): PhraseDataRow(*row) for row in rows}


def load_macro_pattern_lookup(
    macro_db3: Path,
) -> dict[int, tuple[int | None, int | None]]:
    """macro_pattern.id -> (pattern, energy)."""
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute("SELECT id, pattern, energy FROM macro_pattern").fetchall()
    finally:
        conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


def load_macro_assign_rows(
    macro_db3: Path, macro_pattern_id: int
) -> list[tuple[int, int, int]]:
    """`(phase, macro_id, initial_macro_id)` rows for one bank, ordered by
    phase. Read, never derived — phase counts are not uniform (see
    rekordbox-lightingdb-schema skill).
    """
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute(
            "SELECT phase, macro_id, initial_macro_id FROM macro_assign "
            "WHERE macro_pattern_id = ? ORDER BY phase",
            (macro_pattern_id,),
        ).fetchall()
    finally:
        conn.close()
    return [(r[0], r[1], r[2]) for r in rows]


def bank_name(pattern: int | None) -> str:
    if pattern is None:
        return "NONE"
    return PATTERN_NAMES.get(pattern, f"pattern{pattern}")


def energy_name(energy: int | None) -> str:
    if energy is None:
        return "NONE"
    return ENERGY_NAMES.get(energy, f"energy{energy}")


# ---------------------------------------------------------------------------
# Deliverable 1/2 — content diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentDiffResult:
    before_count: int
    after_count: int
    new_rows: list[ContentRow]
    removed_rows: list[ContentRow]
    changed_rows: list[tuple[ContentRow, ContentRow]]  # (before, after)
    max_id_before: int
    max_id_after: int


def diff_content(
    before: dict[int, ContentRow], after: dict[int, ContentRow]
) -> ContentDiffResult:
    new_ids = sorted(after.keys() - before.keys())
    removed_ids = sorted(before.keys() - after.keys())
    common_ids = before.keys() & after.keys()
    changed = sorted(
        ((before[i], after[i]) for i in common_ids if before[i] != after[i]),
        key=lambda pair: pair[0].id,
    )
    return ContentDiffResult(
        before_count=len(before),
        after_count=len(after),
        new_rows=[after[i] for i in new_ids],
        removed_rows=[before[i] for i in removed_ids],
        changed_rows=changed,
        max_id_before=max(before) if before else 0,
        max_id_after=max(after) if after else 0,
    )


def resolves_to_live_track(song_id: int, master_tracks: dict[int, Any]) -> bool:
    return song_id in master_tracks


# ---------------------------------------------------------------------------
# Deliverable 3/4 — phrase_data diff
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhraseDataDiffResult:
    before_count: int
    after_count: int
    new_rows: list[PhraseDataRow]
    removed_rows: list[PhraseDataRow]
    changed_rows: list[tuple[PhraseDataRow, PhraseDataRow]]
    new_rows_by_content_id: dict[int, int]
    changed_content_ids: set[int]


def diff_phrase_data(
    before: dict[tuple[int, int], PhraseDataRow],
    after: dict[tuple[int, int], PhraseDataRow],
) -> PhraseDataDiffResult:
    new_keys = sorted(after.keys() - before.keys())
    removed_keys = sorted(before.keys() - after.keys())
    common_keys = before.keys() & after.keys()
    changed = sorted(
        ((before[k], after[k]) for k in common_keys if before[k] != after[k]),
        key=lambda pair: (pair[0].content_id, pair[0].phrase_num),
    )

    new_rows_by_content: dict[int, int] = {}
    for k in new_keys:
        new_rows_by_content[k[0]] = new_rows_by_content.get(k[0], 0) + 1

    changed_content_ids = {pair[0].content_id for pair in changed}

    return PhraseDataDiffResult(
        before_count=len(before),
        after_count=len(after),
        new_rows=[after[k] for k in new_keys],
        removed_rows=[before[k] for k in removed_keys],
        changed_rows=changed,
        new_rows_by_content_id=new_rows_by_content,
        changed_content_ids=changed_content_ids,
    )


@dataclass(frozen=True)
class PhaseCorrespondenceRow:
    """One phrase_data row lined up against the macro_assign phase (if any)
    that carries the same macro_id, for a single bank's assign list.
    `matched_phase` is the FIRST macro_assign phase with that macro_id
    (macro_assign can carry the same macro_id at more than one phase, e.g.
    a 10-phase CLUB bank duplicating its endpoints — see the report).
    `is_reproducible` is False only if the macro_id does not appear
    anywhere in that bank's macro_assign at all.
    """

    phrase_num: int
    macro_id: int | None
    initial_macro_id: int | None
    matched_phase: int | None
    is_reproducible: bool


def build_phase_correspondence(
    phrase_rows: list[PhraseDataRow],
    assign_rows: list[tuple[int, int, int]],
) -> list[PhaseCorrespondenceRow]:
    """Line up a track's phrase_data rows against one bank's macro_assign,
    by matching macro_id to the first assign phase carrying that value.
    This is the "does phrase_data literally copy macro_assign" check.
    """
    first_phase_for_macro_id: dict[int, int] = {}
    for phase, macro_id, _initial in assign_rows:
        first_phase_for_macro_id.setdefault(macro_id, phase)

    result = []
    for row in sorted(phrase_rows, key=lambda r: r.phrase_num):
        matched = (
            first_phase_for_macro_id.get(row.macro_id)
            if row.macro_id is not None
            else None
        )
        result.append(
            PhaseCorrespondenceRow(
                phrase_num=row.phrase_num,
                macro_id=row.macro_id,
                initial_macro_id=row.initial_macro_id,
                matched_phase=matched,
                is_reproducible=matched is not None,
            )
        )
    return result


# ---------------------------------------------------------------------------
# Deliverable 5 — everything else in user.db3, plus macro.db3
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TableDiffResult:
    table: str
    before_count: int
    after_count: int
    only_before: list[tuple[Any, ...]]
    only_after: list[tuple[Any, ...]]


def diff_full_table(before_path: Path, after_path: Path, table: str) -> TableDiffResult:
    """Set-diff every row (all columns) of one table between two DB files.
    Works for any table with no BLOB columns and no huge row count — every
    table this probe touches qualifies (largest is `content` at ~3k rows).
    """
    before_conn = open_readonly(before_path)
    after_conn = open_readonly(after_path)
    try:
        before_rows = before_conn.execute(f"SELECT * FROM {table}").fetchall()
        after_rows = after_conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        before_conn.close()
        after_conn.close()

    before_set = {tuple(row) for row in before_rows}
    after_set = {tuple(row) for row in after_rows}
    return TableDiffResult(
        table=table,
        before_count=len(before_rows),
        after_count=len(after_rows),
        only_before=sorted(before_set - after_set),
        only_after=sorted(after_set - before_set),
    )


USER_DB3_TABLES: tuple[str, ...] = (
    "content",
    "phrase_data",
    "lighting_data",
    "venue",
    "fixture",
    "direct_control",
    "lighting_property",
)


def diff_all_user_db3_tables(
    before_path: Path, after_path: Path
) -> dict[str, TableDiffResult]:
    return {t: diff_full_table(before_path, after_path, t) for t in USER_DB3_TABLES}


@dataclass(frozen=True)
class MacroDbUntouchedCheck:
    live_macro_mtime: str
    work_macro_mtime: str
    same_mtime: bool


def check_macro_db_untouched(
    work_macro_db3: Path, live_macro_db3: Path
) -> MacroDbUntouchedCheck:
    """Compare the working copy's mtime (preserved from the live file by
    `shutil.copy2` at pull time) against the live file's CURRENT mtime.
    There is no BEFORE byte-copy of macro.db3 to diff against (only
    user.db3 got one — see the task setup), so mtime equality is the
    available signal: if the live file's mtime today matches the mtime
    already carried by the working copy, the live file has not been
    rewritten since that copy was taken, i.e. across this whole E1d
    session.
    """
    work_mtime = work_macro_db3.stat().st_mtime
    live_mtime = live_macro_db3.stat().st_mtime
    return MacroDbUntouchedCheck(
        live_macro_mtime=str(live_mtime),
        work_macro_mtime=str(work_mtime),
        same_mtime=work_mtime == live_mtime,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    content_diff: ContentDiffResult,
    phrase_diff: PhraseDataDiffResult,
    table_diffs: dict[str, TableDiffResult],
    macro_check: MacroDbUntouchedCheck,
    master_tracks: dict[int, Any],
    pattern_lookup: dict[int, tuple[int | None, int | None]],
) -> None:
    """Console summary. NOT the deliverable — see
    docs/experiments/E1d-lighting-mode-row-creation.md.
    """
    print("=" * 70)
    print("Deliverable 1/2 — content diff")
    print("=" * 70)
    print(
        f"content rows: before={content_diff.before_count} "
        f"after={content_diff.after_count} "
        f"(baseline {BASELINE_CONTENT_ROWS}) "
        f"new={len(content_diff.new_rows)} "
        f"removed={len(content_diff.removed_rows)} "
        f"changed={len(content_diff.changed_rows)}"
    )
    print(
        f"max id: before={content_diff.max_id_before} after={content_diff.max_id_after}"
    )

    if content_diff.new_rows:
        print(f"NEW content rows ({len(content_diff.new_rows)}):")
        for row in content_diff.new_rows:
            pattern, energy = pattern_lookup.get(row.macro_pattern_id, (None, None))
            resolves = resolves_to_live_track(row.song_id, master_tracks)
            print(
                f"    id={row.id} song_id={row.song_id} "
                f"master_db_id={row.master_db_id} "
                f"macro_pattern_id={row.macro_pattern_id} "
                f"({bank_name(pattern)}/{energy_name(energy)}) "
                f"resolves_to_live_track={resolves}"
            )
    else:
        print("NEW content rows: NONE.")

    if content_diff.changed_rows:
        print(f"CHANGED content rows ({len(content_diff.changed_rows)}):")
        for before_row, after_row in content_diff.changed_rows:
            b_pattern, b_energy = pattern_lookup.get(
                before_row.macro_pattern_id, (None, None)
            )
            a_pattern, a_energy = pattern_lookup.get(
                after_row.macro_pattern_id, (None, None)
            )
            print(
                f"    id={before_row.id} song_id={before_row.song_id}: "
                f"macro_pattern_id {before_row.macro_pattern_id} "
                f"({bank_name(b_pattern)}/{energy_name(b_energy)}) -> "
                f"{after_row.macro_pattern_id} "
                f"({bank_name(a_pattern)}/{energy_name(a_energy)})"
            )
    else:
        print("CHANGED content rows: NONE.")

    if content_diff.removed_rows:
        print(f"REMOVED content rows ({len(content_diff.removed_rows)}): (unexpected)")
        for row in content_diff.removed_rows:
            print(f"    {row}")

    print()
    print("=" * 70)
    print("Deliverable 3/4 — phrase_data diff")
    print("=" * 70)
    print(
        f"phrase_data rows: before={phrase_diff.before_count} "
        f"after={phrase_diff.after_count} "
        f"(baseline {BASELINE_PHRASE_DATA_ROWS}) "
        f"new={len(phrase_diff.new_rows)} "
        f"removed={len(phrase_diff.removed_rows)} "
        f"changed={len(phrase_diff.changed_rows)}"
    )
    print(f"new rows by content_id: {phrase_diff.new_rows_by_content_id}")
    print(f"changed content_ids: {sorted(phrase_diff.changed_content_ids)}")

    print()
    print("=" * 70)
    print("Deliverable 5 — full table diff, every other table")
    print("=" * 70)
    for table, diff in table_diffs.items():
        print(
            f"{table}: before={diff.before_count} after={diff.after_count} "
            f"only_before={len(diff.only_before)} only_after={len(diff.only_after)}"
        )

    print()
    print("=" * 70)
    print("macro.db3 untouched check")
    print("=" * 70)
    print(
        f"live mtime={macro_check.live_macro_mtime} "
        f"work-copy mtime={macro_check.work_macro_mtime} "
        f"same={macro_check.same_mtime}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        type=Path,
        required=True,
        help="Path to the BEFORE snapshot of user.db3 (e.g. work/e1d_before_user.db3).",
    )
    parser.add_argument(
        "--after",
        type=Path,
        default=Path("work/user.db3"),
        help="Path to the AFTER (current, freshly-pulled) user.db3. Default: work/user.db3.",
    )
    parser.add_argument(
        "--macro-db3",
        type=Path,
        default=Path("work/macro.db3"),
        help="Path to macro.db3 (AFTER). Default: work/macro.db3.",
    )
    parser.add_argument(
        "--live-macro-db3",
        type=Path,
        default=None,
        help="Path to the LIVE macro.db3, read-only, for the mtime-untouched "
        "check. Defaults to rbxlight's standard LightingDB location.",
    )
    args = parser.parse_args()

    if args.live_macro_db3 is None:
        from rbxlight import db as rbxlight_db

        live_macro_db3 = rbxlight_db.LIGHTINGDB / "macro.db3"
    else:
        live_macro_db3 = args.live_macro_db3

    master_path = ensure_master_db_copy()
    master_conn = open_master_db(master_path)
    try:
        master_tracks = load_master_tracks(master_conn)
    finally:
        master_conn.close()

    pattern_lookup = load_macro_pattern_lookup(args.macro_db3)

    before_content = load_content_dict(args.before)
    after_content = load_content_dict(args.after)
    content_diff = diff_content(before_content, after_content)

    before_phrases = load_phrase_data_dict(args.before)
    after_phrases = load_phrase_data_dict(args.after)
    phrase_diff = diff_phrase_data(before_phrases, after_phrases)

    table_diffs = diff_all_user_db3_tables(args.before, args.after)
    macro_check = check_macro_db_untouched(args.macro_db3, live_macro_db3)

    print_report(
        content_diff,
        phrase_diff,
        table_diffs,
        macro_check,
        master_tracks,
        pattern_lookup,
    )


if __name__ == "__main__":
    main()
