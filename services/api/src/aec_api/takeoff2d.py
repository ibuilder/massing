"""TAKEOFF-2D · quantity takeoff from a 2D drawing (PDF page / scan).

The drawings-only case the model takeoff misses: a GC or estimator has a PDF/scan, not a BIM model, and
needs quantities off it. The browser traces regions on the drawing (manual polygon or one-click flood
fill) and calibrates a scale (two points at a known real distance → real units per pixel). This module is
the server-side quantify step: it turns those pixel-space regions + the scale into **real areas / lengths
and priced quantities**, grouped by assembly, feeding the same 5D estimate the model takeoff feeds.

Pure geometry (shoelace area, polyline length) + a small assembly rate table; no model, no network. The
tracer/flood-fill lives in the browser; this is the deterministic, testable measurement + pricing core.
"""
from __future__ import annotations

from typing import Any

# 2D-takeoff assemblies: category → (measure, $/unit, label). `area` bills the polygon area, `length`
# bills the polyline length. Rates are all-in installed benchmarks, overridable per call (project vintage).
TAKEOFF_ASSEMBLIES: dict[str, tuple[str, float, str]] = {
    "floor_slab": ("area", 130.0, "Floor slab (in place)"),
    "roofing": ("area", 210.0, "Roofing assembly"),
    "ceiling": ("area", 55.0, "Ceiling / covering"),
    "partition": ("area", 160.0, "Interior partition (by wall face area)"),
    "exterior_wall": ("area", 320.0, "Exterior wall assembly (by face area)"),
    "curtain_wall": ("area", 600.0, "Curtain wall"),
    "paving": ("area", 90.0, "Site paving"),
    "generic_area": ("area", 100.0, "Generic area"),
    "wall_linear": ("length", 210.0, "Wall run (linear)"),
    "footing_linear": ("length", 240.0, "Strip footing (linear)"),
    "generic_linear": ("length", 50.0, "Generic linear"),
}
_UNIT_LABEL = {"area": "m²", "length": "m"}


def polygon_area_px2(points: list) -> float:
    """Shoelace area of a polygon given as [[x, y], …] in pixels (absolute value, auto-closes)."""
    n = len(points)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[(i + 1) % n][0]), float(points[(i + 1) % n][1])
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def polyline_length_px(points: list) -> float:
    """Total length of a polyline [[x, y], …] in pixels (open — does not close back to the start)."""
    total = 0.0
    for i in range(len(points) - 1):
        dx = float(points[i + 1][0]) - float(points[i][0])
        dy = float(points[i + 1][1]) - float(points[i][1])
        total += (dx * dx + dy * dy) ** 0.5
    return total


def quantify(regions: list[dict], scale_units_per_px: float, *,
             unit: str = "m", overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Measure + price traced regions. `scale_units_per_px` converts pixels → real units (`unit`, from the
    calibration: known real distance ÷ its pixel distance). Each region is
    ``{category, points:[[x,y],…], label?}``; an `area` assembly bills the polygon area, a `length`
    assembly the polyline length. Returns per-region rows, per-assembly subtotals, and the grand total."""
    overrides = overrides or {}
    s = float(scale_units_per_px)
    area_unit = f"{unit}²"
    rows: list[dict] = []
    for i, reg in enumerate(regions or []):
        cat = str(reg.get("category") or "generic_area")
        spec = TAKEOFF_ASSEMBLIES.get(cat) or TAKEOFF_ASSEMBLIES["generic_area"]
        measure, default_rate, label = spec
        rate = float(overrides.get(cat, default_rate))
        pts = reg.get("points") or []
        if measure == "length":
            qty = polyline_length_px(pts) * s
            qunit = unit
        else:
            qty = polygon_area_px2(pts) * s * s
            qunit = area_unit
        cost = qty * rate
        rows.append({"index": i, "category": cat, "assembly": label, "measure": measure,
                     "label": reg.get("label"), "quantity": round(qty, 2), "unit": qunit,
                     "rate": round(rate, 2), "cost": round(cost, 2)})

    by_assembly: dict[str, dict] = {}
    for r in rows:
        agg = by_assembly.setdefault(r["category"], {"category": r["category"], "assembly": r["assembly"],
                                                     "measure": r["measure"], "unit": r["unit"],
                                                     "quantity": 0.0, "cost": 0.0, "count": 0})
        agg["quantity"] = round(agg["quantity"] + r["quantity"], 2)
        agg["cost"] = round(agg["cost"] + r["cost"], 2)
        agg["count"] += 1

    total = round(sum(r["cost"] for r in rows), 2)
    return {
        "scale_units_per_px": s, "unit": unit,
        "region_count": len(rows), "total_cost": total,
        "regions": rows,
        "by_assembly": sorted(by_assembly.values(), key=lambda a: -a["cost"]),
        "assemblies": [{"category": k, "measure": v[0], "rate": v[1], "label": v[2],
                        "unit": _UNIT_LABEL.get(v[0])} for k, v in TAKEOFF_ASSEMBLIES.items()],
        "disclaimer": "PRELIMINARY 2D takeoff — quantities are measured off a traced drawing at the supplied "
                      "calibration and priced at benchmark assembly rates. Accuracy depends on the trace + "
                      "scale; verify against the model takeoff where a model exists.",
    }


def calibration_scale(p1: list, p2: list, real_distance: float) -> float:
    """Real units per pixel from a calibration: two clicked points + the real distance between them."""
    dx = float(p2[0]) - float(p1[0])
    dy = float(p2[1]) - float(p1[1])
    px = (dx * dx + dy * dy) ** 0.5
    if px <= 0:
        return 0.0
    return float(real_distance) / px
