"""Site logistics on the 4D timeline (Wave 9 · W9-5).

SYNCHRO-style site logistics without leaving openBIM: temporary construction resources — cranes, hoists,
laydown yards, gates, fencing, haul routes — as first-class objects placed in project coordinates, each
with a **schedule window**, so they appear and disappear as the 4D timeline advances (the constructability
+ site-safety rehearsal a plain build-order animation misses).

The second step ships too: **motion along paths** (a resource with a `path` interpolates its position
by schedule progress — a crawler crane walking the slab line, a hoist climbing floor by floor) and the
**swept-reach clash** (`swept_clash`): cranes whose swing discs intersect while both are on site, and
static resources (trailers, laydown, gates) parked under a crane's hook, each with the date the
conflict is worst. The rehearsal that catches "both tower cranes swing over the same bay in March".

Resource shape: `{id, kind, label, position:[x,y,z]?, path:[[x,y],...]?, polygon:[[x,y],...]?,
radius?, start?, end?}`. Dates are ISO `YYYY-MM-DD`; a missing bound is open-ended.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
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
            entry = dict(r)
            # W9-5 motion: pathed resources report where they ARE on this date, so the 4D overlay
            # draws the crane at its interpolated spot, not its day-one position
            if r.get("path"):
                pos = position_at(r, on)
                if pos is not None:
                    entry["position"] = pos
            active.append(entry)
    return {"date": str(on) if on else None, "active": active,
            "active_count": len(active), "total": len(resources)}


def _progress(r: dict, d: date | None) -> float:
    """Schedule progress 0..1 for a resource on a date (0 before/without a window, 1 after)."""
    s, e = _d(r.get("start")), _d(r.get("end"))
    if d is None or s is None or e is None or e <= s:
        return 0.0
    return max(0.0, min(1.0, (d - s).days / (e - s).days))


def position_at(r: dict, on: Any) -> list[float] | None:
    """W9-5 motion: a resource's position on a date. With a `path` (≥2 [x,y] points), the position
    interpolates along it by arc length × schedule progress — a crawler crane walking its runway, a
    hoist relocating bay by bay. Without a path, the static `position`."""
    path = r.get("path")
    if not isinstance(path, (list, tuple)) or len(path) < 2:
        pos = r.get("position")
        return [float(c) for c in pos] if isinstance(pos, (list, tuple)) and len(pos) >= 2 else None
    pts = [[float(p[0]), float(p[1])] for p in path]
    t = _progress(r, _d(on))
    lens = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    total = sum(lens)
    if total <= 0:
        return pts[0]
    target = t * total
    for i, seg in enumerate(lens):
        if target <= seg or i == len(lens) - 1:
            f = target / seg if seg > 0 else 0.0
            return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f,
                    pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f]
        target -= seg
    return pts[-1]


def _windows_overlap(a: dict, b: dict) -> tuple[date, date] | None:
    """The overlapping on-site window of two resources, or None. Open bounds clamp to the other's."""
    a_s, a_e = _d(a.get("start")), _d(a.get("end"))
    b_s, b_e = _d(b.get("start")), _d(b.get("end"))
    starts = [x for x in (a_s, b_s) if x]
    ends = [x for x in (a_e, b_e) if x]
    if not starts or not ends:
        # both fully open on one side → treat as always-overlapping; sample "today-like" midpoint
        if not starts and not ends:
            return None
        anchor = (starts or ends)[0]
        return (anchor, anchor)
    s, e = max(starts), min(ends)
    return (s, e) if s <= e else None


def swept_clash(resources: list[dict], samples: int = 16) -> dict[str, Any]:
    """W9-5 swept-reach clash: sample each pair's overlapping on-site window and flag
    **crane↔crane** swing-disc intersections (closest approach < r1+r2, with the worst date) and
    **static resources parked under a crane's hook** (trailer/laydown/gate/parking centroid inside
    the swing at any sample — a safety flag, not always an error). Moving resources are evaluated
    along their paths, so a walking crane clashes only in the weeks it actually swings overhead."""
    cranes = [r for r in resources if r.get("kind") == "crane" and r.get("radius")]
    static_kinds = ("trailer", "laydown", "gate", "parking")
    clashes: list[dict] = []
    warnings: list[dict] = []

    def _dates(win: tuple[date, date]) -> list[date]:
        s, e = win
        days = (e - s).days
        if days <= 0:
            return [s]
        step = max(1, days // max(1, samples - 1))
        return [s + timedelta(days=i) for i in range(0, days + 1, step)]

    for i in range(len(cranes)):
        for j in range(i + 1, len(cranes)):
            a, b = cranes[i], cranes[j]
            win = _windows_overlap(a, b)
            if win is None:
                continue
            best: tuple[float, date] | None = None
            for d in _dates(win):
                pa, pb = position_at(a, d), position_at(b, d)
                if pa is None or pb is None:
                    continue
                dist = math.dist(pa[:2], pb[:2])
                if best is None or dist < best[0]:
                    best = (dist, d)
            if best is None:
                continue
            reach = float(a["radius"]) + float(b["radius"])
            if best[0] < reach:
                clashes.append({
                    "a": a.get("id") or a.get("label"), "b": b.get("id") or b.get("label"),
                    "closest_m": round(best[0], 1), "combined_reach_m": round(reach, 1),
                    "worst_date": best[1].isoformat(),
                    "overlap_m": round(reach - best[0], 1),
                    "note": "swing discs intersect while both cranes are on site — stagger the "
                            "schedules, shorten a jib, or relocate one crane"})

    for c in cranes:
        for r in resources:
            if r.get("kind") not in static_kinds:
                continue
            win = _windows_overlap(c, r)
            if win is None:
                continue
            pos = position_at(r, win[0])
            if pos is None:
                poly = r.get("polygon")
                if isinstance(poly, (list, tuple)) and poly:
                    pos = [sum(float(p[0]) for p in poly) / len(poly),
                           sum(float(p[1]) for p in poly) / len(poly)]
            if pos is None:
                continue
            inside = None
            for d in _dates(win):
                cp = position_at(c, d)
                if cp is not None and math.dist(cp[:2], pos[:2]) < float(c["radius"]):
                    inside = d
                    break
            if inside is not None:
                warnings.append({
                    "crane": c.get("id") or c.get("label"),
                    "resource": r.get("id") or r.get("label"), "kind": r.get("kind"),
                    "date": inside.isoformat(),
                    "note": "sits under the crane's hook — fine for a laydown being served, a "
                            "safety review item for trailers/parking"})

    return {"cranes": len(cranes), "clashes": clashes, "clash_count": len(clashes),
            "under_hook": warnings, "samples_per_window": samples,
            "disclaimer": "Plan-level swept-reach screen (swing discs + schedule windows, sampled "
                          "along motion paths) — not a jib/boom kinematic simulation."}


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
