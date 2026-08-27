"""E1 — "the library join". Disposable, READ-ONLY reverse-engineering probe.

Answers two questions (see docs/experiments/E1-library-join.md for the
written verdict this script exists to produce — that file, not this one,
is the deliverable):

  Q1 (the join): does `work/user.db3.content.song_id` correspond to
     `DjmdContent.ID` in rekordbox's main library (`master.db`)? If not,
     what does it correspond to?
  Q2 (metadata viability): for the tracks that DO join, is genre/colour/My
     Tag/comment/rating/BPM/key metadata populated well enough to drive a
     per-track lighting heuristic?

Safety (amended 2026-08-25 — see rekordbox-data-safety skill):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. This
    script never opens it read-write, not even transiently. It guards
    rekordbox-not-running, then copies the file to `work/master.db` (skip
    if already present) and reads ONLY the copy from then on.
  - `work/user.db3` and `work/macro.db3` are read-only for this probe.
  - This script writes nothing except the one-time `work/master.db` copy
    (a plain file copy, not a database write) and its own stdout.

Nothing in `rbxlight/experiments/` is imported by permanent code — see
rekordbox-lighting-architecture skill, "experiments/ — disposable by
contract". This package/script is deleted once E1's verdict is recorded;
see the report for exactly what to remove.

Requires the optional `experiments` dependency group:
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1_library_join
    python -m rbxlight.experiments.e1_library_join --refresh-master-copy
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rbxlight import safety

try:
    from sqlcipher3 import dbapi2 as sqlcipher  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    print(
        "Missing the 'experiments' optional dependency group.\n"
        'Install with: pip install -e ".[experiments]"',
        file=sys.stderr,
    )
    raise

from pyrekordbox.db6.database import BLOB  # type: ignore[import-untyped]
from pyrekordbox.utils import deobfuscate  # type: ignore[import-untyped]

#: Live, factory-installed rekordbox main library. READ-ONLY, FOREVER — see
#: rekordbox-data-safety skill. Never opened read-write by this script.
LIVE_MASTER_DB = Path.home() / "Library/Pioneer/rekordbox/master.db"

#: Working-copy destination. Gitignored (see .gitignore's `work/` entry).
WORK_MASTER_DB = Path("work/master.db")

#: rekordbox 6/7's static, historically-published SQLCipher key blob. Not a
#: secret this project owns — it ships inside pyrekordbox itself and is
#: re-exported here only to keep the decrypt call sqlite3-shaped. No
#: network access is used to obtain it (contrast with `download-key`,
#: needed only when this static key is stale for the installed rekordbox
#: version — it was not stale for the library this probe ran against).
_MASTER_DB_KEY = deobfuscate(BLOB)

PATTERN_NAMES: dict[int, str] = {
    1: "COOL",
    2: "NATURAL",
    3: "HOT",
    4: "SUBTLE",
    5: "WARM",
    6: "VIVID",
    7: "CLUB1",
    8: "CLUB2",
    99: "INTERLUDE",
}


def ensure_master_db_copy(*, refresh: bool = False) -> Path:
    """Copy the live master.db to work/master.db if not already present.

    Guards rekordbox-not-running first (safety.guard_rekordbox_not_running)
    — the same guard used for every other write in this project. This is a
    plain file copy, never a database write, and the source is opened only
    for `shutil.copy2`'s own read, never read-write.
    """
    if WORK_MASTER_DB.exists() and not refresh:
        return WORK_MASTER_DB
    safety.guard_rekordbox_not_running()
    if not LIVE_MASTER_DB.exists():
        raise FileNotFoundError(f"Live master.db not found at {LIVE_MASTER_DB}")
    WORK_MASTER_DB.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LIVE_MASTER_DB, WORK_MASTER_DB)
    return WORK_MASTER_DB


def open_master_db(path: Path) -> Any:
    """Open the master.db COPY read-only and unlock it with the SQLCipher
    key. Structurally read-only (file: URI, mode=ro) — the same discipline
    the safety skill requires for the plaintext LightingDB files.
    """
    conn = sqlcipher.connect(f"file:{path}?mode=ro", uri=True)
    conn.execute(f"PRAGMA key='{_MASTER_DB_KEY}'")
    conn.execute("PRAGMA cipher_compatibility = 4")
    return conn


def open_readonly(path: Path) -> sqlite3.Connection:
    """Open a plain (unencrypted) SQLite file read-only via the URI form."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@dataclass(frozen=True)
