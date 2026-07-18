"""Role-tailored dashboard (GC portal). Aggregates records across all modules into a
per-party view: KPIs, "ball-in-your-court" action items (records the acting party can move
through the workflow right now), per-module status counts, and a cost snapshot."""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import cost
from . import modules as me
from .timeutil import utc_today


def _overdue(rec: dict) -> bool:
    due = rec["data"].get("due_date")
    try:
        return bool(due) and date.fromisoformat(str(due)[:10]) < utc_today() \
            and rec["workflow_state"] not in ("closed", "answered", "verified", "done")
    except (TypeError, ValueError):
        return False


def build(db: Session, pid: str, party: str | None) -> dict[str, Any]:
    by_module: list[dict] = []
    action_items: list[dict] = []
    overdue = 0
    open_states = {"open", "submitted", "draft", "issued", "scheduled", "investigating",
                   "applied", "agenda", "proposed", "pending"}
    # _overdue ignores these terminal states; loading JSON only for non-terminal records (active set)
    # is the perf win — counts come from a GROUP BY that never touches the JSON `data` blob.
    terminal_states = {"closed", "answered", "verified", "done"}
    counts = Counter()

    ACTION_CAP = 300          # bound the action-item collection (output is sliced to 100 anyway)
    for key, mod in me.REGISTRY.items():
        states = me.state_counts(db, key, pid)           # GROUP BY — no JSON parsed
        total = sum(states.values())
        if not total:
            continue
        by_module.append({"key": key, "name": mod["name"], "section": mod.get("section"),
                          "count": total, "by_state": states})
        counts["total"] += total
        counts[f"open:{key}"] += sum(n for s, n in states.items() if s in open_states)

        # overdue: only modules that actually carry a due-date field need their JSON loaded — at
        # scale this avoids reading the `data` blob for the entire non-terminal tail of every module.
        if me._due_field_name(mod):
            for r in me.active_records(db, key, pid, terminal_states):
                if _overdue(r):
                    overdue += 1

        # action items: query only the states where this party has a move AND that are "open", with
        # lean columns (no JSON) and a cap — not the whole active tail. `available_actions` needs
        # only workflow_state, which is an indexed column.
        if len(action_items) < ACTION_CAP:
            actionable = {s for s in states
                          if s in open_states and me.available_actions(mod, s, party)}
            if actionable:
                need = ACTION_CAP - len(action_items)
                for r in me.active_records(db, key, pid, terminal_states, with_data=False,
                                           states=actionable, limit=need):
                    action_items.append({
                        "module": key, "module_name": mod["name"], "id": r["id"], "ref": r["ref"],
                        "title": r["title"], "state": r["workflow_state"],
                        "actions": [a["action"] for a in me.available_actions(mod, r["workflow_state"], party)],
                    })

    def open_count(key):
        return counts.get(f"open:{key}", 0)

    kpis = {
        "total_records": counts["total"],
        "my_action_items": len(action_items),
        "overdue": overdue,
        "open_rfis": open_count("rfi"),
        "pending_change_orders": open_count("cor"),
        "open_issues": open_count("issue") + open_count("coordination_issue"),
        "open_quality": open_count("ncr") + open_count("deficiency") + open_count("inspection"),
        "open_safety": open_count("incident") + open_count("observation"),
        "open_punchlist": open_count("punchlist"),
    }

    try:
        cost_snapshot = cost.summary(db, pid)
    except Exception:
        cost_snapshot = None

    by_module.sort(key=lambda m: (-m["count"], m["name"]))
    action_items.sort(key=lambda a: a["module"])
    return {"party": party or "GC", "kpis": kpis, "cost": cost_snapshot,
            "action_items": action_items[:100], "by_module": by_module}
