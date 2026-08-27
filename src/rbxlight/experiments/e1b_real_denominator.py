"""E1b — "the real denominator". Disposable, READ-ONLY probe, extends E1.

See docs/experiments/E1b-real-denominator.md for the written verdict this
script exists to produce — that file, not this one, is the deliverable.

E1 (docs/experiments/E1-library-join.md) established that `content.song_id`
IS `DjmdContent.ID`, but only 1183 of 2966 `content` rows resolve to a live
track (39.9%), and 6432 of 7615 library tracks have no `content` row at all.
E1b tests one hypothesis before any feature gets designed on top of that
39.9%: **are the 1783 non-resolving `content` rows dead weight from a past
library migration, with the 1183 resolving rows being "the tracks that
matter"?** If true, coverage over the tracks the DJ actually organises/plays
is far better than 39.9%. If false, the design needs an honest fallback path
and possibly a re-analysis campaign, not just a join filter.

Seven questions, answered in order of importance (see report for full
evidence): the real denominator (playlist/history join rate), whether the
stale rows show any sign of being dead, a coverage forecast, taxonomy signal
coverage over the right denominator, My Tag co-occurrence within `Mood`,
Situation-tag vs rekordbox energy, and BPM vs Situation.

Safety (see rekordbox-data-safety skill, `master.db` section):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. This
    script reuses `work/master.db` (E1's copy) if present; only copies
    fresh if missing, guarded by rekordbox-not-running (same as E1).
  - `work/user.db3` and `work/macro.db3` are read-only for this probe.
  - This script writes nothing except the possible one-time `work/master.db`
    copy (a plain file copy, not a database write, inherited unchanged from
    e1_library_join) and its own stdout.

This module imports shared helpers from `e1_library_join` — both modules
are disposable probes in the same `experiments/` package (see
rekordbox-lighting-architecture skill: the dependency arrow only ever
points inward, i.e. experiments -> permanent code, never the reverse;
one probe importing a sibling probe's helpers does not violate that).

Requires the optional `experiments` dependency group (same as E1):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1b_real_denominator
"""

from __future__ import annotations

import argparse
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    ensure_master_db_copy,
    load_master_tracks,
    load_my_tags,
    open_master_db,
    open_readonly,
)

ENERGY_NAMES: dict[int, str] = {1: "HIGH", 2: "MID", 3: "LOW"}

MOOD_CATEGORY = "Mood"
SITUATION_CATEGORY = "Situation"


def load_playlist_content_ids(master_conn: Any) -> set[int]:
    """Distinct `DjmdContent.ID` referenced by any real (non-smart,
    non-folder) playlist. `djmdSongPlaylist` only ever contains rows for
    `Attribute=0` playlists in this library — smart playlists (Attribute=4)
    compute membership dynamically and have no materialized song rows,
    folders (Attribute=1) hold no songs directly — so no extra filtering
    on `djmdPlaylist.Attribute` is needed; verified empirically, not
    assumed.
    """
    rows = master_conn.execute(
        "SELECT DISTINCT ContentID FROM djmdSongPlaylist"
    ).fetchall()
    return {int(r[0]) for r in rows}


def load_history_content_ids(master_conn: Any) -> set[int]:
    """Distinct `DjmdContent.ID` referenced by any play-history session."""
    rows = master_conn.execute(
        "SELECT DISTINCT ContentID FROM djmdSongHistory"
    ).fetchall()
    return {int(r[0]) for r in rows}


def load_song_my_tags_dedup(master_conn: Any) -> dict[int, set[str]]:
    """content_id (int) -> set of MyTagID. `djmdSongMyTag` has 84 exact
    (ContentID, MyTagID) duplicate rows in this library (a data quirk, not
    a track-identifying fact) — using a set rather than a list, as E1's
    `load_song_my_tags` does, avoids inflating tag-count-per-track and
    co-occurrence-pair statistics.
    """
    rows = master_conn.execute(
        "SELECT ContentID, MyTagID FROM djmdSongMyTag"
    ).fetchall()
    result: dict[int, set[str]] = defaultdict(set)
    for content_id, mytag_id in rows:
        result[int(content_id)].add(mytag_id)
    return result


