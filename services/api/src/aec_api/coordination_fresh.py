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
    """Open clash/coordination topics whose referenced elements changed between versions a→b,
    **beside the ones this check could not rule on at all**.

    COORD-UNANCHORED — AN UNANCHORED TOPIC IS NOT A FRESH ONE
    --------------------------------------------------------
    The whole test is `topic.element_guids ∩ changed`, so a topic carrying **no element GUIDs** can
    never be stale by construction: the intersection is empty however much of the model moved. It
    was therefore reported as one of the `open_coordination_issues` that did not go stale — and a
    coordinator reading *"2 of 40 open issues are stale"* concludes the other 38 are still valid.
    For an unanchored one the truth is *"this check cannot say"*.

    That is not a hypothetical shape: BCF topics created by hand, imported from another tool, or
    logged against a drawing rather than a model element routinely carry no `element_guids`, and the
    clash engine is only one of the ways a `clash`/`coordination` topic gets created. *A verdict
    whose own premise is absent for a row has not been reached on that row.*

    So the population splits. `stale_count` counts over the ASSESSABLE set, `unanchored` counts what
    the premise does not apply to, and the two sum to `open_coordination_issues` — asserted in
    `services/api/test_coord_unanchored.py` so a later field cannot drift out of the identity.

    AND A DIFF THAT FOUND NOTHING IS ITS OWN STATE
    ----------------------------------------------
    When `changed_elements` is 0 — the versions are identical, or a fingerprint set is missing so
    `versions.diff` has nothing to compare — every assessable topic is trivially not stale, and a
    "0 stale" answer says nothing about any of them. `comparable` is false in that case, for the
    same reason `soft_clash` keeps `untested` out of `clean`.
    """
    diff = versions.diff(db, pid, a, b)
    changed = _changed_guids(diff)
    rows = (db.query(Topic)
            .filter(Topic.project_id == pid, Topic.type.in_(_CLASH_TYPES), Topic.status == "open")
            .all())
    stale = []
    unanchored = []
    for t in rows:
        anchors = set(t.element_guids or [])
        if not anchors:
            # Reported, not counted as fresh. The id and title travel so a screen can offer to go
            # and anchor it — which is the only thing that makes this check apply to it next time.
            #
            # The `continue` is an EARLY EXIT, not a guard, and that is worth saying because a
            # mutation deleting it changes nothing: `set() & changed` is empty, so the stale test
            # below cannot fire for this row anyway. It was nearly recorded as a surviving mutation
            # — *a mutation that does not change the property under test is mis-stated, not
            # survived.* What IS load-bearing is the `append` above it, and deleting that reds seven
            # assertions.
            unanchored.append({"id": t.id, "guid": t.guid, "title": t.title})
            continue
        hit = sorted(anchors & changed)
        if hit:
            stale.append({"id": t.id, "guid": t.guid, "title": t.title,
                          "changed_guids": hit, "already_flagged": _FLAG_LABEL in (t.labels or [])})
    assessable = len(rows) - len(unanchored)
    return {"from": a, "to": b, "changed_elements": len(changed),
            "open_coordination_issues": len(rows), "stale": stale, "stale_count": len(stale),
            "assessable": assessable,
            "unanchored": len(unanchored), "unanchored_topics": unanchored[:200],
            # False when the diff found nothing to compare, or when no open topic carries an anchor:
            # in both cases a `stale_count` of 0 is an absence of evidence, not a clean bill.
            "comparable": bool(changed) and assessable > 0,
            "note": ("Open clash/coordination topics whose anchored elements changed between the two "
                     "published versions \u2014 advisory, never auto-closed, because a changed element "
                     "can mean the clash is gone OR worse. `stale_count` is over the ASSESSABLE "
                     f"topics ({assessable} of {len(rows)} open): a topic with no element GlobalIds "
                     "cannot be ruled on by this check at all and is counted in `unanchored` rather "
                     "than reported as still valid."
                     + ("" if changed else " No element changed between these versions, so nothing "
                        "here is evidence about any topic.")
                     + ("" if assessable else " NO open topic carries an element anchor, so this "
                        "check ruled on nothing."))}


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
