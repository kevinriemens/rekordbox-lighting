"""E1f — "the fingerprint bridge at scale". Disposable, READ-ONLY probe,
seventh in the E1/E1b/E1c/E1d/E1d2/E1e series.

See docs/experiments/E1f-fingerprint-bridge.md for the written verdict this
script exists to produce — that file, not this one, is the deliverable.

E1d2 demonstrated the content-based fingerprint bridge on 7 hand-picked
tracks: bank + PSSI phrase-kind sequence + row count, no `song_id`
involved, resolving 5 of 7 to exactly one stale `content` row. This probe
runs the same bridge at library scale, in two passes:

  1. VALIDATION — take the ~1,183 `content` rows that already resolve by
     ID. Hide the ID link (the matcher never sees `content.song_id`), run
     the bridge, and check whether it independently finds the SAME track
     the ID says it is. This measures precision/recall the honest way:
     against known answers, not against an assumption that a match is
     correct just because it's unique.
  2. RECOVERY — run the identical bridge over the ~1,783 stranded rows
     (song_id does not resolve to a live `DjmdContent.ID`), against a
     candidate pool of library tracks NOT already claimed by an
     ID-resolving row.

Everything downstream (the headline "how many library tracks are lit"
number) is only as trustworthy as pass 1's precision figure — see the
report's lead section before trusting pass 2's numbers as fact.

Safety (see rekordbox-data-safety skill):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. Reused
    via `ensure_master_db_copy` (E1's helper) — this script does NOT
    refresh it, and does not refresh `work/user.db3`/`work/macro.db3`
    either (the task instructs against any refresh — the working copies
    were already brought current during E1d2 and must be used as-is).
    `work/e1d_before_user.db3` and `work/e1d2_before_user.db3` are
    irreplaceable snapshots and are never opened by this script at all.
  - `work/user.db3` and `work/macro.db3` are opened read-only
    (`open_readonly`).
  - The `ANLZ0000.EXT` analysis cache files are opened with a plain
    read-only file open via `pyrekordbox`'s `AnlzFile.parse_file` — the
    exact mechanism `e1d2_candidate_tracks.py`/`e1e_phrase_phase_mapping.py`
    already used.
  - This script writes nothing except its own stdout. It does not call
    `sync.pull`/`sync.push` and does not open any `.db3` read-write.

This module imports shared helpers from `e1_library_join`,
`e1b_real_denominator`, `e1e_phrase_phase_mapping`, and
`e1d2_lighting_mode_rerun` — all disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward).

Requires the optional `experiments` dependency group (same as E1/E1b/E1d):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1f_fingerprint_bridge
"""

from __future__ import annotations

import argparse
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    MasterTrack,
    ensure_master_db_copy,
    load_master_tracks,
    load_my_tags,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import (
    ENERGY_NAMES,
    MOOD_CATEGORY,
    load_song_my_tags_dedup,
    tag_category,
)
from rbxlight.experiments.e1d2_lighting_mode_rerun import (
    ANALYSED_LOCKED_VALUE,
    SubkindLookup,
    build_subkind_lookup,
)
from rbxlight.experiments.e1e_phrase_phase_mapping import (
    PhraseRow,
    SubkindKey,
    build_reverse_lookup_first_phase,
    load_content_info,
    load_macro_assign_by_pattern,
    load_pattern_energy,
    load_phrase_data_by_content,
    read_pssi_content,
    subkind_key_of,
)

#: "Genres" is the sibling of e1b's MOOD_CATEGORY/SITUATION_CATEGORY — used
#: only here to reproduce E1c's exact "any usable My Tag" definition
#: (Mood-or-Genres category, per E1c section 3.6), not redefined there
#: since e1b had no need for it.
GENRES_CATEGORY = "Genres"

#: Task's assumed baseline figures, quoted only for direct comparison —
#: this probe measures its own fresh numbers rather than trusting these
#: (see E1d2's own precedent: measured 7615 library tracks, not the 7607
#: quoted in its task).
TASK_BASELINE_CONTENT_ROWS = 2966
TASK_BASELINE_STRANDED_ROWS = 1783
TASK_BASELINE_RESOLVING_ROWS = 1183
TASK_BASELINE_LIBRARY_TRACKS = 7607

