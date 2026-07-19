"""Overdue escalation — the automation layer over the SLA due-feed (WORKFLOW-ENGINE).

`modules.due_feed` already answers *what is overdue*; this decides *what to do about it*. Each overdue
record climbs an escalation LADDER as it ages past its due date. At each new rung it gets an
`escalation:L{n}` entry on its activity timeline — which the notifications feed already surfaces to the
record's ball-in-court party and its assignee — so an ignored RFI / submittal / change order nudges the
responsible party harder the longer it sits.

Idempotent per rung: a record is escalated to a given level at most once, guarded by the highest
`escalation:L*` already on its timeline. A nightly scan (or a re-run after a worker crash — the job
kind is crash-recovered) therefore never spams; a record only fires again when it climbs to the next
rung. No new tables: it rides `RecordActivity` + the existing feed."""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from . import modules as mod
from .models import RecordActivity

# (min days overdue, level). A record `days_overdue` late gets the level of the first rung it clears,
# checked high→low: 7+ days → L3, 3–6 → L2, 0–2 → L1. Override per call via `ladder`.
DEFAULT_LADDER: list[tuple[int, int]] = [(7, 3), (3, 2), (0, 1)]
SYSTEM_ACTOR = "system"


def _ladder(ladder: Sequence[Sequence[int]] | None) -> list[tuple[int, int]]:
    """Normalize a caller-supplied ladder to sorted (min_days, level) tuples, high→low. Falls back to
    the default when empty/None so a bad override can never disable escalation silently."""
    if not ladder:
        return DEFAULT_LADDER
    try:
        norm = sorted(((int(d), int(lvl)) for d, lvl in ladder), reverse=True)
    except (TypeError, ValueError):
        return DEFAULT_LADDER
    return norm or DEFAULT_LADDER


def _level(days_overdue: int, ladder: list[tuple[int, int]]) -> int:
    for min_days, lvl in ladder:
        if days_overdue >= min_days:
            return lvl
    return 0


def _applied_level(db: Session, project_id: str, module: str, rid: str) -> int:
    """Highest escalation level already recorded on a record's timeline (0 if never escalated)."""
    rows = (db.query(RecordActivity.action)
            .filter(RecordActivity.project_id == project_id, RecordActivity.module == module,
                    RecordActivity.record_id == rid,
                    RecordActivity.action.like("escalation:L%")).all())
    best = 0
    for (a,) in rows:
        try:
            best = max(best, int(a.rsplit("L", 1)[1]))
        except (ValueError, IndexError):
            continue
    return best


def scan(db: Session, project_id: str, ladder: Sequence[Sequence[int]] | None = None) -> dict:
    """Read-only: every overdue record with its computed escalation level, the level already applied,
    and whether it still needs escalating (computed > applied). Drives the escalation preview + badge."""
    lad = _ladder(ladder)
    feed = mod.due_feed(db, project_id)
    items: list[dict] = []
    for x in feed.get("overdue", []):
        days_over = -int(x.get("days", 0))
        lvl = _level(days_over, lad)
        applied = _applied_level(db, project_id, x["module"], x["id"])
        court = mod.court_party(mod.REGISTRY.get(x["module"], {}), x.get("state"))
        items.append({
            "module": x["module"], "module_name": x.get("module_name"), "icon": x.get("icon"),
            "id": x["id"], "ref": x.get("ref"), "title": x.get("title"), "state": x.get("state"),
            "assignee": x.get("assignee"), "due_date": x.get("due_date"),
            "days_overdue": days_over, "level": lvl, "applied_level": applied,
            "court": court, "needs_escalation": lvl > applied,
        })
    items.sort(key=lambda i: (-i["level"], -i["days_overdue"]))
    by_level: dict[int, int] = {}
    for i in items:
        by_level[i["level"]] = by_level.get(i["level"], 0) + 1
    return {"as_of": feed.get("as_of"), "count": len(items),
            "pending": sum(1 for i in items if i["needs_escalation"]),
            "by_level": by_level, "items": items}


def run(db: Session, project_id: str, actor: str = SYSTEM_ACTOR,
        ladder: Sequence[Sequence[int]] | None = None) -> dict:
    """Apply escalations: for each overdue record whose computed level exceeds the level already on its
    timeline, write an `escalation:L{n}` activity — surfaced to the ball-in-court party + the assignee
    by the notifications feed. Idempotent: re-running before a record climbs the next rung escalates
    nothing new."""
    result = scan(db, project_id, ladder)
    escalated: list[dict] = []
    for i in result["items"]:
        if not i["needs_escalation"]:
            continue
        mod._log(db, project_id, i["module"], i["id"], actor, i.get("court"),
                 f"escalation:L{i['level']}",
                 {"level": i["level"], "days_overdue": i["days_overdue"],
                  "due_date": i["due_date"], "court": i.get("court")})
        escalated.append({"module": i["module"], "id": i["id"], "ref": i["ref"],
                          "title": i["title"], "level": i["level"],
                          "days_overdue": i["days_overdue"], "court": i.get("court")})
    if escalated:
        db.commit()
    by_level: dict[int, int] = {}
    for e in escalated:
        by_level[e["level"]] = by_level.get(e["level"], 0) + 1
    return {"as_of": result["as_of"], "escalated": len(escalated),
            "by_level": by_level, "items": escalated}
