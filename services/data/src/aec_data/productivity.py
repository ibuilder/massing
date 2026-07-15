"""EST-1 — a construction **productivity-rate** library for labour cost + duration estimating.

The estimating link between *quantities* and *schedule + 5D cost*: each work activity has a typical
**man-hours per unit** and crew size, so a quantity of work → labour hours → crew-days → cost. Rates are
industry benchmarks (facts/averages, user-adjustable per project); condition **loading factors** (weather,
congestion, shift) inflate the hours to cover real-world inefficiency. Encodes the *structure*, not any
proprietary rate set — every value is an editable default.
"""
from __future__ import annotations

from typing import Any

# work activity -> (unit, average man-hours per unit, typical crew size). Industry-benchmark averages.
RATES: dict[str, dict[str, Any]] = {
    "excavation_soil":   {"unit": "m3", "mh": 0.040, "crew": 5, "group": "Earthworks"},
    "backfill_compact":  {"unit": "m3", "mh": 0.060, "crew": 3, "group": "Earthworks"},
    "blinding_concrete": {"unit": "m3", "mh": 1.000, "crew": 4, "group": "Concrete"},
    "rc_formwork":       {"unit": "m2", "mh": 3.500, "crew": 7, "group": "Concrete"},
    "rc_rebar_fixing":   {"unit": "ton", "mh": 32.000, "crew": 5, "group": "Concrete"},
    "rc_casting":        {"unit": "m3", "mh": 10.000, "crew": 7, "group": "Concrete"},
    "concrete_finish":   {"unit": "m2", "mh": 0.600, "crew": 3, "group": "Concrete"},
    "block_masonry":     {"unit": "m2", "mh": 1.300, "crew": 3, "group": "Masonry"},
    "brick_masonry":     {"unit": "m2", "mh": 1.500, "crew": 3, "group": "Masonry"},
    "internal_plaster":  {"unit": "m2", "mh": 0.700, "crew": 3, "group": "Finishes"},
    "external_plaster":  {"unit": "m2", "mh": 0.800, "crew": 3, "group": "Finishes"},
    "painting":          {"unit": "m2", "mh": 0.350, "crew": 2, "group": "Finishes"},
    "steel_erection":    {"unit": "ton", "mh": 37.000, "crew": 5, "group": "Structural Steel"},
    "duct_install":      {"unit": "m2", "mh": 1.000, "crew": 3, "group": "MEP"},
    "pipe_install":      {"unit": "m", "mh": 0.400, "crew": 3, "group": "MEP"},
    "conduit_install":   {"unit": "m", "mh": 0.160, "crew": 2, "group": "MEP"},
    "cable_pulling":     {"unit": "m", "mh": 0.040, "crew": 2, "group": "MEP"},
    "floor_tile":        {"unit": "m2", "mh": 0.900, "crew": 3, "group": "Finishes"},
    "false_ceiling":     {"unit": "m2", "mh": 0.700, "crew": 3, "group": "Finishes"},
    "waterproofing":     {"unit": "m2", "mh": 0.400, "crew": 2, "group": "Finishes"},
}

# condition -> productivity loading factor (>1 inflates hours to cover inefficiency)
LOADING: dict[str, float] = {
    "standard": 1.00, "residential": 1.15, "commercial": 1.15, "highrise": 1.25,
    "industrial": 1.20, "infrastructure": 1.10, "remote": 1.25, "summer": 1.15,
    "congested": 1.15, "nightshift": 1.10,
}


def catalog() -> dict[str, Any]:
    """The productivity-rate catalog grouped by trade + the loading factors (for an estimating UI)."""
    groups: dict[str, list[dict]] = {}
    for key, r in RATES.items():
        groups.setdefault(r["group"], []).append(
            {"activity": key, "unit": r["unit"], "man_hours_per_unit": r["mh"], "crew": r["crew"]})
    return {"groups": {g: sorted(v, key=lambda x: x["activity"]) for g, v in sorted(groups.items())},
            "loading_factors": LOADING,
            "note": "Man-hours/unit are industry-benchmark averages — adjust per project. Loading factors "
                    "inflate hours for real-world conditions."}