def tag_category(tag_id: str, my_tags: dict[str, dict[str, str | None]]) -> str | None:
    """Resolve a My Tag id to its parent category name (Mood/Situation/
    Genres/Components), or None if it has no parent (i.e. it IS a category
    row) or the parent can't be resolved.
    """
    info = my_tags.get(tag_id)
    if not info or not info.get("parent_id"):
        return None
    parent = my_tags.get(info["parent_id"] or "")
    return parent["name"] if parent else None


def load_energy_of_macro_pattern(macro_db3: Path) -> dict[int, int]:
    """macro_pattern.id -> energy (1=HIGH, 2=MID, 3=LOW)."""
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute("SELECT id, energy FROM macro_pattern").fetchall()
    finally:
        conn.close()
    return dict(rows)


@dataclass
class Q1RealDenominator:
    """Q1 — the real denominator: playlist/history join rates."""

    playlist_track_count: int
    playlist_joined: int
    history_track_count: int
    history_joined: int
    union_track_count: int
    union_joined: int
    total_joined: int
    joined_in_playlist_or_history: int
    joined_in_neither: int


def run_q1(
    playlist_ids: set[int],
    history_ids: set[int],
    content_song_ids: set[int],
    joined_song_ids: set[int],
) -> Q1RealDenominator:
    union_ids = playlist_ids | history_ids
    return Q1RealDenominator(
        playlist_track_count=len(playlist_ids),
        playlist_joined=len(playlist_ids & content_song_ids),
        history_track_count=len(history_ids),
        history_joined=len(history_ids & content_song_ids),
        union_track_count=len(union_ids),
        union_joined=len(union_ids & content_song_ids),
        total_joined=len(joined_song_ids),
        joined_in_playlist_or_history=len(joined_song_ids & union_ids),
        joined_in_neither=len(joined_song_ids - union_ids),
    )


@dataclass
class IdBand:
    lo: int
    hi: int
    n: int
    matched: int

    @property
    def pct(self) -> float:
        return round(100 * self.matched / self.n, 1) if self.n else 0.0


@dataclass
class Q2DeadWeight:
    """Q2 — is the stale set dead weight, or stranded real work?"""

    stale_count: int
    stale_with_phrase_data: int
    stale_phrase_data_total_rows: int
    joined_with_phrase_data: int
    joined_phrase_data_total_rows: int
    stale_mpid_zero: int
    stale_real_pattern: int
    stale_bank_distribution: Counter[str]
    joined_bank_distribution: Counter[str]
    id_bands: list[IdBand]


def run_q2(
    content_rows: list[tuple[int, int, int]],
    master_ids: set[int],
    phrase_data_counts: dict[int, int],
    pattern_of_mpid: dict[int, int],
    pattern_names: dict[int, str],
    n_bands: int = 10,
) -> Q2DeadWeight:
    stale = [row for row in content_rows if row[1] not in master_ids]
    joined = [row for row in content_rows if row[1] in master_ids]

    stale_ids = {cid for cid, _sid, _mpid in stale}
    joined_ids = {cid for cid, _sid, _mpid in joined}
    stale_with_phrase = sum(1 for cid in stale_ids if phrase_data_counts.get(cid, 0))
    joined_with_phrase = sum(1 for cid in joined_ids if phrase_data_counts.get(cid, 0))
    stale_phrase_total = sum(phrase_data_counts.get(cid, 0) for cid in stale_ids)
    joined_phrase_total = sum(phrase_data_counts.get(cid, 0) for cid in joined_ids)

    stale_mpid_zero = sum(1 for _cid, _sid, mpid in stale if mpid == 0)

    def bank_dist(rows: list[tuple[int, int, int]]) -> Counter[str]:
        c: Counter[str] = Counter()
        for _cid, _sid, mpid in rows:
            if mpid == 0:
                continue
            pattern = pattern_of_mpid.get(mpid)
            name = (
                pattern_names.get(pattern, f"pattern{pattern}")
                if pattern
                else "UNKNOWN"
            )
            c[name] += 1
        return c

    n = len(content_rows)
    binsize = n // n_bands
    bands: list[IdBand] = []
    for b in range(n_bands):
        lo = b * binsize
        hi = (b + 1) * binsize if b < n_bands - 1 else n
        chunk = content_rows[lo:hi]
        matched = sum(1 for _cid, sid, _mpid in chunk if sid in master_ids)
        bands.append(
            IdBand(lo=chunk[0][0], hi=chunk[-1][0], n=len(chunk), matched=matched)
        )

    return Q2DeadWeight(
        stale_count=len(stale),
        stale_with_phrase_data=stale_with_phrase,
        stale_phrase_data_total_rows=stale_phrase_total,
        joined_with_phrase_data=joined_with_phrase,
        joined_phrase_data_total_rows=joined_phrase_total,
        stale_mpid_zero=stale_mpid_zero,
        stale_real_pattern=len(stale) - stale_mpid_zero,
        stale_bank_distribution=bank_dist(stale),
        joined_bank_distribution=bank_dist(joined),
        id_bands=bands,
    )


