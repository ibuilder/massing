"""Model-based estimating: aggregate the IFC quantity takeoff by element class and apply unit
rates to produce a priced, conceptual estimate (feeds the budget + the proforma hard cost).
Pure over the takeoff rows (aec_data.qto) so it's testable without an IFC."""
from __future__ import annotations

from typing import Any

# Rough commercial unit rates by IFC class — (billing unit, $/unit). QTO areas/volumes are in
# metric (m², m³, m). Editable per project via `overrides` (class -> rate). Conceptual-grade.
DEFAULT_RATES: dict[str, tuple[str, float]] = {
    "IfcWall": ("area", 160.0), "IfcWallStandardCase": ("area", 160.0),
    "IfcSlab": ("area", 130.0), "IfcRoof": ("area", 210.0),
    "IfcCovering": ("area", 55.0), "IfcCurtainWall": ("area", 600.0),
    "IfcColumn": ("count", 450.0), "IfcBeam": ("length", 90.0), "IfcMember": ("length", 70.0),
    "IfcDoor": ("count", 1200.0), "IfcWindow": ("count", 850.0),
    "IfcStair": ("count", 6000.0), "IfcRailing": ("length", 120.0),
    "IfcFooting": ("volume", 280.0), "IfcPile": ("count", 1500.0),
    "IfcPlate": ("area", 95.0), "IfcRamp": ("area", 180.0),
}
_UNIT_LABEL = {"area": "m²", "length": "m", "volume": "m³", "count": "ea"}


def estimate_from_takeoff(rows: list[dict], overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """rows: aec_data.qto.takeoff output (per-element: ifc_class, area, length, volume...).
    Returns priced line items grouped by class + a grand total + any unpriced classes."""
    overrides = overrides or {}
    agg: dict[str, dict[str, float]] = {}
    for r in rows:
        c = r.get("ifc_class") or "Unknown"
        a = agg.setdefault(c, {"count": 0.0, "area": 0.0, "length": 0.0, "volume": 0.0})
        a["count"] += 1
        for k in ("area", "length", "volume"):
            v = r.get(k)
            if isinstance(v, (int, float)):
                a[k] += v
    lines, unpriced = [], []
    for c, a in sorted(agg.items()):
        spec = DEFAULT_RATES.get(c)
        if not spec:
            unpriced.append({"ifc_class": c, "count": int(a["count"])})
            continue
        unit, default_rate = spec
        rate = float(overrides.get(c, default_rate))
        qty = round(a["count"] if unit == "count" else a.get(unit, 0.0), 2)
        amount = round(qty * rate, 2)
        lines.append({"ifc_class": c, "count": int(a["count"]), "unit": _UNIT_LABEL.get(unit, unit),
                      "quantity": qty, "rate": rate, "amount": amount})
    lines.sort(key=lambda x: x["amount"], reverse=True)
    total = round(sum(x["amount"] for x in lines), 2)
    return {"lines": lines, "total": total, "unpriced": unpriced,
            "element_count": sum(int(a["count"]) for a in agg.values())}
