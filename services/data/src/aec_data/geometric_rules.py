"""RULE-LIB-2 — geometric/relational rule checks over the baked AABB geometry path.

Property rules (aec_api rule_library) answer "does this element *declare* X?"; these answer the
spatial questions the property index cannot: is there clear space in front of a door, how far is a
space from an exit, is a door wide enough for an accessible route. All checks are **AABB-level** —
deliberate first-order approximations on the same world-space boxes the clash broad phase bakes
(fast, no mesh booleans needed), not swept-path analysis:

  * ``clearance``       — an element needs ``distance_m`` of clear approach on at least one side
                          along its thin horizontal axis (door swing / equipment maintenance
                          access). Anything overlapping the scope element itself (its host wall,
                          frame) is not an obstruction; the probe volume is trimmed 5 cm off the
                          element's top/bottom so the floor it sits on doesn't count either.
  * ``escape_distance`` — straight-line horizontal distance from each scope element to the nearest
                          exit element must be ≤ ``max_m``. Egress travel distance is a path
                          measure; the straight line is its lower bound, so a straight-line
                          violation is always a real violation (no false positives, some misses).
  * ``clear_width``     — the larger horizontal AABB dimension (the opening width) must be
                          ≥ ``min_m`` (ADA 815 mm / 32 in accessible clear-width proxy).

Checks take plain box dicts (``{guid, ifc_class, name, min, max}``) so they unit-test without any
IFC; ``bake_boxes(ifc_path)`` produces them from a model via the clash iterator.
"""
from __future__ import annotations

import math
from typing import Any

KINDS = ("clearance", "escape_distance", "clear_width")
_EPS = 1e-6
_Z_TRIM = 0.05          # metres shaved off the probe's top/bottom (floor below / lintel above)


def bake_boxes(ifc_path: str) -> list[dict[str, Any]]:
    """World-space AABB per element (SI metres, same iterator as the clash broad phase)."""
    from .clash import _compute_geometry
    from .ifc_loader import open_model

    model = open_model(ifc_path)
    return [{"guid": e.guid, "ifc_class": e.ifc_class, "name": e.name,
             "min": tuple(float(v) for v in e.min), "max": tuple(float(v) for v in e.max)}
            for e in _compute_geometry(model, keep_mesh=False)]


def _overlap(amin, amax, bmin, bmax) -> bool:
    return all(min(amax[i], bmax[i]) - max(amin[i], bmin[i]) > _EPS for i in range(3))


def _center(b: dict) -> tuple[float, float, float]:
    return tuple((b["min"][i] + b["max"][i]) / 2 for i in range(3))


def check_clearance(boxes: list[dict], scope: set[str], distance_m: float,
                    obstructions: set[str] | None = None) -> dict:
    """Each scope element needs a clear ``distance_m`` slab on at least ONE side along its thin
    horizontal axis. ``obstructions=None`` means every other element can obstruct."""
    elems = [b for b in boxes if b["guid"] in scope]
    obst = [b for b in boxes if obstructions is None or b["guid"] in obstructions]
    viol = []
    for e in elems:
        dims = (e["max"][0] - e["min"][0], e["max"][1] - e["min"][1])
        thin = 0 if dims[0] <= dims[1] else 1          # approach axis: across the leaf/face
        zlo = e["min"][2] + _Z_TRIM
        zhi = max(zlo + _EPS, e["max"][2] - _Z_TRIM)
        blocking = []
        for sign in (-1, 1):                            # both approach sides
            lo, hi = list(e["min"]), list(e["max"])
            if sign < 0:
                lo[thin], hi[thin] = e["min"][thin] - distance_m, e["min"][thin]
            else:
                lo[thin], hi[thin] = e["max"][thin], e["max"][thin] + distance_m
            lo[2], hi[2] = zlo, zhi
            hit = next((o["guid"] for o in obst
                        if o["guid"] != e["guid"]
                        # the host wall / frame overlaps the element itself — not an obstruction
                        and not _overlap(o["min"], o["max"], e["min"], e["max"])
                        and _overlap(o["min"], o["max"], tuple(lo), tuple(hi))), None)
            blocking.append(hit)
        if blocking[0] and blocking[1]:                 # neither side clear
            viol.append({"guid": e["guid"], "name": e.get("name"),
                         "detail": f"no clear {distance_m} m approach on either side",
                         "blocking": blocking})
    return {"checked": len(elems), "violations": viol}


def check_escape_distance(boxes: list[dict], scope: set[str], exits: set[str],
                          max_m: float) -> dict:
    """Straight-line horizontal centre-to-centre distance to the nearest exit element ≤ max_m."""
    exit_pts = [_center(b) for b in boxes if b["guid"] in exits]
    elems = [b for b in boxes if b["guid"] in scope and b["guid"] not in exits]
    if not exit_pts:
        return {"checked": len(elems), "violations": [], "note": "no exit elements matched"}
    viol = []
    for e in elems:
        c = _center(e)
        d = min(math.hypot(c[0] - x[0], c[1] - x[1]) for x in exit_pts)
        if d > max_m:
            viol.append({"guid": e["guid"], "name": e.get("name"), "distance_m": round(d, 2),
                         "detail": f"nearest exit {round(d, 1)} m away (max {max_m} m, straight-line)"})
    return {"checked": len(elems), "violations": viol}


def check_clear_width(boxes: list[dict], scope: set[str], min_m: float) -> dict:
    """The larger horizontal AABB dimension (the opening width) must be ≥ min_m."""
    viol = []
    elems = [b for b in boxes if b["guid"] in scope]
    for e in elems:
        width = max(e["max"][0] - e["min"][0], e["max"][1] - e["min"][1])
        if width + _EPS < min_m:
            viol.append({"guid": e["guid"], "name": e.get("name"), "width_m": round(width, 3),
                         "detail": f"clear width {round(width * 1000)} mm < {round(min_m * 1000)} mm"})
    return {"checked": len(elems), "violations": viol}


def run(boxes: list[dict], checks: list[dict]) -> dict:
    """Evaluate resolved checks (scope/exits/obstructions already GUID sets). Returns per-check
    results + a by-severity rollup, mirroring the property rule-library's run() shape."""
    results, by_sev = [], {}
    for c in checks:
        kind = c.get("kind")
        scope = set(c.get("scope") or ())
        if kind == "clearance":
            r = check_clearance(boxes, scope, float(c.get("distance_m") or 0.9),
                                set(c["obstructions"]) if c.get("obstructions") is not None else None)
        elif kind == "escape_distance":
            r = check_escape_distance(boxes, scope, set(c.get("exits") or ()),
                                      float(c.get("max_m") or 60.0))
        elif kind == "clear_width":
            r = check_clear_width(boxes, scope, float(c.get("min_m") or 0.815))
        else:
            raise ValueError(f"unknown geometric check kind {kind!r} (one of {KINDS})")
        sev = c.get("severity") or "medium"
        n = len(r["violations"])
        by_sev[sev] = by_sev.get(sev, 0) + n
        results.append({"id": c.get("id"), "kind": kind, "name": c.get("name") or kind,
                        "severity": sev, "passed": n == 0, **r})
    return {"results": results, "violation_total": sum(by_sev.values()), "by_severity": by_sev}
