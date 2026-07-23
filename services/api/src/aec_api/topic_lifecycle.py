"""TOPIC-LIFE — the BCF-topic lifecycle spine: a status state machine enforced on PATCH, threaded
comments (reply_to), and a per-topic timeline merged from the audit trail + comment thread.

The state machine covers the four canonical workflow statuses; anything outside the canonical set
(imported BCF files carry vendor statuses) passes through unvalidated for round-trip compatibility —
we enforce OUR workflow, we don't reject THEIRS.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog, Comment, Topic

STATUSES = ("open", "in progress", "resolved", "closed")

# who can go where: resolved/closed can reopen (back to "in progress"), open<->in progress freely,
# anything live can resolve or close. No self-transitions (a no-op PATCH just omits status).
_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in progress", "resolved", "closed"},
    "in progress": {"open", "resolved", "closed"},
    "resolved": {"in progress", "closed"},
    "closed": {"in progress"},
}

_TIMELINE_CAP = 500          # newest-kept cap on the merged feed (HARDEN-2: desc-limit, re-sort asc)


def validate_transition(current: str | None, new: str | None) -> str | None:
    """Return an error string when the move violates the canonical state machine, else None.
    Non-canonical statuses (vendor BCF imports) on EITHER side pass through — compatibility over purity."""
    cur = str(current or "open").strip().lower()
    nxt = str(new or "").strip().lower()
    if cur not in _TRANSITIONS or nxt not in STATUSES:
        return None                       # outside the canonical machine → not ours to police
    if nxt == cur:
        return None                       # idempotent PATCH is fine
    if nxt not in _TRANSITIONS[cur]:
        return (f"invalid status transition {cur!r} -> {nxt!r}; "
                f"allowed from {cur!r}: {sorted(_TRANSITIONS[cur])}")
    return None


def validate_reply(db: Session, topic_id: str, reply_to: str | None) -> str | None:
    """Return an error string when reply_to doesn't name a comment on THIS topic, else None."""
    if not reply_to:
        return None
    parent = db.get(Comment, reply_to)
    if parent is None or parent.topic_id != topic_id:
        return "reply_to must reference an existing comment on the same topic"
    return None


def _event(ts: Any, kind: str, actor: str | None, summary: str,
           detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"ts": ts.isoformat() if ts is not None and hasattr(ts, "isoformat") else ts,
            "kind": kind, "actor": actor, "summary": summary, **({"detail": detail} if detail else {})}


def timeline(db: Session, topic: Topic) -> dict[str, Any]:
    """The topic's merged history, oldest→newest: creation, status moves, field edits, comments
    (threaded via reply_to), viewpoints, attachments — assembled from the audit trail + comment rows."""
    events: list[dict[str, Any]] = []

    audits = (db.query(AuditLog).filter(AuditLog.topic_id == topic.id)
              .order_by(AuditLog.ts.desc()).limit(_TIMELINE_CAP).all())
    for a in audits:
        det = a.detail or {}
        if a.action == "topic.create":
            events.append(_event(a.ts, "created", a.actor,
                                 f"created {det.get('type', 'topic')} “{det.get('title', '')}”"))
        elif a.action == "topic.update":
            if "status" in det:
                events.append(_event(a.ts, "status", a.actor, f"status → {det['status']}",
                                     {k: v for k, v in det.items() if k != "status"} or None))
            other = sorted(k for k in det if k != "status")
            if other:
                events.append(_event(a.ts, "update", a.actor, "updated " + ", ".join(other)))
        elif a.action == "viewpoint.create":
            events.append(_event(a.ts, "viewpoint", a.actor, "added a viewpoint"))
        elif a.action == "attachment.create":
            events.append(_event(a.ts, "attachment", a.actor,
                                 f"attached {det.get('filename', 'a file')}"))

    comments = (db.query(Comment).filter(Comment.topic_id == topic.id)
                .order_by(Comment.created_at.desc()).limit(_TIMELINE_CAP).all())
    for c in comments:
        ev = _event(c.created_at, "comment", c.author, c.text,
                    {"comment_id": c.id, **({"reply_to": c.reply_to} if c.reply_to else {})})
        events.append(ev)

    events.sort(key=lambda e: e["ts"] or "")
    if len(events) > _TIMELINE_CAP:
        events = events[-_TIMELINE_CAP:]              # keep the newest, chronological order preserved
    return {"topic_id": topic.id, "title": topic.title, "type": topic.type, "status": topic.status,
            "events": events, "event_count": len(events),
            "statuses": list(STATUSES),
            "allowed_next": sorted(_TRANSITIONS.get(str(topic.status or "").strip().lower(), set()))}