class ContentRow:
    """One row of user.db3.content."""

    id: int
    song_id: int
    master_db_id: int
    macro_pattern_id: int


@dataclass(frozen=True)
class MasterTrack:
    """The subset of DjmdContent columns this probe needs."""

    id: int
    title: str | None
    artist_id: str | None
    genre_id: str | None
    bpm: int | None
    comment: str | None
    rating: int | None
    key_id: str | None
    color_id: str | None


def load_content_rows(user_db3: Path) -> list[ContentRow]:
    """All rows of user.db3.content, ordered by id."""
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT id, song_id, master_db_id, macro_pattern_id "
            "FROM content ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return [ContentRow(*row) for row in rows]


def load_master_tracks(master_conn: Any) -> dict[int, MasterTrack]:
    """All DjmdContent rows, keyed by int(ID). ID is stored as VARCHAR in
    master.db (a rekordbox schema quirk, not a formatting error here).
    """
    cols = (
        "ID",
        "Title",
        "ArtistID",
        "GenreID",
        "BPM",
        "Commnt",
        "Rating",
        "KeyID",
        "ColorID",
    )
    rows = master_conn.execute(f"SELECT {','.join(cols)} FROM djmdContent").fetchall()
    return {
        int(row[0]): MasterTrack(
            id=int(row[0]),
            title=row[1],
            artist_id=row[2],
            genre_id=row[3],
            bpm=row[4],
            comment=row[5],
            rating=row[6],
            key_id=row[7],
            color_id=row[8],
        )
        for row in rows
    }


def load_lookup(master_conn: Any, table: str, name_col: str) -> dict[str, str]:
    """Generic ID -> name lookup for a master.db reference table."""
    rows = master_conn.execute(f"SELECT ID, {name_col} FROM {table}").fetchall()
    return {row[0]: row[1] for row in rows}


def load_my_tags(master_conn: Any) -> dict[str, dict[str, str | None]]:
    rows = master_conn.execute("SELECT ID, Name, ParentID FROM djmdMyTag").fetchall()
    return {row[0]: {"name": row[1], "parent_id": row[2]} for row in rows}


def load_song_my_tags(master_conn: Any) -> dict[int, list[str]]:
    """content_id (int) -> list of MyTagID. Keys must be cast to int —
    ContentID is stored as text in djmdSongMyTag, same VARCHAR-PK quirk as
    DjmdContent.ID.
    """
    rows = master_conn.execute(
        "SELECT ContentID, MyTagID FROM djmdSongMyTag"
    ).fetchall()
    result: dict[int, list[str]] = defaultdict(list)
    for content_id, mytag_id in rows:
        result[int(content_id)].append(mytag_id)
    return result


def load_macro_pattern_map(macro_db3: Path) -> dict[int, int]:
    """macro_pattern.id -> pattern (the bank; energy is a separate HIGH/
    MID/LOW axis and does not affect the bank name — see
    rekordbox-lightingdb-schema skill).
    """
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute("SELECT id, pattern FROM macro_pattern").fetchall()
    finally:
        conn.close()
    return dict(rows)


@dataclass
class Q1Result:
    """Everything Q1 (the join) measured."""

    total_content_rows: int
    total_master_tracks: int
    sample_matches: int
    sample_size: int
    forward_matched: int
    forward_unmatched: int
    unmatched_below_master_min_id: int
    unmatched_above_master_max_id: int
    unmatched_within_range_missing: int
    never_lit_tracks: int
    master_db_id_constant: int
    djmd_property_dbid_match: bool
    djmd_content_masterdbid_match: bool
    alternative_candidates: dict[str, int] = field(default_factory=dict)


