"""Resource-based (assembly) estimating: build unit costs UP from labor + material + equipment
rather than a single blended $/unit (which is all estimate.py does). This is how estimators actually
price work (RSMeans-style): a crew installs a quantity at a productivity, consuming materials and
running equipment. The output carries the labor / material / equipment split AND the crew-hours —
so it can feed resource loading and the schedule, not just a dollar total. It also exposes *why* a
number is what it is (the component breakdown), which a single blended rate never can.

Pure over dict inputs (no DB / no IFC) so it's unit-testable. Quantities are metric to match the
QTO takeoff (m², m³, m, each). Rates are conceptual USD and overridable per project."""
from __future__ import annotations

from typing import Any

RESOURCE_KINDS = ("labor", "material", "equipment")

# Resource catalog: id -> {kind, unit, rate ($/unit), name}. Conceptual crew/material/equipment rates.
DEFAULT_RESOURCES: dict[str, dict[str, Any]] = {
    # labor — fully-burdened $/hr
    "lab_laborer": {"kind": "labor", "unit": "hr", "rate": 48.0, "name": "Laborer"},
    "lab_carpenter": {"kind": "labor", "unit": "hr", "rate": 72.0, "name": "Carpenter"},
    "lab_cementmason": {"kind": "labor", "unit": "hr", "rate": 70.0, "name": "Cement mason"},
    "lab_ironworker": {"kind": "labor", "unit": "hr", "rate": 85.0, "name": "Ironworker"},
    "lab_mason": {"kind": "labor", "unit": "hr", "rate": 68.0, "name": "Mason"},
    "lab_electrician": {"kind": "labor", "unit": "hr", "rate": 88.0, "name": "Electrician"},
    "lab_plumber": {"kind": "labor", "unit": "hr", "rate": 90.0, "name": "Plumber"},
    "lab_glazier": {"kind": "labor", "unit": "hr", "rate": 74.0, "name": "Glazier"},
    # material — $/unit
    "mat_concrete": {"kind": "material", "unit": "m3", "rate": 175.0, "name": "Ready-mix concrete"},
    "mat_rebar": {"kind": "material", "unit": "kg", "rate": 1.5, "name": "Reinforcing steel"},
    "mat_formwork": {"kind": "material", "unit": "m2", "rate": 38.0, "name": "Formwork (contact area)"},
    "mat_cmu": {"kind": "material", "unit": "ea", "rate": 3.2, "name": "CMU block"},
    "mat_stud": {"kind": "material", "unit": "m", "rate": 2.4, "name": "Metal stud"},
    "mat_gwb": {"kind": "material", "unit": "m2", "rate": 9.0, "name": "Gypsum board"},
    "mat_steel": {"kind": "material", "unit": "kg", "rate": 2.8, "name": "Structural steel"},
    "mat_curtainwall": {"kind": "material", "unit": "m2", "rate": 480.0, "name": "Curtain-wall unit"},
    "mat_door": {"kind": "material", "unit": "ea", "rate": 780.0, "name": "Door + frame + hardware"},
    "mat_window": {"kind": "material", "unit": "ea", "rate": 520.0, "name": "Window unit"},
    # equipment — $/hr (allocated)
    "eq_crane": {"kind": "equipment", "unit": "hr", "rate": 320.0, "name": "Tower crane (allocated)"},
    "eq_pump": {"kind": "equipment", "unit": "hr", "rate": 180.0, "name": "Concrete pump"},
    "eq_lift": {"kind": "equipment", "unit": "hr", "rate": 55.0, "name": "Scissor / boom lift"},
}

