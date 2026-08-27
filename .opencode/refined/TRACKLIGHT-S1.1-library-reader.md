---
epic: "TRACKLIGHT"
title: "Library reader module — promote E1 probe to production"
estimate: M
status: ready
created: 2026-08-26
depends_on: ["E1c"]
labels: [library, database, safety, schema]
priority: P1
claimed_by:
claimed_by_date:
---

## 1. User Story

**As a** tool user\
**I want** to read track metadata from rekordbox's encrypted `master.db` and identify tracks by ID or by fingerprint (ANLZ phrase-kind matching) when ID fails\
**So that** every subsequent stage can resolve library tracks to genre, BPM, key, rating, and My Tag categories without duplicating the join logic, and can address permanently-unidentifiable tracks as a separate category

## 2. Business Context & Value

E1-E1f proved that track identity requires two mechanisms: direct `content.song_id` → `DjmdContent.ID` lookup (fast, correct when it resolves) and fingerprint-based recovery when ID fails (matching ANLZ `PSSI` phrase kinds + sequence length against known banks). The probe code currently lives in `src/rbxlight/experiments/` as disposable investigation. This story promotes it into a reusable production module so S1.2, S1.3, and S1.4 can depend on it and know which tracks are addressable and which are unidentifiable forever.

**Measured baseline (E1c-E1f):**
- Total library tracks: 7,615
- Total lit tracks (`content` rows): 2,972 (39.0% upper bound)
- ID-resolvable: 1,188 of 2,972
- Stranded (non-resolving): 1,784 of 2,972
- Recovered by fingerprint bridge (99.68% precision on 927/930 known-answer rows): 893 of 1,784, identifying 893 distinct library tracks
- **True addressable set: 2,081 of 7,615 library tracks (27.3%)** — both identified by ID and by fingerprint, proven unambiguously
- Upper-bound lit but unidentifiable: ~889 tracks (stranded rows that the fingerprint bridge cannot resolve unambiguously)
- My Tag coverage in the recovered (fingerprint-identified) population: 49.5%

Once built, `src/rbxlight/experiments/e1_library_join.py`, `e1b_real_denominator.py`, `e1c_after_full_analysis.py`, `e1d_lighting_mode_row_creation.py`, `e1d2_candidate_tracks.py`, `e1d2_lighting_mode_rerun.py`, `e1e_phrase_phase_mapping.py`, and `e1f_fingerprint_bridge.py` are **deleted**. The probe code is disposable; the verdicts in `docs/experiments/` are permanent.

## 3. Acceptance Criteria

* [ ] **Scenario 1: Successful connection and decryption**
    * Given the working copy `work/master.db` exists and is a valid SQLCipher 3 file
    * When the library module is imported and initialized with the database path
    * Then the module successfully decrypts and opens a read-only connection

* [ ] **Scenario 2: Track lookup by song_id returns all required fields (ID path)**
    * Given a song_id that resolves to a `DjmdContent` row
    * When calling the lookup function with that song_id
    * Then the result contains: ID3 genre name, BPM as a real number (not scaled ×100), musical key, rating, all My Tag names grouped by their parent category (Mood, Situation, Genres, Components), **and identity method = "ID"**

* [ ] **Scenario 3: Multi-valued Genres remain intact**
    * Given a track with multiple genre tags (e.g., `Genres: Urban, Deep House`)
    * When looking up that track
    * Then both genres appear in the returned `Genres` category, never collapsed to one

* [ ] **Scenario 4: Unresolvable song_id triggers fingerprint bridge lookup**
    * Given a `content.song_id` that does not exist in `DjmdContent`
    * When performing bulk load and encountering that row
    * Then the reader: (1) extracts the track's ANLZ file via `DjmdContent.AnalysisDataPath`, (2) reads its PSSI phrase kinds, (3) matches predicted sequence + phrase count against other `content` rows in the same bank, (4) returns one of three outcomes: **identified by fingerprint** (exactly one match, marked with identity method = "fingerprint"), **ambiguous** (multiple candidates, listed without guessing), or **unidentifiable** (zero matches or unreadable ANLZ)

* [ ] **Scenario 5: Bulk load covers the addressable set efficiently**
    * Given the library module is initialized
    * When calling bulk_load() to retrieve all lit tracks
    * Then identified and fingerprint-recovered tracks are returned keyed by content.id or song_id, unidentifiable and ambiguous tracks are reported with their identity status, and the operation completes within reasonable time. Coverage report shows counts for ID-identified, fingerprint-identified, ambiguous, unidentifiable, and total.

* [ ] **Scenario 6: Read-only by construction**
    * Given the library module is in use
    * When inspecting any code path (including test fixtures)
    * Then no code path opens a write handle, issues an UPDATE/DELETE/INSERT, or modifies `master.db` in any way

* [ ] **Scenario 7: testable with unencrypted fixture database**
    * Given a test fixture with the same table structure as `master.db` but unencrypted
    * When the library module is injected with that connection instead of opening the live file
    * Then all lookup and bulk_load tests pass without requiring a real `master.db` or its key

* [ ] **Edge Case: SQLCipher key is not available**
    * Given the static key is unknown and `pyrekordbox` is not installed
    * When the library module is initialized
    * Then it fails with a clear, actionable error message naming the missing dependency

## 4. Technical Constraints

> ⚠️ Describe WHAT is needed, not HOW. No class names, method signatures, DTO shapes, or endpoint paths.
> The implementing agents + architecture skill decide those.