def run_q1(
    content_rows: list[ContentRow],
    master_tracks: dict[int, MasterTrack],
    master_conn: Any,
) -> Q1Result:
    """The join itself: does content.song_id == DjmdContent.ID?"""
    n = len(content_rows)
    idx = [round(i * (n - 1) / 9) for i in range(10)]
    sample = [content_rows[i] for i in idx]
    sample_matches = sum(1 for row in sample if row.song_id in master_tracks)

    song_ids = [row.song_id for row in content_rows]
    matched = [sid for sid in song_ids if sid in master_tracks]
    unmatched = [sid for sid in song_ids if sid not in master_tracks]

    min_id = min(master_tracks)
    max_id = max(master_tracks)
    below = [sid for sid in unmatched if sid < min_id]
    above = [sid for sid in unmatched if sid > max_id]
    within = [sid for sid in unmatched if min_id <= sid <= max_id]

    lit_song_ids = set(song_ids)
    never_lit = set(master_tracks) - lit_song_ids

    # Alternative candidate columns, tested regardless of match rate so the
    # report can state plainly that nothing beats direct ID equality.
    alt_cols = (
        "rb_local_usn",
        "usn",
        "ContentLink",
        "TrackNo",
        "DJPlayCount",
        "FileSize",
        "SampleRate",
        "BitRate",
    )
    song_id_set = set(song_ids)
    alternatives: dict[str, int] = {}
    for col in alt_cols:
        rows = master_conn.execute(f"SELECT {col} FROM djmdContent").fetchall()
        values: set[int] = set()
        for (value,) in rows:
            if value is None:
                continue
            try:
                values.add(int(value))
            except (ValueError, TypeError):
                continue
        alternatives[col] = len(song_id_set & values)

    # master_db_id semantic sanity check: the constant on every content
    # row (127286662) should identify the *same* library instance, not a
    # coincidence.
    master_db_id_constant = content_rows[0].master_db_id
    (dbid,) = master_conn.execute("SELECT DBID FROM djmdProperty").fetchone()
    (content_masterdbid,) = master_conn.execute(
        "SELECT DISTINCT MasterDBID FROM djmdContent"
    ).fetchone()

    return Q1Result(
        total_content_rows=n,
        total_master_tracks=len(master_tracks),
        sample_matches=sample_matches,
        sample_size=len(sample),
        forward_matched=len(matched),
        forward_unmatched=len(unmatched),
        unmatched_below_master_min_id=len(below),
        unmatched_above_master_max_id=len(above),
        unmatched_within_range_missing=len(within),
        never_lit_tracks=len(never_lit),
        master_db_id_constant=master_db_id_constant,
        djmd_property_dbid_match=(str(master_db_id_constant) == str(dbid)),
        djmd_content_masterdbid_match=(
            str(master_db_id_constant) == str(content_masterdbid)
        ),
        alternative_candidates=alternatives,
    )


@dataclass
class Q2Result:
    """Everything Q2 (metadata viability) measured, over the JOINED tracks
    only — the tracks Q1 established have real metadata to measure.
    """

    joined_count: int
    genre_populated_pct: float
    genre_counts: Counter[str]
    distinct_genre_count: int
    long_tail_genre_count: int
    long_tail_track_count: int
    color_set_pct: float
    color_counts: dict[str, int]
    my_tag_track_pct: float
    my_tag_catalogue: list[tuple[str, str | None, int]]
    comment_nonempty_pct: float
    comment_samples: list[str]
    rating_counts: Counter[int]
    bpm_min: float
    bpm_median: float
    bpm_max: float
    bpm_populated_pct: float
    key_populated_pct: float
    genre_bank_crosstab: dict[str, Counter[str]]
    genre_bank_overall: Counter[str]


