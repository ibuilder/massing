"""SMART-VIEWS (clash-bound freshness) — flag open clash/coordination issues whose elements changed
between two published model versions, so a coordinator knows which are likely stale (resolved, moved,
or worse) and worth a re-check.

Deliberately **advisory, not auto-close**: a changed element doesn't prove a clash is gone (it could be
worse), so `recheck` adds a comment + a `model-changed` label to the affected open topics rather than
silently closing them — the human decides. Pure glue over `versions.diff` (which already returns the
added/removed/modified GUIDs) + the BCF-model Topic/Comment rows.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import versions
from .models import Comment, Topic

# topic types whose element_guids anchor a model-coordination issue
_CLASH_TYPES = ("clash", "coordination")
_FLAG_LABEL = "model-changed"


def _changed_guids(diff: dict) -> set[str]:
    """Every GUID that changed a→b: added ∪ removed ∪ modified."""
    return set(diff.get("added") or []) | set(diff.get("removed") or []) \
        | {m["guid"] for m in (diff.get("modified") or []) if m.get("guid")}


def stale_clashes(db: Session, pid: str, a: int, b: int) -> dict[str, Any]:
    """Open clash/coordination topics whose referenced elements changed between versions a→b."""
    diff = versions.diff(db, pid, a, b)
    changed = _changed_guids(diff)
    rows = (db.query(Topic)
            .filter(Topic.project_id == pid, Topic.type.in_(_CLASH_TYPES), Topic.status == "open")
            .all())
    stale = []
    for t in rows:
        hit = sorted(set(t.element_guids or []) & changed)
        if hit:
            stale.append({"id": t.id, "guid": t.guid, "title": t.title,
                          "changed_guids": hit, "already_flagged": _FLAG_LABEL in (t.labels or [])})
    return {"from": a, "to": b, "changed_elements": len(changed),
            "open_coordination_issues": len(rows), "stale": stale, "stale_count": len(stale)}


def recheck(db: Session, pid: str, a: int, b: int, actor: str = "system") -> dict[str, Any]:
    """Flag each stale clash topic (a `model-changed` label + a re-verify comment) — idempotent, and
    never closes a topic. Returns the count newly flagged."""
    res = stale_clashes(db, pid, a, b)
    flagged = 0
    for s in res["stale"]:
        if s["already_flagged"]:
            continue
        t = db.get(Topic, s["id"])
        if not t:
            continue
        t.labels = sorted(set(t.labels or []) | {_FLAG_LABEL})
        db.add(Comment(topic_id=t.id, author=actor,
                       text=(f"Elements changed in v{b} since this issue was logged "
                             f"({len(s['changed_guids'])} affected) — re-verify whether it still applies.")))
        flagged += 1
    db.commit()
    return {**res, "flagged": flagged}
