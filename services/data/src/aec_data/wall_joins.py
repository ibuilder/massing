"""AUTH-CONSTRAINTS ③ — wall-join resolution (R18).

Walls authored as axis-placed rectangular extrusions overlap (or gap) where they meet. This leaf
detects the joins and resolves them the way a drafter would butt-join them:

- **find(model)** — every L join (two wall endpoints coincide) and T join (one wall's endpoint
  lands on another wall's axis mid-segment), classified with the participating GUIDs, the corner
  point, and each wall's axis geometry. Same-storey pairs only; degenerate/parallel pairs skipped.
- **resolve(model)** — deterministic butt joins:
  - **L:** the LONGER wall runs through; it is *extended* past the corner by half the stub's
    thickness (closing the outside corner) and the stub is *trimmed* back by half the through
    wall's thickness (so its end face meets the through wall's side face — no overlap, no gap).
  - **T:** the stub is trimmed back by half the through wall's thickness; the through wall is
    untouched.
  Geometry edits touch only the rectangle profile's length (XDim) and slide the placement
  midpoint along the axis — GUID-stable, representation untouched otherwise. Openings are placed
  in world coordinates (see edit_enclosure.add_opening), so hosted doors/windows stay exactly
  where they are. Resolution is **idempotent**: resolved ends sit half-a-thickness off the other
  wall's axis, outside the detection tolerance, so a second pass finds nothing.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell

_TOL = 0.05          # metres — endpoint coincidence tolerance for detection


def _wall_geo(model, wall, scale: float) -> dict[str, Any] | None:
    """Axis geometry for one wall: midpoint, unit direction, length, thickness (all metres),
    plus the profile entity so resolve() can edit XDim in place."""
    import ifcopenshell.util.element as ue
    import ifcopenshell.util.placement as uplace
    import numpy as np

    if not getattr(wall, "ObjectPlacement", None) or not getattr(wall, "Representation", None):
        return None
    m = np.array(uplace.get_local_placement(wall.ObjectPlacement), dtype=float)
    mid = m[:2, 3] * scale
    d = m[:2, 0]
    n = float(np.hypot(d[0], d[1]))
    if n < 1e-9:
        return None
    d = d / n
    profile = None
    for rep in wall.Representation.Representations or []:
        for item in rep.Items or []:
            if item.is_a("IfcExtrudedAreaSolid") and item.SweptArea is not None \
                    and item.SweptArea.is_a("IfcRectangleProfileDef"):
                profile = item.SweptArea
                break
        if profile is not None:
            break
    if profile is None:
        return None
    length = float(profile.XDim) * scale
    thick = float(profile.YDim) * scale
    if length < 1e-6:
        return None
    half = d * (length / 2.0)
    st = None
    try:
        st = getattr(ue.get_container(wall), "Name", None)
    except Exception:                                  # noqa: BLE001
        st = None
    return {"guid": wall.GlobalId, "wall": wall, "profile": profile, "matrix": m,
            "mid": mid, "dir": d, "length": length, "thickness": thick,
            "ends": (mid - half, mid + half), "storey": st}


def _geos(model) -> list[dict[str, Any]]:
    import ifcopenshell.util.unit as uunit
    scale = uunit.calculate_unit_scale(model)
    out = []
    for w in model.by_type("IfcWall"):
        g = _wall_geo(model, w, scale)
        if g:
            g["scale"] = scale
            out.append(g)
    return out


def _dist(a, b) -> float:
    return math.hypot(float(a[0] - b[0]), float(a[1] - b[1]))


def _on_segment(p, geo, tol: float) -> bool:
    """Is point p on geo's axis segment (perpendicular distance ≤ tol, projection strictly
    interior — endpoints are L territory, not T)?"""
    v = p - geo["mid"]
    along = float(v[0] * geo["dir"][0] + v[1] * geo["dir"][1])
    perp = abs(float(v[0] * -geo["dir"][1] + v[1] * geo["dir"][0]))
    half = geo["length"] / 2.0
    return perp <= tol and -half + tol < along < half - tol


def find(model: ifcopenshell.file, tol: float = _TOL) -> dict[str, Any]:
    geos = _geos(model)
    joins: list[dict[str, Any]] = []
    for i in range(len(geos)):
        for j in range(i + 1, len(geos)):
            a, b = geos[i], geos[j]
            if a["storey"] != b["storey"]:
                continue
            # parallel walls never butt-join (co-linear runs are a different feature)
            cross = abs(a["dir"][0] * b["dir"][1] - a["dir"][1] * b["dir"][0])
            if cross < 0.1:
                continue
            hit = None
            for ea in a["ends"]:
                for eb in b["ends"]:
                    if _dist(ea, eb) <= tol:
                        hit = {"kind": "L", "corner": [round(float(ea[0]), 4), round(float(ea[1]), 4)]}
            if hit is None:
                for ea in a["ends"]:
                    if _on_segment(ea, b, tol):
                        hit = {"kind": "T", "corner": [round(float(ea[0]), 4), round(float(ea[1]), 4)],
                               "stub": a["guid"], "through": b["guid"]}
                for eb in b["ends"]:
                    if hit is None and _on_segment(eb, a, tol):
                        hit = {"kind": "T", "corner": [round(float(eb[0]), 4), round(float(eb[1]), 4)],
                               "stub": b["guid"], "through": a["guid"]}
            if hit is not None:
                if hit["kind"] == "L":
                    through, stub = (a, b) if a["length"] >= b["length"] else (b, a)
                    hit["through"], hit["stub"] = through["guid"], stub["guid"]
                hit["walls"] = [a["guid"], b["guid"]]
                joins.append(hit)
    return {"joins": joins, "wall_count": len(geos),
            "counts": {"L": sum(1 for x in joins if x["kind"] == "L"),
                       "T": sum(1 for x in joins if x["kind"] == "T")}}


def _retrim(model, geo: dict[str, Any], corner, delta_m: float) -> None:
    """Change geo's length by delta_m (positive = extend, negative = trim) AT the end nearest
    `corner`, keeping the other end fixed: XDim += Δ, midpoint slides Δ/2 toward/away the corner."""
    import ifcopenshell.api
    import numpy as np
    d = geo["dir"]
    toward = 1.0 if _dist(geo["ends"][1], corner) < _dist(geo["ends"][0], corner) else -1.0
    new_len = geo["length"] + delta_m
    if new_len < geo["thickness"]:                    # never trim a wall away
        return
    geo["profile"].XDim = new_len / geo["scale"]
    m = np.array(geo["matrix"], dtype=float)
    m[:3, 3] *= geo["scale"]                          # file units -> metres
    m[0, 3] += toward * d[0] * delta_m / 2.0
    m[1, 3] += toward * d[1] * delta_m / 2.0
    ifcopenshell.api.run("geometry.edit_object_placement", model, product=geo["wall"], matrix=m)
    geo["length"] = new_len


def resolve(model: ifcopenshell.file, tol: float = _TOL) -> dict[str, Any]:
    found = find(model, tol)
    geos = {g["guid"]: g for g in _geos(model)}
    resolved = []
    for jn in found["joins"]:
        through, stub = geos.get(jn["through"]), geos.get(jn["stub"])
        if not through or not stub:
            continue
        corner = jn["corner"]
        if jn["kind"] == "L":
            _retrim(model, through, corner, +stub["thickness"] / 2.0)   # close the outside corner
        _retrim(model, stub, corner, -through["thickness"] / 2.0)       # butt into the through face
        resolved.append({**jn, "trimmed_m": round(through["thickness"] / 2.0, 4),
                         **({"extended_m": round(stub["thickness"] / 2.0, 4)} if jn["kind"] == "L" else {})})
    return {"resolved": resolved, "count": len(resolved), "counts": found["counts"]}