def run_q2(
    joined: list[tuple[ContentRow, MasterTrack]],
    genre_names: dict[str, str],
    color_names: dict[str, str],
    my_tags: dict[str, dict[str, str | None]],
    song_my_tags: dict[int, list[str]],
    pattern_of_mpid: dict[int, int],
) -> Q2Result:
    n = len(joined)

    genre_counts: Counter[str] = Counter()
    for _content, track in joined:
        name = genre_names.get(track.genre_id) if track.genre_id else None
        if name:
            genre_counts[name] += 1
    genre_populated = sum(genre_counts.values())
    long_tail = [(g, c) for g, c in genre_counts.items() if c < 5]

    color_counts: dict[str, int] = defaultdict(int)
    for _content, track in joined:
        if track.color_id and track.color_id != "0":
            color_counts[color_names.get(track.color_id, track.color_id)] += 1
    color_set = sum(color_counts.values())

    my_tag_track_count = 0
    tag_track_counts: Counter[str] = Counter()
    for _content, track in joined:
        tags = song_my_tags.get(track.id, [])
        if tags:
            my_tag_track_count += 1
        for tag_id in tags:
            tag_track_counts[tag_id] += 1
    catalogue: list[tuple[str, str | None, int]] = []
    for tag_id, info in my_tags.items():
        parent_name = (
            my_tags.get(info["parent_id"], {}).get("name")
            if info["parent_id"]
            else None
        )
        catalogue.append(
            (info["name"] or tag_id, parent_name, tag_track_counts.get(tag_id, 0))
        )

    comments = [track.comment for _content, track in joined]
    non_empty_comments = [c for c in comments if c and c.strip()]
    seen: set[str] = set()
    samples: list[str] = []
    for c in non_empty_comments:
        assert c is not None
        if c not in seen:
            seen.add(c)
            samples.append(c)
        if len(samples) >= 10:
            break

    rating_counts: Counter[int] = Counter(
        track.rating for _content, track in joined if track.rating is not None
    )

    bpms = [track.bpm for _content, track in joined if track.bpm]
    bpm_populated = len(bpms)

    key_populated = sum(1 for _content, track in joined if track.key_id)

    crosstab: dict[str, Counter[str]] = defaultdict(Counter)
    overall: Counter[str] = Counter()
    top10 = [g for g, _c in genre_counts.most_common(10)]
    for content, track in joined:
        name = genre_names.get(track.genre_id) if track.genre_id else None
        if name not in top10:
            continue
        pattern = pattern_of_mpid.get(content.macro_pattern_id)
        bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "UNKNOWN"
        crosstab[name][bank] += 1
        overall[bank] += 1

    return Q2Result(
        joined_count=n,
        genre_populated_pct=round(100 * genre_populated / n, 1),
        genre_counts=genre_counts,
        distinct_genre_count=len(genre_counts),
        long_tail_genre_count=len(long_tail),
        long_tail_track_count=sum(c for _g, c in long_tail),
        color_set_pct=round(100 * color_set / n, 1),
        color_counts=dict(color_counts),
        my_tag_track_pct=round(100 * my_tag_track_count / n, 1),
        my_tag_catalogue=sorted(catalogue, key=lambda t: (-t[2], t[0])),
        comment_nonempty_pct=round(100 * len(non_empty_comments) / n, 1),
        comment_samples=samples,
        rating_counts=rating_counts,
        bpm_min=min(bpms) / 100 if bpms else 0.0,
        bpm_median=statistics.median(bpms) / 100 if bpms else 0.0,
        bpm_max=max(bpms) / 100 if bpms else 0.0,
        bpm_populated_pct=round(100 * bpm_populated / n, 1),
        key_populated_pct=round(100 * key_populated / n, 1),
        genre_bank_crosstab=dict(crosstab),
        genre_bank_overall=overall,
    )


def print_track_samples(
    joined: list[tuple[ContentRow, MasterTrack]], artist_names: dict[str, str]
) -> None:
    """Semantic sanity check for Q1: print title + artist for a handful of
    joined tracks spread across the matched set, so a human can confirm
    these are real, distinct tracks and not a coincidental small-integer
    collision. Off by default (--show-track-samples) — this is real
    library data and should not appear in default console output or be
    pasted into the (public) written report; see
    docs/experiments/E1-library-join.md for the redacted summary.
    """
    if not joined:
        return
    n = len(joined)
    idx = [round(i * (n - 1) / 4) for i in range(5)]
    print("track samples (semantic sanity check — NOT for the public report):")
    for i in idx:
        _content, track = joined[i]
        artist = artist_names.get(track.artist_id or "", "?")
        print(f"    {track.title!r} — {artist!r}")


