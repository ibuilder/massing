"""Stakeholder analysis — turn the stakeholder register into a power/interest (Mendelow) grid and a
stance read, so a PM knows who to manage closely, who to keep satisfied, and which high-power parties
are blockers. Pure over the `stakeholder` module records."""
from __future__ import annotations

from typing import Any

from . import modules as me

_QUAD_LABEL = {"manage_closely": "Manage closely", "keep_satisfied": "Keep satisfied",
               "keep_informed": "Keep informed", "monitor": "Monitor"}
_QUAD_ADVICE = {
    "manage_closely": "High power + high interest — engage fully, involve in key decisions.",
    "keep_satisfied": "High power, lower interest — keep satisfied, don't overload with detail.",
    "keep_informed": "High interest, lower power — keep informed, they're allies/advocates.",
    "monitor": "Low power + low interest — monitor with minimal effort.",
}


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def analysis(db, pid: str) -> dict[str, Any]:
    """Power/interest quadrants + stance tally + category mix + the high-power blockers to watch."""
    recs = me.list_records(db, "stakeholder", pid, limit=10000)
    active = [r for r in recs if (r.get("workflow_state") or "active") == "active"]
    quads: dict[str, list] = {k: [] for k in _QUAD_LABEL}
    stance = {"Supporter": 0, "Neutral": 0, "Blocker": 0}
    by_category: dict[str, int] = {}
    blockers = []
    for r in active:
        d = r.get("data") or {}
        ph, ih = d.get("power") == "High", d.get("interest") == "High"
        q = ("manage_closely" if ph and ih else "keep_satisfied" if ph
             else "keep_informed" if ih else "monitor")
        brief = {"ref": r.get("ref"), "name": r.get("title"), "organization": d.get("organization"),
                 "category": d.get("category"), "stance": d.get("stance")}
        quads[q].append(brief)
        s = d.get("stance") or "Neutral"
        stance[s] = stance.get(s, 0) + 1
        cat = d.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1
        if ph and d.get("stance") == "Blocker":
            blockers.append(brief)
    return {
        "total": len(active),
        "quadrants": {k: {"label": _QUAD_LABEL[k], "advice": _QUAD_ADVICE[k], "count": len(v),
                          "stakeholders": v} for k, v in quads.items()},
        "stance": stance, "supporter_pct": _pct(stance["Supporter"], len(active)),
        "by_category": by_category, "high_power_blockers": blockers,
        "note": "Mendelow power/interest grid: manage-closely (high/high), keep-satisfied (high power), "
                "keep-informed (high interest), monitor (low/low). High-power blockers are flagged.",
    }
