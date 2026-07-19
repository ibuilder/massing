"""EST-ASSEMBLIES (R15) — cost-item **assemblies**: a unit rate built up from its component resources
(labour crew + material + equipment + subcontract), the way an estimator actually constructs a price.

`estimate.py` prices by a flat $/unit per IFC class; this composes that rate from first principles —
e.g. an 8" CMU wall at ~$X/SF = mason-hours × wage + blocks × block-cost + mortar + grout — so the
number is auditable and re-costs cleanly when a wage or material price moves. Pure/deterministic; a
small starter LIBRARY ships, and callers can pass their own component list.

A component: ``{resource, kind, qty, unit, unit_cost, waste_pct?}`` where ``kind`` ∈
labour / material / equipment / sub. Extended = ``qty × unit_cost × (1 + waste_pct/100)``; the
assembly's unit rate is the sum of its components' extended cost.
"""
from __future__ import annotations

from typing import Any

KINDS = ("labour", "material", "equipment", "sub")


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def build_up(components: list[dict], overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Compose a unit rate from component lines. `overrides` maps a component `resource` → a new
    `unit_cost` (re-cost when a wage/material price moves). Returns the rate + per-kind subtotals +
    the priced line breakdown."""
    overrides = overrides or {}
    lines: list[dict] = []
    by_kind: dict[str, float] = dict.fromkeys(KINDS, 0.0)
    for c in components or []:
        kind = str(c.get("kind") or "material").strip().lower()
        if kind not in KINDS:
            kind = "material"
        qty = _num(c.get("qty"))
        unit_cost = _num(overrides.get(c.get("resource"), c.get("unit_cost")))
        waste = _num(c.get("waste_pct"))
        ext = round(qty * unit_cost * (1 + waste / 100.0), 4)
        by_kind[kind] += ext
        lines.append({"resource": c.get("resource"), "kind": kind, "qty": qty,
                      "unit": c.get("unit"), "unit_cost": round(unit_cost, 4),
                      "waste_pct": waste, "extended": round(ext, 4)})
    rate = round(sum(by_kind.values()), 4)
    return {"unit_rate": rate, "by_kind": {k: round(v, 4) for k, v in by_kind.items()},
            "lines": lines, "component_count": len(lines)}


def price(components: list[dict], quantity: float, overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Build up the unit rate, then extend it over a take-off `quantity`."""
    b = build_up(components, overrides)
    q = _num(quantity)
    return {**b, "quantity": q, "total": round(b["unit_rate"] * q, 2)}


# --- a small starter library (illustrative RSMeans-style build-ups; operators edit/extend) ----------
LIBRARY: list[dict[str, Any]] = [
    {"id": "cmu-8-wall", "name": '8" CMU wall', "unit": "SF", "csi": "04 22 00",
     "components": [
         {"resource": "Mason (crew hr)", "kind": "labour", "qty": 0.125, "unit": "hr", "unit_cost": 68.0},
         {"resource": "8\" CMU block", "kind": "material", "qty": 1.125, "unit": "ea", "unit_cost": 2.35, "waste_pct": 5},
         {"resource": "Mortar", "kind": "material", "qty": 0.02, "unit": "bag", "unit_cost": 9.5, "waste_pct": 10},
         {"resource": "Grout / rebar", "kind": "material", "qty": 0.015, "unit": "cf", "unit_cost": 12.0}]},
    {"id": "cip-slab-6", "name": '6" cast-in-place slab on grade', "unit": "SF", "csi": "03 30 00",
     "components": [
         {"resource": "Finisher crew (hr)", "kind": "labour", "qty": 0.012, "unit": "hr", "unit_cost": 62.0},
         {"resource": "Concrete 4000psi", "kind": "material", "qty": 0.0185, "unit": "cy", "unit_cost": 165.0, "waste_pct": 5},
         {"resource": "WWF / rebar", "kind": "material", "qty": 1.0, "unit": "sf", "unit_cost": 0.55},
         {"resource": "Pump", "kind": "equipment", "qty": 0.0185, "unit": "cy", "unit_cost": 22.0}]},
    {"id": "mtl-stud-partition", "name": "Metal-stud + GWB partition (one side)", "unit": "SF", "csi": "09 21 16",
     "components": [
         {"resource": "Carpenter (hr)", "kind": "labour", "qty": 0.035, "unit": "hr", "unit_cost": 60.0},
         {"resource": "3-5/8\" stud", "kind": "material", "qty": 0.9, "unit": "lf", "unit_cost": 0.95, "waste_pct": 10},
         {"resource": "5/8\" GWB", "kind": "material", "qty": 1.05, "unit": "sf", "unit_cost": 0.62, "waste_pct": 8},
         {"resource": "Finish (tape/mud)", "kind": "labour", "qty": 0.02, "unit": "hr", "unit_cost": 55.0}]},
]
_BY_ID = {a["id"]: a for a in LIBRARY}


def library() -> list[dict[str, Any]]:
    """The starter assemblies with each unit rate pre-computed (for a picker)."""
    return [{"id": a["id"], "name": a["name"], "unit": a["unit"], "csi": a.get("csi"),
             "unit_rate": build_up(a["components"])["unit_rate"], "component_count": len(a["components"])}
            for a in LIBRARY]


def get(assembly_id: str) -> dict | None:
    return _BY_ID.get(assembly_id)