#: pyrekordbox logs one WARNING per unsupported ANLZ tag type (e.g. PKEY)
#: per file parsed — harmless (PKEY isn't used by this probe) but at
#: library scale (~7600 files) it drowns stdout. Quieted here only for
#: this probe's own run, not globally for the package.
logging.getLogger("pyrekordbox").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# PSSI caching — read each track's PSSI tag exactly once for the whole run
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PssiCacheEntry:
    """One track's PSSI phrase-kind fingerprint, read once and reused for
    every bank this probe tests it against — the phrase-kind sequence
    itself does not depend on `macro_pattern_id`; only which phase it
    predicts does (a `subkind_lookup` lookup, not a re-read).
    """

    subkinds: tuple[SubkindKey, ...]
    len_entries: int


def build_pssi_cache(
    track_ids: list[int], analysis_paths: dict[int, str | None]
) -> dict[int, PssiCacheEntry | None]:
    """Read every track's PSSI tag exactly once. `None` means unreadable
    (no analysis path, no `.EXT` file, or no `PSSI` tag) — never treated
    as a phrase count of zero.
    """
    cache: dict[int, PssiCacheEntry | None] = {}
    for track_id in track_ids:
        content = read_pssi_content(analysis_paths.get(track_id))
        if content is None:
            cache[track_id] = None
            continue
        subkinds = tuple(subkind_key_of(e) for e in content.entries)
        cache[track_id] = PssiCacheEntry(
            subkinds=subkinds, len_entries=int(content.len_entries)
        )
    return cache


def index_by_phrase_count(
    cache: dict[int, PssiCacheEntry | None], allowed_ids: set[int] | None = None
) -> dict[int, list[int]]:
    """`phrase_count -> [track_id, ...]`, restricted to `allowed_ids` if
    given (the candidate-pool exclusion for the stranded-row pass).
    Built once per pass, reused for every row in that pass — this is the
    "index by phrase count first" the task asks for.
    """
    idx: dict[int, list[int]] = defaultdict(list)
    for track_id, entry in cache.items():
        if entry is None:
            continue
        if allowed_ids is not None and track_id not in allowed_ids:
            continue
        idx[entry.len_entries].append(track_id)
    return dict(idx)


def predict_from_cache(
    entry: PssiCacheEntry, mpid: int, subkind_lookup: SubkindLookup
) -> list[int | None]:
    table = subkind_lookup.by_pattern.get(mpid, {})
    return [table.get(sk) for sk in entry.subkinds]


# ---------------------------------------------------------------------------
# content rows, loaded raw (id, song_id, macro_pattern_id)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentRow:
    id: int
    song_id: int
    macro_pattern_id: int


def load_content_rows(user_db3: Path) -> list[ContentRow]:
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT id, song_id, macro_pattern_id FROM content ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [ContentRow(*row) for row in rows]


# ---------------------------------------------------------------------------
# The bridge attempt — shared by both passes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeAttempt:
    content_id: int
    song_id: int
    macro_pattern_id: int
    phrase_count: int
    actual: tuple[int | None, ...]
    has_override: bool
    unresolved_sequence: bool  # any None in `actual` — row excluded from matching
    matches: tuple[int, ...]  # candidate track ids whose predicted == actual


