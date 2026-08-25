"""Backups submenu: List (read-only), Restore (mutating, live tier)."""

from __future__ import annotations

from rbxlight import safety
from rbxlight.menu import actions
from rbxlight.menu.mutation import run_live_mutation
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer

_CHOICES = ("List", "Restore", "Back")
_DESCRIPTIONS = {
    "List": "List available live database backups",
    "Restore": "Restore the live database from a backup",
    "Back": "Return to the previous menu",
}


def _list(prompter: Prompter, renderer: Renderer) -> None:
    backups = actions.list_backups()
    if not backups:
        renderer.line(f"No backups found under {safety.BACKUP_ROOT}.")
        return
    renderer.line("Backups (newest first):")
    for info in backups:
        renderer.line(f"  {info.name}  {info.timestamp}  ({info.trigger_command})")


def _restore(prompter: Prompter, renderer: Renderer) -> None:
    name = prompter.text("Backup name to restore:")
    backup_dir = safety.BACKUP_ROOT / name
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        renderer.error(f"No backup named '{name}' found under {safety.BACKUP_ROOT}.")
        return

    try:
        safety.preflight_restore(backup_dir)
    except safety.RekordboxRunningError as exc:
        renderer.error(str(exc))
        return
    except safety.BackupCorruptedError as exc:
        renderer.error(str(exc))
        return

    def _render_plan(plan: safety.RestorePlan) -> None:
        renderer.line(
            f"This will overwrite the following live files from backup "
            f"'{name}': {', '.join(plan.file_names)}"
        )

    def _apply(_: safety.RestorePlan) -> str:
        safety.restore_from_backup(backup_dir)
        return name

    def _render_result(restored_name: str) -> None:
        renderer.line(f"Restored live data from backup '{restored_name}'.")

    run_live_mutation(
        prompter,
        renderer,
        build_plan=lambda: safety.build_restore_plan(backup_dir, safety.LIGHTINGDB),
        render_plan=_render_plan,
        danger_message=(
            f"This overwrites LIVE macro.db3/user.db3 from backup '{name}'. "
            f"A restore command to undo it is: rbxlight restore --from {name}"
        ),
        confirm_message="Type RESTORE to overwrite live data",
        expected_word="RESTORE",
        apply=_apply,
        render_result=_render_result,
    )


def run(prompter: Prompter, renderer: Renderer) -> None:
    while True:
        choice = prompter.select("Backups", list(_CHOICES), descriptions=_DESCRIPTIONS)
        if choice == "Back":
            return
        if choice == "List":
            _list(prompter, renderer)
        elif choice == "Restore":
            _restore(prompter, renderer)
        else:
            return
