"""E1c — "after full analysis". Disposable, READ-ONLY probe, third in the
E1/E1b series.

See docs/experiments/E1c-after-full-analysis.md for the written verdict this
script exists to produce — that file, not this one, is the deliverable.

E1 (docs/experiments/E1-library-join.md) established that `content.song_id`
IS `DjmdContent.ID`, but only 1183 of 2966 `content` rows resolve (39.9%).
E1b (docs/experiments/E1b-real-denominator.md) established the real
denominator is playlist/history tracks (22.6%/30.4%), that the 1783 stale
rows are stranded real work rather than dead weight, and produced the first
taxonomy-signal numbers (genre/BPM/key coverage, Mood co-occurrence,
Situation vs energy, Situation vs BPM).

E1c re-measures everything after the DJ ran a full lighting-analysis pass on
the whole collection, and builds the **rule-authoring matrix** TRACKLIGHT
story S1.2 will be written against: full Genres/Mood My Tag catalogues,
Genres x Mood and ID3-genre x Mood co-occurrence tables, agreement between
the two genre sources, mutually-exclusive coverage buckets, Situation x
Mood, Components, and BPM-per-tag for both Mood and Situation.

Safety (see rekordbox-data-safety skill, `master.db` section):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. This
    script reuses `work/master.db` if present; refresh explicitly with
    --refresh-master-copy (this probe's task required a fresh copy, since
    the DJ had just re-analysed the library — see the report for what
    that refresh did and did not change).
  - `work/user.db3` and `work/macro.db3` are read-only for this probe.
  - This script writes nothing except the possible `work/master.db` copy
    (a plain file copy, not a database write, inherited unchanged from
    e1_library_join) and its own stdout.

This module imports shared helpers from `e1_library_join` and
`e1b_real_denominator` — both are disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward, i.e. experiments -> permanent
code, never the reverse; one probe importing a sibling probe's helpers does
not violate that).

Requires the optional `experiments` dependency group (same as E1/E1b):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1c_after_full_analysis
    python -m rbxlight.experiments.e1c_after_full_analysis --refresh-master-copy
"""

from __future__ import annotations

import argparse
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    ContentRow,
    MasterTrack,
    ensure_master_db_copy,
    load_lookup,
    load_macro_pattern_map,
    load_master_tracks,
    load_my_tags,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import (
    ENERGY_NAMES,
    load_energy_of_macro_pattern,
    load_song_my_tags_dedup,
    tag_category,
)

#: My Tag top-level category names, per E1's catalogue.
GENRES_CATEGORY = "Genres"
MOOD_CATEGORY = "Mood"
SITUATION_CATEGORY = "Situation"
COMPONENTS_CATEGORY = "Components"

#: Baseline figures from E1/E1b, quoted here only for direct comparison in
#: run_deliverable_1 / run_deliverable_2 — never used as a substitute for a
#: fresh measurement.
BASELINE_CONTENT_ROWS = 2966
BASELINE_PHRASE_DATA_ROWS = 41742
BASELINE_PHRASE_DATA_DISTINCT_CONTENT = 2905
BASELINE_LIBRARY_TRACKS = 7615
BASELINE_FORWARD_MATCHED = 1183
BASELINE_UNMATCHED_BELOW_MIN = 1183
BASELINE_UNMATCHED_WITHIN_RANGE = 600
BASELINE_UNMATCHED_ABOVE_MAX = 0
BASELINE_MPID_ZERO_ORPHANS = 61
BASELINE_PHRASE_OVERRIDES = 36
BASELINE_PHRASE_NULLS = 0
BASELINE_COOL_PCT = 63.7
BASELINE_ENERGY_HIGH_PCT = 57.6
BASELINE_ENERGY_MID_PCT = 36.4
BASELINE_ENERGY_LOW_PCT = 6.0


def _normalize_genre_name(name: str) -> str:
    """Case/punctuation-insensitive form for comparing an ID3 genre string
    against a Genres My Tag name (e.g. 'Apres-Ski' vs 'Apres Ski').
    """
    return re.sub(r"[\s\-/]+", " ", name.strip().lower()).strip()


