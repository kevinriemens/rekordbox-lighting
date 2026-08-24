"""Per-action specifics and the edge cases known to exist in real data /
real usage: factory macro deletion refusal, rekordbox running during a
live action, a corrupt backup, layout install venue mismatch, and the
three distinct "no usable venue" conditions.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from rbxlight import safety
from rbxlight.menu.app import run_menu
from tests.fixtures.macro_fixtures import a_factory_macro, a_user_macro
from tests.fixtures.venue_fixtures import a_venue, set_lighting_property
from tests.tui.doubles import RecordingRenderer, ScriptedPrompter


class TestMacroCreateSpecifics:
    def test_should_state_the_target_is_the_working_copy(
        self, work_macro_db: Path
    ) -> None:
        # Given: a create flow that declines
        prompter = ScriptedPrompter(
            answers=["Macros", "Create", "NEW", "16", False, "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the plan states the working copy is the target
        assert "working copy" in renderer.all_text.lower()


class TestMacroDeleteSpecifics:
    def test_should_state_what_will_be_deleted_and_the_working_copy_target(
        self, work_macro_db: Path
    ) -> None:
        conn = sqlite3.connect(work_macro_db)
        a_user_macro(conn, macro_id=10001, name="TO DELETE")
        conn.close()

        # Given: a delete flow that declines
        prompter = ScriptedPrompter(
            answers=["Macros", "Delete", "10001", False, "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the plan names the macro and the working copy target
        assert "TO DELETE" in renderer.all_text
        assert "working copy" in renderer.all_text.lower()

    def test_should_refuse_to_delete_a_factory_macro(self, work_macro_db: Path) -> None:
        conn = sqlite3.connect(work_macro_db)
        a_factory_macro(conn, macro_id=61, name="FACTORY ONE")
        conn.close()
        original_bytes = work_macro_db.read_bytes()

        # Given: attempting to delete a factory (preset=1) macro,
        # confirming
        prompter = ScriptedPrompter(
            answers=["Macros", "Delete", "61", True, "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a clean refusal is rendered, no traceback, no write
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert work_macro_db.read_bytes() == original_bytes


class TestLayoutRegenerateSpecifics:
    def test_should_prompt_whether_to_reset_structure_and_render_the_diff(
        self, work_user_db: Path, work_dir: Path
    ) -> None:
        conn = sqlite3.connect(work_user_db)
        a_venue(conn, venue_id=2, name="ROOM")
        conn.close()

        # Given: navigating to Layout -> Regenerate, declining reset,
        # then declining the write confirmation
        prompter = ScriptedPrompter(
            answers=[
                "Layout",
                "Regenerate",
                "2",
                False,  # reset structure? no
                False,  # confirm write? no
                "Back",
                "Exit",
            ]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a plan was rendered (the diff), no traceback
        assert renderer.plans != []
        assert "Traceback" not in renderer.all_text


class TestLayoutInstallSpecifics:
    def test_should_report_a_clean_message_and_no_write_on_venue_mismatch(
        self, work_user_db: Path, work_dir: Path, tmp_path: Path
    ) -> None:
        from rbxlight.preview import layout as preview_layout

        conn = sqlite3.connect(work_user_db)
        a_venue(conn, venue_id=2, name="ROOM")
        conn.close()

        # Given: an incoming layout file for a different venue id
        other_layout = preview_layout.generate_layout(venue_id=999, fixtures=[])
        incoming_path = tmp_path / "mismatched.json"
        preview_layout.save_layout(incoming_path, other_layout)

        prompter = ScriptedPrompter(
            answers=["Layout", "Install", "2", str(incoming_path), "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a clean message, no traceback, no plan-confirm ever asked
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert not any(call[0] == "confirm" for call in prompter.calls)


class TestSyncPullSpecifics:
    def test_should_render_plan_confirm_then_refresh_working_copy_only(
        self, work_dir: Path, live_dir: Path, rekordbox_not_running: None
    ) -> None:
        (live_dir / "macro.db3").write_bytes(b"fresh-macro")
        (live_dir / "user.db3").write_bytes(b"fresh-user")

        # Given: navigating to Sync -> Pull and confirming
        prompter = ScriptedPrompter(answers=["Sync", "Pull", True, "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: the working copy now has the fresh content, live is
        # never written to by pull
        assert (work_dir / "macro.db3").read_bytes() == b"fresh-macro"
        assert (live_dir / "macro.db3").read_bytes() == b"fresh-macro"
        assert renderer.plans != []


class TestBackupsRestoreSpecifics:
    def test_should_report_corrupt_backup_cleanly_with_no_write(
        self, backup_root: Path, live_dir: Path, rekordbox_not_running: None
    ) -> None:
        (live_dir / "macro.db3").write_bytes(b"live-macro")
        (live_dir / "user.db3").write_bytes(b"live-user")
        backup_dir = safety.backup_all("seed")
        # Corrupt the backup after the fact
        (backup_dir / "macro.db3").write_bytes(b"tampered")
        original_live = (live_dir / "macro.db3").read_bytes()

        # Given: attempting to restore from the corrupted backup
        prompter = ScriptedPrompter(
            answers=["Backups", "Restore", backup_dir.name, "RESTORE", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        exit_code = run_menu(prompter, renderer)

        # Then: a clean message, no traceback, live untouched
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert (live_dir / "macro.db3").read_bytes() == original_live
        assert exit_code == 0

    def test_should_report_rekordbox_running_cleanly_with_no_write(
        self, backup_root: Path, live_dir: Path, rekordbox_running: None
    ) -> None:
        (live_dir / "macro.db3").write_bytes(b"live-macro")
        (live_dir / "user.db3").write_bytes(b"live-user")

        # Given: a backup exists but rekordbox is running
        ScriptedPrompter(answers=[])
        # (backup_all itself guards, so seed a backup via direct filesystem
        # to isolate this test from that other guard)
        manifest_dir = backup_root / "2026-01-01T000000Z"
        manifest_dir.mkdir(parents=True)
        import hashlib
        import json

        digest = hashlib.sha256(b"live-macro").hexdigest()
        digest_user = hashlib.sha256(b"live-user").hexdigest()
        (manifest_dir / "macro.db3").write_bytes(b"live-macro")
        (manifest_dir / "user.db3").write_bytes(b"live-user")
        (manifest_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-01-01T000000Z",
                    "trigger_command": "seed",
                    "files": {
                        "macro.db3": {
                            "source": str(live_dir / "macro.db3"),
                            "sha256": digest,
                            "bytes": 11,
                        },
                        "user.db3": {
                            "source": str(live_dir / "user.db3"),
                            "sha256": digest_user,
                            "bytes": 10,
                        },
                    },
                }
            )
        )
        original_live = (live_dir / "macro.db3").read_bytes()

        # When: attempting to restore while rekordbox is running
        prompter = ScriptedPrompter(
            answers=["Backups", "Restore", manifest_dir.name, "RESTORE", "Back", "Exit"]
        )
        renderer = RecordingRenderer()
        exit_code = run_menu(prompter, renderer)

        # Then: a clean message, no traceback, live untouched
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
        assert (live_dir / "macro.db3").read_bytes() == original_live
        assert exit_code == 0


class TestVenueEdgeCases:
    def test_should_report_no_venues_exist_at_all(self, work_user_db: Path) -> None:
        # Given: an empty user.db3 (no venues at all)
        prompter = ScriptedPrompter(answers=["Layout", "Regenerate", "Back", "Exit"])
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a clean "no venues" message, no traceback
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text

    def test_should_report_a_selected_venue_that_no_longer_exists(
        self, work_user_db: Path
    ) -> None:
        conn = sqlite3.connect(work_user_db)
        a_venue(conn, venue_id=2, name="ROOM")
        conn.close()

        # Given: explicitly selecting a venue id that doesn't exist
        prompter = ScriptedPrompter(
            answers=["Layout", "Regenerate", "999", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a clean "venue not found" message, no traceback
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text

    def test_should_report_a_stale_active_venue_pointer(
        self, work_user_db: Path
    ) -> None:
        conn = sqlite3.connect(work_user_db)
        set_lighting_property(conn, "ExecVenueId", "12345")
        conn.close()

        # Given: the active venue pointer refers to a deleted venue, and
        # no explicit venue id given
        prompter = ScriptedPrompter(
            answers=["Layout", "Regenerate", "", "Back", "Exit"]
        )
        renderer = RecordingRenderer()

        # When: running the menu
        run_menu(prompter, renderer)

        # Then: a clean "stale active venue" message, no traceback
        assert renderer.errors != []
        assert "Traceback" not in renderer.all_text