@dataclass
class Q3CoverageForecast:
    """Q3 — arithmetic forecast: analyse every playlist track."""

    current_total_content_rows: int
    current_total_joined: int
    playlist_track_count: int
    playlist_already_joined: int
    playlist_needing_analysis: int
    projected_total_content_rows: int
    projected_total_joined: int

    @property
    def current_overall_pct(self) -> float:
        return round(
            100 * self.current_total_joined / self.current_total_content_rows, 1
        )

    @property
    def projected_overall_pct(self) -> float:
        return round(
            100 * self.projected_total_joined / self.projected_total_content_rows, 1
        )

    @property
    def current_playlist_pct(self) -> float:
        return round(100 * self.playlist_already_joined / self.playlist_track_count, 1)


def run_q3(
    total_content_rows: int,
    total_joined: int,
    playlist_track_count: int,
    playlist_joined: int,
) -> Q3CoverageForecast:
    needing = playlist_track_count - playlist_joined
    return Q3CoverageForecast(
        current_total_content_rows=total_content_rows,
        current_total_joined=total_joined,
        playlist_track_count=playlist_track_count,
        playlist_already_joined=playlist_joined,
        playlist_needing_analysis=needing,
        projected_total_content_rows=total_content_rows + needing,
        projected_total_joined=total_joined + needing,
    )


@dataclass
class Q4SignalCoverage:
    """Q4 — genre/My Tag/BPM/key coverage over playlist tracks (the real
    target set), whether or not they currently have a `content` row.
    """

    n: int
    genre_pct: float
    bpm_pct: float
    key_pct: float
    any_my_tag_pct: float
    mood_tag_pct: float
    situation_tag_pct: float


def run_q4(
    playlist_ids: set[int],
    master_tracks: dict[int, Any],
    song_my_tags: dict[int, set[str]],
    my_tags: dict[str, dict[str, str | None]],
) -> Q4SignalCoverage:
    n = len(playlist_ids)
    genre_pop = sum(1 for cid in playlist_ids if master_tracks[cid].genre_id)
    bpm_pop = sum(1 for cid in playlist_ids if master_tracks[cid].bpm)
    key_pop = sum(1 for cid in playlist_ids if master_tracks[cid].key_id)

    any_tag = 0
    mood = 0
    situation = 0
    for cid in playlist_ids:
        tags = song_my_tags.get(cid, set())
        if tags:
            any_tag += 1
        cats = {tag_category(t, my_tags) for t in tags}
        if MOOD_CATEGORY in cats:
            mood += 1
        if SITUATION_CATEGORY in cats:
            situation += 1

    return Q4SignalCoverage(
        n=n,
        genre_pct=round(100 * genre_pop / n, 1),
        bpm_pct=round(100 * bpm_pop / n, 1),
        key_pct=round(100 * key_pop / n, 1),
        any_my_tag_pct=round(100 * any_tag / n, 1),
        mood_tag_pct=round(100 * mood / n, 1),
        situation_tag_pct=round(100 * situation / n, 1),
    )


@dataclass
class Q5MoodCooccurrence:
    """Q5 — My Tag co-occurrence within Mood, measured library-wide (all
    tracks carrying >=1 Mood tag) since this is a taxonomy-consistency
    question, not a join-coverage question.
    """

    tracks_with_mood_tag: int
    tag_count_distribution: Counter[int]
    top_pairs: list[tuple[tuple[str, str], int]]


