"""E1e — "the phrase-phase mapping". Disposable, READ-ONLY probe, fifth in
the E1/E1b/E1c/E1d series.

See docs/experiments/E1e-phrase-phase-mapping.md for the written verdict
this script exists to produce — that file, not this one, is the
deliverable.

E1d (docs/experiments/E1d-lighting-mode-row-creation.md) found that a bank
change on an already-lit track rewrites `phrase_data.macro_id` from the new
bank's `macro_assign`, but could not explain *which* `phrase_num` receives
*which* `macro_assign.phase` — the single unresolved blocker for both Stage
1 (rebuilding `phrase_data` after a bank change) and Stage 3 (per-track
shows). This probe mines the answer out of data already on disk: no new
manual experiment, no DJ session required.

Four questions, answered in order:

  1. Is the `macro_id -> phase` reverse lookup (per `macro_pattern_id`)
     unambiguous? (classify every one of the 41742 `phrase_data` rows)
  2. Is `phrase_num -> phase` a stable per-(pattern, track-phrase-count)
     lookup table, or track-specific? What happens when a track's phrase
     count differs from its bank's phase count?
  3. Does the track's own ANLZ `PSSI` phrase-*kind* structure predict the
     phase better than ordinal `phrase_num` does? (reuses the PSSI-reading
     approach `e1d2_candidate_tracks.py` already demonstrated — file
     resolution via `DjmdContent.AnalysisDataPath`, `AnlzFile.parse_file`,
     scanning for the `PSSIAnlzTag`)
  4. Given all of the above: is forging a `phrase_data` row set for a
     never-lit track viable?

Safety (see rekordbox-data-safety skill):
  - `~/Library/Pioneer/rekordbox/master.db` is READ-ONLY, FOREVER. Reused
    via `ensure_master_db_copy` (E1's helper) — this script does NOT
    refresh it (the task instructs against any refresh; the working
    copies are current as of E1d).
  - `work/user.db3` and `work/macro.db3` are opened read-only
    (`open_readonly`).
  - The `ANLZ0000.EXT` analysis cache files under
    `~/Library/Pioneer/rekordbox/share/...` are opened with a plain
    read-only file open via `pyrekordbox`'s `AnlzFile.parse_file` — the
    exact mechanism `e1d2_candidate_tracks.py` already used for phrase
    *count*; this probe reuses that mechanism to also read phrase *kind*.
  - This script writes nothing. It does not call `sync.pull`/`sync.push`
    and does not open any `.db3` read-write.

No refresh needed: all three working copies are current as of E1d/E1d2.
Guard confirmed clear (`pgrep -x rekordbox` exit 1) before this probe ran.

This module imports shared helpers from `e1_library_join`,
`e1b_real_denominator`, and reuses the ANLZ-reading approach from
`e1d2_candidate_tracks` — all disposable probes in the same
`experiments/` package (see rekordbox-lighting-architecture skill: the
dependency arrow only ever points inward).

Requires the optional `experiments` dependency group (same as E1/E1b/E1d):
    pip install -e ".[experiments]"

Run:
    python -m rbxlight.experiments.e1e_phrase_phase_mapping
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from construct import ConstructError  # type: ignore[import-untyped]
from pyrekordbox.anlz import AnlzFile  # type: ignore[import-untyped]

from rbxlight.experiments.e1_library_join import (
    PATTERN_NAMES,
    ensure_master_db_copy,
    load_master_tracks,
    open_master_db,
    open_readonly,
)
from rbxlight.experiments.e1b_real_denominator import ENERGY_NAMES

#: rekordbox's own on-disk analysis cache root — same constant
#: `e1d2_candidate_tracks.py` uses. A different tree from both `master.db`
#: and the LightingDB files; read-only, plain file reads.
ANALYSIS_SHARE_ROOT = Path.home() / "Library/Pioneer/rekordbox/share"

#: Baseline figures from E1c/E1d, quoted only for direct comparison.
BASELINE_CONTENT_ROWS = 2966
BASELINE_PHRASE_DATA_ROWS = 41742
BASELINE_PHRASE_DATA_DISTINCT_CONTENT = 2905
BASELINE_PHRASE_OVERRIDES = 36

#: A (pattern, N) group needs at least this many tracks before its
#: consistency (or inconsistency) across tracks is reported individually —
#: below this, a single track trivially produces a "consistent" group of
#: size 1, which says nothing about a general rule.
MIN_GROUP_SIZE_FOR_REPORT = 5


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_macro_assign_by_pattern(macro_db3: Path) -> dict[int, list[tuple[int, int]]]:
    """`macro_pattern_id -> [(phase, macro_id), ...]`, ordered by phase.
    Read directly, never derived — phase counts are not uniform (see
    rekordbox-lightingdb-schema skill).
    """
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute(
            "SELECT macro_pattern_id, phase, macro_id FROM macro_assign "
            "ORDER BY macro_pattern_id, phase"
        ).fetchall()
    finally:
        conn.close()
    by_pattern: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for mpid, phase, macro_id in rows:
        by_pattern[mpid].append((phase, macro_id))
    return dict(by_pattern)


def build_reverse_lookup_all_phases(
    assign_by_pattern: dict[int, list[tuple[int, int]]],
) -> dict[int, dict[int, list[int]]]:
    """`macro_pattern_id -> macro_id -> [every phase carrying that macro_id]`.
    Used to classify ambiguity — a macro_id with >1 phase in its own
    pattern is genuinely ambiguous for reverse lookup, not a bug in this
    probe's logic.
    """
    reverse: dict[int, dict[int, list[int]]] = {}
    for mpid, rows in assign_by_pattern.items():
        d: dict[int, list[int]] = defaultdict(list)
        for phase, macro_id in rows:
            d[macro_id].append(phase)
        reverse[mpid] = dict(d)
    return reverse


def build_reverse_lookup_first_phase(
    assign_by_pattern: dict[int, list[tuple[int, int]]],
) -> dict[int, dict[int, int]]:
    """`macro_pattern_id -> macro_id -> first (lowest) phase carrying that
    macro_id`. This is the same "first matching phase" convention E1d used
    (`build_phase_correspondence`) — for ambiguous macro_ids we cannot know
    which phase a track's phrase actually came from without more context,
    so we pick the lowest phase index as the representative and rely on
    Part 3 (subkind consistency) to show whether this convention actually
    matters in practice.
    """
    reverse: dict[int, dict[int, int]] = {}
    for mpid, rows in assign_by_pattern.items():
        d: dict[int, int] = {}
        for phase, macro_id in sorted(rows):
            d.setdefault(macro_id, phase)
        reverse[mpid] = d
    return reverse


@dataclass(frozen=True)
class ContentInfo:
    macro_pattern_id: int
    song_id: int


def load_content_info(user_db3: Path) -> dict[int, ContentInfo]:
    """`content.id -> ContentInfo`."""
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT id, macro_pattern_id, song_id FROM content"
        ).fetchall()
    finally:
        conn.close()
    return {
        row[0]: ContentInfo(macro_pattern_id=row[1], song_id=row[2]) for row in rows
    }


@dataclass(frozen=True)
class PhraseRow:
    phrase_num: int
    macro_id: int
    initial_macro_id: int


def load_phrase_data_by_content(user_db3: Path) -> dict[int, list[PhraseRow]]:
    """`content_id -> [PhraseRow, ...]`, ordered by `phrase_num`."""
    conn = open_readonly(user_db3)
    try:
        rows = conn.execute(
            "SELECT content_id, phrase_num, macro_id, initial_macro_id "
            "FROM phrase_data ORDER BY content_id, phrase_num"
        ).fetchall()
    finally:
        conn.close()
    by_content: dict[int, list[PhraseRow]] = defaultdict(list)
    for content_id, phrase_num, macro_id, initial_macro_id in rows:
        by_content[content_id].append(
            PhraseRow(
                phrase_num=phrase_num,
                macro_id=macro_id,
                initial_macro_id=initial_macro_id,
            )
        )
    return dict(by_content)


def load_pattern_energy(macro_db3: Path) -> dict[int, tuple[int, int]]:
    """`macro_pattern.id -> (pattern, energy)`."""
    conn = open_readonly(macro_db3)
    try:
        rows = conn.execute("SELECT id, pattern, energy FROM macro_pattern").fetchall()
    finally:
        conn.close()
    return {row[0]: (row[1], row[2]) for row in rows}


def bank_energy_label(mpid: int, pattern_energy: dict[int, tuple[int, int]]) -> str:
    pattern, energy = pattern_energy.get(mpid, (None, None))
    bank = PATTERN_NAMES.get(pattern, f"pattern{pattern}") if pattern else "NONE"
    energy_name = ENERGY_NAMES.get(energy, "NONE") if energy else "NONE"
    return f"{bank}/{energy_name}"


# ---------------------------------------------------------------------------
# Part 1 — reverse lookup ambiguity classification
# ---------------------------------------------------------------------------


@dataclass
class ReverseLookupResult:
    """Classifies every `phrase_data` row by how its `macro_id` resolves
    against its own track's bank `macro_assign`.
    """

    total_rows: int
    unambiguous: int
    ambiguous: int
    not_found: int
    ambiguous_by_pattern: Counter[int]
    not_found_is_override: int
    not_found_other: int
    not_found_other_examples: list[
        tuple[int, int, int, int]
    ]  # content_id, phrase_num, mpid, macro_id

    @property
    def unambiguous_pct(self) -> float:
        return round(100 * self.unambiguous / self.total_rows, 2)

    @property
    def ambiguous_pct(self) -> float:
        return round(100 * self.ambiguous / self.total_rows, 2)

    @property
    def not_found_pct(self) -> float:
        return round(100 * self.not_found / self.total_rows, 2)


def run_reverse_lookup_classification(
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_all: dict[int, dict[int, list[int]]],
) -> ReverseLookupResult:
    total = 0
    unambiguous = 0
    ambiguous = 0
    not_found = 0
    ambiguous_by_pattern: Counter[int] = Counter()
    not_found_is_override = 0
    not_found_other = 0
    not_found_other_examples: list[tuple[int, int, int, int]] = []

    for content_id, rows in phrase_by_content.items():
        info = content_info.get(content_id)
        mpid = info.macro_pattern_id if info else None
        rev = reverse_all.get(mpid, {}) if mpid is not None else {}
        for row in rows:
            total += 1
            phases = rev.get(row.macro_id)
            if not phases:
                not_found += 1
                if row.macro_id != row.initial_macro_id:
                    not_found_is_override += 1
                else:
                    not_found_other += 1
                    if len(not_found_other_examples) < 20:
                        not_found_other_examples.append(
                            (content_id, row.phrase_num, mpid or 0, row.macro_id)
                        )
                continue
            if len(phases) == 1:
                unambiguous += 1
            else:
                ambiguous += 1
                if mpid is not None:
                    ambiguous_by_pattern[mpid] += 1

    return ReverseLookupResult(
        total_rows=total,
        unambiguous=unambiguous,
        ambiguous=ambiguous,
        not_found=not_found,
        ambiguous_by_pattern=ambiguous_by_pattern,
        not_found_is_override=not_found_is_override,
        not_found_other=not_found_other,
        not_found_other_examples=not_found_other_examples,
    )


# ---------------------------------------------------------------------------
# Part 2 — is phrase_num -> phase a per-(pattern, N) lookup table?
# ---------------------------------------------------------------------------


@dataclass
class TrackResolution:
    """One track's phrase_data rows resolved to phases via the
    first-matching-phase convention. `resolved` is False if any row's
    macro_id was not found in the pattern's macro_assign at all (a
    phrase-level override, or another unresolved case from Part 1).
    """

    content_id: int
    macro_pattern_id: int
    phrase_count: int
    phases: list[int]
    resolved: bool
    has_override: bool


def resolve_tracks(
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_first: dict[int, dict[int, int]],
) -> list[TrackResolution]:
    results = []
    for content_id, rows in phrase_by_content.items():
        info = content_info.get(content_id)
        mpid = info.macro_pattern_id if info else None
        has_override = any(r.macro_id != r.initial_macro_id for r in rows)
        rev = reverse_first.get(mpid, {}) if mpid is not None else {}
        phases: list[int] = []
        ok = True
        for row in sorted(rows, key=lambda r: r.phrase_num):
            phase = rev.get(row.macro_id)
            if phase is None:
                ok = False
                break
            phases.append(phase)
        results.append(
            TrackResolution(
                content_id=content_id,
                macro_pattern_id=mpid or 0,
                phrase_count=len(rows),
                phases=phases if ok else [],
                resolved=ok and not has_override,
                has_override=has_override,
            )
        )
    return results


@dataclass
class GroupConsistency:
    macro_pattern_id: int
    phrase_count: int
    track_count: int
    distinct_sequences: int
    mode_sequence: tuple[int, ...]
    mode_pct: float


@dataclass
class Part2Result:
    track_phrase_count_dist: Counter[int]
    pattern_phrase_count_dist: dict[int, Counter[int]]
    n_phases_of_pattern: dict[int, int]
    n_lt_phases: int  # tracks with FEWER phrases than their bank has phases
    n_eq_phases: int  # tracks with phrase count == bank phase count
    n_gt_phases: int  # tracks with MORE phrases than their bank has phases
    identity_match_when_eq: int
    identity_total_when_eq: int
    groups_considered: int
    groups_consistent: int
    groups_inconsistent: int
    worst_inconsistent_groups: list[GroupConsistency]  # by track_count desc
    excluded_override_tracks: int
    excluded_unresolved_tracks: int


def run_part2(
    resolutions: list[TrackResolution],
    n_phases_of_pattern: dict[int, int],
    min_group_size: int = MIN_GROUP_SIZE_FOR_REPORT,
) -> Part2Result:
    track_phrase_count_dist: Counter[int] = Counter()
    pattern_phrase_count_dist: dict[int, Counter[int]] = defaultdict(Counter)
    excluded_override = 0
    excluded_unresolved = 0
    n_lt = n_eq = n_gt = 0
    identity_match = identity_total = 0

    group_sequences: dict[tuple[int, int], Counter[tuple[int, ...]]] = defaultdict(
        Counter
    )

    for res in resolutions:
        track_phrase_count_dist[res.phrase_count] += 1
        pattern_phrase_count_dist[res.macro_pattern_id][res.phrase_count] += 1

        if res.has_override:
            excluded_override += 1
            continue
        if not res.resolved:
            excluded_unresolved += 1
            continue

        n_phases = n_phases_of_pattern.get(res.macro_pattern_id)
        if n_phases is not None:
            if res.phrase_count < n_phases:
                n_lt += 1
            elif res.phrase_count == n_phases:
                n_eq += 1
                identity_total += 1
                if res.phases == list(range(1, res.phrase_count + 1)):
                    identity_match += 1
            else:
                n_gt += 1

        key = (res.macro_pattern_id, res.phrase_count)
        group_sequences[key][tuple(res.phases)] += 1

    groups_considered = 0
    groups_consistent = 0
    groups_inconsistent = 0
    inconsistent_detail: list[GroupConsistency] = []
    for (mpid, n), seq_counter in group_sequences.items():
        track_count = sum(seq_counter.values())
        if track_count < min_group_size:
            continue
        groups_considered += 1
        if len(seq_counter) == 1:
            groups_consistent += 1
        else:
            groups_inconsistent += 1
            mode_seq, mode_count = seq_counter.most_common(1)[0]
            inconsistent_detail.append(
                GroupConsistency(
                    macro_pattern_id=mpid,
                    phrase_count=n,
                    track_count=track_count,
                    distinct_sequences=len(seq_counter),
                    mode_sequence=mode_seq,
                    mode_pct=round(100 * mode_count / track_count, 1),
                )
            )
    inconsistent_detail.sort(key=lambda g: -g.track_count)

    return Part2Result(
        track_phrase_count_dist=track_phrase_count_dist,
        pattern_phrase_count_dist=dict(pattern_phrase_count_dist),
        n_phases_of_pattern=n_phases_of_pattern,
        n_lt_phases=n_lt,
        n_eq_phases=n_eq,
        n_gt_phases=n_gt,
        identity_match_when_eq=identity_match,
        identity_total_when_eq=identity_total,
        groups_considered=groups_considered,
        groups_consistent=groups_consistent,
        groups_inconsistent=groups_inconsistent,
        worst_inconsistent_groups=inconsistent_detail[:15],
        excluded_override_tracks=excluded_override,
        excluded_unresolved_tracks=excluded_unresolved,
    )


# ---------------------------------------------------------------------------
# Part 3 — ANLZ PSSI: does phrase KIND predict phase better than phrase_num?
# ---------------------------------------------------------------------------


def read_pssi_content(analysis_data_path: str | None) -> Any | None:
    """Read the `PSSI` (song structure) tag's `.content` straight out of a
    track's own `ANLZ0000.EXT` cache file — the exact mechanism
    `e1d2_candidate_tracks.py`'s `phrase_count_from_analysis` already
    demonstrated (path resolution under `ANALYSIS_SHARE_ROOT`,
    `AnlzFile.parse_file`, scanning `parsed.tags` for the PSSI type).
    That function only returns `len_entries` (the phrase count); this
    probe additionally needs each entry's `kind` and sub-kind flags, so it
    returns the tag's full parsed `.content` rather than reinventing the
    file-reading path.
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
            return tag.content
    return None