def run_bridge(
    rows: list[ContentRow],
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_first: dict[int, dict[int, int]],
    phrase_count_index: dict[int, list[int]],
    pssi_cache: dict[int, PssiCacheEntry | None],
    subkind_lookup: SubkindLookup,
) -> list[BridgeAttempt]:
    attempts: list[BridgeAttempt] = []
    for row in rows:
        phrases = sorted(
            phrase_by_content.get(row.id, []), key=lambda r: r.phrase_num
        )
        has_override = any(p.macro_id != p.initial_macro_id for p in phrases)
        rev = reverse_first.get(row.macro_pattern_id, {})
        actual: tuple[int | None, ...] = tuple(rev.get(p.macro_id) for p in phrases)
        unresolved = any(a is None for a in actual)
        n = len(actual)

        matches: list[int] = []
        if not unresolved and n > 0:
            table = subkind_lookup.by_pattern.get(row.macro_pattern_id, {})
            for track_id in phrase_count_index.get(n, []):
                entry = pssi_cache[track_id]
                assert entry is not None  # index only contains readable entries
                predicted = tuple(table.get(sk) for sk in entry.subkinds)
                if predicted == actual and all(p is not None for p in predicted):
                    matches.append(track_id)

        attempts.append(
            BridgeAttempt(
                content_id=row.id,
                song_id=row.song_id,
                macro_pattern_id=row.macro_pattern_id,
                phrase_count=n,
                actual=actual,
                has_override=has_override,
                unresolved_sequence=unresolved,
                matches=tuple(matches),
            )
        )
    return attempts


# ---------------------------------------------------------------------------
# Part 1 — validation over the ID-resolving population
# ---------------------------------------------------------------------------


@dataclass
class ValidationSummary:
    total_rows: int
    excluded_unresolved: int
    attempted: int
    exact_one: int
    exact_one_correct: int
    exact_one_wrong: int
    multi: int
    multi_size_dist: Counter[int]
    multi_contains_correct: int
    zero: int
    zero_true_unreadable: int
    zero_true_count_drift: int
    zero_divergence: int
    override_rows_attempted: int
    override_rows_exact_one_correct: int
    non_override_attempted: int
    non_override_exact_one_correct: int
    by_bank: dict[int, dict[str, int]]
    by_phrase_count_bucket: dict[str, dict[str, int]]

    @property
    def precision_pct(self) -> float:
        """Of rows resolving to exactly one candidate, how often that one
        candidate is the CORRECT track. This is the number the task says
        governs everything downstream.
        """
        return (
            round(100 * self.exact_one_correct / self.exact_one, 2)
            if self.exact_one
            else 0.0
        )

    @property
    def recall_in_multi_pct(self) -> float:
        return (
            round(100 * self.multi_contains_correct / self.multi, 1)
            if self.multi
            else 0.0
        )


def summarize_validation(
    attempts: list[BridgeAttempt],
    pssi_cache: dict[int, PssiCacheEntry | None],
    pattern_energy: dict[int, tuple[int, int]],
) -> ValidationSummary:
    total = len(attempts)
    excluded_unresolved = sum(1 for a in attempts if a.unresolved_sequence)

    exact_one = exact_one_correct = exact_one_wrong = 0
    multi = multi_contains_correct = 0
    multi_size_dist: Counter[int] = Counter()
    zero = zero_true_unreadable = zero_true_count_drift = zero_divergence = 0
    override_attempted = override_correct = 0
    non_override_attempted = non_override_correct = 0

    by_bank: dict[int, dict[str, int]] = defaultdict(
        lambda: {"attempted": 0, "exact_one": 0, "exact_one_correct": 0}
    )
    by_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempted": 0, "exact_one": 0, "exact_one_correct": 0}
    )

    for a in attempts:
        if a.unresolved_sequence:
            continue

        n_matches = len(a.matches)
        correct_present = a.song_id in a.matches

        if a.has_override:
            override_attempted += 1
        else:
            non_override_attempted += 1

        bank_stat = by_bank[a.macro_pattern_id]
        bank_stat["attempted"] += 1
        bucket = _phrase_count_bucket(a.phrase_count)
        bucket_stat = by_bucket[bucket]
        bucket_stat["attempted"] += 1

        if n_matches == 1:
            exact_one += 1
            bank_stat["exact_one"] += 1
            bucket_stat["exact_one"] += 1
            if correct_present:
                exact_one_correct += 1
                bank_stat["exact_one_correct"] += 1
                bucket_stat["exact_one_correct"] += 1
                if a.has_override:
                    override_correct += 1
                else:
                    non_override_correct += 1
            else:
                exact_one_wrong += 1
        elif n_matches > 1:
            multi += 1
            multi_size_dist[n_matches] += 1
            if correct_present:
                multi_contains_correct += 1
        else:
            zero += 1
            true_entry = pssi_cache.get(a.song_id)
            if true_entry is None:
                zero_true_unreadable += 1
            elif true_entry.len_entries != a.phrase_count:
                zero_true_count_drift += 1
            else:
                zero_divergence += 1

    return ValidationSummary(
        total_rows=total,
        excluded_unresolved=excluded_unresolved,
        attempted=total - excluded_unresolved,
        exact_one=exact_one,
        exact_one_correct=exact_one_correct,
        exact_one_wrong=exact_one_wrong,
        multi=multi,
        multi_size_dist=multi_size_dist,
        multi_contains_correct=multi_contains_correct,
        zero=zero,
        zero_true_unreadable=zero_true_unreadable,
        zero_true_count_drift=zero_true_count_drift,
        zero_divergence=zero_divergence,
        override_rows_attempted=override_attempted,
        override_rows_exact_one_correct=override_correct,
        non_override_attempted=non_override_attempted,
        non_override_exact_one_correct=non_override_correct,
        by_bank=dict(by_bank),
        by_phrase_count_bucket=dict(by_bucket),
    )


