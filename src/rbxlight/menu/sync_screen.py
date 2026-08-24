"""Sync submenu: Pull (working-copy tier — only ever refreshes the
disposable working copy) and Push (live tier — the stronger typed
confirmation gate).
"""

from __future__ import annotations

from rbxlight import db, safety, sync
from rbxlight.menu.mutation import run_live_mutation, run_working_copy_mutation
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer

_CHOICES = ("Pull", "Push", "Back")


def _pull(prompter: Prompter, renderer: Renderer) -> None:
    def _render_plan(plan: sync.PullPlan) -> None:
        renderer.line(
            f"Plan: pull {', '.join(plan.db_names)} from live into the working copy."
        )

    def _apply(_: sync.PullPlan) -> None:
        sync.pull(safety.LIGHTINGDB, db.WORK_DIR)

    def _render_result(_: None) -> None:
        renderer.line("Pulled from live into the working copy.")

    try:
        run_working_copy_mutation(
            prompter,
            renderer,
            build_plan=lambda: sync.build_pull_plan(safety.LIGHTINGDB, db.WORK_DIR),
            render_plan=_render_plan,
            confirm_message="Pull from live now?",
            apply=_apply,
            render_result=_render_result,
        )
    except safety.RekordboxRunningError as exc:
        renderer.error(str(exc))


def _push(prompter: Prompter, renderer: Renderer) -> None:
    try:
        plan = sync.build_push_plan(db.WORK_DIR, safety.LIGHTINGDB)
    except FileNotFoundError as exc:
        renderer.error(f"{exc}. Run `rbxlight pull` first.")
        return

    def _render_plan(plan: sync.PushPlan) -> None:
        renderer.line(
            f"Plan: push {', '.join(plan.db_names)} from the working copy to "
            f"{plan.lightingdb_dir}."
        )

    def _apply(_: sync.PushPlan) -> object:
        trigger_command = "rbxlight menu sync push"
        return sync.push(
            safety.LIGHTINGDB, db.WORK_DIR, safety.BACKUP_ROOT, trigger_command
        )

    def _render_result(backup_dir: object) -> None:
        renderer.line(f"Pushed to live. Backup saved at:\n  {backup_dir}")

    try:
        run_live_mutation(
            prompter,
            renderer,
            build_plan=lambda: plan,
            render_plan=_render_plan,
            danger_message=(
                f"This will overwrite LIVE {', '.join(plan.db_names)} in "
                f"{plan.lightingdb_dir}. A backup will be taken first; "
                "restore it with `rbxlight restore --from <backup name>`."
            ),
            confirm_message="Type PUSH to overwrite live data",
            expected_word="PUSH",
            apply=_apply,
            render_result=_render_result,
        )
    except safety.RekordboxRunningError as exc:
        renderer.error(str(exc))
    except sync.StaleWorkingCopyError as exc:
        renderer.error(str(exc))
    except FileNotFoundError as exc:
        renderer.error(f"{exc}. Run `rbxlight pull` first.")


def run(prompter: Prompter, renderer: Renderer) -> None:
    while True:
        choice = prompter.select("Sync", list(_CHOICES))
        if choice == "Back":
            return
        if choice == "Pull":
            _pull(prompter, renderer)
        elif choice == "Push":
            _push(prompter, renderer)
        else:
            return
