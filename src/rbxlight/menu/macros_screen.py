"""Macros submenu: List, Search, Show (read-only), Create, Delete
(mutating, working-copy tier).
"""

from __future__ import annotations

from rbxlight import db
from rbxlight.macros import repo as macros_repo
from rbxlight.menu import actions
from rbxlight.menu.mutation import run_working_copy_mutation
from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer

_CHOICES = ("List", "Search", "Show", "Create", "Delete", "Back")
_SCOPE_CHOICES = ("user", "factory", "all")


def _render_working_copy_missing(
    renderer: Renderer, exc: db.WorkingCopyMissingError
) -> None:
    renderer.error(f"Working copy not found at {exc.path}. Run `rbxlight pull` first.")


def _render_macro_listing(renderer: Renderer, macros: list[macros_repo.Macro]) -> None:
    if not macros:
        renderer.line("No macros found.")
        return
    renderer.line("Macros:")
    for macro in macros:
        renderer.line(f"  {macro.id}: {macro.name} ({macro.beats} beats)")


def _list(prompter: Prompter, renderer: Renderer) -> None:
    scope = prompter.select("Scope?", list(_SCOPE_CHOICES))
    try:
        macros = actions.list_macros(scope)
    except db.WorkingCopyMissingError as exc:
        _render_working_copy_missing(renderer, exc)
        return
    _render_macro_listing(renderer, macros)


def _search(prompter: Prompter, renderer: Renderer) -> None:
    term = prompter.text("Search term:")
    scope = prompter.select("Scope?", list(_SCOPE_CHOICES))
    try:
        results = actions.search_macros(term, scope)
    except db.WorkingCopyMissingError as exc:
        _render_working_copy_missing(renderer, exc)
        return
    _render_macro_listing(renderer, results)


def _show(prompter: Prompter, renderer: Renderer) -> None:
    raw = prompter.text("Macro id:")
    try:
        macro_id = int(raw)
    except ValueError:
        renderer.error(f"'{raw}' is not a valid macro id.")
        return

    try:
        macro, slots = actions.get_macro_detail(macro_id)
    except LookupError:
        renderer.error(f"Macro {macro_id} not found.")
        return
    except db.WorkingCopyMissingError as exc:
        _render_working_copy_missing(renderer, exc)
        return

    preset_label = "user" if macro.preset == 0 else "factory"
    renderer.line(f"Macro {macro.id}: {macro.name}")
    renderer.line(f"  Beats: {macro.beats}")
    renderer.line(f"  Preset: {preset_label} ({macro.preset})")
    renderer.line("  Fixture slots:")
    for slot in slots:
        status = "programmed" if slot.programmed else "empty"
        renderer.line(f"    {slot.slot_id}: {status}")


def _create(prompter: Prompter, renderer: Renderer) -> None:
    name = prompter.text("Macro name:")
    beats_raw = prompter.text("Beats:")
    try:
        beats = int(beats_raw)
    except ValueError:
        renderer.error(f"'{beats_raw}' is not a valid number of beats.")
        return

    def _render_plan(plan: macros_repo.CreateMacroPlan) -> None:
        renderer.line(
            f"Plan: create macro '{plan.name}' ({plan.beats} beats) in the "
            "working copy, all 25 fixture slots empty."
        )

    def _apply(_: macros_repo.CreateMacroPlan) -> macros_repo.Macro:
        return actions.create_macro(name=name, beats=beats)

    def _render_result(macro: macros_repo.Macro) -> None:
        renderer.line(f"Created macro '{macro.name}' (id={macro.id}).")

    run_working_copy_mutation(
        prompter,
        renderer,
        build_plan=lambda: actions.build_create_macro_plan(name=name, beats=beats),
        render_plan=_render_plan,
        confirm_message=f"Create macro '{name}'?",
        apply=_apply,
        render_result=_render_result,
    )


def _delete(prompter: Prompter, renderer: Renderer) -> None:
    raw = prompter.text("Macro id to delete:")
    try:
        macro_id = int(raw)
    except ValueError:
        renderer.error(f"'{raw}' is not a valid macro id.")
        return

    try:
        plan = actions.build_delete_macro_plan(macro_id)
    except LookupError:
        renderer.error(f"Macro {macro_id} not found.")
        return
    except db.WorkingCopyMissingError as exc:
        _render_working_copy_missing(renderer, exc)
        return

    renderer.plan(plan)
    renderer.line(
        f"Plan: delete macro '{plan.macro_name}' (id={plan.macro_id}, "
        f"beats={plan.beats}) from the working copy."
    )
    if not prompter.confirm(f"Delete macro '{plan.macro_name}'?", default=False):
        return

    try:
        actions.delete_macro(macro_id)
    except macros_repo.FactoryMacroImmutableError as exc:
        renderer.error(f"Refused: {exc}")
        return

    renderer.line(f"Deleted macro '{plan.macro_name}' (id={plan.macro_id}).")


def run(prompter: Prompter, renderer: Renderer) -> None:
    while True:
        choice = prompter.select("Macros", list(_CHOICES))
        if choice == "Back":
            return
        if choice == "List":
            _list(prompter, renderer)
        elif choice == "Search":
            _search(prompter, renderer)
        elif choice == "Show":
            _show(prompter, renderer)
        elif choice == "Create":
            _create(prompter, renderer)
        elif choice == "Delete":
            _delete(prompter, renderer)
        else:
            return
