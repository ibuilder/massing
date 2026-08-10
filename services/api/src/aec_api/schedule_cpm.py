"""Critical Path Method over `schedule_activity` records.

**This module is now a shim.** The engine lives in `services/api/src/massingplan`
(vendored from MassingCloud/massingplan -- see its VENDOR.md) and the mapping
from records to engine inputs lives in `schedule_engine.py`. `compute()` keeps
the exact shape it has always returned, so EVM, the extension-of-time analysis,
resource loading, the vitals dashboard and the Gantt renderer are unaffected.

What changed underneath, and why it mattered
--------------------------------------------
The previous implementation was 105 lines and, on any real schedule, wrong in
four ways that produced plausible numbers rather than errors:

* **Finish-to-Start only, no lags.** Predecessors were bare tokens. SS, FF and
  SF ties -- and every lead or lag -- were unrepresentable, so a schedule that
  used them computed as though it did not.
* **No calendars.** The pass counted abstract "days from day zero" and never
  consulted a working week, so a five-day and a seven-day crew were treated as
  interchangeable and the offsets were never reconciled with the `start`/`finish`
  fields sitting on the same records.
* **No constraints and no data date.** A progressed job rescheduled from day
  zero and reported completed work as still to do.
* **`max(0, free_float)`.** Negative free float -- the signal that a recorded
  actual contradicts the remaining logic -- was clamped away.

And one behaviour deliberately reversed: on a circular network the old code
appended the unorderable remainder in dictionary order and **returned numbers
anyway**, flagged only by `has_cycle`. Numbers computed over a broken network
are worse than no numbers, because they are used. `compute()` now returns an
empty result with `has_cycle: True` and names the loop in `cycle`.

New keys are additive: real dates, calendars, the driving path, constraint
violations and an import/issue log. Nothing was removed.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from massingplan.core.graph import ScheduleCycleError
from massingplan.core.network import RelationType
from massingplan.core.schedule import schedule_network

from . import schedule_engine


def compute(activities: list[dict], *, data_date: date | None = None) -> dict[str, Any]:
    """activities: records with `id`, `ref`, `title`, `data{}`. Returns the CPM result."""
    if not activities:
        return _empty()

    tasks, links, calendars, issues = schedule_engine.build_network(activities)
    dd = data_date or schedule_engine.data_date_for(activities)

    try:
        outcome = schedule_network(tasks, links, calendars, data_date=dd)
    except ScheduleCycleError as exc:
        return _cyclic(tasks, activities, issues, exc.cycle)

    result = schedule_engine.to_legacy_rows(outcome, tasks, links, activities)
    result["issues"] = [*[i.to_dict() for i in issues], *result.get("issues", [])]
    return result


def _empty() -> dict[str, Any]:
    """No activities. Every key present, so a caller need not special-case it."""
    return schedule_engine.blank_result()


def _cyclic(tasks: list, activities: list[dict], issues: Any, cycle: list[str]) -> dict[str, Any]:
    """A cyclic network: the activities, and **no computed dates**.

    The old engine broke the loop in dictionary order and returned a full set of
    dates anyway, flagged only by `has_cycle`. Those numbers were consumed by
    EVM and the delay analysis exactly as if they meant something.

    Callers still get every activity, so anything that counts or lists them is
    unaffected, and every *position* field -- dates and day offsets -- is `None`
    rather than a fabricated value. A caller that renders `None` shows a gap; a
    caller that rendered the old numbers showed a schedule.

    **`total_float` and `free_float` stay numeric even here**, and that is not
    an inconsistency. They are filter keys: `px.optimize` does
    `0 < x["total_float"] <= 5` without checking, so `None` turns a refusal into
    a TypeError in a route -- a crash rather than a clean "this schedule has a
    loop". The first version of this fix coerced the float only on the computed
    exit and left this one raising, which is the same defect one exit further
    along.

    The rows come from `schedule_engine.blank_row`, which the computed exit also
    builds from, so the two cannot drift.
    """
    refs = {r["id"]: r.get("ref") for r in activities}
    rows = [schedule_engine.blank_row(t, refs.get(t.id)) for t in tasks]
    return {
        **schedule_engine.blank_result(),
        "activity_count": len(rows),
        "has_cycle": True,
        "activities": rows,
        "cycle": cycle,
        "issues": [
            *[i.to_dict() for i in issues],
            {
                "severity": "error",
                "code": "CPM.CIRCULAR_LOGIC",
                "message": "Circular logic: " + " -> ".join(cycle),
                "action": "no dates computed; break the loop and recalculate",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Kept for `schedule_risk.py`, which imports both privately. Re-exported from
# the adapter rather than reimplemented, so there is one definition of what a
# duration and a predecessor token mean.
# ---------------------------------------------------------------------------


def _duration(a: dict) -> int:
    """Duration in days for one activity's `data` blob.

    Now inclusive of both endpoints when derived from dates: an activity
    recorded as starting and finishing on the same day is one day of work. The
    previous `(finish - start).days` made every such activity zero-duration,
    which silently removed it from the critical path.
    """
    return schedule_engine._duration_days(a)


def _preds(raw: Any) -> list[str]:
    """Predecessor refs from a token string, ignoring type and lag.

    `schedule_risk` only needs the graph shape. The full parse -- relationship
    type and lag -- is `schedule_engine.parse_predecessor_tokens`.
    """
    return [ref for ref, _type, _lag in schedule_engine.parse_predecessor_tokens(raw)]


__all__ = ["RelationType", "compute"]
