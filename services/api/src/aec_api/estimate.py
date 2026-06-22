"""Model-based estimating: aggregate the IFC quantity takeoff by element class and apply unit
rates to produce a priced, conceptual estimate (feeds the budget + the proforma hard cost).
Pure over the takeoff rows (aec_data.qto) so it's testable without an IFC."""
from __future__ import annotations

from typing import Any

# Rough commercial unit rates by IFC class — (billing unit, $/unit). QTO areas/volumes are in
# metric (m², m³, m). Editable per project via `overrides` (class -> rate). Conceptual-grade.
DEFAULT_RATES: dict[str, tuple[str, float]] = {
    "IfcWall": ("area", 160.0), "IfcWallStandardCase": ("area", 160.0),
    "IfcSlab": ("volume", 550.0), "IfcRoof": ("area", 210.0),
    "IfcCovering": ("area", 55.0), "IfcCurtainWall": ("area", 600.0),
    # concrete superstructure billed by volume ($/m³ in place, incl. formwork + rebar)
    "IfcColumn": ("volume", 650.0), "IfcBeam": ("volume", 700.0), "IfcMember": ("volume", 600.0),
    "IfcDoor": ("count", 1200.0), "IfcWindow": ("count", 850.0),
    "IfcStair": ("count", 6000.0), "IfcRailing": ("length", 120.0),
    "IfcFooting": ("volume", 280.0), "IfcPile": ("count", 1500.0),
    "IfcPlate": ("area", 95.0), "IfcRamp": ("area", 180.0),
    "IfcTransportElement": ("count", 85000.0),    # elevator
}
_UNIT_LABEL = {"area": "m²", "length": "m", "volume": "m³", "count": "ea"}

M2_TO_SF = 10.7639
DEFAULT_PSF = 220.0          # conceptual all-in $/sf benchmark (residential concrete) for the GFA floor


def estimate_from_takeoff(rows: list[dict], overrides: dict[str, float] | None = None,
                          gfa_sf: float | None = None, psf: float = DEFAULT_PSF) -> dict[str, Any]:
    """rows: aec_data.qto.takeoff output (per-element: ifc_class, area, length, volume...).
    Returns priced line items grouped by class + a grand total + any unpriced classes.

    When `gfa_sf` is given, also returns a GFA-based benchmark (gfa_sf × $/sf) and a `recommended`
    source: the model takeoff is only trustworthy once it has real structure, so if the model total
    is implausibly low vs. the benchmark (or the model is sparse) we recommend the GFA figure and
    flag it — surfacing *which* number to feed the budget/proforma rather than a misleading $0."""
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
    element_count = sum(int(a["count"]) for a in agg.values())
    out: dict[str, Any] = {"lines": lines, "total": total, "unpriced": unpriced,
                           "element_count": element_count, "source": "model"}
    if gfa_sf and gfa_sf > 0:
        benchmark = round(gfa_sf * psf)
        out["gfa_benchmark"] = {"gfa_sf": round(gfa_sf), "psf": psf, "amount": benchmark}
        # trust the model takeoff only if it has structure AND lands within a sane band of the
        # GFA benchmark; otherwise the GFA figure is the honest number to underwrite against.
        trustworthy = element_count >= 10 and total >= 0.4 * benchmark
        out["recommended"] = "model" if trustworthy else "gfa"
        out["recommended_total"] = total if trustworthy else benchmark
    return out
