"""Pre-flight — the one-click **"is this model clean enough to issue?"** gate. The platform already scores
model health (`model_health.scorecard`: hygiene · KPIs · clash · verified-as-built · code readiness) and
flags decision-readiness gaps; what it lacked is a single crisp **PASS / HOLD verdict** with a pre-issue
checklist — the pyRevit "run the pre-flight before you publish" moment.

This composes the shipped lenses into a checklist, adds the one missing lens — **discipline-classification
completeness** (elements that don't map to the discipline tree can't be scheduled / priced / drawn by
discipline) — and folds in **open high-priority issues** as a hard blocker. Reuses the engines; no
duplicate logic.
"""
from __future__ import annotations

from typing import Any

_PASS, _WARN, _FAIL = "pass", "warn", "fail"
_ORDER = {_FAIL: 0, _WARN: 1, _PASS: 2}


def _lens_status(score: float) -> str:
    return _PASS if score >= 85 else _WARN if score >= 60 else _FAIL


def issuance_gate(db, pid: str, model, elements: list[dict] | None) -> dict[str, Any]:
    """A pre-issue checklist + a single ready/hold verdict. `model` enables the hygiene lens; `elements`
    is the published property index (for classification completeness)."""
    from . import classification, model_health
    from .models import Topic

    card = model_health.scorecard(db, pid, model=model, elements=elements)
    checks: list[dict[str, Any]] = []

    # 1) every scored model-health lens becomes a checklist item
    for ln in card.get("lenses", []):
        if ln.get("score") is None:
            continue
        checks.append({"key": ln["key"], "label": ln["label"], "status": _lens_status(ln["score"]),
                       "detail": ln.get("headline", ""), "score": ln["score"]})

    # 2) discipline-classification completeness — the missing lens (elements that don't map to the tree)
    els = elements or []
    total = len(els)
    if total:
        unclassified = [e.get("guid") for e in els
                        if not classification.discipline_of_ifc_class(e.get("ifc_class", ""))]
        pct = round(100 * (1 - len(unclassified) / total), 1)
        checks.append({"key": "classification", "label": "Discipline classification",
                       "status": _PASS if pct >= 95 else _WARN if pct >= 80 else _FAIL,
                       "detail": f"{total - len(unclassified)}/{total} elements classified ({pct}%)",
                       "score": pct, "count": len(unclassified),
                       "guids": [g for g in unclassified if g][:200]})

    # 3) open high-priority coordination / RFI issues are a hard blocker to issuing
    open_high = (db.query(Topic)
                 .filter(Topic.project_id == pid, Topic.status != "closed", Topic.priority == "high")
                 .count())
    checks.append({"key": "open_issues", "label": "Open high-priority issues",
                   "status": _FAIL if open_high else _PASS,
                   "detail": (f"{open_high} open high-priority BCF/RFI item(s) to resolve" if open_high
                              else "no open high-priority issues"),
                   "count": open_high})

    blocking = [c for c in checks if c["status"] == _FAIL]
    warnings = [c for c in checks if c["status"] == _WARN]
    ready = not blocking
    return {
        "ready": ready,
        "verdict": "READY TO ISSUE" if ready else "HOLD — resolve the blocker(s) first",
        "overall_score": card.get("overall_score"),
        "band": card.get("band"),
        "blocking": len(blocking),
        "warnings": len(warnings),
        "checks": sorted(checks, key=lambda c: _ORDER[c["status"]]),
        "disclaimer": "A pre-issue model-health gate composing hygiene, clash coordination, code readiness, "
                      "verified-as-built, and classification completeness. Not a substitute for a "
                      "professional review or the AHJ.",
    }