def run_q5(
    song_my_tags: dict[int, set[str]], my_tags: dict[str, dict[str, str | None]]
) -> Q5MoodCooccurrence:
    mood_tag_name: dict[str, str] = {
        tid: info["name"] or tid
        for tid, info in my_tags.items()
        if tag_category(tid, my_tags) == MOOD_CATEGORY
    }

    per_track_counts: list[int] = []
    pair_counter: Counter[tuple[str, str]] = Counter()
    tracks_with_mood = 0
    for tags in song_my_tags.values():
        mood_tags = [t for t in tags if t in mood_tag_name]
        if not mood_tags:
            continue
        tracks_with_mood += 1
        per_track_counts.append(len(mood_tags))
        names = sorted(mood_tag_name[t] for t in mood_tags)
        for a, b in combinations(names, 2):
            pair_counter[(a, b)] += 1

    return Q5MoodCooccurrence(
        tracks_with_mood_tag=tracks_with_mood,
        tag_count_distribution=Counter(per_track_counts),
        top_pairs=pair_counter.most_common(15),
    )


@dataclass
class Q6SituationEnergy:
    """Q6 — Situation tag vs rekordbox's current energy verdict, for
    joined tracks only (energy comes from `content.macro_pattern_id`,
    which only exists/resolves for joined rows).
    """

    baseline_energy_distribution: Counter[str]
    situation_energy_crosstab: dict[str, Counter[str]]


def run_q6(
    joined_rows: list[tuple[int, int, int]],
    song_my_tags: dict[int, set[str]],
    my_tags: dict[str, dict[str, str | None]],
    energy_of_mpid: dict[int, int],
) -> Q6SituationEnergy:
    situation_tag_name: dict[str, str] = {
        tid: info["name"] or tid
        for tid, info in my_tags.items()
        if tag_category(tid, my_tags) == SITUATION_CATEGORY
    }

    baseline: Counter[str] = Counter()
    crosstab: dict[str, Counter[str]] = defaultdict(Counter)
    for _cid, sid, mpid in joined_rows:
        energy = ENERGY_NAMES.get(energy_of_mpid.get(mpid, 0), "UNKNOWN")
        baseline[energy] += 1
        tags = song_my_tags.get(sid, set())
        for st in {situation_tag_name[t] for t in tags if t in situation_tag_name}:
            crosstab[st][energy] += 1

    return Q6SituationEnergy(
        baseline_energy_distribution=baseline,
        situation_energy_crosstab=dict(crosstab),
    )


@dataclass
class SituationBpmStats:
    n: int
    median: float
    q1: float | None
    q3: float | None
    bpm_min: float
    bpm_max: float


@dataclass
class Q7SituationBpm:
    """Q7 — BPM distribution per Situation tag, same joined-tracks set
    as Q6.
    """

    stats: dict[str, SituationBpmStats]


def run_q7(
    joined_rows: list[tuple[int, int, int]],
    master_tracks: dict[int, Any],
    song_my_tags: dict[int, set[str]],
    my_tags: dict[str, dict[str, str | None]],
) -> Q7SituationBpm:
    situation_tag_name: dict[str, str] = {
        tid: info["name"] or tid
        for tid, info in my_tags.items()
        if tag_category(tid, my_tags) == SITUATION_CATEGORY
    }

    bpm_by_situation: dict[str, list[float]] = defaultdict(list)
    for _cid, sid, _mpid in joined_rows:
        bpm = master_tracks[sid].bpm
        if not bpm:
            continue
        tags = song_my_tags.get(sid, set())
        for st in {situation_tag_name[t] for t in tags if t in situation_tag_name}:
            bpm_by_situation[st].append(bpm / 100)

    stats: dict[str, SituationBpmStats] = {}
    for st, vals in bpm_by_situation.items():
        q1: float | None
        q3: float | None
        if len(vals) >= 2:
            q = statistics.quantiles(vals, n=4, method="inclusive")
            q1, q3 = q[0], q[2]
        else:
            q1 = q3 = None
        stats[st] = SituationBpmStats(
            n=len(vals),
            median=round(statistics.median(vals), 1),
            q1=round(q1, 1) if q1 is not None else None,
            q3=round(q3, 1) if q3 is not None else None,
            bpm_min=round(min(vals), 1),
            bpm_max=round(max(vals), 1),
        )
    return Q7SituationBpm(stats=stats)