* **Database access**: Guard that rekordbox is not running before opening `master.db`. Copy `~/Library/Pioneer/rekordbox/master.db` to `work/master.db` (read-only). Connect via SQLCipher using the known static key or document the `pyrekordbox download-key` fallback. **Never open the live file. Never write.** ANLZ files are read-only, same posture as `master.db`.

* **Dual-path identity resolution**: (1) ID path: Join `DjmdContent.ID` with `content.song_id` to retrieve genre (via `DjmdGenre.Name`), BPM (divide stored integer by 100), key, rating, My Tags. (2) Fingerprint path for unresolved rows: for each unresolvable `content` row, read its track's ANLZ file via `DjmdContent.AnalysisDataPath`, extract the PSSI phrase kinds (`kind, k1, k2, k3, b`), look up the predicted phase sequence per `macro_pattern_id` (using the E1e-validated table), count the phrases, and match both sequence and count against other `content` rows in the same bank. Return exactly one match as "identified by fingerprint", multiple matches as "ambiguous" (list all candidates), zero or unreadable ANLZ as "unidentifiable".

* **Metadata shape**: Return a track metadata record carrying: genre (list, multi-valued), BPM (real number), key, rating, my_tags (dict of category → list of tag names), **identity_method** ("ID", "fingerprint", "ambiguous", or "unidentifiable"), and for ambiguous/unidentifiable rows, the reason and any partial match candidates.

* **Dependency injection**: The connection must be an injected dependency so test code can supply a plain SQLite fixture instead of a real encrypted `master.db`.

* **Coverage reporting**: Expose a method that returns counts of: ID-identified tracks, fingerprint-identified tracks, ambiguous matches, unidentifiable rows, total `content` rows, and total library tracks. Report the true addressable ceiling (2,081 of 7,615 = 27.3%) alongside counts. Broken-out coverage helps downstream stories (S1.2, S1.3) understand what is reachable and what is lost forever.

* **Optional dependency**: `pyrekordbox` and `pycryptodome` (SQLCipher's dependency) are optional. If the group is not installed, the library module must not be importable, and any command requiring it must say so clearly rather than failing at runtime.

## 5. Design & UI/UX

The module has no UI. The CLI that uses it (S1.3) is responsible for presenting coverage reports to the user.

## 6. Scope & Context

### What exists today

- `src/rbxlight/experiments/e1_library_join.py` — the probe code that proves the join works. Its logic is correct; the story is to move it into a production home.
- Verdict files in `docs/experiments/` — these record the measured coverage and are permanent.
- `pyrekordbox` is already an optional dependency group (for optional commands that need master.db access).

### Domain rules (non-negotiable)

- **`master.db` and ANLZ files are read-only forever** — rekordbox is the authority, and our assignment logic is downstream of it.
- **ID lookup is the fast path; fingerprint is the recovery path.** Report three outcomes separately: identified by ID, identified by fingerprint, or unidentifiable. This allows downstream stories to refuse writes to unidentifiable tracks.
- **Fingerprint precision is 99.68% on known-answer rows (927/930).** Ambiguous matches (multiple candidates) are surfaced as ambiguous, never silently resolved to the first match. Unidentifiable rows (zero matches, unreadable ANLZ, or PSSI/phrase-count drift) are reported as unidentifiable — never guessed at.
- **The true addressable ceiling is 2,081 of 7,615 tracks (27.3%),** not earlier claims of 1,183 (ID-only). This is the honest floor of what any tool can safely rewrite. Some lit tracks are permanently unidentifiable; those must never be touched.
- **My Tags are never written** — they are the DJ's live filtering vocabulary, off limits. Read only.
- **Multi-valued Genres must survive** — tracks legitimately carry several genre tags; collapsing to one silently is data loss.

### Known edge cases

- Tracks with no My Tags at all — valid, will have an empty dict in the result.
- Tracks with a genre ID that does not resolve to a name — handle gracefully (ID3 genre field may be broken).
- SQLCipher key is missing — this is an operational issue, not a code defect; fail with a clear error.

## 7. Test Impact Analysis

**Greenfield story** — no existing code is refactored or moved, so no existing tests are affected. Tests are newly written.

### Test files to be created

- New tests for the library module, covering:
  - Successful decryption and connection (smoke test)
  - Single track lookup with all fields present
  - Bulk load of entire fixture library
  - Unresolvable song_id handling in bulk load
  - Multi-valued Genres preservation
  - Coverage report accuracy
  - Read-only enforcement (no write paths)
  - Injected connection with unencrypted fixture
  - Missing key error handling

### Cleanup impact

| File | Action |
|------|--------|
| `src/rbxlight/experiments/e1_library_join.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1b_real_denominator.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1c_after_full_analysis.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1d_lighting_mode_row_creation.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1d2_candidate_tracks.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1d2_lighting_mode_rerun.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1e_phrase_phase_mapping.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/e1f_fingerprint_bridge.py` | **Delete** after this module lands |
| `src/rbxlight/experiments/__init__.py` | **Delete** the experiments optional-dependency group |
| `docs/experiments/E1*.md` | Keep (verdicts are permanent) |
| `docs/experiments/E1d*.md` | Keep (verdicts are permanent) |
| `docs/experiments/E1e*.md` | Keep (verdicts are permanent) |
| `docs/experiments/E1f*.md` | Keep (verdicts are permanent) |

## 8. Mandatory Skills for Implementation

- `rekordbox-data-safety` — guard rekordbox-not-running, safe copy, read-only enforcement
- `rekordbox-lightingdb-schema` — `master.db` table layout, column meanings, join semantics
- `rekordbox-lighting-architecture` — module placement, import patterns, optional dependency groups