def _phrase_count_bucket(n: int) -> str:
    if n <= 10:
        return "<=10"
    if n <= 20:
        return "11-20"
    if n <= 30:
        return "21-30"
    return ">30"


# ---------------------------------------------------------------------------
# Part 2 — recovery over the stranded population
# ---------------------------------------------------------------------------


@dataclass
class RecoverySummary:
    total_rows: int
    excluded_unresolved: int
    attempted: int
    exact_one: int
    multi: int
    multi_size_dist: Counter[int]
    zero: int
    zero_no_candidate_at_count: int
    zero_divergence: int
    recovered_track_ids: list[int]  # one per exact-one row, may repeat
    duplicate_claims: dict[int, list[int]]  # track_id -> [content_id, ...] (len>1)


def summarize_recovery(
    attempts: list[BridgeAttempt],
    phrase_count_index: dict[int, list[int]],
) -> RecoverySummary:
    total = len(attempts)
    excluded_unresolved = sum(1 for a in attempts if a.unresolved_sequence)

    exact_one = multi = zero = 0
    zero_no_candidate = zero_divergence = 0
    multi_size_dist: Counter[int] = Counter()
    recovered: list[int] = []
    claims: dict[int, list[int]] = defaultdict(list)

    for a in attempts:
        if a.unresolved_sequence:
            continue
        n_matches = len(a.matches)
        if n_matches == 1:
            exact_one += 1
            recovered.append(a.matches[0])
            claims[a.matches[0]].append(a.content_id)
        elif n_matches > 1:
            multi += 1
            multi_size_dist[n_matches] += 1
        else:
            zero += 1
            if not phrase_count_index.get(a.phrase_count):
                zero_no_candidate += 1
            else:
                zero_divergence += 1

    duplicate_claims = {tid: cids for tid, cids in claims.items() if len(cids) > 1}

    return RecoverySummary(
        total_rows=total,
        excluded_unresolved=excluded_unresolved,
        attempted=total - excluded_unresolved,
        exact_one=exact_one,
        multi=multi,
        multi_size_dist=multi_size_dist,
        zero=zero,
        zero_no_candidate_at_count=zero_no_candidate,
        zero_divergence=zero_divergence,
        recovered_track_ids=recovered,
        duplicate_claims=duplicate_claims,
    )


# ---------------------------------------------------------------------------
# Part 3 — bank distribution comparison (resolving vs recovered)
# ---------------------------------------------------------------------------


def bank_distribution(
    mpids: list[int], pattern_energy: dict[int, tuple[int, int]]
) -> Counter[str]:
    dist: Counter[str] = Counter()
    for mpid in mpids:
        pattern, energy = pattern_energy.get(mpid, (None, None))
        bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "UNKNOWN"
        energy_name = ENERGY_NAMES.get(energy, "UNKNOWN") if energy else "UNKNOWN"
        dist[f"{bank}/{energy_name}"] += 1
    return dist


# ---------------------------------------------------------------------------
# Part 4 — secondary: recovered-track metadata coverage, no-ANLZ / lock counts
# ---------------------------------------------------------------------------


