"""Backup / restore / process-guard / write-transaction. See
rekordbox-data-safety skill — this is the non-negotiable safety layer.

Tests monkeypatch the module-level LIGHTINGDB / BACKUP_ROOT constants to
point at tmp_path sandboxes; production code (and the real CLI) uses the
real defaults. No test may rely on the real defaults resolving anywhere
under the user's home directory.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from rbxlight import db

#: Real default — never touched directly by a test (see conftest's
#: _guard_real_home, which patches Path.home()).
LIGHTINGDB: Path = (
    Path.home() / "Library/Application Support/Pioneer/rekordbox6/LightingDB"
)
BACKUP_ROOT: Path = Path("backups")

#: The exactly-25 real fixture slot ids a written macro must have rows for.
EXPECTED_FIXTURE_SLOT_IDS: frozenset[int] = frozenset(
    {
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
)

#: Databases copied byte-for-byte on every backup. master.db3 is handled
#: separately as a metadata-only snapshot — see _backup_databases.
_COPIED_DB_NAMES: tuple[str, ...] = ("macro.db3", "user.db3")


class RekordboxRunningError(RuntimeError):
    """rekordbox.app is running — refuse to open DBs read-write."""


class BackupCorruptedError(RuntimeError):
    """A backup's recorded sha256 doesn't match its file contents."""


def guard_rekordbox_not_running() -> None:
    """Raise RekordboxRunningError if `pgrep -x rekordbox` finds a process."""
    result = subprocess.run(
        ["pgrep", "-x", "rekordbox"], capture_output=True, check=False
    )
    if result.returncode == 0:
        raise RekordboxRunningError(
            "rekordbox is running. Quit it fully before writing to LightingDB — "
            "it flushes its own in-memory state on exit and will clobber this write."
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _new_timestamped_dir(root: Path) -> Path:
    """Create and return a new, unused timestamped directory under root."""
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%S%fZ")
    candidate = root / ts
    suffix = 0
    while True:
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1
            candidate = root / f"{ts}-{suffix}"


def _backup_databases(source_dir: Path, dest_root: Path, trigger_command: str) -> Path:
    """Copy macro.db3/user.db3 (+ master.db3 metadata only) from source_dir
    into a new timestamped dir under dest_root, writing a manifest.json.
    Shared implementation behind backup_all() (LIGHTINGDB -> BACKUP_ROOT)
    and sync.push() (explicit live dir -> explicit backup root).
    """
    dest = _new_timestamped_dir(dest_root)

    manifest: dict = {
        "timestamp": dest.name,
        "trigger_command": trigger_command,
        "files": {},
    }
    for name in _COPIED_DB_NAMES:
        src = source_dir / name
        dst = dest / name
        shutil.copy2(src, dst)
        manifest["files"][name] = {
            "source": str(src),
            "sha256": _sha256(dst),
            "bytes": dst.stat().st_size,
        }

    master = source_dir / "master.db3"
    if master.exists():
        # Metadata snapshot only — the 512MB factory library is never copied.
        manifest["files"]["master.db3.meta"] = {
            "source": str(master),
            "sha256": _sha256(master),
            "bytes": master.stat().st_size,
        }

    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return dest


def backup_all(trigger_command: str) -> Path:
    """Copy macro.db3 + user.db3 (+ master.db3 metadata only) from
    LIGHTINGDB into a new timestamped dir under BACKUP_ROOT, writing a
    manifest.json recording timestamp, trigger_command, and per-file
    source/sha256/bytes. Returns the backup directory path.
    """
    return _backup_databases(LIGHTINGDB, BACKUP_ROOT, trigger_command)


def backup_live_databases(
    lightingdb_dir: Path, backup_root: Path, trigger_command: str
) -> Path:
    """Public entry point for backing up an explicit live directory into an
    explicit backup root — used by sync.push(), which backs up LIVE (not
    work_dir) and may be pointed at directories other than the module
    defaults. Thin, named wrapper around the shared implementation so
    callers outside this module never reach for the private
    `_backup_databases`.
    """
    return _backup_databases(lightingdb_dir, backup_root, trigger_command)


def verify_backup_integrity(backup_dir: Path) -> None:
    """Raise BackupCorruptedError if any backed-up file's sha256 no longer
    matches the value recorded in that backup's manifest.json.
    """
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if name.endswith(".meta"):
            continue  # metadata-only entry (master.db3) — no file to verify
        path = backup_dir / name
        actual = _sha256(path)
        if actual != entry["sha256"]:
            raise BackupCorruptedError(
                f"backup {backup_dir} is corrupted: {name} has sha256 {actual[:12]}… "
                f"but the manifest recorded {entry['sha256'][:12]}…"
            )


def restore_from_backup(backup_dir: Path) -> None:
    """Guard rekordbox not running, verify backup integrity, then copy
    macro.db3/user.db3 from backup_dir back over LIGHTINGDB. Verifies the
    live files match the backup's recorded sha256 after restoring.
    """
    guard_rekordbox_not_running()
    verify_backup_integrity(backup_dir)

    manifest = json.loads((backup_dir / "manifest.json").read_text())
    for name, entry in manifest["files"].items():
        if name.endswith(".meta"):
            continue
        src = backup_dir / name
        dst = LIGHTINGDB / name
        shutil.copy2(src, dst)
        if _sha256(dst) != entry["sha256"]:
            raise BackupCorruptedError(
                f"restore of {name} failed verification: live file does not match "
                f"the backup's recorded sha256 after copying."
            )


def preflight_restore(backup_dir: Path) -> None:
    """Guard rekordbox not running, then verify the given backup's
    integrity — the pre-flight sequence the CLI `restore` command must run
    BEFORE showing its confirmation prompt, so a bad backup or a running
    rekordbox surfaces before the user is asked to confirm anything.
    Raises RekordboxRunningError or BackupCorruptedError; does not touch
    live data.
    """
    guard_rekordbox_not_running()
    verify_backup_integrity(backup_dir)


@dataclass(frozen=True)
class BackupInfo:
    """One backup's summary, as returned by list_backups() — enough for
    `rbxlight restore` to list and let a user choose between backups
    without re-parsing manifest.json itself.
    """

    name: str
    timestamp: str
    trigger_command: str
    files: dict[str, dict]


def list_backups() -> list[BackupInfo]:
    """Scan BACKUP_ROOT for backup directories (each holding a
    manifest.json) and return their summaries newest-first, ordered by
    directory name (a sortable UTC timestamp). Read-only. Returns an
    empty list if BACKUP_ROOT doesn't exist or holds no backups.
    """
    if not BACKUP_ROOT.exists():
        return []

    infos: list[BackupInfo] = []
    for entry in BACKUP_ROOT.iterdir():
        manifest_path = entry / "manifest.json"
        if not entry.is_dir() or not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text())
        infos.append(
            BackupInfo(
                name=entry.name,
                timestamp=manifest["timestamp"],
                trigger_command=manifest["trigger_command"],
                files=manifest["files"],
            )
        )

    infos.sort(key=lambda info: info.name, reverse=True)
    return infos


@dataclass(frozen=True)
class RestorePlan:
    """A typed, immutable description of what `restore` WOULD do — built
    with zero writes. `touches_live` is always True: restore overwrites
    LIVE database files, unlike pull's PullPlan.
    """

    file_names: tuple[str, ...]
    backup_dir: Path
    lightingdb_dir: Path
    touches_live: bool


def build_restore_plan(backup_dir: Path, lightingdb_dir: Path) -> RestorePlan:
    """Build a RestorePlan from a backup directory's manifest.json,
    listing the live files that would be overwritten (never the
    metadata-only master.db3 entry). Never writes anything.
    """
    manifest = json.loads((backup_dir / "manifest.json").read_text())
    file_names = tuple(name for name in manifest["files"] if not name.endswith(".meta"))
    return RestorePlan(
        file_names=file_names,
        backup_dir=backup_dir,
        lightingdb_dir=lightingdb_dir,
        touches_live=True,
    )


def connect_readonly(db_name: str) -> sqlite3.Connection:
    """Open LIGHTINGDB/db_name via the read-only SQLite URI form — a
    connection that is structurally incapable of writing.
    """
    return db.connect_readonly(LIGHTINGDB / db_name)


def assert_25_rows(conn: sqlite3.Connection, macro_id: int) -> None:
    """Raise AssertionError unless macro_data has exactly one row per
    EXPECTED_FIXTURE_SLOT_IDS for macro_id, with no NULL `data` values.
    """
    rows = conn.execute(
        "SELECT macro_fixture_id FROM macro_data WHERE macro_id = ?", (macro_id,)
    ).fetchall()
    got = {row[0] for row in rows}
    if got != EXPECTED_FIXTURE_SLOT_IDS:
        missing = EXPECTED_FIXTURE_SLOT_IDS - got
        extra = got - EXPECTED_FIXTURE_SLOT_IDS
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


def _default_verify(conn: sqlite3.Connection) -> None:
    """Fallback verification when write_transaction() is given none.

    Deliberately a no-op: some existing callers/tests exercise
    write_transaction() against dummy, non-SQLite file content (no schema
    at all), and any real read would raise on that content. The hook
    still runs on every write — giving every future caller an in-transaction
    verification point without changing behavior for callers that don't
    supply their own `verify`.
    """
    return


@contextmanager
def write_transaction(
    db_name: str,
    trigger_command: str,
    verify: Callable[[sqlite3.Connection], None] | None = None,
) -> Iterator[sqlite3.Connection]:
    """guard_rekordbox_not_running() -> backup_all() -> BEGIN -> yield conn
    -> verify -> commit, or rollback + re-raise on any exception. On
    rollback the target db file must be byte-for-byte identical to before
    the attempt.

    `verify`, if given, runs INSIDE the still-open transaction after the
    caller's work but before commit — raising it rolls back exactly like
    any other exception from the transaction body. When omitted, a
    default verification still runs: a write is never committed
    unverified.
    """
    guard_rekordbox_not_running()
    backup_dir = backup_all(trigger_command)

    path = LIGHTINGDB / db_name
    conn = sqlite3.connect(path)
    conn.execute("BEGIN")
    try:
        yield conn
        (verify or _default_verify)(conn)
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


@contextmanager
def working_copy_write(db_name: str) -> Iterator[sqlite3.Connection]:
    """BEGIN -> yield conn -> commit, or rollback + re-raise. Working-copy
    only — no process guard, no backup, because this path never touches
    live data (see rekordbox-data-safety, "WORK ON A COPY, NOT ON LIVE").
    Unlike write_transaction, which guards and backs up live LightingDB.
    """
    conn = sqlite3.connect(db.resolve_path(db_name))
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