def load_content_rows(user_db3: Path) -> list[ContentRow]:
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT id, song_id, master_db_id, macro_pattern_id "
            "FROM content ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [ContentRow(*row) for row in rows]


def load_phrase_data_counts(user_db3: Path) -> dict[int, int]:
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT content_id, COUNT(*) FROM phrase_data GROUP BY content_id"
        ).fetchall()
    finally:
        conn.close()
    return dict(rows)


def load_phrase_data_override_and_null_counts(user_db3: Path) -> tuple[int, int]:
    conn = open_readonly(user_db3)
    try:
        (overrides,) = conn.execute(
            "SELECT COUNT(*) FROM phrase_data WHERE macro_id <> initial_macro_id"
        ).fetchone()
        (nulls,) = conn.execute(
            "SELECT COUNT(*) FROM phrase_data WHERE macro_id IS NULL"
        ).fetchone()
    finally:
        conn.close()
    return overrides, nulls


def load_uuid_id_map_count(master_conn: Any) -> int:
    (count,) = master_conn.execute("SELECT COUNT(*) FROM uuidIDMap").fetchone()
    return int(count)


# ---------------------------------------------------------------------------
# Deliverable 1 — coverage at the new scale
# ---------------------------------------------------------------------------


@dataclass
class Deliverable1Result:
    content_row_count: int
    phrase_data_row_count: int
    phrase_data_distinct_content: int
    library_track_count: int
    forward_matched: int
    backward_matched: int  # library tracks that have >=1 content row
    unmatched_below_min: int
    unmatched_within_range: int
    unmatched_above_max: int
    duplicate_song_ids: int  # song_id values appearing on >1 content row
    mpid_zero_orphans: int
    rewritten_stale_ids: int  # stale song_ids from E1's sample that resolved now
    uuid_id_map_rows: int

    @property
    def forward_pct(self) -> float:
        return round(100 * self.forward_matched / self.content_row_count, 1)

    @property
    def backward_pct(self) -> float:
        return round(100 * self.backward_matched / self.library_track_count, 1)


def run_deliverable_1(
    content_rows: list[ContentRow],
    master_tracks: dict[int, MasterTrack],
    master_conn: Any,
) -> Deliverable1Result:
    song_ids = [row.song_id for row in content_rows]
    song_id_counts = Counter(song_ids)
    duplicates = sum(1 for _sid, c in song_id_counts.items() if c > 1)

    matched = [sid for sid in song_ids if sid in master_tracks]
    unmatched = [sid for sid in song_ids if sid not in master_tracks]
    min_id = min(master_tracks)
    max_id = max(master_tracks)
    below = [sid for sid in unmatched if sid < min_id]
    within = [sid for sid in unmatched if min_id <= sid <= max_id]
    above = [sid for sid in unmatched if sid > max_id]

    matched_song_ids = set(matched)
    backward_matched = sum(1 for lib_id in master_tracks if lib_id in matched_song_ids)

    mpid_zero = sum(1 for row in content_rows if row.macro_pattern_id == 0)

    # E1's 10-row spanning sample of content.id -> song_id, all of which were
    # stale (did not resolve) at E1's baseline. If any of these now resolve,
    # a stale row was rewritten by re-analysis rather than left alone.
    e1_stale_sample_song_ids = {
        1708,  # content.id=1
        19458,  # content.id=330
        86257187,  # content.id=660
        8299,  # content.id=1978
        90,  # content.id=2307
        5060,  # content.id=2637
        108,  # content.id=2966
    }
    rewritten = sum(1 for sid in e1_stale_sample_song_ids if sid in master_tracks)

    uuid_id_map_rows = load_uuid_id_map_count(master_conn)

    return Deliverable1Result(
        content_row_count=len(content_rows),
        phrase_data_row_count=0,  # filled in by caller (needs user_db3 path)
        phrase_data_distinct_content=0,
        library_track_count=len(master_tracks),
        forward_matched=len(matched),
        backward_matched=backward_matched,
        unmatched_below_min=len(below),
        unmatched_within_range=len(within),
        unmatched_above_max=len(above),
        duplicate_song_ids=duplicates,
        mpid_zero_orphans=mpid_zero,
        rewritten_stale_ids=rewritten,
        uuid_id_map_rows=uuid_id_map_rows,
    )


