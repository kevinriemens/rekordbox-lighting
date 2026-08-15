"""Connection helpers + path resolution. Default resolution is ALWAYS the
working copy — only sync.py's pull/push pass live=True. See
rekordbox-lighting-architecture skill, "The Flow That Must Not Break".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

#: Working-copy directory. Ordinary commands resolve here by default.
WORK_DIR: Path = Path("work")

#: Live LightingDB directory — only sync.py may resolve here.
LIGHTINGDB: Path = (
    Path.home() / "Library/Application Support/Pioneer/rekordbox6/LightingDB"
)


def resolve_path(db_name: str, *, live: bool = False) -> Path:
    """Return WORK_DIR/db_name unless live=True, in which case LIGHTINGDB/db_name.

    Only sync.py is permitted to pass live=True.
    """
    base = LIGHTINGDB if live else WORK_DIR
    return base / db_name


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open path via the read-only SQLite URI form."""
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