@dataclass
class MetadataCoverage:
    n: int
    genre_pct: float
    bpm_pct: float
    any_my_tag_pct: float


def measure_metadata_coverage(
    track_ids: list[int],
    master_tracks: dict[int, MasterTrack],
    song_my_tags: dict[int, set[str]],
    my_tags: dict[str, dict[str, str | None]],
) -> MetadataCoverage:
    n = len(track_ids)
    if n == 0:
        return MetadataCoverage(n=0, genre_pct=0.0, bpm_pct=0.0, any_my_tag_pct=0.0)
    genre = sum(1 for t in track_ids if master_tracks[t].genre_id)
    bpm = sum(1 for t in track_ids if master_tracks[t].bpm)
    any_tag = 0
    for t in track_ids:
        tags = song_my_tags.get(t, set())
        cats = {tag_category(tg, my_tags) for tg in tags}
        if MOOD_CATEGORY in cats or GENRES_CATEGORY in cats:
            any_tag += 1
    return MetadataCoverage(
        n=n,
        genre_pct=round(100 * genre / n, 1),
        bpm_pct=round(100 * bpm / n, 1),
        any_my_tag_pct=round(100 * any_tag / n, 1),
    )


@dataclass
class AnlzCoverage:
    total_library_tracks: int
    no_readable_anlz: int
    locked_count: int
    locked_and_no_readable_anlz: int