# Assemblies: a recipe per ONE unit of finished work. `unit` is the billing unit of the output;
# each component consumes `qty` of a resource per output unit (productivity for labor/equipment,
# take-off factor incl. waste for material).
DEFAULT_ASSEMBLIES: dict[str, dict[str, Any]] = {
    "cip_wall": {"name": "Cast-in-place concrete wall", "unit": "m3", "components": [
        {"resource": "mat_concrete", "qty": 1.02}, {"resource": "mat_rebar", "qty": 90.0},
        {"resource": "mat_formwork", "qty": 8.0}, {"resource": "lab_cementmason", "qty": 3.5},
        {"resource": "lab_laborer", "qty": 2.5}, {"resource": "lab_carpenter", "qty": 2.0},
        {"resource": "eq_pump", "qty": 0.25}]},
    "cip_slab": {"name": "Cast-in-place suspended slab", "unit": "m3", "components": [
        {"resource": "mat_concrete", "qty": 1.02}, {"resource": "mat_rebar", "qty": 110.0},
        {"resource": "mat_formwork", "qty": 6.0}, {"resource": "lab_cementmason", "qty": 2.8},
        {"resource": "lab_laborer", "qty": 2.2}, {"resource": "eq_pump", "qty": 0.2}]},
    "cip_column": {"name": "Cast-in-place concrete column", "unit": "m3", "components": [
        {"resource": "mat_concrete", "qty": 1.03}, {"resource": "mat_rebar", "qty": 160.0},
        {"resource": "mat_formwork", "qty": 11.0}, {"resource": "lab_cementmason", "qty": 4.5},
        {"resource": "lab_laborer", "qty": 3.0}, {"resource": "eq_pump", "qty": 0.3}]},
    "steel_beam": {"name": "Structural steel beam (erected)", "unit": "kg", "components": [
        {"resource": "mat_steel", "qty": 1.0}, {"resource": "lab_ironworker", "qty": 0.03},
        {"resource": "eq_crane", "qty": 0.006}]},
    "cmu_wall": {"name": "CMU masonry wall", "unit": "m2", "components": [
        {"resource": "mat_cmu", "qty": 12.5}, {"resource": "lab_mason", "qty": 0.9},
        {"resource": "lab_laborer", "qty": 0.5}]},
    "stud_gwb_wall": {"name": "Metal-stud + gypsum partition", "unit": "m2", "components": [
        {"resource": "mat_stud", "qty": 2.7}, {"resource": "mat_gwb", "qty": 2.1},
        {"resource": "lab_carpenter", "qty": 0.55}, {"resource": "lab_laborer", "qty": 0.2}]},
    "curtainwall": {"name": "Curtain wall (glazed)", "unit": "m2", "components": [
        {"resource": "mat_curtainwall", "qty": 1.0}, {"resource": "lab_glazier", "qty": 0.8},
        {"resource": "eq_lift", "qty": 0.15}]},
    "door_install": {"name": "Door assembly (supply + install)", "unit": "ea", "components": [
        {"resource": "mat_door", "qty": 1.0}, {"resource": "lab_carpenter", "qty": 2.5}]},
    "window_install": {"name": "Window assembly (supply + install)", "unit": "ea", "components": [
        {"resource": "mat_window", "qty": 1.0}, {"resource": "lab_glazier", "qty": 1.8}]},
    "cip_footing": {"name": "Cast-in-place footing", "unit": "m3", "components": [
        {"resource": "mat_concrete", "qty": 1.03}, {"resource": "mat_rebar", "qty": 70.0},
        {"resource": "mat_formwork", "qty": 2.0}, {"resource": "lab_cementmason", "qty": 1.8},
        {"resource": "lab_laborer", "qty": 1.6}]},
}

# Which assembly prices each IFC class by default (editable via `mapping` override on the estimate).
CLASS_TO_ASSEMBLY: dict[str, str] = {
    "IfcWall": "stud_gwb_wall", "IfcWallStandardCase": "stud_gwb_wall",
    "IfcSlab": "cip_slab", "IfcColumn": "cip_column", "IfcBeam": "steel_beam",
    "IfcMember": "steel_beam", "IfcCurtainWall": "curtainwall", "IfcCovering": "stud_gwb_wall",
    "IfcDoor": "door_install", "IfcWindow": "window_install", "IfcFooting": "cip_footing",
}
# assembly unit -> which takeoff dimension supplies the quantity
_UNIT_DIM = {"m2": "area", "m3": "volume", "m": "length", "kg": "volume", "ea": "count"}
# rough conversions when the assembly bills in a unit the takeoff doesn't carry directly
_STEEL_KG_PER_M3 = 7850.0     # density, for volume(m³) -> kg of structural steel