#: The sub-kind key: PSSI's `SongStructureEntry.kind` field alone collapses
#: several genuinely distinct phrase variants observed in the LIGHTINGDB
#: mapping (e.g. one raw `kind` value maps to 3 different phases in the
#: 11-phase HIGH-energy banks). The struct's `k1`/`k2`/`k3`/`b` fields are
#: otherwise-unlabelled per-entry flags that, empirically, disambiguate
#: exactly these cases — see the report for the worked examples. This
#: type alias documents that the 5-tuple, not `kind` alone, is the unit
#: this probe found to be phase-deterministic.
SubkindKey = tuple[int, int, int, int, int]


def subkind_key_of(entry: Any) -> SubkindKey:
    return (int(entry.kind), int(entry.k1), int(entry.k2), int(entry.k3), int(entry.b))


@dataclass
class PssiSampleResult:
    tracks_with_song_id: int
    tracks_resolving_to_master: int
    tracks_with_pssi: int
    mood_energy_match: int
    mood_energy_total: int
    bank_field_distribution: Counter[int]
    len_entries_match_n: int
    len_entries_checked: int
    len_entries_mismatch_examples: list[
        tuple[int, int, int]
    ]  # content_id, N, len_entries
    tracks_used_for_subkind_table: int
    subkind_table: dict[
        int, dict[SubkindKey, Counter[int]]
    ]  # mpid -> subkind -> phase counter