def print_report(
    q1: Q1RealDenominator,
    q2: Q2DeadWeight,
    q3: Q3CoverageForecast,
    q4: Q4SignalCoverage,
    q5: Q5MoodCooccurrence,
    q6: Q6SituationEnergy,
    q7: Q7SituationBpm,
) -> None:
    """Console summary. NOT the deliverable — see
    docs/experiments/E1b-real-denominator.md.
    """
    print("=" * 70)
    print("Q1 — the real denominator")
    print("=" * 70)
    print(
        f"playlist tracks: {q1.playlist_joined}/{q1.playlist_track_count} joined "
        f"({round(100 * q1.playlist_joined / q1.playlist_track_count, 1)}%), "
        f"{q1.playlist_track_count - q1.playlist_joined} no content row"
    )
    print(
        f"history tracks:  {q1.history_joined}/{q1.history_track_count} joined "
        f"({round(100 * q1.history_joined / q1.history_track_count, 1)}%), "
        f"{q1.history_track_count - q1.history_joined} no content row"
    )
    print(
        f"union (playlist or history): {q1.union_joined}/{q1.union_track_count} joined "
        f"({round(100 * q1.union_joined / q1.union_track_count, 1)}%)"
    )
    print(
        f"of the {q1.total_joined} currently-joining content rows: "
        f"{q1.joined_in_playlist_or_history} are playlist/history tracks, "
        f"{q1.joined_in_neither} are neither"
    )

    print()
    print("=" * 70)
    print("Q2 — is the stale set dead weight?")
    print("=" * 70)
    print(
        f"stale rows: {q2.stale_count}  with phrase_data: {q2.stale_with_phrase_data} "
        f"({round(100 * q2.stale_with_phrase_data / q2.stale_count, 1)}%)  "
        f"total phrase_data rows: {q2.stale_phrase_data_total_rows} "
        f"(avg {round(q2.stale_phrase_data_total_rows / q2.stale_count, 2)}/row)"
    )
    print(
        f"joined rows: with phrase_data: {q2.joined_with_phrase_data}  "
        f"total phrase_data rows: {q2.joined_phrase_data_total_rows} "
        f"(avg {round(q2.joined_phrase_data_total_rows / q2.joined_with_phrase_data, 2)}/row)"
    )
    print(
        f"stale rows with macro_pattern_id=0 (true orphans): {q2.stale_mpid_zero}/{q2.stale_count}  "
        f"with a real pattern: {q2.stale_real_pattern}"
    )
    print(
        f"stale bank distribution (excl mpid=0): {dict(q2.stale_bank_distribution.most_common())}"
    )
    print(
        f"joined bank distribution: {dict(q2.joined_bank_distribution.most_common())}"
    )
    print("id bands (match rate by content.id range):")
    for band in q2.id_bands:
        print(
            f"    {band.lo}..{band.hi}  n={band.n}  matched={band.matched} ({band.pct}%)"
        )

    print()
    print("=" * 70)
    print("Q3 — coverage forecast (analyse every playlist track)")
    print("=" * 70)
    print(
        f"today: {q3.current_total_joined}/{q3.current_total_content_rows} "
        f"({q3.current_overall_pct}%) overall, "
        f"{q3.playlist_already_joined}/{q3.playlist_track_count} "
        f"({q3.current_playlist_pct}%) of playlist tracks"
    )
    print(
        f"analysing the {q3.playlist_needing_analysis} never-lit playlist tracks -> "
        f"{q3.projected_total_joined}/{q3.projected_total_content_rows} "
        f"({q3.projected_overall_pct}%) overall, 100% of playlist tracks"
    )

    print()
    print("=" * 70)
    print(f"Q4 — signal coverage over playlist tracks (n={q4.n})")
    print("=" * 70)
    print(f"genre populated: {q4.genre_pct}%")
    print(f"BPM populated: {q4.bpm_pct}%")
    print(f"key populated: {q4.key_pct}%")
    print(f"any My Tag: {q4.any_my_tag_pct}%")
    print(f"Mood tag: {q4.mood_tag_pct}%")
    print(f"Situation tag: {q4.situation_tag_pct}%")

    print()
    print("=" * 70)
    print(f"Q5 — Mood co-occurrence (library-wide, n={q5.tracks_with_mood_tag})")
    print("=" * 70)
    for k in sorted(q5.tag_count_distribution):
        count = q5.tag_count_distribution[k]
        print(
            f"    {k} tag(s): {count} tracks "
            f"({round(100 * count / q5.tracks_with_mood_tag, 1)}%)"
        )
    print("top 15 co-occurring Mood pairs:")
    for pair, count in q5.top_pairs:
        print(f"    {pair}: {count}")

    print()
    print("=" * 70)
    print("Q6 — Situation tag vs current energy (joined tracks)")
    print("=" * 70)
    total_baseline = sum(q6.baseline_energy_distribution.values())
    print(
        "baseline energy distribution (all joined tracks): "
        + ", ".join(
            f"{k}={v} ({round(100 * v / total_baseline, 1)}%)"
            for k, v in q6.baseline_energy_distribution.most_common()
        )
    )
    for situation, counter in sorted(
        q6.situation_energy_crosstab.items(), key=lambda kv: -sum(kv[1].values())
    ):
        total = sum(counter.values())
        parts = ", ".join(
            f"{k}={counter.get(k, 0)} ({round(100 * counter.get(k, 0) / total, 1)}%)"
            for k in ("HIGH", "MID", "LOW")
        )
        print(f"    {situation} (n={total}): {parts}")

    print()
    print("=" * 70)
    print("Q7 — BPM per Situation tag (joined tracks)")
    print("=" * 70)
    for st, s in sorted(q7.stats.items(), key=lambda kv: -kv[1].n):
        iqr = f"[{s.q1},{s.q3}]" if s.q1 is not None else "(n<2)"
        print(
            f"    {st}: n={s.n} median={s.median} IQR={iqr} "
            f"min={s.bpm_min} max={s.bpm_max}"
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
        master_ids = set(master_tracks)
        my_tags = load_my_tags(master_conn)
        song_my_tags = load_song_my_tags_dedup(master_conn)
        playlist_ids = load_playlist_content_ids(master_conn)
        history_ids = load_history_content_ids(master_conn)
        energy_of_mpid = load_energy_of_macro_pattern(Path("work/macro.db3"))

        macro_conn = open_readonly(Path("work/macro.db3"))
        try:
            pattern_of_mpid = dict(
                macro_conn.execute("SELECT id, pattern FROM macro_pattern").fetchall()
            )
        finally:
            macro_conn.close()

        user_conn = open_readonly(Path("work/user.db3"))
        try:
            content_rows = user_conn.execute(
                "SELECT id, song_id, macro_pattern_id FROM content ORDER BY id"
            ).fetchall()
            phrase_data_counts = dict(
                user_conn.execute(
                    "SELECT content_id, COUNT(*) FROM phrase_data GROUP BY content_id"
                ).fetchall()
            )
        finally:
            user_conn.close()

        content_song_ids = {sid for _cid, sid, _mpid in content_rows}
        joined_rows = [row for row in content_rows if row[1] in master_ids]
        joined_song_ids = {sid for _cid, sid, _mpid in joined_rows}

        q1 = run_q1(playlist_ids, history_ids, content_song_ids, joined_song_ids)
        q2 = run_q2(
            content_rows, master_ids, phrase_data_counts, pattern_of_mpid, PATTERN_NAMES
        )
        q3 = run_q3(
            total_content_rows=len(content_rows),
            total_joined=len(joined_rows),
            playlist_track_count=len(playlist_ids),
            playlist_joined=q1.playlist_joined,
        )
        q4 = run_q4(playlist_ids, master_tracks, song_my_tags, my_tags)
        q5 = run_q5(song_my_tags, my_tags)
        q6 = run_q6(joined_rows, song_my_tags, my_tags, energy_of_mpid)
        q7 = run_q7(joined_rows, master_tracks, song_my_tags, my_tags)

        print_report(q1, q2, q3, q4, q5, q6, q7)
    finally:
        master_conn.close()


if __name__ == "__main__":
    main()