def price_assembly(assembly: dict, quantity: float,
                   resources: dict[str, dict] | None = None) -> dict[str, Any]:
    """Build up the cost of `quantity` units of `assembly`. Returns the total, the labor/material/
    equipment split, crew labor-hours, the built-up unit cost, and a per-component breakdown."""
    catalog = {**DEFAULT_RESOURCES, **(resources or {})}
    by_kind = {"labor": 0.0, "material": 0.0, "equipment": 0.0}
    labor_hours = 0.0
    lines = []
    for comp in assembly.get("components", []):
        r = catalog.get(comp["resource"])
        if not r:
            continue
        qty = float(comp.get("qty", 0.0)) * quantity
        cost = qty * float(r["rate"])
        kind = r["kind"]
        by_kind[kind] = by_kind.get(kind, 0.0) + cost
        if kind == "labor" and r.get("unit") == "hr":
            labor_hours += qty
        lines.append({"resource": comp["resource"], "name": r["name"], "kind": kind,
                      "unit": r["unit"], "quantity": round(qty, 2), "rate": float(r["rate"]),
                      "amount": round(cost, 2)})
    total = sum(by_kind.values())
    return {"assembly": assembly.get("name", ""), "unit": assembly.get("unit", ""),
            "quantity": round(quantity, 2), "total": round(total, 2),
            "by_kind": {k: round(v, 2) for k, v in by_kind.items()},
            "labor_hours": round(labor_hours, 2),
            "unit_cost": round(total / quantity, 2) if quantity else 0.0, "lines": lines}


def _class_quantity(agg: dict[str, float], asm_unit: str, ifc_class: str) -> float:
    """Pick the takeoff quantity that feeds an assembly's billing unit (with a steel kg proxy)."""
    dim = _UNIT_DIM.get(asm_unit, "count")
    qty = float(agg.get(dim, 0.0) if dim != "count" else agg.get("count", 0.0))
    if asm_unit == "kg" and ifc_class in ("IfcBeam", "IfcMember"):
        # takeoff carries steel members by volume; convert to erected weight
        qty = float(agg.get("volume", 0.0)) * _STEEL_KG_PER_M3
    return qty


def estimate_resource_based(rows: list[dict], mapping: dict[str, str] | None = None,
                            resources: dict[str, dict] | None = None,
                            assemblies: dict[str, dict] | None = None) -> dict[str, Any]:
    """Price a model takeoff resource-by-resource. rows: aec_data.qto per-element takeoff. Aggregates
    by IFC class, maps each class to an assembly, and builds the cost up from labor + material +
    equipment. Returns line items with the L/M/E split + labor-hours, a project total, the L/M/E
    rollup, total crew-hours, and any classes with no assembly mapped."""
    cls_map = {**CLASS_TO_ASSEMBLY, **(mapping or {})}
    asm_lib = {**DEFAULT_ASSEMBLIES, **(assemblies or {})}
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        c = r.get("ifc_class") or "Unknown"
        a = agg.setdefault(c, {"count": 0.0, "area": 0.0, "length": 0.0, "volume": 0.0})
        a["count"] += 1
        for k in ("area", "length", "volume"):
            v = r.get(k)
            if isinstance(v, (int, float)):
                a[k] += v
    lines, unmapped = [], []
    roll = {"labor": 0.0, "material": 0.0, "equipment": 0.0}
    labor_hours = 0.0
    for c, a in sorted(agg.items()):
        asm_key = cls_map.get(c)
        asm = asm_lib.get(asm_key) if asm_key else None
        if not asm:
            unmapped.append({"ifc_class": c, "count": int(a["count"])})
            continue
        qty = _class_quantity(a, asm["unit"], c)
        priced = price_assembly(asm, qty, resources)
        for k in roll:
            roll[k] += priced["by_kind"].get(k, 0.0)
        labor_hours += priced["labor_hours"]
        # spread the build-up, but keep the assembly KEY (price_assembly returns the display name)
        lines.append({**priced, "ifc_class": c, "assembly": asm_key,
                      "assembly_name": asm["name"], "count": int(a["count"])})
    lines.sort(key=lambda x: x["total"], reverse=True)
    total = round(sum(x["total"] for x in lines), 2)
    return {"lines": lines, "total": total, "by_kind": {k: round(v, 2) for k, v in roll.items()},
            "labor_hours": round(labor_hours, 2), "unmapped": unmapped, "source": "resource",
            "element_count": int(sum(a["count"] for a in agg.values()))}


def catalog() -> dict[str, Any]:
    """The reference catalog — resources + assemblies (with each assembly's built-up unit cost)."""
    asm = []
    for key, a in DEFAULT_ASSEMBLIES.items():
        p = price_assembly(a, 1.0)
        asm.append({"key": key, "name": a["name"], "unit": a["unit"], "unit_cost": p["unit_cost"],
                    "by_kind": p["by_kind"], "labor_hours": p["labor_hours"],
                    "components": a["components"]})
    return {"resources": DEFAULT_RESOURCES, "assemblies": asm, "class_map": CLASS_TO_ASSEMBLY}