def run_pssi_sample(
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    reverse_first: dict[int, dict[int, int]],
    master_tracks: dict[int, Any],
    analysis_paths: dict[int, str | None],
    pattern_energy: dict[int, tuple[int, int]],
    *,
    max_tracks: int | None = None,
) -> PssiSampleResult:
    tracks_with_song_id = 0
    tracks_resolving = 0
    tracks_with_pssi = 0
    mood_match = 0
    mood_total = 0
    bank_dist: Counter[int] = Counter()
    len_match = 0
    len_checked = 0
    len_mismatch_examples: list[tuple[int, int, int]] = []
    tracks_used = 0

    subkind_table: dict[int, dict[SubkindKey, Counter[int]]] = defaultdict(
        lambda: defaultdict(Counter)
    )

    scanned = 0
    for content_id, rows in sorted(phrase_by_content.items()):
        info = content_info.get(content_id)
        if info is None:
            continue
        tracks_with_song_id += 1
        mpid = info.macro_pattern_id
        has_override = any(r.macro_id != r.initial_macro_id for r in rows)
        if has_override:
            continue
        if info.song_id not in master_tracks:
            continue
        tracks_resolving += 1

        path = analysis_paths.get(info.song_id)
        content = read_pssi_content(path)
        if content is None:
            continue
        tracks_with_pssi += 1

        scanned += 1
        if max_tracks is not None and scanned > max_tracks:
            break

        n = len(rows)
        _pattern, energy = pattern_energy.get(mpid, (None, None))
        mood_total += 1
        if int(content.mood) == energy:
            mood_match += 1
        bank_dist[int(content.bank)] += 1

        len_checked += 1
        if int(content.len_entries) == n:
            len_match += 1
        elif len(len_mismatch_examples) < 15:
            len_mismatch_examples.append((content_id, n, int(content.len_entries)))

        rev = reverse_first.get(mpid, {})
        phases: list[int] = []
        ok = True
        for row in sorted(rows, key=lambda r: r.phrase_num):
            phase = rev.get(row.macro_id)
            if phase is None:
                ok = False
                break
            phases.append(phase)
        if not ok or int(content.len_entries) != n:
            continue

        tracks_used += 1
        for entry, phase in zip(content.entries, phases):
            key = subkind_key_of(entry)
            subkind_table[mpid][key][phase] += 1

    return PssiSampleResult(
        tracks_with_song_id=tracks_with_song_id,
        tracks_resolving_to_master=tracks_resolving,
        tracks_with_pssi=tracks_with_pssi,
        mood_energy_match=mood_match,
        mood_energy_total=mood_total,
        bank_field_distribution=bank_dist,
        len_entries_match_n=len_match,
        len_entries_checked=len_checked,
        len_entries_mismatch_examples=len_mismatch_examples,
        tracks_used_for_subkind_table=tracks_used,
        subkind_table={mpid: dict(d) for mpid, d in subkind_table.items()},
    )


