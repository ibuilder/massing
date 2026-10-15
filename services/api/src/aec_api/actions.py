"""Meeting & action-item tracker — open/overdue action items by assignee & priority, completion rate,
and the meeting log (by type, cadence). Pure read-side aggregation over the action_item / meeting
modules; no writes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

DONE = ("done",)
_ROLLUP_BASIS = (
    "`by_assignee` and `by_priority` are over EVERY action item, done or not. `open_by_assignee` and "
    "`open_by_priority` are over the outstanding ones, which is the population every other number "
    "here is about — a tracker whose assignee rollup counts completed work points at whoever has "
    "finished the most rather than whoever owes the most."
)


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _d(r: dict) -> dict:
    return r.get("data") or r


def action_tracker(db, pid: str, as_of: date | None = None) -> dict[str, Any]:
    from . import modules as me
    today = as_of or date.today()
    items = me.list_records(db, "action_item", pid, limit=100000) if "action_item" in me.TABLES else []
    meetings = me.list_records(db, "meeting", pid, limit=100000) if "meeting" in me.TABLES else []

    by_assignee, by_priority, by_state = {}, {}, {}
    open_by_assignee, open_by_priority = {}, {}
    done = overdue = 0
    rows = []
    for a in items:
        d = _d(a)
        st = a.get("workflow_state") or "open"
        by_state[st] = by_state.get(st, 0) + 1
        is_done = st in DONE
        if is_done:
            done += 1
        who = (d.get("assignee") or d.get("responsible") or "(unassigned)").strip() or "(unassigned)"
        by_assignee[who] = by_assignee.get(who, 0) + 1
        pri = (d.get("priority") or "(none)").strip() or "(none)"
        by_priority[pri] = by_priority.get(pri, 0) + 1
        # ACTION-SUBSET. The two rollups above are over the WHOLE register, and every other number
        # this returns is about what is OUTSTANDING. Measured on a 14-item tracker with 3 open:
        # `by_assignee` reports `Ana: 11` and Ana has **zero** open items, while the two people who
        # actually owe work are reported at 2 and 1. *A reader asking an action tracker who owes what
        # is sent to the wrong person by the only rollup that was declared.* Both are kept — "where
        # has the work been" is a fair question — and the open-scoped pair is what a screen about
        # outstanding work reads.
        if not is_done:
            open_by_assignee[who] = open_by_assignee.get(who, 0) + 1
            open_by_priority[pri] = open_by_priority.get(pri, 0) + 1
        due = _parse(d.get("due_date"))
        is_overdue = bool(due and due < today and not is_done)
        if is_overdue:
            overdue += 1
        rows.append({
            "ref": a.get("ref"), "subject": d.get("subject"), "assignee": who, "priority": pri,
            "state": st, "due_date": d.get("due_date"), "overdue": is_overdue,
        })

    by_type = {}
    dates: list[date] = []
    for m in meetings:
        d = _d(m)
        mt = (d.get("meeting_type") or "(untyped)").strip() or "(untyped)"
        by_type[mt] = by_type.get(mt, 0) + 1
        md = _parse(d.get("date"))
        if md:
            dates.append(md)

    n = len(rows)
    return {
        "action_count": n, "open_count": n - done, "done_count": done, "overdue_count": overdue,
        "completion_pct": round(100 * done / n, 1) if n else None,
        "by_assignee": dict(sorted(by_assignee.items(), key=lambda kv: -kv[1])),
        "by_priority": dict(sorted(by_priority.items())), "by_state": by_state,
        # Worst-first, because the question these answer is who to chase.
        "open_by_assignee": dict(sorted(open_by_assignee.items(), key=lambda kv: -kv[1])),
        "open_by_priority": dict(sorted(open_by_priority.items())),
        "rollup_basis": _ROLLUP_BASIS,
        "meeting_count": len(meetings),
        "last_meeting": max(dates).isoformat() if dates else None,
        "meetings_by_type": dict(sorted(by_type.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("assignee") or "", r.get("ref") or "")),
    }