# ---------------------------------------------------------------------------
# Deliverable 2 — quantify the COOL default
# ---------------------------------------------------------------------------


@dataclass
class Deliverable2Result:
    bank_energy_table: dict[tuple[str, str], int]  # (bank, energy_name) -> count
    bank_totals: Counter[str]
    total: int
    id_ordering_is_weak_evidence_only: bool
    phrase_overrides: int
    phrase_nulls: int


def run_deliverable_2(
    content_rows: list[ContentRow],
    pattern_of_mpid: dict[int, int],
    energy_of_mpid: dict[int, int],
    phrase_overrides: int,
    phrase_nulls: int,
) -> Deliverable2Result:
    table: dict[tuple[str, str], int] = defaultdict(int)
    bank_totals: Counter[str] = Counter()
    for row in content_rows:
        pattern = pattern_of_mpid.get(row.macro_pattern_id)
        energy = energy_of_mpid.get(row.macro_pattern_id)
        bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "NONE"
        energy_name = ENERGY_NAMES.get(energy, "NONE") if energy else "NONE"
        table[(bank, energy_name)] += 1
        bank_totals[bank] += 1

    return Deliverable2Result(
        bank_energy_table=dict(table),
        bank_totals=bank_totals,
        total=len(content_rows),
        # content has no timestamp column (see E1); content.id ordering is
        # the only available proxy for "old vs new" and is weak evidence,
        # not proof — see the report for why this split could not be done
        # at all (content is unchanged since E1/E1b, see Deliverable 1).
        id_ordering_is_weak_evidence_only=True,
        phrase_overrides=phrase_overrides,
        phrase_nulls=phrase_nulls,
    )


# ---------------------------------------------------------------------------
# Deliverable 3 — the rule-authoring matrix
# ---------------------------------------------------------------------------


@dataclass
class TagCatalogueResult:
    """Full My Tag counts + tags-per-track distribution for one category."""

    category: str
    tag_counts: list[tuple[str, int, float]]  # (name, tracks, pct of denominator)
    tags_per_track: Counter[int]  # 0, 1, 2, 3 (3 means "3+")
    denominator: int


def _tags_of_category(
    tag_id_set: set[str], song_my_tags: dict[int, set[str]], track_id: int
) -> set[str]:
    return song_my_tags.get(track_id, set()) & tag_id_set


def run_tag_catalogue(
    category: str,
    joined_track_ids: list[int],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
) -> TagCatalogueResult:
    category_tag_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == category
    }
    tag_name = {tid: my_tags[tid]["name"] or tid for tid in category_tag_ids}

    counts: Counter[str] = Counter()
    per_track_dist: Counter[int] = Counter()
    n = len(joined_track_ids)
    for track_id in joined_track_ids:
        tags = _tags_of_category(category_tag_ids, song_my_tags, track_id)
        bucket = min(len(tags), 3)
        per_track_dist[bucket] += 1
        for tid in tags:
            counts[tag_name[tid]] += 1

    table = [
        (name, count, round(100 * count / n, 1)) for name, count in counts.most_common()
    ]
    return TagCatalogueResult(
        category=category,
        tag_counts=table,
        tags_per_track=per_track_dist,
        denominator=n,
    )


@dataclass
class CooccurrenceResult:
    """Top-N pairs of (category_a value, category_b value) by joint track
    count, e.g. Genres x Mood or ID3-genre x Mood.
    """

    label_a: str
    label_b: str
    pairs: list[tuple[str, str, int]]
    denominator: int


def run_genres_mood_pairs(
    joined_track_ids: list[int],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
    top_n: int = 40,
) -> CooccurrenceResult:
    genres_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == GENRES_CATEGORY
    }
    mood_ids = {tid for tid in my_tags if tag_category(tid, my_tags) == MOOD_CATEGORY}
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    pair_counter: Counter[tuple[str, str]] = Counter()
    for track_id in joined_track_ids:
        genres = _tags_of_category(genres_ids, song_my_tags, track_id)
        moods = _tags_of_category(mood_ids, song_my_tags, track_id)
        for g in genres:
            for m in moods:
                pair_counter[(name[g], name[m])] += 1

    pairs = [(g, m, c) for (g, m), c in pair_counter.most_common(top_n)]
    return CooccurrenceResult(
        label_a="Genres (My Tag)",
        label_b="Mood (My Tag)",
        pairs=pairs,
        denominator=len(joined_track_ids),
    )


