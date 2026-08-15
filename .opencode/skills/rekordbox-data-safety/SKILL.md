---
name: rekordbox-data-safety
description: MANDATORY safety rules for reading/writing Pioneer rekordbox LightingDB files. Load BEFORE any code that opens, reads, or writes macro.db3, user.db3, or master.db3. Covers backups, process guards, dry-run, and rollback.
metadata:
  skill-type: safety
  language: python
  project-type: data-tool
---

# rekordbox Data Safety

You are the safety layer standing between this tool and a working DJ's live light show. `macro.db3` and `user.db3` at `~/Library/Application Support/Pioneer/rekordbox6/LightingDB/` are LIVE, IRREPLACEABLE user data — years of programmed macros, venue patches, and per-track phrase assignments, built by hand and used in real performances. There is no upstream copy. If you corrupt these files, the user's next gig has no light show. Every rule below exists to make that outcome structurally impossible, not just unlikely.

## NON-NEGOTIABLE RULES

1. **TIMESTAMPED BACKUP BEFORE ANY WRITE.** No backup, no write — full stop. Back up `macro.db3` and `user.db3` (plus `master.db3` metadata only, per rule 4) to a versioned backup dir before opening either file read-write. NEVER rely on rekordbox's own `macro_old.db3` / `master_old.db3` — those belong to rekordbox and it overwrites them on its own schedule, not yours. If your backup and rekordbox's backup are the same file, you have zero backups.

2. **ABORT IF REKORDBOX IS RUNNING.** Run `pgrep -x rekordbox` before ANY read-write open, every time, no exceptions. rekordbox holds these DBs open and flushes its in-memory state to disk on exit — an external edit made while it's running gets silently clobbered the moment the user quits the app. Reads taken mid-session are also unreliable (rekordbox's in-memory state may not match what's on disk yet).

3. **READS ARE READ-ONLY BY DEFAULT.** Always open with the URI form: `sqlite3.connect("file:...?mode=ro", uri=True)`. A read path must be physically incapable of writing — not "written carefully to only SELECT," but structurally unable to execute a write. This is a hard constraint enforced by SQLite itself, not by code review.

4. **NEVER WRITE `master.db3`.** It is the 512MB factory fixture-profile library. Read-only reference, always. There is no legitimate write path to this file in this tool.

5. **NEVER MODIFY `preset=1` ROWS.** Factory macros are ids `1..916` plus id `-1` and id `10000`. User macros are `preset=0` with `id >= 10001`. New macros allocate `id = max(id) + 1`, starting from `10001`. Any write touching a `preset=1` row is a bug — treat it as such and abort the transaction.

6. **ALL WRITES IN A SINGLE TRANSACTION.** Begin, apply, verify, commit. Any exception anywhere in that sequence rolls back the whole thing. Partial writes are how a 25-row macro becomes a 12-row macro that crashes rekordbox on load.

7. **DRY-RUN BY DEFAULT.** Every mutating command prints a diff/plan and changes nothing unless an explicit `--write` (or `--commit`) flag is passed. There is no implicit write, anywhere, ever. If a user runs a command without the flag, the filesystem is untouched.

8. **RESTORE MUST EXIST BEFORE WRITE DOES.** A `restore` command that rolls back to any timestamped backup must be implemented and tested BEFORE any write command ships. Shipping a write path without a working, tested restore path is the one mistake this project cannot recover from.

9. **WORK ON A COPY, NOT ON LIVE.** All development, generation, and experimentation runs against the working copy in `work/`. The live databases are touched by exactly two commands: `pull` (live -> work) and `push` (work -> live). No other code path opens a live database read-write, ever.

10. **PUSH IS STALE-WRITE PROTECTED.** `pull` records the sha256 of each live DB at the moment it copied. `push` re-hashes live and REFUSES if the hash no longer matches — meaning rekordbox or the user changed something since the pull, and pushing would silently destroy it. Overriding requires an explicit `--force` plus a fresh backup. This is optimistic locking; treat a hash mismatch as a hard stop, not a warning.

## Backup layout

```
backups/
  2026-08-14T193000Z/
    macro.db3
    user.db3
    master.db3.meta.json      # metadata only — see below, never a full copy
    manifest.json
```