@dataclass
class SubkindKeyStat:
    subkind: SubkindKey
    n_obs: int
    mode_phase: int
    mode_pct: float
    distinct_phases: int
    distribution: dict[int, int]


@dataclass
class SubkindTableSummary:
    per_pattern: dict[int, list[SubkindKeyStat]]
    total_keys: int
    fully_consistent_keys: int
    weighted_obs: int
    weighted_mode_matches: int

    @property
    def fully_consistent_pct(self) -> float:
        return round(100 * self.fully_consistent_keys / self.total_keys, 1)

    @property
    def weighted_accuracy_pct(self) -> float:
        return round(100 * self.weighted_mode_matches / self.weighted_obs, 2)


def summarize_subkind_table(
    subkind_table: dict[int, dict[SubkindKey, Counter[int]]],
) -> SubkindTableSummary:
    per_pattern: dict[int, list[SubkindKeyStat]] = {}
    total_keys = 0
    consistent_keys = 0
    weighted_obs = 0
    weighted_mode = 0

    for mpid, keys in subkind_table.items():
        stats = []
        for subkind, counter in sorted(keys.items()):
            total_keys += 1
            n_obs = sum(counter.values())
            mode_phase, mode_count = counter.most_common(1)[0]
            weighted_obs += n_obs
            weighted_mode += mode_count
            if len(counter) == 1:
                consistent_keys += 1
            stats.append(
                SubkindKeyStat(
                    subkind=subkind,
                    n_obs=n_obs,
                    mode_phase=mode_phase,
                    mode_pct=round(100 * mode_count / n_obs, 1),
                    distinct_phases=len(counter),
                    distribution=dict(counter),
                )
            )
        per_pattern[mpid] = stats

    return SubkindTableSummary(
        per_pattern=per_pattern,
        total_keys=total_keys,
        fully_consistent_keys=consistent_keys,
        weighted_obs=weighted_obs,
        weighted_mode_matches=weighted_mode,
    )


