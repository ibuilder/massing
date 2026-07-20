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
# The space schedule sums NET floor areas (program area); the $/sf benchmark is a GROSS-area rate.
# Standard net-to-gross efficiency ~85-87% → gross ≈ net × 1.15. Callers deriving gfa_sf from the
# space schedule multiply by this so the benchmark isn't systematically understated (walls/cores/
# circulation excluded), which biased the model-vs-benchmark trust test toward the model.
NET_TO_GROSS = 1.15


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


# EST-BANDS — design-stage cost uncertainty by discipline (± fraction of the point estimate). A
# conceptual estimate is a range, not a number; MEP/sitework carry more scope risk than well-defined
# structure. Overridable per class.
_DISCIPLINE_SPREAD = {"S": 0.15, "A": 0.20, "M": 0.30, "E": 0.30, "P": 0.30, "FP": 0.30,
                      "C": 0.35, "T": 0.30, "G": 0.25}
_DEFAULT_SPREAD = 0.25
_Z90 = 1.2816   # standard-normal z for the 10th/90th percentile


def bands(rows: list[dict], overrides: dict[str, float] | None = None,
          spreads: dict[str, float] | None = None) -> dict[str, Any]:
    """EST-BANDS — three-point (low / likely / high) cost bands per priced line from design-stage
    uncertainty, rolled to a bid range two ways: a **correlated envelope** (every line at its extreme
    together) and an **independent probabilistic range** (P10/P50/P90 via a CLT normal approximation of
    the summed per-line triangular distributions). Pass firm rates through ``overrides`` to overlay a
    rate sheet. Pure over the takeoff rows — conceptual-grade."""
    from . import classification as cls

    base = estimate_from_takeoff(rows, overrides or {})
    spreads = spreads or {}
    lines, expected, env_lo, env_hi, variance = [], 0.0, 0.0, 0.0, 0.0
    for ln in base["lines"]:
        c, amt = ln["ifc_class"], ln["amount"]
        disc = cls.discipline_of_ifc_class(c) or "G"
        spread = float(spreads.get(c, _DISCIPLINE_SPREAD.get(disc, _DEFAULT_SPREAD)))
        lo, hi = round(amt * (1 - spread), 2), round(amt * (1 + spread), 2)
        lines.append({**ln, "low": lo, "likely": amt, "high": hi, "spread_pct": round(spread * 100, 1)})
        expected += amt
        env_lo += lo
        env_hi += hi
        # variance of triangular(min=lo, mode=amt, max=hi)
        variance += (lo * lo + amt * amt + hi * hi - lo * amt - lo * hi - amt * hi) / 18.0
    std = variance ** 0.5
    return {
        "lines": sorted(lines, key=lambda x: -x["high"]),
        "expected": round(expected, 2),
        "envelope": {"low": round(env_lo, 2), "high": round(env_hi, 2),
                     "note": "fully-correlated worst/best case — every line at its low / its high together"},
        "range": {"p10": round(max(0.0, expected - _Z90 * std), 2), "p50": round(expected, 2),
                  "p90": round(expected + _Z90 * std, 2), "std": round(std, 2),
                  "note": "probabilistic bid range assuming lines vary independently (CLT normal "
                          "approximation of the summed per-line triangular distributions)"},
        "unpriced": base["unpriced"], "element_count": base["element_count"],
        "note": "Three-point bands per line from design-stage cost uncertainty by discipline; roll-up "
                "gives both the correlated envelope and an independent probabilistic range. Overlay a "
                "firm rate sheet via `overrides`. Conceptual-grade — not a bid.",
    }


def estimate_from_takeoff(rows: list[dict], overrides: dict[str, float] | None = None,
                          gfa_sf: float | None = None, psf: float = DEFAULT_PSF,
                          benchmark_factor: float = 1.0) -> dict[str, Any]:
    """rows: aec_data.qto.takeoff output (per-element: ifc_class, area, length, volume...).
    Returns priced line items grouped by class + a grand total + any unpriced classes.

    When `gfa_sf` is given, also returns a GFA-based benchmark (gfa_sf × $/sf) and a `recommended`
    source: the model takeoff is only trustworthy once it has real structure, so if the model total
    is implausibly low vs. the benchmark (or the model is sparse) we recommend the GFA figure and
    flag it — surfacing *which* number to feed the budget/proforma rather than a misleading $0.

    `benchmark_factor` puts the benchmark in the SAME dollars as the model total: when `overrides`
    are localized/escalated vintage rates (construction-midpoint dollars), the caller passes the same
    combined factor here — otherwise the trust comparison mixes dollar-years and can flip
    `recommended` purely on escalation, not model completeness."""
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
        benchmark = round(gfa_sf * psf * benchmark_factor)
        out["gfa_benchmark"] = {"gfa_sf": round(gfa_sf), "psf": psf, "amount": benchmark,
                                **({"factor": round(benchmark_factor, 4)} if benchmark_factor != 1.0 else {})}
        # trust the model takeoff only if it has structure AND lands within a sane band of the
        # GFA benchmark; otherwise the GFA figure is the honest number to underwrite against.
        trustworthy = element_count >= 10 and total >= 0.4 * benchmark
        out["recommended"] = "model" if trustworthy else "gfa"
        out["recommended_total"] = total if trustworthy else benchmark
    return out