def labor_estimate(items, hourly_rate: float = 25.0, loading: str = "standard",
                   crew_day_hours: float = 8.0) -> dict[str, Any]:
    """Given `items` [{activity, quantity}], compute labour hours, crew-days, and cost per line + total.
    `loading` inflates the hours for site conditions; `hourly_rate` is the blended labour rate ($/hr)."""
    lf = LOADING.get((loading or "standard").strip().lower(), 1.0)
    rate = float(hourly_rate)
    lines: list[dict] = []
    total_hours = total_cost = 0.0
    for it in (items or []):
        act = str(it.get("activity") or "").strip().lower()
        r = RATES.get(act)
        try:
            qty = float(it.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if r is None or qty <= 0:
            continue
        hours = qty * r["mh"] * lf
        crew = max(1, int(r["crew"]))
        days = hours / (crew * crew_day_hours) if crew_day_hours else 0.0
        cost = hours * rate
        total_hours += hours
        total_cost += cost
        lines.append({"activity": act, "group": r["group"], "unit": r["unit"], "quantity": round(qty, 2),
                      "man_hours": round(hours, 1), "crew": crew, "crew_days": round(days, 1),
                      "labor_cost": round(cost, 2)})
    lines.sort(key=lambda x: -x["labor_cost"])
    return {"loading": loading, "loading_factor": lf, "hourly_rate": rate,
            "lines": lines, "line_count": len(lines),
            "total_man_hours": round(total_hours, 1),
            "total_labor_cost": round(total_cost, 2),
            "note": "Labour only (man-hours × rate) — add materials/equipment/overhead for a full cost. "
                    "Rates are editable benchmarks; verify against local crews."}


# IFC-class -> (activity, how to get the quantity from an element) for a rough model-driven takeoff
def from_model(model, hourly_rate: float = 25.0, loading: str = "standard") -> dict[str, Any]:
    """Derive a rough labour estimate straight from the model — walls → masonry area (length×height),
    slabs → concrete volume + finish area, columns → concrete. Approximate (uses element dimensions, not a
    full QTO); a starting point the estimator refines."""
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(model)
    agg: dict[str, float] = {}

    def _add(activity: str, qty: float) -> None:
        if qty > 0:
            agg[activity] = agg.get(activity, 0.0) + qty

    for w in model.by_type("IfcWall"):
        rep = next((r for r in (getattr(getattr(w, "Representation", None), "Representations", None) or [])
                    if getattr(r, "RepresentationIdentifier", None) == "Body"), None)
        solid = rep.Items[0] if (rep and rep.Items) else None
        if solid is not None and solid.is_a("IfcExtrudedAreaSolid") and solid.SweptArea.is_a("IfcRectangleProfileDef"):
            length = float(solid.SweptArea.XDim) * scale
            height = float(solid.Depth) * scale
            _add("block_masonry", length * height)          # face area (one side)
    for s in model.by_type("IfcSlab"):
        rep = next((r for r in (getattr(getattr(s, "Representation", None), "Representations", None) or [])
                    if getattr(r, "RepresentationIdentifier", None) == "Body"), None)
        solid = rep.Items[0] if (rep and rep.Items) else None
        if solid is not None and solid.is_a("IfcExtrudedAreaSolid"):
            try:
                area = _profile_area(solid.SweptArea) * scale * scale
                thick = float(solid.Depth) * scale
                _add("rc_casting", area * thick)
                _add("concrete_finish", area)
            except Exception:  # noqa: BLE001
                pass
    for c in model.by_type("IfcColumn"):
        rep = next((r for r in (getattr(getattr(c, "Representation", None), "Representations", None) or [])
                    if getattr(r, "RepresentationIdentifier", None) == "Body"), None)
        solid = rep.Items[0] if (rep and rep.Items) else None
        if solid is not None and solid.is_a("IfcExtrudedAreaSolid"):
            try:
                _add("rc_casting", _profile_area(solid.SweptArea) * scale * scale * float(solid.Depth) * scale)
            except Exception:  # noqa: BLE001
                pass

    items = [{"activity": a, "quantity": q} for a, q in agg.items()]
    out = labor_estimate(items, hourly_rate, loading)
    out["derived_from_model"] = True
    out["note"] = "Rough model-driven takeoff (element dimensions, not a full QTO). " + out["note"]
    return out


def _profile_area(prof) -> float:
    """Approximate the area of a swept profile in profile (file) units²."""
    if prof.is_a("IfcRectangleProfileDef"):
        return float(prof.XDim) * float(prof.YDim)
    if prof.is_a("IfcCircleProfileDef"):
        import math
        return math.pi * float(prof.Radius) ** 2
    if prof.is_a("IfcArbitraryClosedProfileDef") and prof.OuterCurve.is_a("IfcPolyline"):
        pts = [(float(p.Coordinates[0]), float(p.Coordinates[1])) for p in prof.OuterCurve.Points]
        a = 0.0
        for i in range(len(pts) - 1):
            a += pts[i][0] * pts[i + 1][1] - pts[i + 1][0] * pts[i][1]
        return abs(a) / 2.0
    return 0.0
