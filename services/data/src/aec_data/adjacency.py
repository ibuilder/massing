"""TESTFIT-ADJ (R16 Tier-2) — **adjacency + dimensional-compliance** over the model's IfcSpaces.

Two deterministic test-fit checks on the spaces already in the model — no solver, no OCC (footprints come
straight from each space's extruded profile + placement, the same way the plan drawings are generated):

- **adjacency matrix** — which spaces physically touch (bounding boxes within a wall-thickness gap, on the
  same storey), scored against a program's desired relations: `required_adjacent` type-pairs that *should*
  touch (satisfied ratio) and `forbidden` type-pairs that must *not* (violations listed).
- **dimensional compliance** — each space vs a rule pack: minimum room dimension (the short side of its
  footprint), minimum floor area, and minimum clear/ceiling height; global or per-space-type thresholds.

Pure over an opened model, so it recomputes on every edit and turns the program brief into a live
constraint beside the geometry. Rules are compared *within* the model's own units (metres for an SI file).
"""
from __future__ import annotations

from typing import Any

_GAP = 0.35     # spaces whose bboxes are within this many metres (≈ a wall) count as adjacent
_EPS = 0.01     # a shared edge needs more than this much overlap on the perpendicular axis (not a corner)


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _space_type(sp) -> str:
    for attr in ("LongName", "ObjectType", "Name"):
        v = getattr(sp, attr, None)
        if v:
            return str(v)
    return "Space"


def _space_box(sp, scale: float) -> dict | None:
    """(minx, miny, maxx, maxy, height) in metres for a space, from its extruded-profile footprint +
    placement — no OCC. None when the space carries no usable extruded geometry."""
    from . import drawing as dw

    fp = dw._footprint(sp)                             # world-XY polygon in file units
    if not fp or len(fp) < 3:
        return None
    xs = [p[0] for p in fp]
    ys = [p[1] for p in fp]
    # extrusion depth = clear height (file units → metres)
    height = 0.0
    rep = getattr(sp, "Representation", None)
    if rep is not None:
        for r in rep.Representations:
            for it in (r.Items or []):
                if it.is_a("IfcExtrudedAreaSolid"):
                    height = _num(getattr(it, "Depth", 0)) * scale
                    break
            if height:
                break
    return {"minx": min(xs) * scale, "miny": min(ys) * scale,
            "maxx": max(xs) * scale, "maxy": max(ys) * scale, "height": round(height, 3)}


def _storey_of(sp) -> str | None:
    for rel in (getattr(sp, "Decomposes", None) or []):
        obj = getattr(rel, "RelatingObject", None)
        if obj is not None and obj.is_a("IfcBuildingStorey"):
            return obj.GlobalId
    return None


def _spaces_geo(model) -> list[dict]:
    import ifcopenshell.util.unit as uunit

    scale = uunit.calculate_unit_scale(model)
    out = []
    for sp in model.by_type("IfcSpace"):
        box = _space_box(sp, scale)
        if box is None:
            continue
        w, d = box["maxx"] - box["minx"], box["maxy"] - box["miny"]
        out.append({"guid": sp.GlobalId, "name": getattr(sp, "Name", None) or "", "type": _space_type(sp),
                    "storey": _storey_of(sp), "width": round(w, 3), "depth": round(d, 3),
                    "min_dim": round(min(w, d), 3), "area": round(w * d, 2), "height": box["height"], **box})
    return out


def _adjacent(a: dict, b: dict) -> bool:
    if a["storey"] and b["storey"] and a["storey"] != b["storey"]:
        return False
    sep_x = max(a["minx"], b["minx"]) - min(a["maxx"], b["maxx"])
    sep_y = max(a["miny"], b["miny"]) - min(a["maxy"], b["maxy"])
    if sep_x > _GAP or sep_y > _GAP:
        return False                                  # separated on an axis by more than a wall
    return max(-sep_x, -sep_y) > _EPS                 # real edge overlap on one axis, not a corner touch


