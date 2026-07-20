"""REBAR-RULES + BBS (R14) — the per-typology reinforcement rule catalog over the rebar-cage
recipe, plus the **bar bending schedule** off the authored ``IfcReinforcingBar`` geometry.

Three deterministic pieces:
  * ``RULES`` / ``column_cage_params`` — code-informed defaults per member typology. The column tie
    spacing is the ACI 318 §25.7.2.1 envelope: min(16·d_bar, 48·d_tie, least column dimension);
    covers follow ACI 318 §20.5.1.3 cast-against-forms values. These size the ``add_rebar_cage``
    recipe instead of leaving every parameter to the operator.
  * ``check_cage`` — verify an authored cage against the catalog (longitudinal bar count, tie
    spacing vs the governing rule) → violations, the Solibri-style closing of the loop.
  * ``bar_bending_schedule`` — walk every ``IfcReinforcingBar``: diameter from the swept-disk
    radius, cut length from the directrix polyline, shape (straight / closed tie / bent), then
    group identical bars into marks with unit mass (πr² × 7850 kg/m³) and total tonnage — the
    number that feeds 5D.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell
import ifcopenshell.util.unit as uu

STEEL_DENSITY = 7850.0                                # kg/m3

# Per-typology reinforcement catalog (ACI 318-informed, deterministic defaults — a firm can read
# the governing rule straight off the response).
RULES: dict[str, dict[str, Any]] = {
    "column": {
        "min_longitudinal_bars": 4,                   # ACI 318 §10.7.3.1 (rect. tied column)
        "default_bar": "#8", "default_tie": "#3",
        "cover_m": 0.04,                              # ACI 318 §20.5.1.3 (formed, not exposed)
        "tie_spacing_rule": "min(16·d_bar, 48·d_tie, least column dimension)",  # §25.7.2.1
    },
    "beam": {
        "min_longitudinal_bars": 2, "default_bar": "#6", "default_stirrup": "#3",
        "cover_m": 0.04, "stirrup_spacing_rule": "d/2 in the shear zone",       # §9.7.6.2.2
    },
    "wall": {"default_bar": "#5", "cover_m": 0.02,
             "spacing_rule": "min(3·t, 450 mm) each way"},                       # §11.7.2
    "slab": {"default_bar": "#4", "cover_m": 0.02,
             "spacing_rule": "min(2·t, 450 mm) at critical sections"},           # §8.7.2.2
}


def column_cage_params(w: float, d: float, bar_size: str | None = None,
                       tie_size: str | None = None, cover: float | None = None) -> dict:
    """Rule-sized `add_rebar_cage` parameters for a w×d (metres) rectangular column, with the
    governing tie-spacing limb named. Pure — unit-testable without a model."""
    from .steel import rebar_diameter
    r = RULES["column"]
    bar = bar_size or r["default_bar"]
    tie = tie_size or r["default_tie"]
    cov = r["cover_m"] if cover is None else cover
    db_, dt = rebar_diameter(bar), rebar_diameter(tie)
    limbs = {"16·d_bar": 16 * db_, "48·d_tie": 48 * dt, "least dimension": min(w, d)}
    governing = min(limbs, key=lambda k: limbs[k])
    return {"bar_size": bar, "tie_size": tie, "cover": cov,
            "tie_spacing": round(limbs[governing], 3), "governing": governing,
            "rule": r["tie_spacing_rule"], "min_longitudinal_bars": r["min_longitudinal_bars"]}


def _bar_geometry(model: ifcopenshell.file, bar) -> dict | None:
    """(radius_m, points_m, closed) from a bar's IfcSweptDiskSolid, or None if not swept-disk."""
    s = uu.calculate_unit_scale(model)
    for rep in (bar.Representation.Representations if bar.Representation else []):
        for it in (rep.Items or []):
            if it.is_a("IfcSweptDiskSolid") and it.Directrix and it.Directrix.is_a("IfcPolyline"):
                pts = [tuple(float(c) * s for c in p.Coordinates) for p in it.Directrix.Points]
                if len(pts) < 2:
                    continue
                closed = len(pts) > 2 and all(abs(a - b) < 1e-9 for a, b in zip(pts[0], pts[-1]))
                return {"radius": float(it.Radius) * s, "points": pts, "closed": closed}
    return None


def _polyline_length(pts: list[tuple]) -> float:
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def _unit(a: tuple, b: tuple) -> tuple | None:
    """Unit direction from a→b (3D), or None for a zero-length segment."""
    d = tuple(bi - ai for ai, bi in zip(a, b))
    n = math.sqrt(sum(c * c for c in d))
    return tuple(c / n for c in d) if n > 1e-9 else None


def bending_detail(pts: list[tuple], closed: bool) -> dict:
    """Fabrication geometry of one bar from its directrix: per-leg lengths (mm) and the deviation
    (bend) angle at each interior vertex (degrees, 0 = straight-through). Pure — a shop drawing a
    detailer reads and checks, NOT a machine bending instruction. Bends count deviations ≥ 1°."""
    legs = [round(math.dist(a, b) * 1000.0, 1) for a, b in zip(pts, pts[1:])]
    angles: list[float] = []
    for i in range(1, len(pts) - 1):
        v1, v2 = _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
        if v1 and v2:
            dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))
            angles.append(round(math.degrees(math.acos(dot)), 1))
    bends = sum(1 for a in angles if a >= 1.0)
    if closed:
        family = "closed tie / stirrup"
    elif bends == 0:
        family = "straight"
    elif bends == 1:
        family = "single bend (L)"
    elif bends == 2:
        family = "double bend (U / crank)"
    else:
        family = f"{bends}-bend"
    return {"legs_mm": legs, "bend_angles_deg": angles, "bends": bends, "shape_family": family}


