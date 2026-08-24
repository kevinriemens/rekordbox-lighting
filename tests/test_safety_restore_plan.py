"""Tests for safety.RestorePlan / safety.build_restore_plan — the restore
side of the dry-run plan pair. Contract: rekordbox-data-safety rule 8
("RESTORE MUST EXIST BEFORE WRITE DOES") — restore overwrites LIVE
database files, and its plan must report that plainly, unlike pull's.
"""

from __future__ import annotations

import json
from pathlib import Path

from rbxlight import safety


def _make_backup_dir(tmp_path: Path) -> Path:
    backup_dir = tmp_path / "backups" / "2026-08-14T193000Z"
    backup_dir.mkdir(parents=True)
    manifest = {
        "timestamp": "2026-08-14T193000Z",
        "trigger_command": "rbxlight push --write",
        "files": {
            "macro.db3": {"source": "/x/macro.db3", "sha256": "a" * 64, "bytes": 10},
            "user.db3": {"source": "/x/user.db3", "sha256": "b" * 64, "bytes": 10},
            "master.db3.meta": {
                "source": "/x/master.db3",
                "sha256": "c" * 64,
                "bytes": 20,
            },
        },
    }
    (backup_dir / "manifest.json").write_text(json.dumps(manifest))
    return backup_dir


class TestBuildRestorePlan:
    def test_should_report_files_that_would_be_overwritten_and_their_backup(
        self, tmp_path: Path
    ) -> None:
        # Given: a backup directory with a manifest describing two real
        # db files plus a metadata-only entry for master.db3
        backup_dir = _make_backup_dir(tmp_path)
        lightingdb_dir = tmp_path / "LightingDB"

        # When: building a restore plan
        plan = safety.build_restore_plan(backup_dir, lightingdb_dir)

        # Then: it reports which live files would be overwritten (never
        # the metadata-only master.db3 entry) and which backup they come
        # from — and, critically, that restore DOES touch live
        assert set(plan.file_names) == {"macro.db3", "user.db3"}
        assert plan.backup_dir == backup_dir
        assert plan.lightingdb_dir == lightingdb_dir
        assert plan.touches_live is True

    def test_should_perform_no_write_when_building(self, tmp_path: Path) -> None:
        # Given: a backup directory, and a live dir with its own current
        # content
        backup_dir = _make_backup_dir(tmp_path)
        lightingdb_dir = tmp_path / "LightingDB"
        lightingdb_dir.mkdir()
        (lightingdb_dir / "macro.db3").write_bytes(b"live-macro-content")
        (lightingdb_dir / "user.db3").write_bytes(b"live-user-content")
        original_macro = (lightingdb_dir / "macro.db3").read_bytes()
        original_user = (lightingdb_dir / "user.db3").read_bytes()

        # When: building the plan (does not restore)
        safety.build_restore_plan(backup_dir, lightingdb_dir)

        # Then: live is untouched, byte-for-byte
        assert (lightingdb_dir / "macro.db3").read_bytes() == original_macro
        assert (lightingdb_dir / "user.db3").read_bytes() == original_user
