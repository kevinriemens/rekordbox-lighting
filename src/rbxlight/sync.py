"""pull (live -> work/), push (work/ -> live), pull-state hashing, staleness
check. The ONLY module permitted to open a live database. See
rekordbox-data-safety skill, "Working copy model".
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from rbxlight import safety

#: Files copied by pull/push. master.db3 is deliberately excluded — it is
#: 512MB and read-only, never copied into the working area.
SYNCED_DB_NAMES: tuple[str, ...] = ("macro.db3", "user.db3")

PULL_STATE_FILENAME: str = ".pull-state.json"

#: Shared sha256 helper — see safety.py, the module that owns backup/restore
#: hashing (this module reuses it rather than duplicating the digest logic).
_sha256 = safety._sha256


class StaleWorkingCopyError(RuntimeError):
    """Live DB changed since the last pull — push refused."""


def pull(lightingdb_dir: Path, work_dir: Path) -> Path:
    """Guard rekordbox not running, copy SYNCED_DB_NAMES from
    lightingdb_dir into work_dir, and write work_dir/.pull-state.json
    recording {source path, sha256} for each copied file at that moment.
    Returns the path to the written pull-state file.
    """
    safety.guard_rekordbox_not_running()
    work_dir.mkdir(parents=True, exist_ok=True)

    state: dict = {
        "pulled_at": datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ"),
        "source_paths": {},
        "sha256": {},
    }
    for name in SYNCED_DB_NAMES:
        src = lightingdb_dir / name
        dst = work_dir / name
        shutil.copy2(src, dst)
        state["source_paths"][name] = str(src)
        state["sha256"][name] = _sha256(src)

    pull_state_path = work_dir / PULL_STATE_FILENAME
    pull_state_path.write_text(json.dumps(state, indent=2))
    return pull_state_path


def verify_not_stale(work_dir: Path, lightingdb_dir: Path) -> None:
    """Re-hash each live file named in the pull-state and raise
    StaleWorkingCopyError naming the first file whose live sha256 no
    longer matches the value recorded at pull time.
    """
    state = json.loads((work_dir / PULL_STATE_FILENAME).read_text())
    for name, expected_hash in state["sha256"].items():
        live_path = lightingdb_dir / name
        current_hash = _sha256(live_path)
        if current_hash != expected_hash:
            raise StaleWorkingCopyError(
                f"{name} has changed on live since the last pull "
                f"(expected sha256 {expected_hash[:12]}…, found {current_hash[:12]}…). "
                f"rekordbox or something else touched it — run `rbxlight pull` again "
                f"before pushing, or pass --force after taking a fresh backup."
            )


def push(
    lightingdb_dir: Path,
    work_dir: Path,
    backup_root: Path,
    trigger_command: str,
    *,
    force: bool = False,
) -> Path:
    """Guard rekordbox not running; unless force=True, verify_not_stale()
    first (hard stop on drift). Back up the LIVE databases (not work_dir),
    then copy work_dir's files over lightingdb_dir, then verify by re-read.
    Returns the backup directory path. force=True still takes a backup.
    """
    safety.guard_rekordbox_not_running()
    if not force:
        verify_not_stale(work_dir, lightingdb_dir)

    backup_dir = safety._backup_databases(lightingdb_dir, backup_root, trigger_command)

    for name in SYNCED_DB_NAMES:
        shutil.copy2(work_dir / name, lightingdb_dir / name)

    for name in SYNCED_DB_NAMES:
        if _sha256(lightingdb_dir / name) != _sha256(work_dir / name):
            raise RuntimeError(
                f"push verification failed for {name}: live content does not match "
                f"the working copy after copying."
            )

    return backup_dir