def _size_for_diameter(dia_m: float) -> str | None:
    """Closest bar designation for a diameter (≤1 mm off), e.g. 0.0254 → '#8'."""
    from .steel import REBAR_SIZES
    best = min(REBAR_SIZES.items(), key=lambda kv: abs(kv[1] - dia_m), default=None)
    return best[0] if best and abs(best[1] - dia_m) <= 0.001 else None


def bar_bending_schedule(model: ifcopenshell.file) -> dict:
    """BBS: every IfcReinforcingBar grouped into marks by (diameter, shape, cut length) with counts,
    unit mass, and total tonnage. Bars without swept-disk geometry are counted as skipped."""
    groups: dict[tuple, dict] = {}
    skipped = 0
    for bar in model.by_type("IfcReinforcingBar"):
        g = _bar_geometry(model, bar)
        if not g:
            skipped += 1
            continue
        length = round(_polyline_length(g["points"]), 2)
        dia = g["radius"] * 2
        shape = "closed tie" if g["closed"] else ("straight" if len(g["points"]) == 2 else "bent")
        key = (round(dia * 1000, 1), shape, length)
        row = groups.setdefault(key, {"count": 0, "guids": [], "pts": g["points"], "closed": g["closed"]})
        row["count"] += 1
        if len(row["guids"]) < 200:
            row["guids"].append(bar.GlobalId)
    rows = []
    total_len = total_kg = 0.0
    for i, ((dia_mm, shape, length), g) in enumerate(sorted(groups.items(), reverse=True), 1):
        r = dia_mm / 2000.0
        kg_m = math.pi * r * r * STEEL_DENSITY
        line_len = round(length * g["count"], 2)
        line_kg = round(kg_m * line_len, 1)
        total_len += line_len
        total_kg += line_kg
        detail = bending_detail(g.get("pts") or [], g.get("closed", False))
        rows.append({"mark": f"B{i}", "size": _size_for_diameter(dia_mm / 1000.0),
                     "diameter_mm": dia_mm, "shape": shape, "cut_length_m": length,
                     "count": g["count"], "unit_mass_kg_m": round(kg_m, 3),
                     "total_length_m": line_len, "total_kg": line_kg,
                     "shape_family": detail["shape_family"], "bends": detail["bends"],
                     "legs_mm": detail["legs_mm"], "bend_angles_deg": detail["bend_angles_deg"],
                     "guids": g["guids"]})
    return {"rows": rows, "marks": len(rows), "bars": sum(r["count"] for r in rows),
            "skipped": skipped, "total_length_m": round(total_len, 1),
            "total_kg": round(total_kg, 1), "total_tonnes": round(total_kg / 1000.0, 3)}


def bbs_csv(bbs: dict) -> str:
    """The schedule as CSV (the format a fabricator or 5D estimate ingests)."""
    import csv
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Mark", "Size", "Dia (mm)", "Shape", "Bends", "Legs (mm)", "Bend angles (deg)",
                "Cut length (m)", "Count", "Unit mass (kg/m)", "Total length (m)", "Total (kg)"])
    for r in bbs["rows"]:
        legs = "; ".join(str(x) for x in r.get("legs_mm", []))
        angs = "; ".join(str(x) for x in r.get("bend_angles_deg", []))
        w.writerow([r["mark"], r["size"] or "", r["diameter_mm"], r.get("shape_family", r["shape"]),
                    r.get("bends", ""), legs, angs, r["cut_length_m"],
                    r["count"], r["unit_mass_kg_m"], r["total_length_m"], r["total_kg"]])
    w.writerow([])
    w.writerow(["TOTAL", "", "", "", "", "", "", "", bbs["bars"], "", bbs["total_length_m"], bbs["total_kg"]])
    return buf.getvalue()


def check_cage(model: ifcopenshell.file, column_guid: str) -> dict:
    """Verify the authored cage on a column against the catalog: enough longitudinal bars, tie
    spacing within the ACI envelope. Returns {checked, violations, params} — no cage is a finding,
    not an error."""
    from .rebar import _column, _column_box
    col = _column(model, column_guid)
    _, _, cz, w, d, h = _column_box(model, col)
    params = column_cage_params(w, d)
    # the cage assembly is the IfcElementAssembly whose members include the column
    bars = []
    for rel in model.by_type("IfcRelAggregates"):
        if rel.RelatingObject.is_a("IfcElementAssembly") and any(
                getattr(o, "GlobalId", None) == column_guid for o in (rel.RelatedObjects or [])):
            bars = [o for o in rel.RelatedObjects if o.is_a("IfcReinforcingBar")]
            break
    if not bars:
        return {"checked": False, "violations": ["no reinforcement cage on this column"],
                "params": params}
    longs, tie_zs = 0, []
    for b in bars:
        g = _bar_geometry(model, b)
        if not g:
            continue
        if g["closed"]:
            tie_zs.append(g["points"][0][2])
        else:
            longs += 1
    viol = []
    if longs < params["min_longitudinal_bars"]:
        viol.append(f"{longs} longitudinal bar(s) < minimum {params['min_longitudinal_bars']}")
    tie_zs.sort()
    if len(tie_zs) >= 2:
        actual = max(b - a for a, b in zip(tie_zs, tie_zs[1:]))
        if actual > params["tie_spacing"] + 0.005:
            viol.append(f"tie spacing {round(actual, 3)} m exceeds {params['tie_spacing']} m "
                        f"(governing: {params['governing']})")
    elif len(tie_zs) < 2:
        viol.append(f"only {len(tie_zs)} tie(s) found")
    return {"checked": True, "longitudinal_bars": longs, "ties": len(tie_zs),
            "violations": viol, "params": params}