@dataclass
class PssiFieldCheck:
    """u1..u5 are documented in pyrekordbox's PSSI struct as unnamed
    filler bytes. This check confirms (or refutes) that they carry no
    signal in this library — if any are ever nonzero, the subkind key
    above would be incomplete.
    """

    tracks_scanned: int
    nonzero_counts: Counter[str]


def run_unused_field_check(
    content_info: dict[int, ContentInfo],
    phrase_by_content: dict[int, list[PhraseRow]],
    master_tracks: dict[int, Any],
    analysis_paths: dict[int, str | None],
    *,
    max_tracks: int = 500,
) -> PssiFieldCheck:
    nonzero: Counter[str] = Counter()
    scanned = 0
    for content_id in phrase_by_content:
        info = content_info.get(content_id)
        if info is None or info.song_id not in master_tracks:
            continue
        content = read_pssi_content(analysis_paths.get(info.song_id))
        if content is None:
            continue
        scanned += 1
        for entry in content.entries:
            for field_name in ("u1", "u2", "u3", "u4", "u5"):
                if getattr(entry, field_name):
                    nonzero[field_name] += 1
        if scanned >= max_tracks:
            break
    return PssiFieldCheck(tracks_scanned=scanned, nonzero_counts=nonzero)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def print_report(
    part1: ReverseLookupResult,
    part2: Part2Result,
    pssi: PssiSampleResult,
    subkind_summary: SubkindTableSummary,
    field_check: PssiFieldCheck,
    pattern_energy: dict[int, tuple[int, int]],
) -> None:
    """Console summary. NOT the deliverable — see
    docs/experiments/E1e-phrase-phase-mapping.md.
    """
    print("=" * 70)
    print("Part 1 — macro_id -> phase reverse lookup ambiguity")
    print("=" * 70)
    print(f"total phrase_data rows: {part1.total_rows}")
    print(f"  unambiguous (1 phase):   {part1.unambiguous} ({part1.unambiguous_pct}%)")
    print(f"  ambiguous (>1 phase):    {part1.ambiguous} ({part1.ambiguous_pct}%)")
    print(
        f"  not found in macro_assign at all: {part1.not_found} ({part1.not_found_pct}%)"
    )
    print(
        f"    of not-found: {part1.not_found_is_override} are phrase-level overrides "
        f"(macro_id != initial_macro_id), {part1.not_found_other} are unexplained"
    )
    print("ambiguous rows by macro_pattern_id:")
    for mpid, count in part1.ambiguous_by_pattern.most_common():
        print(f"    mpid={mpid} ({bank_energy_label(mpid, pattern_energy)}): {count}")
    if part1.not_found_other_examples:
        print(
            "unexplained not-found examples (content_id, phrase_num, mpid, macro_id):"
        )
        for ex in part1.not_found_other_examples:
            print(f"    {ex}")

    print()
    print("=" * 70)
    print("Part 2 — is phrase_num -> phase a stable per-(pattern, N) table?")
    print("=" * 70)
    print(
        f"tracks excluded (has phrase-level override): {part2.excluded_override_tracks}, "
        f"excluded (unresolved macro_id): {part2.excluded_unresolved_tracks}"
    )
    print(
        f"track phrase-count vs bank phase-count: fewer={part2.n_lt_phases} "
        f"equal={part2.n_eq_phases} more={part2.n_gt_phases}"
    )
    print(
        f"identity check (phrase_num==phase) when track N == bank phase count: "
        f"{part2.identity_match_when_eq}/{part2.identity_total_when_eq}"
        + (
            f" ({round(100 * part2.identity_match_when_eq / part2.identity_total_when_eq, 1)}%)"
            if part2.identity_total_when_eq
            else ""
        )
    )
    print(
        f"(pattern, N) groups with >= {MIN_GROUP_SIZE_FOR_REPORT} tracks: "
        f"{part2.groups_considered} — consistent (1 sequence): {part2.groups_consistent}, "
        f"inconsistent: {part2.groups_inconsistent}"
    )
    print("largest inconsistent groups (by track count):")
    for g in part2.worst_inconsistent_groups:
        print(
            f"    mpid={g.macro_pattern_id} N={g.phrase_count} tracks={g.track_count} "
            f"distinct_sequences={g.distinct_sequences} mode_pct={g.mode_pct}%"
        )
    print("track phrase-count distribution (top 15 by frequency):")
    for n, count in part2.track_phrase_count_dist.most_common(15):
        print(f"    N={n}: {count}")

    print()
    print("=" * 70)
    print("Part 3 — ANLZ PSSI: kind vs phrase_num as a phase predictor")
    print("=" * 70)
    print(
        f"tracks with a content row: {pssi.tracks_with_song_id}, resolving to "
        f"master.db: {pssi.tracks_resolving_to_master}, with a readable PSSI tag: "
        f"{pssi.tracks_with_pssi}"
    )
    print(
        f"PSSI mood == macro_pattern.energy: {pssi.mood_energy_match}/"
        f"{pssi.mood_energy_total} "
        f"({round(100 * pssi.mood_energy_match / pssi.mood_energy_total, 1)}%)"
        if pssi.mood_energy_total
        else "PSSI mood == energy: n/a"
    )
    print(f"PSSI 'bank' field distribution: {dict(pssi.bank_field_distribution)}")
    print(
        f"PSSI len_entries == phrase_data row count: {pssi.len_entries_match_n}/"
        f"{pssi.len_entries_checked} "
        f"({round(100 * pssi.len_entries_match_n / pssi.len_entries_checked, 1)}%)"
        if pssi.len_entries_checked
        else "len_entries match: n/a"
    )
    print(
        "len_entries mismatch examples (content_id, phrase_data_N, pssi_len_entries):"
    )
    for mismatch_ex in pssi.len_entries_mismatch_examples:
        print(f"    {mismatch_ex}")
    print(
        f"tracks used to build the subkind->phase table: {pssi.tracks_used_for_subkind_table}"
    )
    print(
        f"u1..u5 nonzero across {field_check.tracks_scanned} scanned tracks: "
        f"{dict(field_check.nonzero_counts) or '(always zero)'}"
    )

    print()
    print(
        f"subkind (kind,k1,k2,k3,b) -> phase: {subkind_summary.total_keys} distinct keys, "
        f"{subkind_summary.fully_consistent_keys} fully consistent "
        f"({subkind_summary.fully_consistent_pct}%); weighted (row-level) accuracy "
        f"{subkind_summary.weighted_mode_matches}/{subkind_summary.weighted_obs} "
        f"({subkind_summary.weighted_accuracy_pct}%)"
    )
    print("full subkind -> phase table, per macro_pattern_id:")
    for mpid, stats in sorted(subkind_summary.per_pattern.items()):
        print(f"  mpid={mpid} ({bank_energy_label(mpid, pattern_energy)}):")
        for s in stats:
            flag = "" if s.distinct_phases == 1 else f" INCONSISTENT{s.distribution}"
            print(
                f"    subkind={s.subkind} n_obs={s.n_obs} -> phase={s.mode_phase} "
                f"({s.mode_pct}%){flag}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-pssi-tracks",
        type=int,
        default=None,
        help="Cap on how many tracks to read ANLZ PSSI data for (default: no cap, "
        "reads every eligible track — see Part 3).",
    )
    args = parser.parse_args()

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
    finally:
        master_conn.close()

    macro_db3 = Path("work/macro.db3")
    user_db3 = Path("work/user.db3")

    assign_by_pattern = load_macro_assign_by_pattern(macro_db3)
    reverse_all = build_reverse_lookup_all_phases(assign_by_pattern)
    reverse_first = build_reverse_lookup_first_phase(assign_by_pattern)
    n_phases_of_pattern = {mpid: len(rows) for mpid, rows in assign_by_pattern.items()}
    pattern_energy = load_pattern_energy(macro_db3)

    content_info = load_content_info(user_db3)
    phrase_by_content = load_phrase_data_by_content(user_db3)

    part1 = run_reverse_lookup_classification(
        content_info, phrase_by_content, reverse_all
    )

    resolutions = resolve_tracks(content_info, phrase_by_content, reverse_first)
    part2 = run_part2(resolutions, n_phases_of_pattern)

    pssi = run_pssi_sample(
        content_info,
        phrase_by_content,
        reverse_first,
        master_tracks,
        analysis_paths,
        pattern_energy,
        max_tracks=args.max_pssi_tracks,
    )
    subkind_summary = summarize_subkind_table(pssi.subkind_table)
    field_check = run_unused_field_check(
        content_info, phrase_by_content, master_tracks, analysis_paths
    )

    print_report(part1, part2, pssi, subkind_summary, field_check, pattern_energy)


if __name__ == "__main__":
    main()
