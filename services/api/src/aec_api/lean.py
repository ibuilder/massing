"""Lean / Last-Planner analytics (R4) — Plan Percent Complete (PPC) and reasons for non-completion,
the core metrics of the Last Planner System (VT lean-construction research). Pure over weekly-plan
records (status ∈ Planned|Complete|Missed, with a variance_reason on misses)."""
from __future__ import annotations

from collections import Counter
from typing import Any

#: Recorded when a missed commitment states no reason. An explicit absence, NOT a reason.
#:
#: This used to be the string "Unspecified", which sorted into `top_variance_reasons` beside
#: "Materials" and "Weather" as though somebody had entered it. The variance reasons ARE the Last
#: Planner learning loop — the whole point of the weekly cycle is that the team acts on them — so a
#: manufactured entry does not merely add noise, it puts a value nobody said at the top of the list
#: a team is asked to fix.
NO_REASON_RECORDED = "(no reason recorded)"


def ppc(records: list[dict]) -> dict[str, Any]:
    """Plan Percent Complete over `weekly_plan` records, or `None` while the period is unmeasurable.

    **The project's one PPC rule (v0.3.974), applied to this register.** `pull_plan.metrics` scores
    the `pull_plan_task` register and `schedule_lastplanner` scores it through the vendored engine;
    this scores `weekly_plan`. Three functions because there are **two registers and a route**, not
    three opinions — the rule they share is:

    * met or not met, no partial credit;
    * an unanswered commitment makes the period **unmeasurable**, so `ppc` is `None`, not a number;
    * nothing promised is `None` too — a team that made no commitments has not broken any.

    Until v0.3.974 this divided by EVERY record, so the still-Planned ones counted as failures and
    every team read as failing on a Wednesday. It also reported `0.0` and a rating of *"needs work"*
    for a project with no commitments at all.
    """
    rows = [(r.get("data") or r) for r in records]
    total = len(rows)
    complete = sum(1 for r in rows if (r.get("status") or "").lower() == "complete")
    missed = [r for r in rows if (r.get("status") or "").lower() == "missed"]
    # Anything neither complete nor missed is still open: promised, not yet answered.
    unassessed = total - complete - len(missed)
    reasons = Counter((r.get("variance_reason") or NO_REASON_RECORDED) for r in missed)

    measurable = total > 0 and unassessed == 0
    value = round(complete / total, 3) if measurable else None
    return {
        "commitments": total,
        "completed": complete,
        "unassessed": unassessed,
        "ppc": value,
        "missed": len(missed),
        "top_variance_reasons": [{"reason": k, "count": v} for k, v in reasons.most_common(5)],
        "reasons_not_recorded": reasons.get(NO_REASON_RECORDED, 0),
        # lean benchmark: high-performing teams sustain ~80%+ PPC. `None` while unmeasurable — a
        # rating is a judgement about a team, and there is nothing yet to judge.
        "rating": (None if value is None else
                   "good" if value >= 0.8 else "fair" if value >= 0.6 else "needs work"),
        "note": ("PPC is null until every commitment in the period has been answered — an unassessed "
                 "promise makes the period unmeasurable, not perfect and not failing. Reasons are "
                 "never defaulted: a missed commitment with no stated reason is recorded as such."),
    }
