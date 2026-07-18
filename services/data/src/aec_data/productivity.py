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

# activity -> installed **material** cost per unit ($). Benchmark averages, editable per project; an absent
# key means negligible material (e.g. excavation). Same unit as the RATES entry.
MATERIALS: dict[str, float] = {
    "backfill_compact": 5.0, "blinding_concrete": 110.0, "rc_formwork": 25.0, "rc_rebar_fixing": 900.0,
    "rc_casting": 130.0, "concrete_finish": 2.0, "block_masonry": 30.0, "brick_masonry": 45.0,
    "internal_plaster": 8.0, "external_plaster": 10.0, "painting": 3.0, "steel_erection": 2000.0,
    "duct_install": 45.0, "pipe_install": 20.0, "conduit_install": 6.0, "cable_pulling": 4.0,
    "floor_tile": 35.0, "false_ceiling": 25.0, "waterproofing": 12.0,
}

# activity -> **equipment / plant** cost per unit ($) — major plant (excavators, cranes, pumps). An absent
# key means hand-tools only (folded into overhead, not itemised here).
EQUIPMENT: dict[str, float] = {
    "excavation_soil": 8.0, "backfill_compact": 6.0, "blinding_concrete": 6.0, "rc_casting": 15.0,
    "rc_rebar_fixing": 20.0, "steel_erection": 80.0,
}


def catalog() -> dict[str, Any]:
    """The productivity-rate catalog grouped by trade + the loading factors (for an estimating UI)."""
    groups: dict[str, list[dict]] = {}
    for key, r in RATES.items():
        groups.setdefault(r["group"], []).append(
            {"activity": key, "unit": r["unit"], "man_hours_per_unit": r["mh"], "crew": r["crew"],
             "material_cost_per_unit": MATERIALS.get(key, 0.0),
             "equipment_cost_per_unit": EQUIPMENT.get(key, 0.0)})
    return {"groups": {g: sorted(v, key=lambda x: x["activity"]) for g, v in sorted(groups.items())},
            "loading_factors": LOADING,
            "note": "Man-hours/unit + material/equipment $/unit are industry-benchmark averages — adjust per "
                    "project. Loading factors inflate labour hours for real-world conditions."}


def full_estimate(items, hourly_rate: float = 25.0, loading: str = "standard",
                  crew_day_hours: float = 8.0, crews_parallel: int = 1) -> dict[str, Any]:
    """A fuller 5D cost: labour (via `labor_estimate`) **plus material and equipment** unit costs per line.
    Returns the labour breakdown (incl. the `schedule` duration) augmented with `material_cost` /
    `equipment_cost` / `line_total` per line and `total_material_cost` / `total_equipment_cost` /
    `total_cost`. Still excludes overhead/profit."""
    base = labor_estimate(items, hourly_rate, loading, crew_day_hours, crews_parallel)
    lines: list[dict] = []
    tmat = teqp = 0.0
    for ln in base["lines"]:
        qty = ln["quantity"]
        mat = round(qty * MATERIALS.get(ln["activity"], 0.0), 2)
        eqp = round(qty * EQUIPMENT.get(ln["activity"], 0.0), 2)
        tmat += mat
        teqp += eqp
        lines.append({**ln, "material_cost": mat, "equipment_cost": eqp,
                      "line_total": round(ln["labor_cost"] + mat + eqp, 2)})
    lines.sort(key=lambda x: -x["line_total"])
    total = round(base["total_labor_cost"] + tmat + teqp, 2)
    return {**base, "lines": lines,
            "total_material_cost": round(tmat, 2), "total_equipment_cost": round(teqp, 2),
            "total_cost": total, "has_material_equipment": True,
            "note": "Labour + material + equipment (benchmark unit costs; excludes overhead / profit / "
                    "markup). Rates are editable benchmarks; verify against local suppliers + crews."}


def labor_estimate(items, hourly_rate: float = 25.0, loading: str = "standard",
                   crew_day_hours: float = 8.0, crews_parallel: int = 1,
                   work_days_per_week: float = 5.0) -> dict[str, Any]:
    """Given `items` [{activity, quantity}], compute labour hours, crew-days, and cost per line + total,
    **plus a schedule duration** (EST-1 5D): the per-line crew-days roll up by trade group into a working-
    and calendar-day duration. `crews_parallel` = how many crews of a trade run at once (shortens that
    trade); `loading` inflates the hours for site conditions; `hourly_rate` is the blended labour rate."""
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
            "schedule": _schedule_from_lines(lines, crews_parallel, work_days_per_week),
            "note": "Labour only (man-hours × rate) — add materials/equipment/overhead for a full cost. "
                    "Rates are editable benchmarks; verify against local crews."}