def run_id3_genre_mood_pairs(
    joined: list[tuple[int, MasterTrack]],
    genre_names: dict[str, str],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
    top_n: int = 40,
) -> CooccurrenceResult:
    mood_ids = {tid for tid in my_tags if tag_category(tid, my_tags) == MOOD_CATEGORY}
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    pair_counter: Counter[tuple[str, str]] = Counter()
    for track_id, track in joined:
        id3_genre = genre_names.get(track.genre_id) if track.genre_id else None
        if not id3_genre:
            continue
        moods = _tags_of_category(mood_ids, song_my_tags, track_id)
        for m in moods:
            pair_counter[(id3_genre, name[m])] += 1

    pairs = [(g, m, c) for (g, m), c in pair_counter.most_common(top_n)]
    return CooccurrenceResult(
        label_a="ID3 genre",
        label_b="Mood (My Tag)",
        pairs=pairs,
        denominator=len(joined),
    )


def run_situation_mood_pairs(
    joined_track_ids: list[int],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
    top_n: int = 25,
) -> CooccurrenceResult:
    situation_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == SITUATION_CATEGORY
    }
    mood_ids = {tid for tid in my_tags if tag_category(tid, my_tags) == MOOD_CATEGORY}
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    pair_counter: Counter[tuple[str, str]] = Counter()
    for track_id in joined_track_ids:
        situations = _tags_of_category(situation_ids, song_my_tags, track_id)
        moods = _tags_of_category(mood_ids, song_my_tags, track_id)
        for s in situations:
            for m in moods:
                pair_counter[(name[s], name[m])] += 1

    pairs = [(s, m, c) for (s, m), c in pair_counter.most_common(top_n)]
    return CooccurrenceResult(
        label_a="Situation (My Tag)",
        label_b="Mood (My Tag)",
        pairs=pairs,
        denominator=len(joined_track_ids),
    )


@dataclass
class GenreAgreementResult:
    both_present: int  # tracks with ID3 genre AND >=1 Genres My Tag
    agree: int
    disagree: int
    top_disagreements: list[tuple[str, str, int]]  # (id3_genre, genres_tag, count)


def run_genre_agreement(
    joined: list[tuple[int, MasterTrack]],
    genre_names: dict[str, str],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
    top_n: int = 15,
) -> GenreAgreementResult:
    genres_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == GENRES_CATEGORY
    }
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    both = 0
    agree = 0
    disagree = 0
    disagreement_pairs: Counter[tuple[str, str]] = Counter()
    for track_id, track in joined:
        id3_genre = genre_names.get(track.genre_id) if track.genre_id else None
        genres_tags = {
            name[t] for t in _tags_of_category(genres_ids, song_my_tags, track_id)
        }
        if not id3_genre or not genres_tags:
            continue
        both += 1
        normalized_id3 = _normalize_genre_name(id3_genre)
        normalized_tags = {_normalize_genre_name(t) for t in genres_tags}
        if normalized_id3 in normalized_tags:
            agree += 1
        else:
            disagree += 1
            for t in genres_tags:
                disagreement_pairs[(id3_genre, t)] += 1

    return GenreAgreementResult(
        both_present=both,
        agree=agree,
        disagree=disagree,
        top_disagreements=[
            (a, b, c) for (a, b), c in disagreement_pairs.most_common(top_n)
        ],
    )


@dataclass
class CoverageBucketsResult:
    denominator: int
    mood_and_genres: int
    mood_only: int
    genres_only: int
    neither_but_has_id3: int
    nothing: int


