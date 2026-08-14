"""R45-SCHED-DEDUPE ② — Last Planner: commitments, PPC, and the two numbers we already disagree on.

**This project computes PPC twice, in two places, with opposite denominators — and both are wrong.**
Found by reading all three implementations rather than the two the R45 table named:

| | denominator | a week with 2 done, 3 still unanswered |
|---|---|---|
| `lean.ppc` | **every** record | `0.4` — the unanswered three count as failures |
| `pull_plan.metrics` | **assessed only** (`done + not_done`) | `1.0` if the one answered was done |
| `core/lastplanner` | frozen at commit, `None` until all answered | `None` — the week is not measurable yet |

`lean.ppc` reads artificially **low** mid-week: on Wednesday every team looks like it is failing.
`pull_plan.metrics` reads artificially **high**: one commitment answered out of twenty, and it was
done, reports 100%. **The one the portal renders is the flattering one.** Neither is a rounding
argument; they are different questions wearing the same label, on the same dashboard.

`lean.ppc` also reports `0.0` and a rating of *"needs work"* for a project with **no commitments at
all**, and defaults a missing variance reason to the string `"Unspecified"` — which quietly fills the
learning loop with a value nobody entered.

## What the vendored engine does instead, and why each rule exists

* **The denominator is frozen when the week is committed.** A commitment added mid-week does not join
  it; one quietly withdrawn does not leave it. Re-planning the week after seeing how it went is how
  PPC becomes a measure of nothing.
* **Partial completion is not partial credit.** Met or not met. "80% done" is a commitment that was
  not met, and the whole value of the number is that it refuses to average away a broken promise.
* **An unassessed commitment makes the week unmeasurable, not perfect.** `ppc` is `None` until every
  commitment has an answer — the same tri-state the DCMA checks use, and for the same reason.
* **A missed commitment must carry a reason.** Never defaulted. The reasons are the entire learning
  loop; PPC without them is a number nobody can act on.
* **Only make-ready work can be committed.** Committing work whose constraints are still live is
  precisely what the method exists to stop, so it is refused rather than warned about.

It also deliberately declines to report a **lifetime average PPC** — the signal is the trend, and one
number across six months hides the month it collapsed.

## Scope: this is additive, and consolidation is a decision

Changing what PPC means on a shipped dashboard is a domain-semantics call with contractual weight — a
GC reports PPC to an owner. So this **adds** the correct measurement and leaves both existing numbers
alone. `test_ppc_divergence.py` pins the disagreement so it cannot widen unnoticed, and the roadmap
carries the consolidation as a decision.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.lastplanner import (
    Commitment,
    Constraint,
    ConstraintKind,
    LastPlannerError,
    Reliability,
    VarianceReason,
    WeeklyPlan,
    commit,
)

from . import modules as me


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _enum(cls: Any, v: Any, default: Any) -> Any:
    try:
        return cls(str(v).strip().lower().replace(" ", "_"))
    except (TypeError, ValueError):
        return default


def _constraints(row: dict) -> tuple[Constraint, ...]:
    """Constraints attached to a task, if the record carries any.

    A record with no constraint data yields none — which means `is_make_ready` is true, and that is
    the right default only because our `pull_plan_task` records do not model live constraints per
    commitment yet. Recorded here rather than assumed: if that ever changes, this is the seam.
    """
    raw = (row.get("data") or {}).get("constraints")
    if not isinstance(raw, list):
        return ()
    out = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            continue
        promised = _date(c.get("promised_by")) or date.today()
        out.append(Constraint(
            id=str(c.get("id") or f"c{i}"),
            description=str(c.get("description") or ""),
            kind=_enum(ConstraintKind, c.get("kind"), ConstraintKind.EXTERNAL),
            owner=str(c.get("owner") or ""),
            promised_by=promised,
            removed_on=_date(c.get("removed_on")),
        ))
    return tuple(out)


def _commitment(row: dict) -> Commitment | None:
    data = row.get("data") or {}
    state = str(data.get("workflow_state") or "").strip().lower()
    completed: bool | None
    if state == "done":
        completed = True
    elif state == "not_done":
        completed = False
    else:
        # Still planned. `None` is the point: an unassessed commitment makes the week unmeasurable,
        # and coercing it to False here would recreate `lean.ppc`'s mid-week pessimism.
        completed = None
    reason = None
    if completed is False:
        reason = _enum(VarianceReason, data.get("variance_reason"), VarianceReason.NOT_RECORDED)
    # The engine validates in `__post_init__` and refuses, among other things, a commitment with no
    # crew — "a commitment needs a crew to make it", which is correct: a promise nobody made is not a
    # commitment. But **one malformed record must not take out the whole report**, so the refusal is
    # caught here and the row is reported as unusable rather than raised into the route.
    try:
        return Commitment(
            id=str(row.get("id") or ""),
            activity_id=str(data.get("activity_id") or row.get("ref") or ""),
            description=str(row.get("title") or data.get("name") or ""),
            crew=str(data.get("trade") or data.get("crew") or ""),
            constraints=_constraints(row),
            completed=completed,
            reason=reason,
        )
    except LastPlannerError:
        return None


def reliability(db: Any, pid: str) -> dict[str, Any]:
    """PPC by week, with the reasons, over `pull_plan_task` records.

    Weeks are grouped by the task's `week` field. A task with no week is skipped rather than bucketed
    into a default — a commitment nobody dated is not a commitment made in any particular week, and
    putting it in one would move a number somebody reports.
    """
    rows = me.list_records(db, "pull_plan_task", pid, limit=1_000_000)
    if not rows:
        return _unavailable("no pull-plan tasks — there are no commitments to score")

    by_week: dict[date, list[Commitment]] = {}
    undated = 0
    unusable = 0
    for row in rows:
        wk = _date((row.get("data") or {}).get("week"))
        if wk is None:
            undated += 1
            continue
        c = _commitment(row)
        if c is None:
            unusable += 1
            continue
        by_week.setdefault(wk, []).append(c)

    if not by_week:
        return _unavailable(
            f"none of the {len(rows)} pull-plan tasks carry a week, so they cannot be grouped into "
            "weekly commitments", undated=undated)

    weeks: list[WeeklyPlan] = []
    refused: list[str] = []
    for wk in sorted(by_week):
        try:
            weeks.append(commit(wk, by_week[wk]))
        except LastPlannerError as exc:
            # `commit` refuses work whose constraints are still live. That refusal is the method
            # working, so it is reported per week rather than failing the whole report.
            refused.append(f"{wk.isoformat()}: {type(exc).__name__}")

    if not weeks:
        return _unavailable("every week was refused at commit", refused=refused)

    rel = Reliability(weeks=tuple(weeks))
    return {
        "available": True,
        "weeks": len(weeks),
        # `None` for a week whose commitments are not all answered — NOT a number.
        # `committed` and `completed` are PROPERTIES returning ints; `unassessed` a property returning
        # a tuple; `ppc` a method. Enumerated from the class, not guessed from the source -- reading a
        # decorated property as a function has now cost a TypeError three times in this ring.
        "trend": [{"week": w.week_starting.isoformat(), "committed": w.committed,
                   "completed": w.completed, "unassessed": len(w.unassessed),
                   "ppc": w.ppc()} for w in weeks],
        "measurable_weeks": len(rel.measurable_weeks()),
        # Mean across MEASURABLE weeks only, and deliberately not a lifetime average: the engine
        # exposes the trend because one number across six months hides the month it collapsed.
        "mean_ppc": rel.mean_ppc(),
        "top_reasons": [{"reason": r.value if hasattr(r, "value") else str(r), "count": n}
                        for r, n in rel.top_reasons(5)],
        "undated_tasks": undated,
        # Rows the engine refused to accept as a commitment at all (no crew, etc). Surfaced, because
        # a silently dropped commitment is a denominator quietly shrinking.
        "unusable_tasks": unusable,
        "weeks_refused_at_commit": refused,
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Nothing scored. `mean_ppc` is `None`, never `0.0` — the defect `lean.ppc` ships today."""
    return {
        "available": False,
        "reason": reason,
        "weeks": None,
        "trend": [],
        "measurable_weeks": None,
        "mean_ppc": None,
        "top_reasons": [],
        "undated_tasks": 0,
        "unusable_tasks": 0,
        "weeks_refused_at_commit": [],
        **extra,
    }
