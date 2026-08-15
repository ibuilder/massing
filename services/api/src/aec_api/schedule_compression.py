"""R46 ⑤ — schedule compression: what finishing earlier would actually take, and cost.

`aec_api/px.optimize` already answers a version of this, and its own docstring is honest about which:
a **rule-based advisory** that "never rewrites the schedule". It picks the longest critical activities
and reports `days_potential = duration × _CRASH_FACTOR` — a fixed fraction of the activity's own
length, chosen once for every project on earth.

The trouble is what that number cannot know. **Shortening a driving activity by five days when it is
only three days ahead of the next path buys three.** The other two are spent and gone. A recovery
figure taken from the activity's duration cannot see the path behind it, so it overstates — and the
overstatement is largest exactly where the schedule is tightest and the decision is most expensive.

This re-schedules after every single day of compression. `days_saved` is what the **project finish**
moved, not what came off the activity, and the plan is built cheapest-useful-day-first: the driving
path shifts as it is compressed, and an algorithm that picks its whole shopping list from the
original critical path keeps spending on an activity that stopped driving three days ago.

## What it refuses

**`cost_per_day` and `max_days` are required per activity, not defaulted.** `max_days` is a fact
about the work — a pour cures in the time it cures, whatever it costs — and a default of "as far as
you like" produces a plan that finishes on any date somebody asks for. An activity with no cost entry
is simply not a candidate, and is listed as such.

**A plan that gets eight of the ten days asked for is returned as eight.** `meets_target` says
whether the target was reached; raising instead would leave a caller to find the eight by bisection.

Both engines still ship. `px.optimize` needs no cost data and answers "where would I look"; this
needs cost data and answers "what does the date cost". They are different questions and the second
one cannot be asked for free.
"""
from __future__ import annotations

from typing import Any

from massingplan.core.compression import CompressionError, CrashCost
from massingplan.core.compression import plan as _plan
from massingplan.core.graph import ScheduleCycleError

from . import schedule_engine


def _costs(raw: list[dict]) -> tuple[list[CrashCost], list[str]]:
    """Per-activity crash costs, with the unusable ones named rather than defaulted."""
    out, bad = [], []
    for c in raw or []:
        aid = str(c.get("activity_id") or c.get("id") or c.get("activity") or "").strip()
        if not aid:
            bad.append("a cost entry names no activity")
            continue
        try:
            out.append(CrashCost(activity_id=aid,
                                 cost_per_day=float(c.get("cost_per_day")),
                                 max_days=int(float(c.get("max_days")))))
        except (TypeError, ValueError):
            bad.append(f"{aid}: needs both cost_per_day and max_days")
        except CompressionError:
            # Negative cost or negative max_days. Counted, not raised — one bad row must not take
            # out the plan, and the engine's refusal is worth surfacing by name.
            bad.append(f"{aid}: refused — a negative cost or max_days")
    return out, bad


def compress(activities: list[dict], target_days: int, costs: list[dict] | None = None,
             fast_trackable: list[list[str]] | None = None) -> dict[str, Any]:
    """Options for finishing `target_days` earlier, cheapest useful day first."""
    if not activities:
        return _unavailable("no activities — there is no schedule to compress")
    try:
        target = int(target_days)
    except (TypeError, ValueError):
        return _unavailable("target_days must be a whole number of days")
    if target < 0:
        return _unavailable("a negative target would be asking to finish later")

    parsed, bad = _costs(costs or [])
    pairs = [(str(a), str(b)) for a, b in (fast_trackable or []) if a and b]
    if not parsed and not pairs:
        return _unavailable(
            "no crash costs and no fast-track pairs — compression needs to know what shortening "
            "each activity costs and how far it can go. Without that there is no plan, only a wish",
            rejected_costs=bad)

    tasks, links, calendars, _ = schedule_engine.build_network(activities)
    try:
        result = _plan(tasks, links, calendars, target_days=target, costs=parsed,
                       fast_trackable=pairs,
                       data_date=schedule_engine.data_date_for(activities))
    except ScheduleCycleError:
        return _unavailable("the logic contains a loop, so the schedule cannot be re-scheduled",
                            rejected_costs=bad)
    except CompressionError:
        # Composed here, never relayed — the v0.3.962 rule.
        return _unavailable("the compression inputs were refused; check that every cost names an "
                            "activity the schedule contains", rejected_costs=bad)

    out = result.to_dict()
    return {
        "available": True,
        "rejected_costs": bad,
        # Activities with no cost entry are not candidates. Named, because "we could only find 3
        # days" reads very differently once you know 40 activities were never eligible.
        "activities_without_costs": sum(1 for t in tasks
                                        if t.id not in {c.activity_id for c in parsed}),
        **out,
    }


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    """Counts `None`, never 0 — 'no time can be recovered' and 'not computed' differ."""
    out: dict[str, Any] = {
        "available": False, "reason": reason, "rejected_costs": [],
        "activities_without_costs": None, "target_days": None,
        "finish_before": None, "best_finish": None, "days_available": None,
        "meets_target": None, "total_cost": None, "options": [], "notes": [],
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