def _schedule_from_lines(lines: list[dict], crews_parallel: int = 1,
                         work_days_per_week: float = 5.0) -> dict[str, Any]:
    """Tie the per-line crew-days to a **schedule duration** (EST-1 5D). Crew-days roll up by trade group;
    each group's duration = its crew-days ÷ `crews_parallel` (crews of that trade working at once). The
    project working-day duration assumes groups run **sequentially** (a conservative critical path — real
    trades overlap, which only shortens it); calendar days convert via the work-week."""
    parallel = max(1, int(crews_parallel or 1))
    wdw = float(work_days_per_week) if work_days_per_week else 5.0
    by_group: dict[str, float] = {}
    for ln in lines:
        by_group[ln["group"]] = by_group.get(ln["group"], 0.0) + float(ln.get("crew_days") or 0.0)
    groups = [{"group": g, "crew_days": round(cd, 1), "duration_days": round(cd / parallel, 1)}
              for g, cd in sorted(by_group.items(), key=lambda x: -x[1])]
    seq_working_days = round(sum(gp["duration_days"] for gp in groups), 1)
    return {"crews_parallel": parallel, "work_days_per_week": wdw, "by_group": groups,
            "duration_working_days": seq_working_days,
            "duration_calendar_days": round(seq_working_days * 7.0 / wdw, 1) if wdw else seq_working_days,
            "note": "Trade groups assumed sequential (conservative critical path); overlapping trades "
                    "shortens the real schedule. Duration = crew-days ÷ parallel crews."}


def from_takeoff(rows: list[dict], hourly_rate: float = 25.0, loading: str = "standard",
                 full: bool = False, crews_parallel: int = 1) -> dict[str, Any]:
    """EST-1 (the QTO half): drive the labour estimate from the **real measured takeoff**
    (`aec_data.qto.takeoff` rows — Qto psets with a geometry fallback) instead of rough element
    dimensions. Element class routes its measured quantity to the matching productivity activity:
    walls → masonry face area · slabs → concrete volume + finish area · columns/beams/footings →
    concrete volume (steel members with a tonnage → steel erection) · coverings → tile/ceiling area ·
    pipe/duct/tray/cable runs → install lengths (duct m² ≈ 1 m²/m run, an approximation)."""
    agg: dict[str, float] = {}
    counted = 0

    def _add(activity: str, qty: Any) -> bool:
        try:
            q = float(qty)
        except (TypeError, ValueError):
            return False
        if q <= 0:
            return False
        agg[activity] = agg.get(activity, 0.0) + q
        return True

    for r in rows:
        c = str(r.get("ifc_class") or "")
        used = False
        if c in ("IfcWall", "IfcWallStandardCase"):
            used = _add("block_masonry", r.get("area"))
        elif c == "IfcSlab":
            used = _add("rc_casting", r.get("volume")) | _add("concrete_finish", r.get("area"))
        elif c in ("IfcColumn", "IfcBeam", "IfcMember", "IfcFooting", "IfcPile"):
            w = r.get("weight")
            if w:                                        # steel members carry a tonnage (kg → tons)
                used = _add("steel_erection", float(w) / 1000.0)
            else:
                used = _add("rc_casting", r.get("volume"))
        elif c == "IfcCovering":
            hint = f"{r.get('name') or ''} {r.get('type') or ''}".lower()
            used = _add("false_ceiling" if "ceil" in hint else "floor_tile", r.get("area"))
        elif c == "IfcPipeSegment":
            used = _add("pipe_install", r.get("length"))
        elif c == "IfcDuctSegment":
            used = _add("duct_install", r.get("length"))   # ≈1 m² duct surface per m run
        elif c == "IfcCableCarrierSegment":
            used = _add("conduit_install", r.get("length"))
        elif c == "IfcCableSegment":
            used = _add("cable_pulling", r.get("length"))
        if used:
            counted += 1

    items = [{"activity": a, "quantity": round(q, 2)} for a, q in sorted(agg.items())]
    out = (full_estimate(items, hourly_rate, loading, crews_parallel=crews_parallel) if full
           else labor_estimate(items, hourly_rate, loading, crews_parallel=crews_parallel))
    out["derived_from_takeoff"] = True
    out["elements_counted"] = counted
    out["note"] = ("Quantities from the measured QTO takeoff (Qto psets + geometry fallback). "
                   + out["note"])
    return out


# IFC-class -> (activity, how to get the quantity from an element) for a rough model-driven takeoff
def from_model(model, hourly_rate: float = 25.0, loading: str = "standard",
               full: bool = False, crews_parallel: int = 1) -> dict[str, Any]:
    """Derive a rough estimate straight from the model — walls → masonry area (length×height),
    slabs → concrete volume + finish area, columns → concrete. Approximate (uses element dimensions, not a
    full QTO); a starting point the estimator refines. `full=True` adds material + equipment cost lines."""
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
    out = (full_estimate(items, hourly_rate, loading, crews_parallel=crews_parallel) if full
           else labor_estimate(items, hourly_rate, loading, crews_parallel=crews_parallel))
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