def print_report(q1: Q1Result, q2: Q2Result) -> None:
    """Console summary. NOT the deliverable — the deliverable is the
    written verdict at docs/experiments/E1-library-join.md. This printout
    is for whoever re-runs the probe later to sanity-check the numbers in
    that doc still hold.
    """
    print("=" * 70)
    print("Q1 — the join")
    print("=" * 70)
    print(f"content rows (LightingDB, user.db3):        {q1.total_content_rows}")
    print(f"DjmdContent rows (master.db):                {q1.total_master_tracks}")
    print(
        f"10-row spanning sample: {q1.sample_matches}/{q1.sample_size} "
        "resolve to a live DjmdContent.ID"
    )
    print(
        f"forward coverage: {q1.forward_matched}/{q1.total_content_rows} "
        f"({round(100 * q1.forward_matched / q1.total_content_rows, 1)}%) "
        "content rows resolve"
    )
    print(f"  of the unmatched {q1.forward_unmatched}:")
    print(
        f"    below master min ID (legacy numbering): {q1.unmatched_below_master_min_id}"
    )
    print(
        f"    within range but missing (deleted?):     {q1.unmatched_within_range_missing}"
    )
    print(
        f"    above master max ID:                     {q1.unmatched_above_master_max_id}"
    )
    print(
        f"backward: {q1.never_lit_tracks}/{q1.total_master_tracks} library "
        "tracks have NO content row (never analysed for lighting)"
    )
    print(f"master_db_id constant on every content row: {q1.master_db_id_constant}")
    print(f"  == djmdProperty.DBID:        {q1.djmd_property_dbid_match}")
    print(f"  == djmdContent.MasterDBID:   {q1.djmd_content_masterdbid_match}")
    print("alternative candidate columns (song_id overlap count):")
    for col, count in q1.alternative_candidates.items():
        print(f"    {col}: {count}")

    print()
    print("=" * 70)
    print("Q2 — metadata viability (over the JOINED tracks only)")
    print("=" * 70)
    print(f"joined tracks: {q2.joined_count}")
    print(
        f"genre populated: {q2.genre_populated_pct}%  distinct genres: {q2.distinct_genre_count}"
    )
    print(
        f"genres with <5 tracks: {q2.long_tail_genre_count} ({q2.long_tail_track_count} tracks)"
    )
    print("top 30 genres:")
    for name, count in q2.genre_counts.most_common(30):
        print(f"    {name}: {count}")
    print(f"colour set: {q2.color_set_pct}%")
    for name, count in sorted(q2.color_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {name!r}: {count}")
    print(f"My Tag: {q2.my_tag_track_pct}% of tracks have >=1 tag")
    for name, parent, count in q2.my_tag_catalogue:
        print(f"    {name!r} (parent={parent!r}): {count}")
    print(f"comment non-empty: {q2.comment_nonempty_pct}%")
    print(f"rating distribution: {dict(sorted(q2.rating_counts.items()))}")
    print(
        f"BPM: min={q2.bpm_min} median={q2.bpm_median} max={q2.bpm_max} populated={q2.bpm_populated_pct}%"
    )
    print(f"key populated: {q2.key_populated_pct}%")
    print("genre x bank crosstab (top 10 genres):")
    for genre, banks in q2.genre_bank_crosstab.items():
        print(f"    {genre}: {dict(banks)}")
    print(
        f"overall bank distribution across top-10-genre tracks: {dict(q2.genre_bank_overall.most_common())}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh-master-copy",
        action="store_true",
        help="Re-copy work/master.db from live even if a copy already exists.",
    )
    parser.add_argument(
        "--show-track-samples",
        action="store_true",
        help=(
            "Print title/artist for 5 sampled joined tracks (real library "
            "data — off by default, never paste this into the report)."
        ),
    )
    args = parser.parse_args()

    master_path = ensure_master_db_copy(refresh=args.refresh_master_copy)
    master_conn = open_master_db(master_path)
    try:
        content_rows = load_content_rows(Path("work/user.db3"))
        master_tracks = load_master_tracks(master_conn)
        genre_names = load_lookup(master_conn, "djmdGenre", "Name")
        color_names = load_lookup(master_conn, "djmdColor", "Commnt")
        my_tags = load_my_tags(master_conn)
        song_my_tags = load_song_my_tags(master_conn)
        pattern_of_mpid = load_macro_pattern_map(Path("work/macro.db3"))

        q1 = run_q1(content_rows, master_tracks, master_conn)

        joined = [
            (row, master_tracks[row.song_id])
            for row in content_rows
            if row.song_id in master_tracks
        ]
        q2 = run_q2(
            joined, genre_names, color_names, my_tags, song_my_tags, pattern_of_mpid
        )

        print_report(q1, q2)

        if args.show_track_samples:
            print()
            artist_names = load_lookup(master_conn, "djmdArtist", "Name")
            print_track_samples(joined, artist_names)
    finally:
        master_conn.close()


if __name__ == "__main__":
    main()
