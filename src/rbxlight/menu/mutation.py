"""Shared "prompt -> build plan -> render -> confirm -> apply" loop for
mutating menu flows. Two tiers:

- `run_working_copy_mutation`: ordinary yes/no confirm, defaulting to
  No. Used by working-copy actions (macro create/delete, layout
  regenerate/install, sync pull).
- `run_live_mutation`: the stronger live-database tier — renders via
  `Renderer.danger` and gates on `Prompter.confirm_typed`, never the
  ordinary confirm. Used by sync push and backups restore.

Both stop before any write if the confirmation is declined/mismatched,
and both build the plan with zero side effects before ever asking.
"""

from __future__ import annotations

from collections.abc import Callable

from rbxlight.menu.prompts import Prompter
from rbxlight.menu.render import Renderer


def run_working_copy_mutation[PlanT, ResultT](
    prompter: Prompter,
    renderer: Renderer,
    *,
    build_plan: Callable[[], PlanT],
    render_plan: Callable[[PlanT], None],
    confirm_message: str,
    apply: Callable[[PlanT], ResultT],
    render_result: Callable[[ResultT], None],
) -> None:
    """Build the plan, render it, ask an ordinary yes/no confirmation
    (default No), and only then apply. Declining leaves everything
    untouched.
    """
    plan = build_plan()
    renderer.plan(plan)
    render_plan(plan)
    if not prompter.confirm(confirm_message, default=False):
        return
    result = apply(plan)
    render_result(result)


def run_live_mutation[PlanT, ResultT](
    prompter: Prompter,
    renderer: Renderer,
    *,
    build_plan: Callable[[], PlanT],
    render_plan: Callable[[PlanT], None],
    danger_message: str,
    confirm_message: str,
    expected_word: str,
    apply: Callable[[PlanT], ResultT],
    render_result: Callable[[ResultT], None],
) -> None:
    """Build the plan, render it, show the danger presentation, and
    require the EXACT `expected_word` typed back before applying — an
    ordinary "y"/wrong word/empty answer is always a refusal.
    """
    plan = build_plan()
    renderer.plan(plan)
    render_plan(plan)
    renderer.danger(danger_message)
    if not prompter.confirm_typed(confirm_message, expected_word=expected_word):
        return
    result = apply(plan)
    render_result(result)
