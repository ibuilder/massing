"""R26-WORK-QUEUE — what is in your court right now, in the order it needs you, actionable in place.

The **Work** room's whole job. The platform already knew both halves — `my_work` finds the records
assigned to you or waiting on your party, and `due_feed` knows what is late — but they were separate
lists on separate screens, and neither carried the one thing that turns a list into a queue: *what
you can do about each item without leaving it*.

Two decisions shape this.

**An item with no due date is not "not urgent".** It is *undated*, which is a different fact and often
a data gap somebody should close. Folding it into "later" would sort a genuinely urgent, dateless RFI
below a routine item due next month, and would hide the gap that caused it. `undated` is its own
bucket, named, sitting above `later` — because an item nobody dated still needs a decision, and the
first decision is usually "when is this due".

**Every item carries the actions the ENGINE will honour.** Not "the actions this module defines" —
the ones this caller's party can actually perform from this state. A queue that offers a button the
API then rejects with a 409 is worse than one that offers nothing, because it spends the user's trust
before it spends their time.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

#: Buckets, in the order they should be worked. `undated` sits ABOVE `later` on purpose.
BUCKETS = ["overdue", "today", "soon", "undated", "later"]

#: Days ahead that still counts as "soon".
SOON_DAYS = 7

BUCKET_LABEL = {
    "overdue": "Overdue",
    "today": "Due today",
    "soon": f"Next {SOON_DAYS} days",
    "undated": "No due date",
    "later": "Later",
}

#: Why each bucket exists, so a UI does not have to invent the explanation.
BUCKET_MEANS = {
    "overdue": "Past its due date",
    "today": "Due before the end of today",
    "soon": f"Due within {SOON_DAYS} days",
    "undated": "Nobody has set a due date — that is a gap, not a low priority",
    "later": "Dated, and beyond the horizon",
}


def bucket(due: str | None, today: date | None = None, soon_days: int = SOON_DAYS) -> str:
    """Which bucket a due date falls in. Absent or unparseable → `undated`, never `later`.

    An unparseable date is the same class of thing as a missing one: the platform does not know when
    this is due. Silently treating it as far-future would bury it.
    """
    if not str(due or "").strip():
        return "undated"
    try:
        d = date.fromisoformat(str(due)[:10])
    except ValueError:
        return "undated"
    t = today or date.today()
    if d < t:
        return "overdue"
    if d == t:
        return "today"
    return "soon" if d <= t + timedelta(days=max(0, soon_days)) else "later"


def _sort_key(item: dict[str, Any]) -> tuple:
    """Within a bucket: dated before undated, earliest first, assigned-to-me ahead of ball-in-court."""
    return (0 if item.get("due") else 1,
            str(item.get("due") or "9999-12-31"),
            0 if item.get("reason") == "assigned" else 1,
            str(item.get("ref") or ""))


def queue(db: Session, project_id: str, user: str, party: str | None,
          today: date | None = None, soon_days: int = SOON_DAYS) -> dict[str, Any]:
    """The caller's work queue: their `my_work` feed, dated, bucketed, and with live actions.

    Built on `my_work` rather than beside it — a second definition of "in my court" is exactly how two
    screens come to disagree, which is the defect `test_consistency` exists to prevent.
    """
    from . import modules as me
    from .modules_query import available_actions

    items = me.my_work(db, project_id, user, party)
    out: list[dict[str, Any]] = []
    for it in items:
        mod = me.get_module(it["module"])
        due = None
        df = me._due_field_name(mod)
        if df:
            try:
                rec = me.get_record(db, it["module"], project_id, it["id"])
                due = (rec.get("data") or {}).get(df)
            except Exception:                 # noqa: BLE001 — a record that vanished is not a crash
                due = None
        acts = available_actions(mod, it["state"], party)
        out.append({**it, "due": due, "bucket": bucket(due, today, soon_days),
                    "actions": [a["action"] for a in acts],
                    # a transition the module gates behind required fields cannot be a one-click
                    # button, and saying so beats offering one that 409s
                    "blocked_actions": [a["action"] for a in acts if a.get("requires")]})

    grouped = {b: sorted([x for x in out if x["bucket"] == b], key=_sort_key) for b in BUCKETS}
    actionable = sum(1 for x in out if x["actions"])
    return {
        "buckets": [{"key": b, "label": BUCKET_LABEL[b], "means": BUCKET_MEANS[b],
                     "count": len(grouped[b]), "items": grouped[b]} for b in BUCKETS],
        "total": len(out),
        "actionable": actionable,
        # An item in your court that you cannot act on is a queue entry with no exit. Counting them
        # separately is the difference between "you have 14 things" and "you have 14 things and 3 of
        # them are waiting on somebody else".
        "no_action": len(out) - actionable,
        "note": ("`undated` is its own bucket, not the bottom of `later` — an item nobody dated needs "
                 "a decision, and the first decision is usually when it is due. Actions are the ones "
                 "this party can perform from this state, so a button offered here will not 409."),
    }