def evaluate(model, program: dict | None = None) -> dict[str, Any]:
    """Adjacency graph + program-relation score + dimensional-compliance over the model's IfcSpaces."""
    spaces = _spaces_geo(model)
    n = len(spaces)
    # adjacency edges + per-space neighbour types
    edges = 0
    neighbors: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if _adjacent(spaces[i], spaces[j]):
                neighbors[i].add(j)
                neighbors[j].add(i)
                edges += 1

    def _tl(s: str) -> str:
        return (s or "").strip().lower()

    # is there at least one A-type space touching a B-type space?
    def _pair_touches(ta: str, tb: str) -> bool:
        ta, tb = _tl(ta), _tl(tb)
        for i, s in enumerate(spaces):
            if _tl(s["type"]) != ta:
                continue
            for j in neighbors[i]:
                if _tl(spaces[j]["type"]) == tb:
                    return True
        return False

    def _pair_instances(ta: str, tb: str) -> list[dict]:
        ta, tb = _tl(ta), _tl(tb)
        hits = []
        for i, s in enumerate(spaces):
            if _tl(s["type"]) != ta:
                continue
            for j in neighbors[i]:
                if _tl(spaces[j]["type"]) == tb and i < j:
                    hits.append({"a": s["guid"], "a_type": s["type"],
                                 "b": spaces[j]["guid"], "b_type": spaces[j]["type"]})
        return hits

    program = program or {}
    required = [p for p in (program.get("required_adjacent") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
    forbidden = [p for p in (program.get("forbidden") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
    req_results = [{"a": a, "b": b, "satisfied": _pair_touches(a, b)} for a, b in required]
    req_ok = sum(1 for r in req_results if r["satisfied"])
    forb_violations = []
    for a, b in forbidden:
        forb_violations.extend({"rule": f"{a} ✗ {b}", **h} for h in _pair_instances(a, b))

    # dimensional compliance — global thresholds, optionally overridden per space type
    dim = program.get("dimensional") or {}
    per_type = {(_tl(k)): v for k, v in (dim.get("by_type") or {}).items()}
    g_min_dim = _num(dim.get("min_room_dim"))
    g_min_area = _num(dim.get("min_area"))
    g_min_h = _num(dim.get("min_ceiling_height"))
    dim_violations = []
    checked = 0
    for s in spaces:
        rule = per_type.get(_tl(s["type"]), {})
        min_dim = _num(rule.get("min_room_dim")) or g_min_dim
        min_area = _num(rule.get("min_area")) or g_min_area
        min_h = _num(rule.get("min_ceiling_height")) or g_min_h
        if not (min_dim or min_area or min_h):
            continue
        checked += 1
        fails = []
        if min_dim and s["min_dim"] < min_dim - 1e-6:
            fails.append(f"min dim {s['min_dim']}m < {min_dim}m")
        if min_area and s["area"] < min_area - 1e-6:
            fails.append(f"area {s['area']}m² < {min_area}m²")
        if min_h and s["height"] and s["height"] < min_h - 1e-6:
            fails.append(f"height {s['height']}m < {min_h}m")
        if fails:
            dim_violations.append({"guid": s["guid"], "name": s["name"], "type": s["type"], "issues": fails})

    return {
        "space_count": n,
        "adjacency": {
            "edge_count": edges,
            "spaces": [{"guid": s["guid"], "name": s["name"], "type": s["type"], "min_dim": s["min_dim"],
                        "area": s["area"], "height": s["height"],
                        "neighbors": sorted({spaces[j]["type"] for j in neighbors[i]})} for i, s in enumerate(spaces)],
        },
        "program": {
            "required_total": len(required), "required_satisfied": req_ok,
            "required_pct": round(req_ok / len(required), 3) if required else None,
            "required_results": req_results,
            "forbidden_violations": forb_violations, "forbidden_ok": not forb_violations and bool(forbidden),
        },
        "dimensional": {"checked": checked, "passed": checked - len(dim_violations),
                        "violations": dim_violations},
        "note": "Adjacency from space bounding boxes within a wall-thickness gap on the same storey (no OCC — "
                "footprints from the extruded profiles). Program relations + dimensional rules are compared "
                "within the model's units; a required pair is met if any A-type space touches a B-type space.",
    }


def evaluate_file(ifc_path: str, program: dict | None = None) -> dict[str, Any]:
    from .ifc_loader import open_model
    return evaluate(open_model(ifc_path), program)
