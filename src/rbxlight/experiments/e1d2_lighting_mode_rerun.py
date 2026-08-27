"""E1d2 — "the lighting-mode row-creation rerun". Disposable, READ-ONLY
probe, sixth in the E1/E1b/E1c/E1d/E1e series.

See docs/experiments/E1d2-row-creation-rerun.md for the written verdict
this script exists to produce — that file, not this one, is the
deliverable.

The headline question is NOT "did opening these tracks create rows" — it
is methodological: `e1d2_candidate_tracks.py` certified 10 tracks as
"provably absent from content" (song_id not present in ANY content.song_id
row, verified twice). The DJ then reported that 7 of those 10 already
showed an assigned bank in rekordbox's UI. A track cannot display a
non-default bank without that assignment being stored somewhere, so
either:

  (a) these tracks DO have `content` rows, keyed by stale/legacy song_ids
      that no longer equal their current `DjmdContent.ID` — meaning
      absence-by-ID-equality was never a valid absence test, and every
      coverage figure this project has published (E1/E1b/E1c) measures ID
      resolvability, not lighting coverage; or
  (b) the displayed bank lives somewhere other than
      `content.macro_pattern_id`, overturning E1c's conclusion.

This probe discriminates between (a) and (b) two ways:

  1. A direct before/after diff (reusing `e1d_lighting_mode_diff.py`'s
     diff functions unmodified) — does content gain rows, and for
     candidate 9 (the one bank change the DJ made), does the changed
     row's song_id match or differ from that track's CURRENT
     DjmdContent.ID?
  2. A content-based identity bridge that needs no IDs at all: for each
     of the 7 candidates with a displayed bank, read the track's own ANLZ
     `PSSI` phrase-kind sequence, predict a phase sequence via E1e's
     `(kind, k1, k2, k3, b) -> phase` subkind table for that bank, and
     search every `content` row sharing that `macro_pattern_id` for one
     whose `phrase_data` phase sequence (translated back through
     `macro_assign`) matches exactly, with a matching row count too. This
     is the "recovery mechanism" the task asks this probe to demonstrate
     alongside the diagnosis.

It also runs down two things the DJ volunteered (candidate 3's
"transition" observation at a phrase boundary; candidate 8's Analysis
Lock) and the Analysis Lock / no-ANLZ overlap this implies for E1e's
forging plan.

Safety (see rekordbox-data-safety skill):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. Reused
    via `ensure_master_db_copy` (E1's helper) — the orchestrator refreshed
    `work/master.db` before this probe ran; this script does not refresh
    it itself.
  - `work/user.db3`, `work/macro.db3`, and the BEFORE snapshot passed via
    `--before` are all opened read-only (`open_readonly`).
  - The `ANLZ0000.EXT` analysis cache files are opened with a plain
    read-only file open via `pyrekordbox`'s `AnlzFile.parse_file` — the
    exact mechanism `e1d2_candidate_tracks.py`/`e1e_phrase_phase_mapping.py`
    already used.
  - This script writes nothing. It does not call `sync.pull`/`sync.push`
    and does not open any `.db3` read-write.

This module imports shared helpers from `e1_library_join`,
`e1b_real_denominator`, `e1d_lighting_mode_diff`, `e1d2_candidate_tracks`,
and `e1e_phrase_phase_mapping` — all disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward).

Requires the optional `experiments` dependency group (same as E1/E1b/E1d):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1d2_lighting_mode_rerun \\
        --before work/e1d2_before_user.db3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    ensure_master_db_copy,
    load_master_tracks,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import ENERGY_NAMES
from rbxlight.experiments.e1d2_candidate_tracks import (
    ANALYSIS_SHARE_ROOT,  # noqa: F401  (re-exported for callers/tests)
    phrase_count_from_analysis,
)
from rbxlight.experiments.e1d_lighting_mode_diff import (
    ContentDiffResult,
    PhraseDataDiffResult,
    check_macro_db_untouched,
    diff_all_user_db3_tables,
    diff_content,
    diff_phrase_data,
    load_content_dict,
    load_macro_pattern_lookup,
    load_phrase_data_dict,
)
from rbxlight.experiments.e1e_phrase_phase_mapping import (
    ContentInfo,
    PhraseRow,
    SubkindKey,
    build_reverse_lookup_first_phase,
    load_content_info,
    load_macro_assign_by_pattern,
    load_pattern_energy,
    load_phrase_data_by_content,
    read_pssi_content,
    run_pssi_sample,
    subkind_key_of,
    summarize_subkind_table,
)

#: Baseline figures the DJ measured just before this session (see
#: work/e1d2-candidates.txt) — quoted only for direct comparison.
BASELINE_CONTENT_ROWS = 2966
BASELINE_PHRASE_DATA_ROWS = 41742
BASELINE_MAX_CONTENT_ID = 2966


#: The 10 candidates from work/e1d2-candidates.txt, by number. Only IDs and
#: bank names travel here — no titles/artists (see anonymisation note in
#: the report). `bank` is the bank NAME the DJ read off the rekordbox UI
#: before the session; `None` means the DJ reported it as looking
#: "untouched" (candidates 2 and 10). Candidate 9 is recorded with the
#: bank the DJ saw BEFORE her one deliberate change (COOL -> SUBTLE).
@dataclass(frozen=True)
class Candidate:
    number: int
    content_id: int  # current DjmdContent.ID
    displayed_bank: str | None  # bank NAME as read off the UI, pre-session


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(1, 1012839, "HOT"),
    Candidate(2, 10907301, None),
    Candidate(3, 21176962, "NATURAL"),
    Candidate(4, 6648040, "SUBTLE"),
    Candidate(5, 26045439, "VIVID"),
    Candidate(6, 33039310, "VIVID"),
    Candidate(7, 74297939, "VIVID"),
    Candidate(8, 357035, "NATURAL"),
    Candidate(9, 62464681, "COOL"),
    Candidate(10, 27457905, None),
)

#: Candidate 8's Analysed value marks it as Analysis-Locked (see
#: Deliverable "Analysis Lock" below) — recorded here only as a named
#: constant for cross-reference, never re-derived silently.
ANALYSED_LOCKED_VALUE = 233
ANALYSED_UNLOCKED_VALUE = 105


# ---------------------------------------------------------------------------
# Part 1 — the diff (thin wrapper around e1d_lighting_mode_diff, unmodified)
# ---------------------------------------------------------------------------


def run_diff(
    before_path: Path, after_path: Path, macro_db3: Path
) -> tuple[ContentDiffResult, PhraseDataDiffResult]:
    before_content = load_content_dict(before_path)
    after_content = load_content_dict(after_path)
    content_diff = diff_content(before_content, after_content)

    before_phrases = load_phrase_data_dict(before_path)
    after_phrases = load_phrase_data_dict(after_path)
    phrase_diff = diff_phrase_data(before_phrases, after_phrases)

    return content_diff, phrase_diff


@dataclass(frozen=True)
class Candidate9Check:
    """Candidate 9 is the one deliberate bank change (COOL -> SUBTLE per
    the DJ's instructions). If the changed row's song_id differs from
    candidate 9's CURRENT DjmdContent.ID, hypothesis (a) is proven
    outright for this track by ID alone — no fingerprint needed.
    """

    found: bool
    content_id: int | None
    row_song_id: int | None
    current_djmd_content_id: int
    song_id_matches_current_id: bool | None
    before_pattern: int | None
    after_pattern: int | None


def check_candidate_9(
    content_diff: ContentDiffResult, candidate9: Candidate
) -> Candidate9Check:
    for before_row, after_row in content_diff.changed_rows:
        # candidate 9 is the only expected bank change this session; any
        # changed row is treated as the candidate until proven otherwise
        return Candidate9Check(
            found=True,
            content_id=before_row.id,
            row_song_id=before_row.song_id,
            current_djmd_content_id=candidate9.content_id,
            song_id_matches_current_id=(before_row.song_id == candidate9.content_id),
            before_pattern=before_row.macro_pattern_id,
            after_pattern=after_row.macro_pattern_id,
        )
    return Candidate9Check(
        found=False,
        content_id=None,
        row_song_id=None,
        current_djmd_content_id=candidate9.content_id,
        song_id_matches_current_id=None,
        before_pattern=None,
        after_pattern=None,
    )


@dataclass(frozen=True)
class Candidate9FingerprintCheck:
    """The fingerprint bridge applied to candidate 9 specifically needs the
    BEFORE snapshot, not AFTER — the DJ's own bank change moved row 1576
    out of its original `macro_pattern_id` during this very session, so
    searching AFTER-state content rows for that original bank will never
    find it. This checks the BEFORE state instead: does the row's phase
    sequence under its OLD bank match what candidate 9's own PSSI predicts
    for that bank? A second, independent confirmation of hypothesis (a)
    for this track, on top of the raw song_id mismatch in
    `Candidate9Check`.
    """

    content_id: int
    macro_pattern_id: int
    predicted: list[int | None]
    actual: list[int | None]
    matches: bool
    same_pattern_rows: int
    same_pattern_same_length_rows: int


def check_candidate9_before_state_fingerprint(
    candidate9_check: Candidate9Check,
    before_path: Path,
    subkind_lookup: SubkindLookup,
    analysis_paths: dict[int, str | None],
    reverse_first: dict[int, dict[int, int]],
) -> Candidate9FingerprintCheck | None:
    if not candidate9_check.found or candidate9_check.before_pattern is None:
        return None
    content_id = candidate9_check.content_id
    mpid = candidate9_check.before_pattern
    assert content_id is not None

    before_content_info = load_content_info(before_path)
    before_phrase_by_content = load_phrase_data_by_content(before_path)

    prediction = predict_phase_sequence(
        candidate9_check.current_djmd_content_id,
        mpid,
        analysis_paths,
        subkind_lookup,
    )
    if prediction is None:
        return None
    predicted, _n_entries = prediction
    actual = actual_phase_sequence(
        content_id, mpid, before_phrase_by_content, reverse_first
    )

    same_pattern = [
        cid
        for cid, info in before_content_info.items()
        if info.macro_pattern_id == mpid
    ]
    same_length = [
        cid
        for cid in same_pattern
        if len(before_phrase_by_content.get(cid, [])) == len(actual)
    ]

    return Candidate9FingerprintCheck(
        content_id=content_id,
        macro_pattern_id=mpid,
        predicted=predicted,
        actual=actual,
        matches=(predicted == actual and None not in actual),
        same_pattern_rows=len(same_pattern),
        same_pattern_same_length_rows=len(same_length),
    )


# ---------------------------------------------------------------------------
# Part 2 — the content-based identity bridge (no IDs required)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubkindLookup:
    """`macro_pattern_id -> subkind -> mode phase`, plus the raw
    per-pattern-id observation counts needed to report accuracy. Built
    fresh from whatever `phrase_by_content`/`content_info` it is given —
    callers decide whether that's BEFORE or AFTER state.
    """

    by_pattern: dict[int, dict[SubkindKey, int]]
    tracks_used: int
    total_keys: int
    weighted_accuracy_pct: float


def build_subkind_lookup(
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_first: dict[int, dict[int, int]],
    master_tracks: dict[int, Any],
    analysis_paths: dict[int, str | None],
    pattern_energy: dict[int, tuple[int, int]],
) -> SubkindLookup:
    pssi = run_pssi_sample(
        content_info,
        phrase_by_content,
        reverse_first,
        master_tracks,
        analysis_paths,
        pattern_energy,
    )
    summary = summarize_subkind_table(pssi.subkind_table)
    by_pattern = {
        mpid: {s.subkind: s.mode_phase for s in stats}
        for mpid, stats in summary.per_pattern.items()
    }
    return SubkindLookup(
        by_pattern=by_pattern,
        tracks_used=pssi.tracks_used_for_subkind_table,
        total_keys=summary.total_keys,
        weighted_accuracy_pct=summary.weighted_accuracy_pct,
    )


def predict_phase_sequence(
    content_id: int,
    macro_pattern_id: int,
    analysis_paths: dict[int, str | None],
    subkind_lookup: SubkindLookup,
) -> tuple[list[int | None], int] | None:
    """Predict a track's phase sequence under one candidate bank, purely
    from its own ANLZ PSSI entries — the forward direction E1e's forging
    plan needs, no content/phrase_data lookup involved. Returns
    `(predicted_phases, pssi_len_entries)`, or None if the track's PSSI is
    unreadable.
    """
    content = read_pssi_content(analysis_paths.get(content_id))
    if content is None:
        return None
    table = subkind_lookup.by_pattern.get(macro_pattern_id, {})
    predicted = [table.get(subkind_key_of(e)) for e in content.entries]
    return predicted, int(content.len_entries)


def actual_phase_sequence(
    content_id: int,
    macro_pattern_id: int,
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_first: dict[int, dict[int, int]],
) -> list[int | None]:
    rows = sorted(phrase_by_content.get(content_id, []), key=lambda r: r.phrase_num)
    rev = reverse_first.get(macro_pattern_id, {})
    return [rev.get(r.macro_id) for r in rows]


@dataclass(frozen=True)
class FingerprintMatch:
    """One candidate's fingerprint-bridge result for one tried
    `macro_pattern_id` (one energy guess). `matches` lists every
    content_id sharing that bank whose phase sequence (and row count)
    exactly reproduces the prediction — this IS the discriminating-power
    number the task asks to be reported honestly.
    """

    macro_pattern_id: int
    pattern: int
    energy: int
    pssi_len_entries: int | None
    predicted: list[int | None] | None
    same_pattern_rows: int
    same_pattern_same_length_rows: int
    matches: list[tuple[int, int]]  # (content_id, song_id)


def try_fingerprint_bridge(
    candidate: Candidate,
    pattern: int,
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    analysis_paths: dict[int, str | None],
    subkind_lookup: SubkindLookup,
    reverse_first: dict[int, dict[int, int]],
    pattern_energy_to_mpid: dict[tuple[int, int], int],
) -> list[FingerprintMatch]:
    """Try all 3 energies for one candidate's reported bank NAME (PSSI's
    own `mood` field only matches `macro_pattern.energy` ~98% of the time
    per E1e, so a single mood-derived guess is not trusted blindly here —
    every energy is tried and every result reported, not just the first
    hit).
    """
    results: list[FingerprintMatch] = []
    for energy in (1, 2, 3):
        mpid = pattern_energy_to_mpid.get((pattern, energy))
        if mpid is None:
            continue
        prediction = predict_phase_sequence(
            candidate.content_id, mpid, analysis_paths, subkind_lookup
        )
        if prediction is None:
            results.append(
                FingerprintMatch(
                    macro_pattern_id=mpid,
                    pattern=pattern,
                    energy=energy,
                    pssi_len_entries=None,
                    predicted=None,
                    same_pattern_rows=0,
                    same_pattern_same_length_rows=0,
                    matches=[],
                )
            )
            continue
        predicted, n_entries = prediction

        same_pattern = [
            cid for cid, info in content_info.items() if info.macro_pattern_id == mpid
        ]
        same_length = [
            cid
            for cid in same_pattern
            if len(phrase_by_content.get(cid, [])) == n_entries
        ]
        matches: list[tuple[int, int]] = []
        for cid in same_length:
            actual = actual_phase_sequence(cid, mpid, phrase_by_content, reverse_first)
            if actual == predicted and None not in actual:
                matches.append((cid, content_info[cid].song_id))

        results.append(
            FingerprintMatch(
                macro_pattern_id=mpid,
                pattern=pattern,
                energy=energy,
                pssi_len_entries=n_entries,
                predicted=predicted,
                same_pattern_rows=len(same_pattern),
                same_pattern_same_length_rows=len(same_length),
                matches=matches,
            )
        )
    return results


@dataclass(frozen=True)
class Candidate10Check:
    """Candidate 10's new row (if any) is identified by phrase_data row
    count alone (28, unique among the 10 candidates' own PSSI counts) and
    then self-validated: does its own bank's subkind prediction match the
    row rekordbox itself just wrote? This is the first ground-truth test
    of E1e's forging mechanism (previous validation was all back-derived
    from existing rows).
    """

    content_id: int | None
    song_id: int | None
    resolves_to_live_track: bool | None
    macro_pattern_id: int | None
    predicted: list[int | None] | None
    actual: list[int | None] | None
    row_count: int | None
    pssi_len_entries: int | None
    per_row_hits: int
    per_row_total: int


def check_candidate_10(
    candidate10: Candidate,
    content_diff: ContentDiffResult,
    phrase_diff: PhraseDataDiffResult,
    phrase_by_content_after: dict[int, list[PhraseRow]],
    analysis_paths: dict[int, str | None],
    subkind_lookup: SubkindLookup,
    reverse_first: dict[int, dict[int, int]],
    master_tracks: dict[int, Any],
) -> Candidate10Check:
    own_pssi = read_pssi_content(analysis_paths.get(candidate10.content_id))
    if own_pssi is None:
        return Candidate10Check(None, None, None, None, None, None, None, None, 0, 0)
    own_len = int(own_pssi.len_entries)

    target_id: int | None = None
    for row in content_diff.new_rows:
        if phrase_diff.new_rows_by_content_id.get(row.id) == own_len:
            target_id = row.id
            break
    if target_id is None:
        return Candidate10Check(None, None, None, None, None, None, None, own_len, 0, 0)

    new_row = next(r for r in content_diff.new_rows if r.id == target_id)
    mpid = new_row.macro_pattern_id
    predicted, _ = predict_phase_sequence(
        candidate10.content_id, mpid, analysis_paths, subkind_lookup
    ) or ([], own_len)
    actual = actual_phase_sequence(
        target_id, mpid, phrase_by_content_after, reverse_first
    )
    hits = sum(1 for a, b in zip(predicted, actual) if a == b and a is not None)
    return Candidate10Check(
        content_id=target_id,
        song_id=new_row.song_id,
        resolves_to_live_track=new_row.song_id in master_tracks,
        macro_pattern_id=mpid,
        predicted=predicted,
        actual=actual,
        row_count=len(actual),
        pssi_len_entries=own_len,
        per_row_hits=hits,
        per_row_total=len(actual),
    )


# ---------------------------------------------------------------------------
# Part 3 — Analysis Lock, and its overlap with unreadable ANLZ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalysisLockResult:
    total_library_tracks: int
    locked_count: int
    locked_and_unreadable_pssi: int


def run_analysis_lock_check(master_conn: Any) -> AnalysisLockResult:
    rows = master_conn.execute(
        "SELECT ID, AnalysisDataPath, Analysed FROM djmdContent"
    ).fetchall()
    total = len(rows)
    locked = [(int(r[0]), r[1]) for r in rows if r[2] == ANALYSED_LOCKED_VALUE]
    unreadable = sum(
        1 for _cid, path in locked if phrase_count_from_analysis(path) is None
    )
    return AnalysisLockResult(
        total_library_tracks=total,
        locked_count=len(locked),
        locked_and_unreadable_pssi=unreadable,
    )


# ---------------------------------------------------------------------------
# Part 4 — the "transitions" observation (candidate 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TransitionsCheck:
    macro_event_rows: int
    interlude_macro_ids: list[int]
    phrase_data_rows_using_interlude: list[
        tuple[int, int, int, int]
    ]  # content_id, phrase_num, macro_id, initial_macro_id
    candidate3_content_id: int | None
    candidate3_uses_interlude: bool
    candidate3_has_override: bool
    candidate3_row_dump: list[
        tuple[int, int, int, str | None]
    ]  # phrase_num, macro_id, initial_macro_id, macro_name


def run_transitions_check(
    user_db3: Path,
    macro_db3: Path,
    candidate3_content_id: int | None,
) -> TransitionsCheck:
    mconn = open_readonly(macro_db3)
    try:
        macro_event_rows = mconn.execute("SELECT COUNT(*) FROM macro_event").fetchone()[
            0
        ]
        interlude_ids = {
            r[0]
            for r in mconn.execute(
                "SELECT DISTINCT macro_assign.macro_id FROM macro_assign "
                "JOIN macro_pattern ON macro_assign.macro_pattern_id = macro_pattern.id "
                "WHERE macro_pattern.pattern = 99"
            ).fetchall()
        }
        macro_names = dict(mconn.execute("SELECT id, name FROM macro").fetchall())
    finally:
        mconn.close()

    uconn = open_readonly(user_db3)
    try:
        all_phrase_rows = uconn.execute(
            "SELECT content_id, phrase_num, macro_id, initial_macro_id FROM phrase_data"
        ).fetchall()
    finally:
        uconn.close()

    using_interlude = [
        (cid, pnum, mid, imid)
        for cid, pnum, mid, imid in all_phrase_rows
        if mid in interlude_ids
    ]

    cand3_rows: list[tuple[int, int, int, str | None]] = []
    cand3_uses_interlude = False
    cand3_has_override = False
    if candidate3_content_id is not None:
        rows = sorted(
            (r for r in all_phrase_rows if r[0] == candidate3_content_id),
            key=lambda r: r[1],
        )
        cand3_rows = [
            (pnum, mid, imid, macro_names.get(mid)) for _cid, pnum, mid, imid in rows
        ]
        cand3_uses_interlude = any(mid in interlude_ids for _c, _p, mid, _i in rows)
        cand3_has_override = any(mid != imid for _c, _p, mid, imid in rows)

    return TransitionsCheck(
        macro_event_rows=macro_event_rows,
        interlude_macro_ids=sorted(interlude_ids),
        phrase_data_rows_using_interlude=using_interlude,
        candidate3_content_id=candidate3_content_id,
        candidate3_uses_interlude=cand3_uses_interlude,
        candidate3_has_override=cand3_has_override,
        candidate3_row_dump=cand3_rows,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def bank_name(pattern: int | None) -> str:
    if pattern is None:
        return "NONE"
    return PATTERN_NAMES.get(pattern, f"pattern{pattern}")


def energy_name(energy: int | None) -> str:
    if energy is None:
        return "NONE"
    return ENERGY_NAMES.get(energy, f"energy{energy}")


def print_report(
    content_diff: ContentDiffResult,
    phrase_diff: PhraseDataDiffResult,
    table_diffs: dict[str, Any],
    macro_check: Any,
    pattern_lookup: dict[int, tuple[int | None, int | None]],
    master_tracks: dict[int, Any],
    candidate9_check: Candidate9Check,
    candidate9_fingerprint: Candidate9FingerprintCheck | None,
    candidate10_check: Candidate10Check,
    fingerprint_results: dict[int, list[FingerprintMatch]],
    analysis_lock: AnalysisLockResult,
    transitions: TransitionsCheck,
) -> None:
    print("=" * 78)
    print("Deliverable 1 — did content gain rows?")
    print("=" * 78)
    print(
        f"content rows: before={content_diff.before_count} "
        f"after={content_diff.after_count} "
        f"(session baseline {BASELINE_CONTENT_ROWS}) "
        f"new={len(content_diff.new_rows)} changed={len(content_diff.changed_rows)}"
    )
    for row in content_diff.new_rows:
        pattern, energy = pattern_lookup.get(row.macro_pattern_id, (None, None))
        print(
            f"  NEW id={row.id} song_id={row.song_id} "
            f"macro_pattern_id={row.macro_pattern_id} "
            f"({bank_name(pattern)}/{energy_name(energy)}) "
            f"resolves_to_live_track={row.song_id in master_tracks}"
        )
    for before_row, after_row in content_diff.changed_rows:
        bp, be = pattern_lookup.get(before_row.macro_pattern_id, (None, None))
        ap, ae = pattern_lookup.get(after_row.macro_pattern_id, (None, None))
        print(
            f"  CHANGED id={before_row.id} song_id={before_row.song_id}: "
            f"{bank_name(bp)}/{energy_name(be)} -> {bank_name(ap)}/{energy_name(ae)}"
        )

    print()
    print("=" * 78)
    print("Deliverable 2 — candidate 9's changed row: stale song_id or not?")
    print("=" * 78)
    if candidate9_check.found:
        print(f"changed content_id={candidate9_check.content_id}")
        print(f"row song_id={candidate9_check.row_song_id}")
        print(
            f"candidate 9's CURRENT DjmdContent.ID={candidate9_check.current_djmd_content_id}"
        )
        print(
            f"song_id == current DjmdContent.ID: {candidate9_check.song_id_matches_current_id}"
        )
        print(
            f"bank: pattern {candidate9_check.before_pattern} -> {candidate9_check.after_pattern}"
        )
    else:
        print("no changed content row found in this session's diff.")

    if candidate9_fingerprint is not None:
        print(
            "fingerprint bridge (BEFORE state, candidate 9's OWN PSSI under its "
            f"OLD bank, mpid={candidate9_fingerprint.macro_pattern_id}):"
        )
        print(f"  predicted: {candidate9_fingerprint.predicted}")
        print(f"  actual:    {candidate9_fingerprint.actual}")
        print(f"  matches exactly: {candidate9_fingerprint.matches}")
        print(
            f"  discriminating power: {candidate9_fingerprint.same_pattern_rows} rows "
            f"share this bank, {candidate9_fingerprint.same_pattern_same_length_rows} "
            "also share this row count"
        )

    print()
    print("=" * 78)
    print("Deliverable 3 — phrase_data diff + candidate 10's new row")
    print("=" * 78)
    print(
        f"phrase_data rows: before={phrase_diff.before_count} "
        f"after={phrase_diff.after_count} new={len(phrase_diff.new_rows)} "
        f"changed={len(phrase_diff.changed_rows)}"
    )
    print(f"new rows by content_id: {phrase_diff.new_rows_by_content_id}")
    if candidate10_check.content_id is not None:
        print(f"candidate 10 identified as content_id={candidate10_check.content_id}")
        print(
            f"  song_id={candidate10_check.song_id} resolves_to_live_track={candidate10_check.resolves_to_live_track}"
        )
        print(f"  macro_pattern_id={candidate10_check.macro_pattern_id}")
        print(
            f"  PSSI len_entries={candidate10_check.pssi_len_entries} row_count={candidate10_check.row_count}"
        )
        print(
            f"  per-row hit rate (predicted vs actual, ground truth): "
            f"{candidate10_check.per_row_hits}/{candidate10_check.per_row_total}"
        )
        print(f"  predicted: {candidate10_check.predicted}")
        print(f"  actual:    {candidate10_check.actual}")
    else:
        print("candidate 10: no matching new row identified by phrase count.")

    print()
    print("=" * 78)
    print("Deliverable — the fingerprint bridge (candidates with a displayed bank)")
    print("=" * 78)
    for num, results in fingerprint_results.items():
        print(f"candidate {num}:")
        for r in results:
            print(
                f"  mpid={r.macro_pattern_id} ({bank_name(r.pattern)}/{energy_name(r.energy)}) "
                f"pssi_len={r.pssi_len_entries} same_pattern_rows={r.same_pattern_rows} "
                f"same_length_rows={r.same_pattern_same_length_rows} "
                f"exact_matches={len(r.matches)} {r.matches}"
            )

    print()
    print("=" * 78)
    print("Deliverable 4 — everything else")
    print("=" * 78)
    for table, diff in table_diffs.items():
        print(
            f"{table}: before={diff.before_count} after={diff.after_count} "
            f"only_before={len(diff.only_before)} only_after={len(diff.only_after)}"
        )
    print(f"macro.db3 untouched: {macro_check.same_mtime}")

    print()
    print("=" * 78)
    print("Analysis Lock")
    print("=" * 78)
    print(
        f"library tracks: {analysis_lock.total_library_tracks}, "
        f"locked (Analysed={ANALYSED_LOCKED_VALUE}): {analysis_lock.locked_count}, "
        f"locked AND unreadable PSSI: {analysis_lock.locked_and_unreadable_pssi}"
    )

    print()
    print("=" * 78)
    print("Transitions (candidate 3)")
    print("=" * 78)
    print(f"macro_event rows: {transitions.macro_event_rows}")
    print(f"INTERLUDE (pattern=99) macro_ids: {transitions.interlude_macro_ids}")
    print(
        f"phrase_data rows anywhere in the library using an INTERLUDE macro_id: "
        f"{len(transitions.phrase_data_rows_using_interlude)} {transitions.phrase_data_rows_using_interlude}"
    )
    if transitions.candidate3_content_id is not None:
        print(f"candidate 3 resolved to content_id={transitions.candidate3_content_id}")
        print(f"  uses an INTERLUDE macro_id: {transitions.candidate3_uses_interlude}")
        print(f"  has a phrase-level override: {transitions.candidate3_has_override}")
        for pnum, mid, imid, name in transitions.candidate3_row_dump:
            print(f"    phrase_num={pnum} macro_id={mid} initial={imid} name={name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before",
        type=Path,
        required=True,
        help="Path to the BEFORE snapshot of user.db3 (e.g. work/e1d2_before_user.db3).",
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
        help="Path to the LIVE macro.db3, read-only, for the mtime-untouched check.",
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
        analysis_paths: dict[int, str | None] = {
            int(track_id): path
            for track_id, path in master_conn.execute(
                "SELECT ID, AnalysisDataPath FROM djmdContent"
            ).fetchall()
        }
        analysis_lock = run_analysis_lock_check(master_conn)
    finally:
        master_conn.close()

    pattern_lookup = load_macro_pattern_lookup(args.macro_db3)
    assign_by_pattern = load_macro_assign_by_pattern(args.macro_db3)
    reverse_first = build_reverse_lookup_first_phase(assign_by_pattern)
    pattern_energy = load_pattern_energy(args.macro_db3)
    mconn = open_readonly(args.macro_db3)
    try:
        pattern_energy_to_mpid = {
            (row[1], row[2]): row[0]
            for row in mconn.execute("SELECT id, pattern, energy FROM macro_pattern")
        }
    finally:
        mconn.close()

    content_diff, phrase_diff = run_diff(args.before, args.after, args.macro_db3)
    table_diffs = diff_all_user_db3_tables(args.before, args.after)
    macro_check = check_macro_db_untouched(args.macro_db3, live_macro_db3)

    content_info = load_content_info(args.after)
    phrase_by_content = load_phrase_data_by_content(args.after)
    subkind_lookup = build_subkind_lookup(
        content_info,
        phrase_by_content,
        reverse_first,
        master_tracks,
        analysis_paths,
        pattern_energy,
    )

    by_number = {c.number: c for c in CANDIDATES}
    candidate9_check = check_candidate_9(content_diff, by_number[9])
    candidate9_fingerprint = check_candidate9_before_state_fingerprint(
        candidate9_check,
        args.before,
        subkind_lookup,
        analysis_paths,
        reverse_first,
    )
    candidate10_check = check_candidate_10(
        by_number[10],
        content_diff,
        phrase_diff,
        phrase_by_content,
        analysis_paths,
        subkind_lookup,
        reverse_first,
        master_tracks,
    )

    fingerprint_results: dict[int, list[FingerprintMatch]] = {}
    for candidate in CANDIDATES:
        if candidate.displayed_bank is None:
            continue
        pattern = {v: k for k, v in PATTERN_NAMES.items()}[candidate.displayed_bank]
        fingerprint_results[candidate.number] = try_fingerprint_bridge(
            candidate,
            pattern,
            content_info,
            phrase_by_content,
            analysis_paths,
            subkind_lookup,
            reverse_first,
            pattern_energy_to_mpid,
        )

    candidate3_content_id = None
    for r in fingerprint_results.get(3, []):
        if r.matches:
            candidate3_content_id = r.matches[0][0]
            break
    transitions = run_transitions_check(
        args.after, args.macro_db3, candidate3_content_id
    )

    print_report(
        content_diff,
        phrase_diff,
        table_diffs,
        macro_check,
        pattern_lookup,
        master_tracks,
        candidate9_check,
        candidate9_fingerprint,
        candidate10_check,
        fingerprint_results,
        analysis_lock,
        transitions,
    )


if __name__ == "__main__":
    main()
