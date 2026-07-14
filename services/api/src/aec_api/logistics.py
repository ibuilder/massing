"""Site logistics on the 4D timeline (Wave 9 · W9-5, M first step).

SYNCHRO-style site logistics without leaving openBIM: temporary construction resources — cranes, hoists,
laydown yards, gates, fencing, haul routes — as first-class objects placed in project coordinates, each
with a **schedule window**, so they appear and disappear as the 4D timeline advances (the constructability
+ site-safety rehearsal a plain build-order animation misses). This is the static, time-phased first step;
smooth motion along paths + swept crane-reach clash is the deferred follow-up.

Resource shape: `{id, kind, label, position:[x,y,z]?, polygon:[[x,y],...]?, radius?, start?, end?}`.
Dates are ISO `YYYY-MM-DD`; a missing bound is open-ended.
"""
from __future__ import annotations

from datetime import date
from typing import Any

KINDS = ("crane", "hoist", "laydown", "gate", "fence", "haul_route", "trailer", "parking")


def _d(s: Any) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def state_at(resources: list[dict], on: Any) -> dict[str, Any]:
    """Which resources are active on a given date (start ≤ on ≤ end; a missing bound is open-ended).
    With no date, everything is active — the whole site plan."""
    d = _d(on)
    active = []
    for r in resources:
        s, e = _d(r.get("start")), _d(r.get("end"))
        if d is None or ((s is None or s <= d) and (e is None or d <= e)):
            active.append(r)
    return {"date": str(on) if on else None, "active": active,
            "active_count": len(active), "total": len(resources)}


def summary(resources: list[dict]) -> dict[str, Any]:
    """Roll-up: count by kind + the overall scheduled window."""
    by_kind: dict[str, int] = {}
    for r in resources:
        k = r.get("kind", "?")
        by_kind[k] = by_kind.get(k, 0) + 1
    starts = [x for x in (_d(r.get("start")) for r in resources) if x]
    ends = [x for x in (_d(r.get("end")) for r in resources) if x]
    return {"total": len(resources), "by_kind": by_kind,
            "start": min(starts).isoformat() if starts else None,
            "end": max(ends).isoformat() if ends else None}