def run_coverage_buckets(
    joined: list[tuple[int, MasterTrack]],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
) -> CoverageBucketsResult:
    genres_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == GENRES_CATEGORY
    }
    mood_ids = {tid for tid in my_tags if tag_category(tid, my_tags) == MOOD_CATEGORY}

    mood_and_genres = 0
    mood_only = 0
    genres_only = 0
    neither_but_id3 = 0
    nothing = 0
    for track_id, track in joined:
        has_mood = bool(_tags_of_category(mood_ids, song_my_tags, track_id))
        has_genres = bool(_tags_of_category(genres_ids, song_my_tags, track_id))
        has_id3 = bool(track.genre_id)
        if has_mood and has_genres:
            mood_and_genres += 1
        elif has_mood:
            mood_only += 1
        elif has_genres:
            genres_only += 1
        elif has_id3:
            neither_but_id3 += 1
        else:
            nothing += 1

    return CoverageBucketsResult(
        denominator=len(joined),
        mood_and_genres=mood_and_genres,
        mood_only=mood_only,
        genres_only=genres_only,
        neither_but_has_id3=neither_but_id3,
        nothing=nothing,
    )


@dataclass
class ComponentsResult:
    tag_counts: list[tuple[str, int, float]]
    denominator: int


def run_components_distribution(
    joined_track_ids: list[int],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
) -> ComponentsResult:
    result = run_tag_catalogue(
        COMPONENTS_CATEGORY, joined_track_ids, my_tags, song_my_tags
    )
    return ComponentsResult(
        tag_counts=result.tag_counts, denominator=result.denominator
    )


@dataclass
class BpmStats:
    n: int
    median: float
    q1: float | None
    q3: float | None
    bpm_min: float
    bpm_max: float


@dataclass
class BpmPerTagResult:
    category: str
    stats: dict[str, BpmStats]


def run_bpm_per_tag(
    category: str,
    joined: list[tuple[int, MasterTrack]],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
) -> BpmPerTagResult:
    category_ids = {tid for tid in my_tags if tag_category(tid, my_tags) == category}
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    bpm_by_tag: dict[str, list[float]] = defaultdict(list)
    for track_id, track in joined:
        if not track.bpm:
            continue
        for tid in _tags_of_category(category_ids, song_my_tags, track_id):
            bpm_by_tag[name[tid]].append(track.bpm / 100)

    stats: dict[str, BpmStats] = {}
    for tag_name_, vals in bpm_by_tag.items():
        q1: float | None
        q3: float | None
        if len(vals) >= 2:
            q = statistics.quantiles(vals, n=4, method="inclusive")
            q1, q3 = q[0], q[2]
        else:
            q1 = q3 = None
        stats[tag_name_] = BpmStats(
            n=len(vals),
            median=round(statistics.median(vals), 1),
            q1=round(q1, 1) if q1 is not None else None,
            q3=round(q3, 1) if q3 is not None else None,
            bpm_min=round(min(vals), 1),
            bpm_max=round(max(vals), 1),
        )
    return BpmPerTagResult(category=category, stats=stats)


@dataclass
class SituationEnergyResult:
    baseline: Counter[str]
    crosstab: dict[str, Counter[str]]


def run_situation_energy_crosstab(
    content_rows: list[ContentRow],
    master_tracks: dict[int, MasterTrack],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, set[str]],
    energy_of_mpid: dict[int, int],
) -> SituationEnergyResult:
    situation_ids = {
        tid for tid in my_tags if tag_category(tid, my_tags) == SITUATION_CATEGORY
    }
    name = {tid: info["name"] or tid for tid, info in my_tags.items()}

    baseline: Counter[str] = Counter()
    crosstab: dict[str, Counter[str]] = defaultdict(Counter)
    for row in content_rows:
        if row.song_id not in master_tracks:
            continue
        energy = ENERGY_NAMES.get(
            energy_of_mpid.get(row.macro_pattern_id, 0), "UNKNOWN"
        )
        baseline[energy] += 1
        for tid in _tags_of_category(situation_ids, song_my_tags, row.song_id):
            crosstab[name[tid]][energy] += 1

    return SituationEnergyResult(baseline=baseline, crosstab=dict(crosstab))


@dataclass
class GenreBankResult:
    crosstab: dict[str, Counter[str]]
    overall: Counter[str]
    top10_genres: list[str]


