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
    # ---- MEP distribution (installed, incl. fittings/hangers) ----
    "IfcPipeSegment": ("length", 180.0), "IfcDuctSegment": ("length", 150.0),
    "IfcCableCarrierSegment": ("length", 220.0),  # bus riser / cable tray
    "IfcPipeFitting": ("count", 120.0), "IfcDuctFitting": ("count", 140.0),
    # ---- MEP / fire terminals & fixtures ----
    "IfcFireSuppressionTerminal": ("count", 95.0),   # sprinkler head installed
    "IfcAirTerminal": ("count", 180.0), "IfcSanitaryTerminal": ("count", 650.0),
    "IfcLightFixture": ("count", 220.0), "IfcOutlet": ("count", 45.0),
    "IfcSwitchingDevice": ("count", 60.0),
    # ---- MEP plant / equipment ----
    "IfcPump": ("count", 18000.0), "IfcBoiler": ("count", 85000.0),
    "IfcTank": ("count", 22000.0), "IfcTransformer": ("count", 45000.0),
    "IfcCoolingTower": ("count", 120000.0), "IfcChiller": ("count", 150000.0),
    "IfcElectricDistributionBoard": ("count", 35000.0),   # switchgear / distribution
    "IfcUnitaryEquipment": ("count", 12000.0), "IfcFan": ("count", 8000.0),
    "IfcElementAssembly": ("count", 850.0),   # steel connection assembly
    # NOTE: IfcReinforcingBar is intentionally NOT priced here — the concrete volume
    # rates (IfcColumn/IfcBeam/IfcFooting) are quoted "in place, incl. rebar", so pricing
    # reinforcement again would double-count. LOD-400 rebar remains a takeoff-only detail.
}
_UNIT_LABEL = {"area": "m²", "length": "m", "volume": "m³", "count": "ea"}

M2_TO_SF = 10.7639
DEFAULT_PSF = 220.0          # conceptual all-in $/sf benchmark (residential concrete) for the GFA floor


def _price(c: str, a: dict, overrides: dict[str, float]) -> dict | None:
    spec = DEFAULT_RATES.get(c)
    if not spec:
        return None
    from . import classification as cls
    unit, default_rate = spec
    rate = float(overrides.get(c, default_rate))
    qty = round(a["count"] if unit == "count" else a.get(unit, 0.0), 2)
    dcode = cls.discipline_of_ifc_class(c)
    return {"ifc_class": c, "count": int(a["count"]), "unit": _UNIT_LABEL.get(unit, unit),
            "quantity": qty, "rate": rate, "amount": round(qty * rate, 2),
            "discipline": cls.discipline_name(dcode) or "General",
            "discipline_code": dcode or "G", "discipline_color": cls.discipline_color(dcode)}


def _agg_add(bucket: dict, r: dict) -> None:
    bucket["count"] += 1
    for k in ("area", "length", "volume"):
        v = r.get(k)
        if isinstance(v, (int, float)):
            bucket[k] += v


def _floor_key(s: str) -> int:
    import re
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else 9999


def estimate_by_storey(rows: list[dict], overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """QTO + cost broken down by storey (floor) AND IFC class — quantities and dollars mapped to
    where they sit in the building, plus a discipline (class) roll-up across all floors."""
    overrides = overrides or {}
    by_storey: dict[str, dict[str, dict]] = {}
    by_class: dict[str, dict] = {}
    blank = lambda: {"count": 0.0, "area": 0.0, "length": 0.0, "volume": 0.0}
    for r in rows:
        st = r.get("storey") or "(unassigned)"
        c = r.get("ifc_class") or "Unknown"
        _agg_add(by_storey.setdefault(st, {}).setdefault(c, blank()), r)
        _agg_add(by_class.setdefault(c, blank()), r)
    storeys = []
    for st in sorted(by_storey, key=_floor_key):
        lines = [p for c, a in sorted(by_storey[st].items()) if (p := _price(c, a, overrides))]
        lines.sort(key=lambda x: -x["amount"])
        storeys.append({"storey": st, "total": round(sum(x["amount"] for x in lines), 2),
                        "element_count": int(sum(a["count"] for a in by_storey[st].values())), "lines": lines})
    class_lines = [p for c, a in sorted(by_class.items()) if (p := _price(c, a, overrides))]
    class_lines.sort(key=lambda x: -x["amount"])
    # a TRUE discipline roll-up: sum the priced class lines into their NCS discipline (the previous
    # "by_discipline" was really per-IFC-class — now each class line also carries its discipline, and
    # this aggregates them so the estimate rolls up by Structural / Architectural / MEP / … as intended).
    roll: dict[str, dict] = {}
    for ln in class_lines:
        d = roll.setdefault(ln["discipline_code"], {"discipline": ln["discipline"], "code": ln["discipline_code"],
                                                    "color": ln["discipline_color"], "amount": 0.0, "count": 0})
        d["amount"] += ln["amount"]; d["count"] += ln["count"]
    by_disc = sorted(({**d, "amount": round(d["amount"], 2)} for d in roll.values()), key=lambda x: -x["amount"])
    return {"storeys": storeys, "by_class": class_lines, "by_discipline_rollup": by_disc,
            "by_discipline": class_lines,  # kept for backward compatibility (per-IFC-class lines)
            "grand_total": round(sum(s["total"] for s in storeys), 2),
            "element_count": int(sum(a["count"] for a in by_class.values()))}


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