def measure_anlz_coverage(
    master_conn: Any, pssi_cache: dict[int, PssiCacheEntry | None]
) -> AnlzCoverage:
    rows = master_conn.execute("SELECT ID, Analysed FROM djmdContent").fetchall()
    total = len(rows)
    no_readable = sum(1 for tid, _ in rows if pssi_cache.get(int(tid)) is None)
    locked = [int(tid) for tid, analysed in rows if analysed == ANALYSED_LOCKED_VALUE]
    locked_no_anlz = sum(1 for tid in locked if pssi_cache.get(tid) is None)
    return AnlzCoverage(
        total_library_tracks=total,
        no_readable_anlz=no_readable,
        locked_count=len(locked),
        locked_and_no_readable_anlz=locked_no_anlz,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def bank_label(mpid: int, pattern_energy: dict[int, tuple[int, int]]) -> str:
    pattern, energy = pattern_energy.get(mpid, (None, None))
    bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "NONE"
    energy_name = ENERGY_NAMES.get(energy, "NONE") if energy else "NONE"
    return f"{bank}/{energy_name}"


def print_report(
    validation: ValidationSummary,
    recovery: RecoverySummary,
    resolving_bank_dist: Counter[str],
    recovered_bank_dist: Counter[str],
    total_library_tracks: int,
    id_resolving_distinct: int,
    recovered_distinct: int,
    total_content_rows: int,
    total_resolving_rows: int,
    total_stranded_rows: int,
    resolving_coverage: MetadataCoverage,
    recovered_coverage: MetadataCoverage,
    anlz_coverage: AnlzCoverage,
    subkind_lookup: SubkindLookup,
    pattern_energy: dict[int, tuple[int, int]],
) -> None:
    print("=" * 78)
    print("Denominators measured fresh this run")
    print("=" * 78)
    print(f"library tracks (djmdContent rows):        {total_library_tracks}")
    print(f"content rows (user.db3):                  {total_content_rows}")
    print(f"  ID-resolving:                            {total_resolving_rows}")
    print(f"  stranded (non-resolving):                {total_stranded_rows}")
    print(
        f"subkind lookup built from {subkind_lookup.tracks_used} tracks, "
        f"{subkind_lookup.total_keys} keys, weighted accuracy "
        f"{subkind_lookup.weighted_accuracy_pct}% (see E1e)"
    )

    print()
    print("=" * 78)
    print("PART 1 — VALIDATION (bridge run over the ID-resolving population, "
          "ID hidden)")
    print("=" * 78)
    print(f"total rows: {validation.total_rows}")
    print(
        f"excluded (own actual sequence unresolved in macro_assign): "
        f"{validation.excluded_unresolved}"
    )
    print(f"attempted: {validation.attempted}")
    print(
        f"  exact-one-match: {validation.exact_one} "
        f"({round(100 * validation.exact_one / validation.attempted, 1)}% of attempted) "
        f"— correct: {validation.exact_one_correct}, wrong: {validation.exact_one_wrong}"
    )
    print(f"  PRECISION (of exact-one matches, % correct): {validation.precision_pct}%")
    print(
        f"  multi-match (ambiguous): {validation.multi} "
        f"({round(100 * validation.multi / validation.attempted, 1)}%) — "
        f"correct track present in candidate set: {validation.multi_contains_correct} "
        f"({validation.recall_in_multi_pct}%)"
    )
    print("    candidate-set-size distribution:")
    for size, count in sorted(validation.multi_size_dist.items()):
        print(f"      {size} candidates: {count} rows")
    print(
        f"  zero-match: {validation.zero} "
        f"({round(100 * validation.zero / validation.attempted, 1)}%)"
    )
    print(f"    true track's own PSSI unreadable: {validation.zero_true_unreadable}")
    print(
        f"    true track's PSSI len_entries != this row's phrase count "
        f"(drift): {validation.zero_true_count_drift}"
    )
    print(f"    candidates existed, sequence diverged: {validation.zero_divergence}")

    print()
    print("  accuracy by override status:")
    print(
        f"    non-override rows: {validation.non_override_attempted} attempted, "
        f"{validation.non_override_exact_one_correct} exact-one-correct"
    )
    print(
        f"    override rows (of the ~36 known): {validation.override_rows_attempted} "
        f"attempted, {validation.override_rows_exact_one_correct} exact-one-correct"
    )

    print()
    print("  accuracy by bank (macro_pattern_id):")
    for mpid, stat in sorted(validation.by_bank.items()):
        label = bank_label(mpid, pattern_energy)
        pct = (
            round(100 * stat["exact_one_correct"] / stat["exact_one"], 1)
            if stat["exact_one"]
            else None
        )
        print(
            f"    mpid={mpid} ({label}): attempted={stat['attempted']} "
            f"exact_one={stat['exact_one']} exact_one_correct={stat['exact_one_correct']} "
            f"precision={pct}%"
        )

    print()
    print("  accuracy by phrase-count bucket:")
    for bucket, stat in sorted(validation.by_phrase_count_bucket.items()):
        pct = (
            round(100 * stat["exact_one_correct"] / stat["exact_one"], 1)
            if stat["exact_one"]
            else None
        )
        print(
            f"    N{bucket}: attempted={stat['attempted']} exact_one={stat['exact_one']} "
            f"exact_one_correct={stat['exact_one_correct']} precision={pct}%"
        )

    print()
    print("=" * 78)
    print("PART 2 — RECOVERY (bridge run over the stranded population)")
    print("=" * 78)
    print(f"total rows: {recovery.total_rows}")
    print(
        f"excluded (own actual sequence unresolved in macro_assign): "
        f"{recovery.excluded_unresolved}"
    )
    print(f"attempted: {recovery.attempted}")
    print(
        f"  exact-one-match (recovered): {recovery.exact_one} "
        f"({round(100 * recovery.exact_one / recovery.attempted, 1)}% of attempted)"
    )
    print(
        f"  multi-match (ambiguous): {recovery.multi} "
        f"({round(100 * recovery.multi / recovery.attempted, 1)}%)"
    )
    print("    candidate-set-size distribution:")
    for size, count in sorted(recovery.multi_size_dist.items()):
        print(f"      {size} candidates: {count} rows")
    print(
        f"  zero-match: {recovery.zero} "
        f"({round(100 * recovery.zero / recovery.attempted, 1)}%)"
    )
    print(
        f"    no candidate at all shares this phrase count: "
        f"{recovery.zero_no_candidate_at_count}"
    )
    print(f"    candidates existed, sequence diverged: {recovery.zero_divergence}")
    print(
        f"  distinct library tracks claimed by exactly-one-match rows: "
        f"{len(set(recovery.recovered_track_ids))} "
        f"(from {recovery.exact_one} recovered rows)"
    )
    if recovery.duplicate_claims:
        print(
            f"  ⚠ {len(recovery.duplicate_claims)} library track(s) claimed by >1 "
            "stranded row:"
        )
        for tid, cids in recovery.duplicate_claims.items():
            print(f"      track {tid}: content_ids {cids}")
    else:
        print("  no library track was claimed by more than one stranded row.")

    print()
    print("  bank distribution — ID-resolving population:")
    total_r = sum(resolving_bank_dist.values())
    for bank, count in resolving_bank_dist.most_common():
        print(f"    {bank}: {count} ({round(100 * count / total_r, 1)}%)")
    print("  bank distribution — recovered (exact-one) stranded rows:")
    total_c = sum(recovered_bank_dist.values())
    if total_c:
        for bank, count in recovered_bank_dist.most_common():
            print(f"    {bank}: {count} ({round(100 * count / total_c, 1)}%)")
    else:
        print("    (no recovered rows)")

    print()
    print("=" * 78)
    print("PART 3 — THE HEADLINE NUMBER")
    print("=" * 78)
    lower_bound = id_resolving_distinct + recovered_distinct
    upper_bound = id_resolving_distinct + total_stranded_rows
    print(f"library tracks total: {total_library_tracks}")
    print(f"identifiable + lit (ID-resolving OR uniquely bridged): {lower_bound}/{total_library_tracks} "
          f"({round(100 * lower_bound / total_library_tracks, 1)}%)")
    print(
        f"  of which: {id_resolving_distinct} by direct ID, "
        f"{recovered_distinct} recovered by the fingerprint bridge"
    )
    print(
        f"upper-bound estimate if EVERY stranded row is a distinct real track "
        f"(per E1d2's finding that stranded rows are real, not junk): "
        f"{upper_bound}/{total_library_tracks} "
        f"({round(100 * upper_bound / total_library_tracks, 1)}%)"
    )
    lit_unidentifiable_rows = (
        recovery.attempted - recovery.exact_one + recovery.excluded_unresolved
    )
    print(
        f"lit but NOT identifiable by this method: {lit_unidentifiable_rows} stranded "
        f"content rows (ambiguous, zero-match, or sequence-unresolved) — each is real "
        "programming for some track, but this bridge cannot safely say which"
    )
    print(
        f"residual uncertainty — library tracks with NO readable ANLZ at all "
        f"(can never be tested by this method, lit or not): "
        f"{anlz_coverage.no_readable_anlz}/{anlz_coverage.total_library_tracks} "
        f"({round(100 * anlz_coverage.no_readable_anlz / anlz_coverage.total_library_tracks, 1)}%)"
    )

    print()
    print("=" * 78)
    print("PART 4 — secondary")
    print("=" * 78)
    print(
        f"metadata coverage, ID-resolving population (n={resolving_coverage.n}): "
        f"genre={resolving_coverage.genre_pct}% bpm={resolving_coverage.bpm_pct}% "
        f"any-usable-My-Tag={resolving_coverage.any_my_tag_pct}%"
    )
    print(
        f"metadata coverage, recovered stranded tracks (n={recovered_coverage.n}): "
        f"genre={recovered_coverage.genre_pct}% bpm={recovered_coverage.bpm_pct}% "
        f"any-usable-My-Tag={recovered_coverage.any_my_tag_pct}%"
    )
    print(
        f"library tracks with no readable ANLZ at all: "
        f"{anlz_coverage.no_readable_anlz}/{anlz_coverage.total_library_tracks} "
        f"({round(100 * anlz_coverage.no_readable_anlz / anlz_coverage.total_library_tracks, 1)}%)"
    )
    print(
        f"Analysis-Locked tracks: {anlz_coverage.locked_count} "
        f"(of which {anlz_coverage.locked_and_no_readable_anlz} also have no readable "
        "ANLZ)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-db3", type=Path, default=Path("work/user.db3"),
        help="Path to user.db3 (current working copy). Default: work/user.db3.",
    )
    parser.add_argument(
        "--macro-db3", type=Path, default=Path("work/macro.db3"),
        help="Path to macro.db3 (current working copy). Default: work/macro.db3.",
    )
    args = parser.parse_args()

    master_path = ensure_master_db_copy()
    master_conn = open_master_db(master_path)
    try:
        master_tracks = load_master_tracks(master_conn)
        my_tags = load_my_tags(master_conn)
        song_my_tags = load_song_my_tags_dedup(master_conn)
        analysis_paths: dict[int, str | None] = {
            int(track_id): path
            for track_id, path in master_conn.execute(
                "SELECT ID, AnalysisDataPath FROM djmdContent"
            ).fetchall()
        }

        content_rows = load_content_rows(args.user_db3)
        content_info = load_content_info(args.user_db3)
        phrase_by_content = load_phrase_data_by_content(args.user_db3)

        assign_by_pattern = load_macro_assign_by_pattern(args.macro_db3)
        reverse_first = build_reverse_lookup_first_phase(assign_by_pattern)
        pattern_energy = load_pattern_energy(args.macro_db3)

        # Subkind lookup — built from the current ID-resolving population,
        # exactly as E1e/E1d2 did (see report for the leave-one-out caveat).
        subkind_lookup = build_subkind_lookup(
            content_info,
            phrase_by_content,
            reverse_first,
            master_tracks,
            analysis_paths,
            pattern_energy,
        )

        # Read every track's PSSI exactly once for the whole run.
        all_track_ids = list(master_tracks)
        print(f"reading PSSI for {len(all_track_ids)} library tracks (once)...")
        pssi_cache = build_pssi_cache(all_track_ids, analysis_paths)
        print(
            f"done — {sum(1 for v in pssi_cache.values() if v is not None)} readable"
        )

        anlz_coverage = measure_anlz_coverage(master_conn, pssi_cache)
    finally:
        master_conn.close()

    resolving_rows = [r for r in content_rows if r.song_id in master_tracks]
    stranded_rows = [r for r in content_rows if r.song_id not in master_tracks]

    # ---- Part 1: validation, full-library candidate pool ----
    full_index = index_by_phrase_count(pssi_cache, allowed_ids=None)
    validation_attempts = run_bridge(
        resolving_rows,
        phrase_by_content,
        reverse_first,
        full_index,
        pssi_cache,
        subkind_lookup,
    )
    validation = summarize_validation(validation_attempts, pssi_cache, pattern_energy)

    # ---- Part 2: recovery, candidate pool excludes already-claimed tracks ----
    claimed_ids = {r.song_id for r in resolving_rows}
    unclaimed_ids = set(master_tracks) - claimed_ids
    unclaimed_index = index_by_phrase_count(pssi_cache, allowed_ids=unclaimed_ids)
    recovery_attempts = run_bridge(
        stranded_rows,
        phrase_by_content,
        reverse_first,
        unclaimed_index,
        pssi_cache,
        subkind_lookup,
    )
    recovery = summarize_recovery(recovery_attempts, unclaimed_index)

    resolving_bank_dist = bank_distribution(
        [r.macro_pattern_id for r in resolving_rows], pattern_energy
    )
    recovered_bank_dist = bank_distribution(
        [a.macro_pattern_id for a in recovery_attempts if len(a.matches) == 1],
        pattern_energy,
    )

    recovered_distinct_ids = sorted(set(recovery.recovered_track_ids))
    resolving_coverage = measure_metadata_coverage(
        sorted(claimed_ids), master_tracks, song_my_tags, my_tags
    )
    recovered_coverage = measure_metadata_coverage(
        recovered_distinct_ids, master_tracks, song_my_tags, my_tags
    )

    print_report(
        validation,
        recovery,
        resolving_bank_dist,
        recovered_bank_dist,
        total_library_tracks=len(master_tracks),
        id_resolving_distinct=len(claimed_ids),
        recovered_distinct=len(recovered_distinct_ids),
        total_content_rows=len(content_rows),
        total_resolving_rows=len(resolving_rows),
        total_stranded_rows=len(stranded_rows),
        resolving_coverage=resolving_coverage,
        recovered_coverage=recovered_coverage,
        anlz_coverage=anlz_coverage,
        subkind_lookup=subkind_lookup,
        pattern_energy=pattern_energy,
    )


if __name__ == "__main__":
    main()
