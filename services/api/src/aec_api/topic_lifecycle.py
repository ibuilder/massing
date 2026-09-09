"""TOPIC-LIFE — the BCF-topic lifecycle spine: a status state machine enforced on PATCH, threaded
comments (reply_to), and a per-topic timeline merged from the audit trail + comment thread.

The state machine covers the four canonical workflow statuses; anything outside the canonical set
(imported BCF files carry vendor statuses) passes through unvalidated for round-trip compatibility —
we enforce OUR workflow, we don't reject THEIRS.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
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


#: The audit actions the timeline renders. **The cap is applied to these in SQL, not to every audit
#: row on the topic** — a topic whose recent trail is `bcf.comment.create` / `markup.promote` /
#: `record.comment.promote` (all real, all rendering nothing here) would otherwise spend its whole
#: 500-row window on rows that produce no events, and the timeline would come back missing history
#: it holds. That is the LIMIT-FILTER shape: cap first, drop after, answer looks like "nothing
#: happened". `_expand` dispatches on exactly these names, so the two cannot disagree about what a
#: rendered action is.
_RENDERED_ACTIONS = ("topic.create", "topic.update", "viewpoint.create", "attachment.create")


def _expand(ts: Any, action: str | None, actor: str | None,
            detail: dict[str, Any] | None) -> list[dict[str, Any]]:
    """One audit row → the timeline events it yields. **The cardinality is not 1.**

    A `topic.update` carrying a status change *and* other field edits yields TWO events; an action
    outside the handled set yields NONE. That is why `_emitted_total` below calls this function
    rather than counting rows: the expansion rule and the count are then the same code, and cannot
    drift into disagreeing about what an event is.
    """
    det = detail or {}
    out: list[dict[str, Any]] = []
    if action == "topic.create":
        out.append(_event(ts, "created", actor,
                          f"created {det.get('type', 'topic')} \u201c{det.get('title', '')}\u201d"))
    elif action == "topic.update":
        if "status" in det:
            out.append(_event(ts, "status", actor, f"status \u2192 {det['status']}",
                              {k: v for k, v in det.items() if k != "status"} or None))
        other = sorted(k for k in det if k != "status")
        if other:
            out.append(_event(ts, "update", actor, "updated " + ", ".join(other)))
    elif action == "viewpoint.create":
        out.append(_event(ts, "viewpoint", actor, "added a viewpoint"))
    elif action == "attachment.create":
        out.append(_event(ts, "attachment", actor,
                          f"attached {det.get('filename', 'a file')}"))
    return out


def _emitted_total(db: Session, topic_id: str) -> int:
    """How many events the whole topic yields — **counted in events, not in rows.**

    The first version of this disclosure counted audit rows, and its own docstring said so: "one
    `topic.update` carrying a status change AND field edits yields two, so the total is a floor."
    A floor is not a total. With 500 such rows the count read 500, `event_count` also read 500, and
    `truncated` came back **False** on a timeline that had dropped half its history — the disclosure
    reporting *itself* complete. (It ran the other way too: an unhandled action counted as a row and
    emitted nothing, so the total could over-report and claim a truncation that had not happened.)

    Naming a defect in a comment and shipping it is the failure this repository has recorded before.
    """
    total = db.query(Comment).filter(Comment.topic_id == topic_id).count()
    for action, detail in db.execute(select(AuditLog.action, AuditLog.detail)
                                     .where(AuditLog.topic_id == topic_id,
                                            AuditLog.action.in_(_RENDERED_ACTIONS))):
        total += len(_expand(None, action, None, detail))
    return total


def timeline(db: Session, topic: Topic) -> dict[str, Any]:
    """The topic's merged history, oldest\u2192newest: creation, status moves, field edits, comments
    (threaded via reply_to), viewpoints, attachments \u2014 assembled from the audit trail + comment rows."""
    events: list[dict[str, Any]] = []

    audits = (db.query(AuditLog).filter(AuditLog.topic_id == topic.id,
                                        AuditLog.action.in_(_RENDERED_ACTIONS))
              .order_by(AuditLog.ts.desc()).limit(_TIMELINE_CAP).all())
    for a in audits:
        events.extend(_expand(a.ts, a.action, a.actor, a.detail))

    comments = (db.query(Comment).filter(Comment.topic_id == topic.id)
                .order_by(Comment.created_at.desc()).limit(_TIMELINE_CAP).all())
    for c in comments:
        events.append(_event(c.created_at, "comment", c.author, c.text,
                             {"comment_id": c.id, **({"reply_to": c.reply_to} if c.reply_to else {})}))

    events.sort(key=lambda e: e["ts"] or "")
    # COUNTED OVER THE WHOLE TOPIC, not from `events`. Both queries above are capped at
    # `_TIMELINE_CAP`, so the assembled list can never exceed 2\u00d7CAP however long the topic is \u2014 the
    # first version of this disclosure used `len(events)` and therefore reported a total that was
    # itself a window, which is the very defect this line exists to disclose, one layer down.
    # The extra scan is skipped when the capped queries came back short, because a `LIMIT n` that
    # returns fewer than n rows has already returned all of them.
    assembled = (len(events) if len(audits) < _TIMELINE_CAP and len(comments) < _TIMELINE_CAP
                 else _emitted_total(db, topic.id))
    if len(events) > _TIMELINE_CAP:
        events = events[-_TIMELINE_CAP:]              # keep the newest, chronological order preserved
    # `event_count` is what this window holds; `event_total` is what the topic has. They used to be
    # the same name for two different numbers \u2014 the count was computed AFTER the cap, so a topic
    # with 800 events reported 500 and said nothing, and "the history" was silently the tail of it.
    # A truncated timeline is the one place a reader is most likely to conclude something did not
    # happen: the missing events are the OLDEST, which is where a decision's origin lives.
    total = max(assembled, len(events))
    return {"topic_id": topic.id, "title": topic.title, "type": topic.type, "status": topic.status,
            "events": events, "event_count": len(events),
            "event_total": total,
            "truncated": total > len(events),
            "statuses": list(STATUSES),
            "allowed_next": sorted(_TRANSITIONS.get(str(topic.status or "").strip().lower(), set()))}
