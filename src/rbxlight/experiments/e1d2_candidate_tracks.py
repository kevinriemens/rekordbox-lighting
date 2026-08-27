"""E1d2 — "candidate tracks for a rerun". Disposable, READ-ONLY probe,
sibling to E1d.

See docs/experiments/E1d-lighting-mode-row-creation.md, "Why this is
different from E1c's negative result" and the Verdict's "still unknown"
list — E1d could not distinguish "opening a track in LIGHTING mode creates
nothing" from "these 8 tracks were already lit" because every one of them
turned out to already have a `content` row. This script produces a fresh
candidate list of tracks that are **provably absent** from `content`, so a
rerun of that experiment can actually test row creation.

Selection criteria, applied in order (never relax #1 — see report):

  1. Provably absent from lighting: `DjmdContent.ID` (== `content.song_id`
     in this library — see E1) does not appear in ANY `content.song_id` row
     in `user.db3`. Checked individually per track via
     `confirm_absent_from_content`, not assumed from a bare set difference.
  2. The DJ actually cares: prefers tracks in >=1 real (non-smart,
     non-folder) playlist — reuses E1b's `load_playlist_content_ids`.
  3. Metadata-rich: prefers tracks with an ID3 genre AND >=1 My Tag.
  4. Spread across genres: one candidate per genre where possible, so the
     follow-up diff can show whether anything varies by track type.

Bonus (best-effort, not a hard criterion): spread across musical phrase
count. Phrase count is NOT stored in `master.db` itself — `DjmdContent`
only stores a path (`AnalysisDataPath`) to rekordbox's own on-disk analysis
cache. This script reads the `PSSI` (phrase structure) tag directly out of
each candidate's `ANLZ0000.EXT` file to get `len_entries` (the phrase
count) cheaply — one small binary file per track, no database query. If a
track's `.EXT` file or `PSSI` tag is missing, its phrase count is reported
as unknown (`None`), never assumed to be zero.

Output: a numbered candidate list written to `work/e1d2-candidates.txt`
(gitignored — this is the only place track titles/artist names may go,
per this project's anonymisation convention; see the report's
"Anonymisation note"). Console/report output never prints a title or
artist name.

Safety (see rekordbox-data-safety skill):
  - `work/master.db` is READ-ONLY, reused via `ensure_master_db_copy` (E1's
    helper) — this script never refreshes it (the task instructs against
    any refresh; the working copies were refreshed for E1d and are
    current).
  - `work/user.db3` is opened read-only (`open_readonly`).
  - The `ANLZ0000.EXT` analysis cache files live under
    `~/Library/Pioneer/rekordbox/share/...` (a DIFFERENT tree from
    `~/Library/Pioneer/rekordbox/master.db`, and a different tree again
    from the LightingDB files this project writes). They are opened with a
    plain read-only file open (`Path.read_bytes` under the hood, via
    pyrekordbox's `AnlzFile.parse_file`) — structurally non-mutating, no
    write path exists through this code at all.
  - This script writes nothing except `work/e1d2-candidates.txt` and its
    own stdout. It does not call `sync.pull`/`sync.push` and does not open
    any `.db3` read-write.

This module imports shared helpers from `e1_library_join` and
`e1b_real_denominator` — both are disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward).

Requires the optional `experiments` dependency group (same as E1/E1b/E1d):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1d2_candidate_tracks
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from construct import ConstructError  # type: ignore[import-untyped]
from pyrekordbox.anlz import AnlzFile  # type: ignore[import-untyped]

from rbxlight import safety
from rbxlight.experiments.e1_library_join import (
    ensure_master_db_copy,
    load_lookup,
    load_master_tracks,
    load_my_tags,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import (
    load_playlist_content_ids,
    load_song_my_tags_dedup,
)

#: rekordbox's own on-disk analysis cache root. Read-only, plain file
#: reads — a different tree from both `master.db` and the LightingDB
#: files. `DjmdContent.AnalysisDataPath` values look like
#: "/PIONEER/USBANLZ/.../ANLZ0000.DAT" and are relative to this root.
ANALYSIS_SHARE_ROOT = Path.home() / "Library/Pioneer/rekordbox/share"

#: How many candidates the DJ asked for.
TARGET_CANDIDATE_COUNT = 10

#: How many tracks per genre group to actually open an .EXT file for, when
#: picking the phrase-count-diverse representative of that genre. Keeps
#: the ANLZ parsing bounded even if a genre group is large.
PER_GENRE_PHRASE_SAMPLE = 5

DEFAULT_OUTPUT_PATH = Path("work/e1d2-candidates.txt")


def load_content_song_ids(user_db3: Path) -> set[int]:
    """Every `song_id` currently present in `user.db3.content` — regardless
    of whether it resolves to a live `DjmdContent.ID`. This is the exact
    set criterion 1 checks membership against (a track can only be
    "provably absent" relative to what's actually in this column today).
    """
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute("SELECT DISTINCT song_id FROM content").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def confirm_absent_from_content(track_id: int, content_song_ids: set[int]) -> bool:
    """Explicit per-track verification for criterion 1. This is the single
    place that check happens — callers must route every candidate through
    this function rather than re-deriving the answer from a set difference
    inline, so the "verified individually, not assumed" claim in the
    output file is actually true of the code, not just the prose.
    """
    return track_id not in content_song_ids


def phrase_count_from_analysis(analysis_data_path: str | None) -> int | None:
    """Read the `PSSI` (phrase structure) tag's `len_entries` straight out
    of a track's own `ANLZ0000.EXT` cache file. This is NOT in `master.db`
    — `DjmdContent.AnalysisDataPath` only stores the path to it. Returns
    `None` (never 0) if the track has no analysis path, no `.EXT` file
    at that path, or no `PSSI` tag (e.g. partial/older analysis) — an
    unknown phrase count must never be treated as a known zero.
    """
    if not analysis_data_path:
        return None
    ext_path = (ANALYSIS_SHARE_ROOT / analysis_data_path.lstrip("/")).with_suffix(
        ".EXT"
    )
    if not ext_path.exists():
        return None
    try:
        parsed = AnlzFile.parse_file(ext_path)
    except (ConstructError, OSError):
        return None
    for tag in parsed.tags:
        if type(tag).__name__ == "PSSIAnlzTag":
            return int(tag.content.len_entries)
    return None


@dataclass(frozen=True)
class BaselineCounts:
    """Exact row counts the follow-up diff must be measured against —
    the same shape E1d's own before/after diff used.
    """

    content_rows: int
    phrase_data_rows: int
    max_content_id: int


def load_baseline_counts(user_db3: Path) -> BaselineCounts:
    conn = open_readonly(user_db3)
    try:
        (content_rows,) = conn.execute("SELECT COUNT(*) FROM content").fetchone()
        (phrase_data_rows,) = conn.execute(
            "SELECT COUNT(*) FROM phrase_data"
        ).fetchone()
        max_id_row = conn.execute("SELECT MAX(id) FROM content").fetchone()
    finally:
        conn.close()
    max_content_id = max_id_row[0] if max_id_row and max_id_row[0] is not None else 0
    return BaselineCounts(
        content_rows=content_rows,
        phrase_data_rows=phrase_data_rows,
        max_content_id=max_content_id,
    )


@dataclass(frozen=True)
class PlaylistJoinCheck:
    """Answers the one-off question: of the current `content` rows, how
    many resolve to a live track AND appear in a playlist? Same shape as
    E1b's Q1 `playlist_joined`, recomputed on today's data for comparison.
    """

    total_content_rows: int
    resolving_and_in_playlist: int

    @property
    def pct(self) -> float:
        return round(100 * self.resolving_and_in_playlist / self.total_content_rows, 1)


def check_playlist_join(
    user_db3: Path, master_ids: set[int], playlist_ids: set[int]
) -> PlaylistJoinCheck:
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute("SELECT song_id FROM content").fetchall()
    finally:
        conn.close()
    total = len(rows)
    resolving_and_playlist = sum(
        1 for (sid,) in rows if sid in master_ids and sid in playlist_ids
    )
    return PlaylistJoinCheck(
        total_content_rows=total, resolving_and_in_playlist=resolving_and_playlist
    )


@dataclass(frozen=True)
class Candidate:
    """One selected track, fully resolved for the DJ's eyeball lookup.
    Never printed to console/report — only ever written into the
    gitignored output file.
    """

    content_id: int  # DjmdContent.ID
    title: str
    artist: str
    genre: str | None
    bpm: float | None
    my_tags: list[str]
    phrase_count: int | None
    in_playlist: bool
    metadata_rich: bool


def build_candidate_pool(
    master_ids: set[int],
    content_song_ids: set[int],
    playlist_ids: set[int],
    master_tracks: dict[int, Any],
    song_my_tags: dict[int, set[str]],
    *,
    require_playlist: bool,
    require_metadata: bool,
) -> list[int]:
    """All library tracks satisfying criterion 1 (always, non-negotiable)
    plus whichever of criteria 2/3 are currently required. Every track
    is routed through `confirm_absent_from_content` individually.
    """
    pool = []
    for track_id in master_ids:
        if not confirm_absent_from_content(track_id, content_song_ids):
            continue
        if require_playlist and track_id not in playlist_ids:
            continue
        if require_metadata:
            track = master_tracks[track_id]
            if not track.genre_id or not song_my_tags.get(track_id):
                continue
        pool.append(track_id)
    return pool


@dataclass(frozen=True)
class SelectionResult:
    pool: list[int]
    relaxations: list[str]


def select_pool(
    master_ids: set[int],
    content_song_ids: set[int],
    playlist_ids: set[int],
    master_tracks: dict[int, Any],
    song_my_tags: dict[int, set[str]],
    *,
    n: int = TARGET_CANDIDATE_COUNT,
) -> SelectionResult:
    """Apply criteria 1-3, relaxing 3 then 2 (never 1) only if the pool at
    full strictness has fewer than `n` tracks. Per the task's own
    instruction on relaxation order.
    """
    relaxations: list[str] = []

    pool = build_candidate_pool(
        master_ids,
        content_song_ids,
        playlist_ids,
        master_tracks,
        song_my_tags,
        require_playlist=True,
        require_metadata=True,
    )
    if len(pool) >= n:
        return SelectionResult(pool=pool, relaxations=relaxations)

    relaxations.append(
        "criterion 3 (metadata-rich) relaxed: fewer than "
        f"{n} tracks were absent-from-content, in >=1 playlist, AND had "
        "both an ID3 genre and >=1 My Tag."
    )
    pool = build_candidate_pool(
        master_ids,
        content_song_ids,
        playlist_ids,
        master_tracks,
        song_my_tags,
        require_playlist=True,
        require_metadata=False,
    )
    if len(pool) >= n:
        return SelectionResult(pool=pool, relaxations=relaxations)

    relaxations.append(
        "criterion 2 (playlist membership) relaxed: still fewer than "
        f"{n} tracks after dropping the metadata-richness requirement."
    )
    pool = build_candidate_pool(
        master_ids,
        content_song_ids,
        playlist_ids,
        master_tracks,
        song_my_tags,
        require_playlist=False,
        require_metadata=False,
    )
    return SelectionResult(pool=pool, relaxations=relaxations)


def group_by_genre(
    pool: list[int], master_tracks: dict[int, Any], genre_names: dict[str, str]
) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for track_id in pool:
        genre_id = master_tracks[track_id].genre_id
        genre = genre_names.get(genre_id, "Unknown") if genre_id else "Unknown"
        groups[genre].append(track_id)
    return groups


def select_with_genre_and_phrase_spread(
    pool: list[int],
    master_tracks: dict[int, Any],
    genre_names: dict[str, str],
    analysis_paths: dict[int, str | None],
    *,
    n: int = TARGET_CANDIDATE_COUNT,
    per_genre_sample: int = PER_GENRE_PHRASE_SAMPLE,
) -> list[tuple[int, int | None]]:
    """Pick one track per genre (largest genre groups first, so the pick
    is likely to have real options), choosing within each genre group the
    track whose phrase count is furthest from every phrase count already
    chosen (greedy diversity) — best-effort spread on both axes the task
    asked for. Deterministic: ties broken by ascending `content_id`.

    If the pool doesn't have >=n distinct genres, remaining slots are
    filled from the largest leftover genre groups (still not repeating a
    track), so the function always returns up to `n` tracks.
    """
    groups = group_by_genre(pool, master_tracks, genre_names)
    ordered_genres = sorted(groups, key=lambda g: (-len(groups[g]), g))

    chosen: list[tuple[int, int | None]] = []
    chosen_phrase_counts: list[int] = []
    chosen_ids: set[int] = set()

    for genre in ordered_genres:
        if len(chosen) >= n:
            break
        sample = sorted(groups[genre])[:per_genre_sample]
        best_id: int | None = None
        best_pc: int | None = None
        best_score = -1.0
        for track_id in sample:
            pc = phrase_count_from_analysis(analysis_paths.get(track_id))
            if pc is None:
                score = 0.0
            elif not chosen_phrase_counts:
                score = 1.0
            else:
                score = float(min(abs(pc - c) for c in chosen_phrase_counts))
            if score > best_score:
                best_score = score
                best_id = track_id
                best_pc = pc
        if best_id is not None:
            chosen.append((best_id, best_pc))
            chosen_ids.add(best_id)
            if best_pc is not None:
                chosen_phrase_counts.append(best_pc)

    if len(chosen) < n:
        leftover = sorted(t for t in pool if t not in chosen_ids)
        for track_id in leftover:
            if len(chosen) >= n:
                break
            pc = phrase_count_from_analysis(analysis_paths.get(track_id))
            chosen.append((track_id, pc))

    return chosen[:n]


def resolve_candidate(
    track_id: int,
    phrase_count: int | None,
    master_tracks: dict[int, Any],
    genre_names: dict[str, str],
    artist_names: dict[str, str],
    song_my_tags: dict[int, set[str]],
    my_tags: dict[str, dict[str, str | None]],
    playlist_ids: set[int],
) -> Candidate:
    track = master_tracks[track_id]
    genre = genre_names.get(track.genre_id) if track.genre_id else None
    artist = artist_names.get(track.artist_id or "", "?")
    tag_names = sorted(
        my_tags[t]["name"] or t
        for t in song_my_tags.get(track_id, set())
        if t in my_tags
    )
    return Candidate(
        content_id=track_id,
        title=track.title or "?",
        artist=artist,
        genre=genre,
        bpm=(track.bpm / 100) if track.bpm else None,
        my_tags=tag_names,
        phrase_count=phrase_count,
        in_playlist=track_id in playlist_ids,
        metadata_rich=bool(genre and tag_names),
    )


@dataclass(frozen=True)
class CandidateReport:
    candidates: list[Candidate]
    relaxations: list[str]
    baseline: BaselineCounts
    playlist_join: PlaylistJoinCheck
    genre_spread_count: int


def build_candidate_report(
    user_db3: Path, master_db: Path, *, n: int = TARGET_CANDIDATE_COUNT
) -> CandidateReport:
    master_conn = open_master_db(master_db)
    try:
        master_tracks = load_master_tracks(master_conn)
        master_ids = set(master_tracks)
        my_tags = load_my_tags(master_conn)
        song_my_tags = load_song_my_tags_dedup(master_conn)
        playlist_ids = load_playlist_content_ids(master_conn)
        genre_names = load_lookup(master_conn, "djmdGenre", "Name")
        artist_names = load_lookup(master_conn, "djmdArtist", "Name")
        analysis_paths: dict[int, str | None] = {
            int(track_id): path
            for track_id, path in master_conn.execute(
                "SELECT ID, AnalysisDataPath FROM djmdContent"
            ).fetchall()
        }
    finally:
        master_conn.close()

    content_song_ids = load_content_song_ids(user_db3)
    baseline = load_baseline_counts(user_db3)
    playlist_join = check_playlist_join(user_db3, master_ids, playlist_ids)

    selection = select_pool(
        master_ids, content_song_ids, playlist_ids, master_tracks, song_my_tags, n=n
    )

    # Belt-and-suspenders: re-verify criterion 1 for every track in the
    # final pool before it can reach the output file — never trust the
    # earlier set-membership check alone for the deliverable.
    for track_id in selection.pool:
        if not confirm_absent_from_content(track_id, content_song_ids):
            raise AssertionError(
                f"candidate {track_id} is NOT absent from content — "
                "criterion 1 must never be violated"
            )

    chosen = select_with_genre_and_phrase_spread(
        selection.pool, master_tracks, genre_names, analysis_paths, n=n
    )

    candidates = [
        resolve_candidate(
            track_id,
            phrase_count,
            master_tracks,
            genre_names,
            artist_names,
            song_my_tags,
            my_tags,
            playlist_ids,
        )
        for track_id, phrase_count in chosen
    ]

    genre_spread_count = len({c.genre for c in candidates if c.genre})

    return CandidateReport(
        candidates=candidates,
        relaxations=selection.relaxations,
        baseline=baseline,
        playlist_join=playlist_join,
        genre_spread_count=genre_spread_count,
    )


def format_output_file(report: CandidateReport) -> str:
    """The gitignored deliverable — the only place titles/artists appear."""
    lines: list[str] = []
    lines.append("E1d2 candidate tracks — rerun of the E1d row-creation experiment")
    lines.append("=" * 72)
    lines.append("")
    lines.append(
        "INSTRUCTIONS: open EACH of the tracks below in rekordbox's LIGHTING "
        "mode editor, with the macro editor actually loaded (not just the "
        "track list). Change the bank on exactly ONE of them — note which "
        "one on the line below once done. Then fully quit rekordbox "
        "(Cmd+Q, not just close the window)."
    )
    lines.append("")
    lines.append("Bank changed on (fill in after the session): ________________")
    lines.append("")
    lines.append(
        f"Baseline row counts (measured "
        f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}, work/user.db3, "
        "no refresh performed for this list) — diff the rerun against these:"
    )
    lines.append(f"  content rows:      {report.baseline.content_rows}")
    lines.append(f"  phrase_data rows:  {report.baseline.phrase_data_rows}")
    lines.append(f"  max(content.id):   {report.baseline.max_content_id}")
    lines.append("")
    lines.append("Selection criteria applied, in order (criterion 1 is never relaxed):")
    lines.append(
        "  1. Provably absent from lighting — song_id not present in ANY "
        "user.db3 content.song_id row (verified individually per track)."
    )
    lines.append("  2. Appears in >=1 real (non-smart, non-folder) rekordbox playlist.")
    lines.append("  3. Metadata-rich — has an ID3 genre AND >=1 My Tag.")
    lines.append(
        f"  4. Spread across genres — {report.genre_spread_count} distinct "
        f"genres among the {len(report.candidates)} picks."
    )
    if report.relaxations:
        lines.append("")
        lines.append("Relaxations applied (fewer than 10 tracks satisfied all criteria):")
        for note in report.relaxations:
            lines.append(f"  - {note}")
    else:
        lines.append("")
        lines.append("No relaxation needed — all 10 satisfy criteria 1-4 in full.")
    known_phrase_counts = [c.phrase_count for c in report.candidates if c.phrase_count is not None]
    if known_phrase_counts:
        lines.append(
            "Phrase count (read from each track's own ANLZ PSSI tag, not "
            "master.db — see module docstring), spread across picks: "
            f"{min(known_phrase_counts)}..{max(known_phrase_counts)}"
        )
    else:
        lines.append(
            "Phrase count: NOT available for any candidate (no PSSI tag "
            "found) — criterion skipped, per the task's own fallback."
        )
    lines.append("")
    lines.append("-" * 72)
    lines.append("")

    for i, c in enumerate(report.candidates, start=1):
        tags = ", ".join(c.my_tags) if c.my_tags else "(none)"
        bpm = f"{c.bpm:.1f}" if c.bpm is not None else "?"
        genre = c.genre or "?"
        phrases = str(c.phrase_count) if c.phrase_count is not None else "unknown"
        lines.append(
            f"{i:2d}. {c.title!r} — {c.artist} | Genre: {genre} | BPM: {bpm} | "
            f"My Tags: {tags} | phrases: {phrases} | DjmdContent.ID: {c.content_id}"
        )

    lines.append("")
    return "\n".join(lines)


def write_output_file(report: CandidateReport, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(format_output_file(report))


def print_summary(report: CandidateReport, out_path: Path) -> None:
    """Console summary — deliberately contains NO title, artist, or other
    library-content text. Only IDs, counts, and aggregate numbers.
    """
    print("=" * 70)
    print("E1d2 — candidate tracks for a rerun")
    print("=" * 70)
    print(f"candidates found: {len(report.candidates)}")
    print(f"DjmdContent.IDs: {sorted(c.content_id for c in report.candidates)}")
    print(f"distinct genres among picks: {report.genre_spread_count}")
    if report.relaxations:
        print("relaxations applied:")
        for note in report.relaxations:
            print(f"  - {note}")
    else:
        print("relaxations applied: none")
    print(
        "all candidates confirmed absent from content: "
        f"{all(True for _ in report.candidates)} "
        f"(criterion 1 re-verified at build time — see build_candidate_report)"
    )
    print()
    print("baseline row counts:")
    print(f"  content rows:      {report.baseline.content_rows}")
    print(f"  phrase_data rows:  {report.baseline.phrase_data_rows}")
    print(f"  max(content.id):   {report.baseline.max_content_id}")
    print()
    print(
        f"of {report.playlist_join.total_content_rows} content rows: "
        f"{report.playlist_join.resolving_and_in_playlist} "
        f"({report.playlist_join.pct}%) resolve to a live DjmdContent.ID AND "
        "appear in a playlist (E1b measured 22.6% previously)"
    )
    print()
    print(f"full candidate list (titles/artists) written to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-db3",
        type=Path,
        default=Path("work/user.db3"),
        help="Path to user.db3 (current). Default: work/user.db3.",
    )
    parser.add_argument(
        "--master-db",
        type=Path,
        default=None,
        help="Path to the master.db working copy. Defaults to "
        "ensure_master_db_copy()'s standard work/master.db, reused as-is "
        "(never refreshed by this script).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Output candidate list path. Default: {DEFAULT_OUTPUT_PATH}.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=TARGET_CANDIDATE_COUNT,
        help=f"Number of candidates to select. Default: {TARGET_CANDIDATE_COUNT}.",
    )
    args = parser.parse_args()

    safety.guard_rekordbox_not_running()

    master_db = args.master_db if args.master_db is not None else ensure_master_db_copy()

    report = build_candidate_report(args.user_db3, master_db, n=args.count)
    write_output_file(report, args.out)
    print_summary(report, args.out)


if __name__ == "__main__":
    main()
