"""Meeting & action-item tracker — open/overdue action items by assignee & priority, completion rate,
and the meeting log (by type, cadence). Pure read-side aggregation over the action_item / meeting
modules; no writes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

DONE = ("done",)


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
        "meeting_count": len(meetings),
        "last_meeting": max(dates).isoformat() if dates else None,
        "meetings_by_type": dict(sorted(by_type.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("assignee") or "", r.get("ref") or "")),
    }
