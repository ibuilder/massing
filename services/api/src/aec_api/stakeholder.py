"""Stakeholder analysis — turn the stakeholder register into a power/interest (Mendelow) grid and a
stance read, so a PM knows who to manage closely, who to keep satisfied, and which high-power parties
are blockers. Pure over the `stakeholder` module records."""
from __future__ import annotations

from typing import Any

from . import modules as me

_QUAD_LABEL = {"manage_closely": "Manage closely", "keep_satisfied": "Keep satisfied",
               "keep_informed": "Keep informed", "monitor": "Monitor",
               "unassessed": "Not assessed"}
_QUAD_ADVICE = {
    "manage_closely": "High power + high interest — engage fully, involve in key decisions.",
    "keep_satisfied": "High power, lower interest — keep satisfied, don't overload with detail.",
    "keep_informed": "High interest, lower power — keep informed, they're allies/advocates.",
    "monitor": "Low power + low interest — monitor with minimal effort.",
    "unassessed": "Power or interest has not been recorded — the grid cannot place these, and "
                  "they are NOT low priority. Assess them before trusting the quadrants.",
}

#: The level this 2x2 splits on. STATED rather than implied, because the register's `power` and
#: `interest` fields are three-option selects (High / Medium / Low) and Mendelow is a 2x2: so
#: **`Medium` sits on the LOW side of both axes**, and a party assessed Medium/Medium is advised
#: "monitor with minimal effort". That may be the right policy or the wrong one — it is a product
#: decision, not a bug, and it is not one this engine should make silently. What WAS a bug is that
#: nothing said so, so `by_level` below reports the distribution and the note names the split.
HIGH = "High"
#: THE BUCKET LIST, OWNED HERE. `report_builders/precon.py` iterated a hardcoded
#: `("manage_closely", "keep_satisfied", "keep_informed", "monitor")`, so adding a fifth bucket
#: would have left it out of the PDF a PM circulates — silently, because a tuple of names cannot
#: notice a name it does not contain. *A consumer that enumerates the buckets by hand cannot see a
#: new one*, and `services/api/test_stakeholder.py` now asserts this list covers every key the
#: response carries.
QUADRANT_ORDER = ("manage_closely", "keep_satisfied", "keep_informed", "monitor", "unassessed")
#: Levels a reader can be shown, in order, so a count of 0 for a level is visible as a 0 rather
#: than as an absent key.
_LEVELS = ("High", "Medium", "Low")


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def analysis(db, pid: str) -> dict[str, Any]:
    """Power/interest quadrants + stance tally + category mix + the high-power blockers to watch."""
    recs = me.list_records(db, "stakeholder", pid, limit=10000)
    active = [r for r in recs if (r.get("workflow_state") or "active") == "active"]
    quads: dict[str, list] = {k: [] for k in _QUAD_LABEL}
    stance = {"Supporter": 0, "Neutral": 0, "Blocker": 0}
    by_category: dict[str, int] = {}
    by_level = {"power": dict.fromkeys(_LEVELS, 0), "interest": dict.fromkeys(_LEVELS, 0)}
    unrecorded = {"power": 0, "interest": 0}
    blockers = []
    for r in active:
        d = r.get("data") or {}
        pw, it = (d.get("power") or "").strip(), (d.get("interest") or "").strip()
        for axis, lv in (("power", pw), ("interest", it)):
            if lv in by_level[axis]:
                by_level[axis][lv] += 1
            else:
                unrecorded[axis] += 1          # blank, or a value outside the register's options
        ph, ih = pw == HIGH, it == HIGH
        # UNASSESSED IS ITS OWN BUCKET, not `monitor`. A record with no power or no interest used to
        # fall through to "Low power + low interest — monitor with minimal effort", so a register
        # nobody had assessed read as "everybody is low priority and there are no blockers". *The
        # default branch of a 2x2 is not a place to put "unknown".*
        q = ("unassessed" if not pw or not it
             else "manage_closely" if ph and ih else "keep_satisfied" if ph
             else "keep_informed" if ih else "monitor")
        brief = {"ref": r.get("ref"), "name": r.get("title"), "organization": d.get("organization"),
                 "category": d.get("category"), "stance": d.get("stance"),
                 "power": pw or None, "interest": it or None}
        quads[q].append(brief)
        st = d.get("stance") or "Neutral"
        stance[st] = stance.get(st, 0) + 1
        cat = d.get("category") or "Other"
        by_category[cat] = by_category.get(cat, 0) + 1
        if d.get("stance") == "Blocker":
            blockers.append(brief)
    assessed = len(active) - len(quads["unassessed"])
    return {
        "total": len(active),
        "assessed": assessed,
        "quadrants": {k: {"label": _QUAD_LABEL[k], "advice": _QUAD_ADVICE[k], "count": len(v),
                          "stakeholders": v} for k, v in quads.items()},
        "stance": stance, "supporter_pct": _pct(stance["Supporter"], len(active)),
        "by_category": by_category,
        # BOTH, and the narrow one is NOT dropped: `high_power_blockers` is the subset it has always
        # been and a caller may still want exactly that. What was wrong was having only it — the
        # register's scale has three levels, so a MEDIUM-power Blocker is a real party a PM needs to
        # see and this engine never mentioned one. *A subset is fine; a subset standing in for the
        # whole is not.*
        "blockers": blockers,
        "high_power_blockers": [b for b in blockers if b["power"] == HIGH],
        "grid": {
            "high_level": HIGH, "levels": list(_LEVELS), "by_level": by_level,
            "unrecorded": unrecorded, "unassessed": len(quads["unassessed"]),
            "reason": ("no active stakeholder is recorded" if not active
                       else "every active stakeholder has a power and an interest level"
                       if not quads["unassessed"]
                       else f"{len(quads['unassessed'])} of {len(active)} active stakeholder(s) "
                            "have no power or no interest level, so the grid cannot place them"),
        },
        "note": "Mendelow power/interest grid: manage-closely (high/high), keep-satisfied (high power), "
                "keep-informed (high interest), monitor (low/low). The register's scale has THREE "
                f"levels and this grid splits at '{HIGH}', so Medium sits on the low side of both "
                "axes — see `grid.by_level` for the distribution. Stakeholders missing either level "
                "are in 'Not assessed' rather than 'Monitor'. Blockers are listed at every power "
                "level; `high_power_blockers` is the high-power subset.",
    }