`manifest.json`:

```json
{
  "timestamp": "2026-08-14T19:30:00Z",
  "trigger_command": "rbxlight macro create --write --name 'HIGH DROP1'",
  "files": {
    "macro.db3": {
      "source": "/Users/<user>/Library/Application Support/Pioneer/rekordbox6/LightingDB/macro.db3",
      "sha256": "…",
      "bytes": 10276352
    },
    "user.db3": {
      "source": ".../user.db3",
      "sha256": "…",
      "bytes": 13631488
    }
  }
}
```

`master.db3` is 512MB and read-only (rule 4) — never copy it wholesale. Instead record a metadata snapshot (`sha256` + `bytes` + `lighting_property` row values if present) so `restore` and future runs can detect "master.db3 changed since we last looked," without paying the cost of duplicating half a gigabyte per backup.

The sha256 per file buys two things:
- `restore` can verify a backup is intact before writing it back over live data.
- Any command can hash the live file at startup and compare to the last known backup hash — if they differ, rekordbox (or something else) touched the file since our last backup, and that's a signal to take a fresh backup before proceeding rather than trust a stale one.

Note: `push` backs up LIVE, not `work/` — the backup is a restore point for the files about to be overwritten, so it is only ever a snapshot of what's currently on disk in LightingDB.

## Working copy model

```
work/
  macro.db3          copy of live
  user.db3           copy of live
  .pull-state.json   {pulled_at, source_paths, sha256 per file, rbxlight version}
```

- `work/*.db3` is GITIGNORED — 23MB of binary re-committed on every change bloats the repo, and it is reproducible via `pull`. Golden XML fixtures under `tests/fixtures/` are text and ARE committed.
- `master.db3` (512MB) is NEVER copied into `work/`. If it is ever needed, read it read-only from its live path.
- `pull` requires rekordbox to be closed (same guard as any write) — copying a DB mid-session can capture a torn/incomplete state.
- `push` runs the FULL safety chain: guard rekordbox not running -> backup live -> verify pull-state hashes -> copy/apply inside a transaction -> verify by re-read -> print the restore command.
- Direction is always explicit. There is no "sync" command, no auto-detect, no merge. Ambiguous direction is how live data gets destroyed.

Staleness check, run at the top of `push` before touching anything:

```python
class StaleWorkingCopyError(RuntimeError):
    """Live DB changed since the last pull — push refused."""


def verify_not_stale(work_dir: Path) -> None:
    state = json.loads((work_dir / ".pull-state.json").read_text())
    for name, recorded in state["source_paths"].items():
        live_path = Path(recorded)
        current_hash = _sha256(live_path)
        expected_hash = state["sha256"][name]
        if current_hash != expected_hash:
            raise StaleWorkingCopyError(
                f"{name} has changed on live since the last pull "
                f"(expected sha256 {expected_hash[:12]}…, found {current_hash[:12]}…). "
                f"rekordbox or something else touched it — run `rbxlight pull` again "
                f"before pushing, or pass --force after taking a fresh backup."
            )
```

## Code patterns

Stdlib `sqlite3` only, no ORM.