def run_genre_bank_crosstab(
    content_rows: list[ContentRow],
    master_tracks: dict[int, MasterTrack],
    genre_names: dict[str, str],
    pattern_of_mpid: dict[int, int],
) -> GenreBankResult:
    genre_counts: Counter[str] = Counter()
    for row in content_rows:
        track = master_tracks.get(row.song_id)
        if not track or not track.genre_id:
            continue
        name = genre_names.get(track.genre_id)
        if name:
            genre_counts[name] += 1
    top10 = [g for g, _c in genre_counts.most_common(10)]

    crosstab: dict[str, Counter[str]] = defaultdict(Counter)
    overall: Counter[str] = Counter()
    for row in content_rows:
        track = master_tracks.get(row.song_id)
        if not track or not track.genre_id:
            continue
        name = genre_names.get(track.genre_id)
        if name not in top10:
            continue
        pattern = pattern_of_mpid.get(row.macro_pattern_id)
        bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "NONE"
        crosstab[name][bank] += 1
        overall[bank] += 1

    return GenreBankResult(crosstab=dict(crosstab), overall=overall, top10_genres=top10)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    d1: Deliverable1Result,
    d2: Deliverable2Result,
    genres_cat: TagCatalogueResult,
    mood_cat: TagCatalogueResult,
    genres_mood: CooccurrenceResult,
    id3_mood: CooccurrenceResult,
    agreement: GenreAgreementResult,
    buckets: CoverageBucketsResult,
    situation_mood: CooccurrenceResult,
    components: ComponentsResult,
    bpm_mood: BpmPerTagResult,
    bpm_situation: BpmPerTagResult,
    situation_energy: SituationEnergyResult,
    genre_bank: GenreBankResult,
) -> None:
    """Console summary. NOT the deliverable — see
    docs/experiments/E1c-after-full-analysis.md.
    """
    print("=" * 70)
    print("Deliverable 1 — coverage at the new scale")
    print("=" * 70)
    print(f"content rows: {d1.content_row_count} (baseline {BASELINE_CONTENT_ROWS})")
    print(
        f"phrase_data rows: {d1.phrase_data_row_count} "
        f"(baseline {BASELINE_PHRASE_DATA_ROWS}), distinct content_id: "
        f"{d1.phrase_data_distinct_content} (baseline "
        f"{BASELINE_PHRASE_DATA_DISTINCT_CONTENT})"
    )
    print(
        f"library tracks (DjmdContent): {d1.library_track_count} "
        f"(baseline {BASELINE_LIBRARY_TRACKS})"
    )
    print(
        f"forward join: {d1.forward_matched}/{d1.content_row_count} "
        f"({d1.forward_pct}%) (baseline {BASELINE_FORWARD_MATCHED}/"
        f"{BASELINE_CONTENT_ROWS} = 39.9%)"
    )
    print(
        f"backward join: {d1.backward_matched}/{d1.library_track_count} "
        f"({d1.backward_pct}%) library tracks have a content row"
    )
    print(
        f"unmatched below min: {d1.unmatched_below_min} (baseline "
        f"{BASELINE_UNMATCHED_BELOW_MIN}), within range: "
        f"{d1.unmatched_within_range} (baseline {BASELINE_UNMATCHED_WITHIN_RANGE}), "
        f"above max: {d1.unmatched_above_max} (baseline {BASELINE_UNMATCHED_ABOVE_MAX})"
    )
    print(f"duplicate song_id values across content rows: {d1.duplicate_song_ids}")
    print(
        f"macro_pattern_id=0 orphans: {d1.mpid_zero_orphans} "
        f"(baseline {BASELINE_MPID_ZERO_ORPHANS})"
    )
    print(
        f"of E1's 7-id stale sample, now-resolving: {d1.rewritten_stale_ids}/7 "
        "(0 expected if nothing was rewritten)"
    )
    print(f"uuidIDMap rows (master.db): {d1.uuid_id_map_rows} (baseline 0)")

    print()
    print("=" * 70)
    print("Deliverable 2 — quantify the COOL default")
    print("=" * 70)
    print("bank totals:")
    for bank, count in d2.bank_totals.most_common():
        print(f"    {bank}: {count} ({round(100 * count / d2.total, 1)}%)")
    print(f"(baseline COOL {BASELINE_COOL_PCT}%)")
    print("bank x energy table:")
    for (bank, energy), count in sorted(
        d2.bank_energy_table.items(), key=lambda kv: (-kv[1], kv[0])
    ):
        print(f"    {bank} / {energy}: {count}")
    print(
        f"phrase overrides: {d2.phrase_overrides} (baseline {BASELINE_PHRASE_OVERRIDES}), "
        f"NULLs: {d2.phrase_nulls} (baseline {BASELINE_PHRASE_NULLS})"
    )

    print()
    print("=" * 70)
    print(f"Deliverable 3.1 — Genres My Tag catalogue (n={genres_cat.denominator})")
    print("=" * 70)
    for name, count, pct in genres_cat.tag_counts:
        print(f"    {name}: {count} ({pct}%)")
    print(f"tags-per-track: {dict(sorted(genres_cat.tags_per_track.items()))}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.2 — Mood My Tag catalogue (n={mood_cat.denominator})")
    print("=" * 70)
    for name, count, pct in mood_cat.tag_counts:
        print(f"    {name}: {count} ({pct}%)")
    print(f"tags-per-track: {dict(sorted(mood_cat.tags_per_track.items()))}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.3 — top {len(genres_mood.pairs)} Genres x Mood pairs")
    print("=" * 70)
    for g, m, c in genres_mood.pairs:
        print(f"    {g} / {m}: {c}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.4 — top {len(id3_mood.pairs)} ID3-genre x Mood pairs")
    print("=" * 70)
    for g, m, c in id3_mood.pairs:
        print(f"    {g} / {m}: {c}")

    print()
    print("=" * 70)
    print("Deliverable 3.5 — genre-source agreement")
    print("=" * 70)
    print(f"tracks with both ID3 genre and >=1 Genres My Tag: {agreement.both_present}")
    if agreement.both_present:
        print(
            f"agree: {agreement.agree} "
            f"({round(100 * agreement.agree / agreement.both_present, 1)}%)  "
            f"disagree: {agreement.disagree} "
            f"({round(100 * agreement.disagree / agreement.both_present, 1)}%)"
        )
    print("top disagreement pairs:")
    for a, b, c in agreement.top_disagreements:
        print(f"    {a} / {b}: {c}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.6 — coverage buckets (n={buckets.denominator})")
    print("=" * 70)
    print(f"    Mood + Genres: {buckets.mood_and_genres}")
    print(f"    Mood only: {buckets.mood_only}")
    print(f"    Genres only: {buckets.genres_only}")
    print(f"    neither, but has ID3 genre: {buckets.neither_but_has_id3}")
    print(f"    nothing: {buckets.nothing}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.7 — top {len(situation_mood.pairs)} Situation x Mood pairs")
    print("=" * 70)
    for s, m, c in situation_mood.pairs:
        print(f"    {s} / {m}: {c}")

    print()
    print("=" * 70)
    print(f"Deliverable 3.8 — Components distribution (n={components.denominator})")
    print("=" * 70)
    for name, count, pct in components.tag_counts:
        print(f"    {name}: {count} ({pct}%)")

    print()
    print("=" * 70)
    print("Deliverable 3.9 — BPM per Mood tag")
    print("=" * 70)
    for name, stats in sorted(bpm_mood.stats.items(), key=lambda kv: -kv[1].n):
        iqr = f"[{stats.q1},{stats.q3}]" if stats.q1 is not None else "(n<2)"
        print(f"    {name}: n={stats.n} median={stats.median} IQR={iqr}")

    print()
    print("=" * 70)
    print("Deliverable 3.9 — BPM per Situation tag")
    print("=" * 70)
    for name, stats in sorted(bpm_situation.stats.items(), key=lambda kv: -kv[1].n):
        iqr = f"[{stats.q1},{stats.q3}]" if stats.q1 is not None else "(n<2)"
        print(f"    {name}: n={stats.n} median={stats.median} IQR={iqr}")

    print()
    print("=" * 70)
    print("Deliverable 3.10 — refresh: Situation x energy")
    print("=" * 70)
    total_baseline = sum(situation_energy.baseline.values())
    print(
        "baseline energy distribution: "
        + ", ".join(
            f"{k}={v} ({round(100 * v / total_baseline, 1)}%)"
            for k, v in situation_energy.baseline.most_common()
        )
    )
    for situation, counter in sorted(
        situation_energy.crosstab.items(), key=lambda kv: -sum(kv[1].values())
    ):
        total = sum(counter.values())
        parts = ", ".join(
            f"{k}={counter.get(k, 0)} ({round(100 * counter.get(k, 0) / total, 1)}%)"
            for k in ("HIGH", "MID", "LOW")
        )
        print(f"    {situation} (n={total}): {parts}")

    print()
    print("=" * 70)
    print("Deliverable 3.10 — refresh: top-genre x bank")
    print("=" * 70)
    for genre in genre_bank.top10_genres:
        print(f"    {genre}: {dict(genre_bank.crosstab.get(genre, {}))}")
    total_gb = sum(genre_bank.overall.values())
    print(
        "overall: "
        + ", ".join(
            f"{k}={v} ({round(100 * v / total_gb, 1)}%)"
            for k, v in genre_bank.overall.most_common()
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-master-copy",
        action="store_true",
        help="Re-copy work/master.db from live even if a copy already exists.",
    )
    args = parser.parse_args()

    master_path = ensure_master_db_copy(refresh=args.refresh_master_copy)
    master_conn = open_master_db(master_path)
    try:
        master_tracks = load_master_tracks(master_conn)
        genre_names = load_lookup(master_conn, "djmdGenre", "Name")
        my_tags = load_my_tags(master_conn)
        song_my_tags = load_song_my_tags_dedup(master_conn)

        content_rows = load_content_rows(Path("work/user.db3"))
        phrase_counts = load_phrase_data_counts(Path("work/user.db3"))
        phrase_overrides, phrase_nulls = load_phrase_data_override_and_null_counts(
            Path("work/user.db3")
        )
        pattern_of_mpid = load_macro_pattern_map(Path("work/macro.db3"))
        energy_of_mpid = load_energy_of_macro_pattern(Path("work/macro.db3"))

        joined_rows = [row for row in content_rows if row.song_id in master_tracks]
        joined_track_ids = [row.song_id for row in joined_rows]
        joined_pairs = [
            (row.song_id, master_tracks[row.song_id]) for row in joined_rows
        ]

        d1 = run_deliverable_1(content_rows, master_tracks, master_conn)
        d1.phrase_data_row_count = sum(phrase_counts.values())
        d1.phrase_data_distinct_content = len(phrase_counts)

        d2 = run_deliverable_2(
            content_rows,
            pattern_of_mpid,
            energy_of_mpid,
            phrase_overrides,
            phrase_nulls,
        )

        genres_cat = run_tag_catalogue(
            GENRES_CATEGORY, joined_track_ids, my_tags, song_my_tags
        )
        mood_cat = run_tag_catalogue(
            MOOD_CATEGORY, joined_track_ids, my_tags, song_my_tags
        )
        genres_mood = run_genres_mood_pairs(joined_track_ids, my_tags, song_my_tags)
        id3_mood = run_id3_genre_mood_pairs(
            joined_pairs, genre_names, my_tags, song_my_tags
        )
        agreement = run_genre_agreement(
            joined_pairs, genre_names, my_tags, song_my_tags
        )
        buckets = run_coverage_buckets(joined_pairs, my_tags, song_my_tags)
        situation_mood = run_situation_mood_pairs(
            joined_track_ids, my_tags, song_my_tags
        )
        components = run_components_distribution(
            joined_track_ids, my_tags, song_my_tags
        )
        bpm_mood = run_bpm_per_tag(MOOD_CATEGORY, joined_pairs, my_tags, song_my_tags)
        bpm_situation = run_bpm_per_tag(
            SITUATION_CATEGORY, joined_pairs, my_tags, song_my_tags
        )
        situation_energy = run_situation_energy_crosstab(
            content_rows, master_tracks, my_tags, song_my_tags, energy_of_mpid
        )
        genre_bank = run_genre_bank_crosstab(
            content_rows, master_tracks, genre_names, pattern_of_mpid
        )

        print_report(
            d1,
            d2,
            genres_cat,
            mood_cat,
            genres_mood,
            id3_mood,
            agreement,
            buckets,
            situation_mood,
            components,
            bpm_mood,
            bpm_situation,
            situation_energy,
            genre_bank,
        )
    finally:
        master_conn.close()


if __name__ == "__main__":
    main()
