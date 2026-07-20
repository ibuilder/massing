"""GOLDEN-THREAD (R14) — the compliance **evidence ledger** rollup.

The "golden thread" of building-safety practice is the unbroken trace from every requirement to the
evidence that it was met and the person who signed it off. This rolls up the ``compliance_evidence``
module records into that picture: how complete the thread is (share signed off), the outcome/category
spread, and — most useful — the **broken-thread list**: requirements still missing evidence or a
sign-off, worst first (a failed/pending requirement with no evidence attached is the top risk).

Pure over the module records — a persisted, versioned ledger that extends the preflight/code checks
from a point-in-time score into an auditable, sign-off-tracked record.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

_MAX_BROKEN = 100


def summary(db: Session, pid: str) -> dict[str, Any]:
    """Roll up the project's ``compliance_evidence`` ledger into the golden-thread picture."""
    from . import modules as me

    recs = me.list_records(db, "compliance_evidence", pid, limit=100_000)
    by_outcome: dict[str, int] = {}
    by_category: dict[str, int] = {}
    signed = evidenced = 0
    broken: list[dict] = []
    for r in recs:
        d = r.get("data") or {}
        oc = (d.get("outcome") or "Pending").strip() or "Pending"
        cat = (d.get("category") or "Other").strip() or "Other"
        by_outcome[oc] = by_outcome.get(oc, 0) + 1
        by_category[cat] = by_category.get(cat, 0) + 1
        state = r.get("workflow_state")
        has_ev = bool((d.get("evidence_ref") or "").strip())
        if state == "signed_off":
            signed += 1
        if has_ev:
            evidenced += 1
        if state != "signed_off":               # a broken link in the thread
            broken.append({"ref": r.get("ref"), "requirement": d.get("requirement"),
                           "category": cat, "outcome": oc, "state": state or "open",
                           "has_evidence": has_ev,
                           "risk": "high" if (oc in ("Fail", "Pending") and not has_ev) else
                                   "medium" if not has_ev else "low"})
    total = len(recs)
    _risk = {"high": 0, "medium": 1, "low": 2}
    broken.sort(key=lambda b: (_risk.get(b["risk"], 3), b["category"]))
    return {
        "total": total, "signed_off": signed, "evidenced": evidenced,
        "completeness_pct": round(100.0 * signed / total, 1) if total else 0.0,
        "evidenced_pct": round(100.0 * evidenced / total, 1) if total else 0.0,
        "by_outcome": by_outcome, "by_category": by_category,
        "broken_count": len(broken), "broken_thread": broken[:_MAX_BROKEN],
        "note": "The golden thread = every requirement traced to evidence + a sign-off. Completeness is "
                "the signed-off share; the broken-thread list is the requirements still missing evidence "
                "or a sign-off — a failed/pending requirement with no evidence attached ranks highest.",
    }