```python
import subprocess
import sqlite3
import shutil
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LIGHTINGDB = Path.home() / "Library/Application Support/Pioneer/rekordbox6/LightingDB"
BACKUP_ROOT = Path("backups")


class RekordboxRunningError(RuntimeError):
    """rekordbox.app is running — refuse to open DBs read-write."""


def guard_rekordbox_not_running() -> None:
    result = subprocess.run(["pgrep", "-x", "rekordbox"], capture_output=True)
    if result.returncode == 0:
        raise RekordboxRunningError(
            "rekordbox is running. Quit it fully before writing to LightingDB — "
            "it flushes its own in-memory state on exit and will clobber this write."
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def backup_all(trigger_command: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    dest = BACKUP_ROOT / ts
    dest.mkdir(parents=True, exist_ok=False)

    manifest = {"timestamp": ts, "trigger_command": trigger_command, "files": {}}
    for name in ("macro.db3", "user.db3"):
        src = LIGHTINGDB / name
        dst = dest / name
        shutil.copy2(src, dst)
        manifest["files"][name] = {
            "source": str(src),
            "sha256": _sha256(dst),
            "bytes": dst.stat().st_size,
        }

    master = LIGHTINGDB / "master.db3"
    manifest["files"]["master.db3.meta"] = {
        "source": str(master),
        "sha256": _sha256(master),  # metadata snapshot only — never copy the 512MB file
        "bytes": master.stat().st_size,
    }

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return dest


def connect_readonly(db_name: str) -> sqlite3.Connection:
    path = LIGHTINGDB / db_name
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


@contextmanager
def write_transaction(db_name: str, trigger_command: str):
    """Guard -> backup -> BEGIN -> yield -> commit / rollback.

    Usage:
        with write_transaction("macro.db3", "macro create HIGH DROP1") as conn:
            conn.execute("INSERT INTO macro ...")
            conn.executemany("INSERT INTO macro_data ...", rows)
    """
    guard_rekordbox_not_running()
    backup_dir = backup_all(trigger_command)

    path = LIGHTINGDB / db_name
    conn = sqlite3.connect(path)
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        print(
            f"Write rolled back. DB untouched. Backup preserved at:\n  {backup_dir}\n"
            f"If the live file looks wrong anyway, run:\n"
            f"  rbxlight restore --from {backup_dir.name}"
        )
        raise
    finally:
        conn.close()
```

## The 25-row invariant

Every macro MUST have exactly 25 `macro_data` rows — one per `macro_fixture` slot id (`1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,101,102,105,106,111,112`). A slot with no programming gets an **empty string** `data` value, never a missing row and never `NULL`. Writing a macro with fewer than 25 rows produces undefined behavior in rekordbox — this is not a "probably fine" corner, it's unverified territory (see Known Unknowns) and treated as unsafe by default.

Any macro-write function must assert this before commit:

```python
def assert_25_rows(conn: sqlite3.Connection, macro_id: int) -> None:
    expected = {
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        101,
        102,
        105,
        106,
        111,
        112,
    }
    rows = conn.execute(
        "SELECT macro_fixture_id FROM macro_data WHERE macro_id = ?", (macro_id,)
    ).fetchall()
    got = {r[0] for r in rows}
    if got != expected:
        missing = expected - got
        extra = got - expected
        raise AssertionError(
            f"macro {macro_id}: expected 25 macro_data rows, missing={missing} extra={extra}"
        )
    nulls = conn.execute(
        "SELECT COUNT(*) FROM macro_data WHERE macro_id = ? AND data IS NULL",
        (macro_id,),
    ).fetchone()[0]
    if nulls:
        raise AssertionError(
            f"macro {macro_id}: {nulls} row(s) have NULL data, must be ''"
        )
```

Call this inside the `write_transaction` block, before `conn.commit()` runs — a failed assertion raises, which rolls back the transaction per the pattern above.

## Verification after write

A write is not "done" when `commit()` returns. It is done when:

1. The tool re-reads the DB (fresh read-only connection, not the same connection used to write) and confirms the expected rows/values are present.
2. The user opens rekordbox and visually confirms the change in the UI.

rekordbox may cache its view of the DB. If a change doesn't appear after step 2, the correct next step is to fully quit rekordbox (not just switch views) and relaunch it, before concluding the write failed. Don't chase a phantom bug that's actually just app-level caching.

## Known unknowns (do not assume)

These are genuinely unverified — do not write code that depends on any of them being true, and do not present them as fact in comments or docs:

- Whether rekordbox validates `lighting_property.MacroVersionNum` (currently `1061`) or `DbVersionNum` (currently `1854`) on load, and what it does if either is stale or mismatched.
- Whether rekordbox prunes or rejects rows/columns it doesn't recognize (e.g. from a schema it considers newer or older than expected).
- Whether rekordbox silently rewrites user macros on its own version upgrades, and whether that would step on macros this tool created.

Because these are unknown, a full round-trip test — write with this tool, then open in rekordbox, then re-export/re-read — is required before trusting any new write path in practice, no matter how confident the code looks.

## References

Schema and XML payload format (fixture slots, `LightingEditModel` structure, colour encoding, movement patterns) live in a separate schema-reference skill — this skill covers safety only. Do not duplicate schema details here beyond what rules 4/5 and the 25-row invariant require to be self-contained.
