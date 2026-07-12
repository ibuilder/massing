"""Operational energy — EUI + monthly trends from meter readings, fully offline.

The benchmarking currency for building operations is **EUI** (Energy Use Intensity, kBtu/sf/yr) —
what ENERGY STAR Portfolio Manager scores against and what an ASHRAE Level 1 audit starts from.
Readings are entered manually or CSV-imported (the generic module import); all site energy is
converted to kBtu with standard factors and normalized by the model's GFA. Deterministic — a live
Portfolio Manager sync stays behind `energy_star_bridge` (feature-flagged, never fabricates)."""
from __future__ import annotations

from datetime import date
from typing import Any

from . import modules as me

# site-energy conversion to kBtu (standard factors: 1 kWh = 3.412 kBtu, 1 therm = 100 kBtu,
# water tracked separately in gallons — not energy)
KBTU_PER_UNIT: dict[str, float] = {"kWh": 3.412, "therms": 100.0, "kBtu": 1.0, "ton-hours": 12.0}
WATER_UNITS = ("gallons",)


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _month(v) -> str | None:
    try:
        return str(v)[:7] if v else None                     # YYYY-MM
    except (TypeError, ValueError):
        return None


def summary(db, pid: str, gfa_sf: float | None = None) -> dict[str, Any]:
    """Energy rollup: total site kBtu + cost by utility, monthly trend, water use, and EUI when a GFA
    is known (from the model's space areas or supplied). 12-month EUI uses the trailing year."""
    meters = {m["id"]: _d(m) for m in me.list_records(db, "meter", pid, limit=1000)}
    readings = me.list_records(db, "meter_reading", pid, limit=100000)
    by_month: dict[str, float] = {}
    by_utility: dict[str, dict] = {}
    water_gal = 0.0
    total_kbtu = total_cost = 0.0
    months_seen: set[str] = set()
    for r in readings:
        d = _d(r)
        m = meters.get(d.get("meter") or "")
        if m is None:
            continue
        unit = m.get("unit") or "kWh"
        qty = float(d.get("consumption") or 0)
        cost = float(d.get("cost") or 0)
        mo = _month(d.get("reading_date"))
        util = m.get("utility") or "Electric"
        u = by_utility.setdefault(util, {"consumption": 0.0, "unit": unit, "kbtu": 0.0, "cost": 0.0})
        u["consumption"] += qty
        u["cost"] += cost
        total_cost += cost
        if unit in WATER_UNITS:
            water_gal += qty
        else:
            kbtu = qty * KBTU_PER_UNIT.get(unit, 0.0)
            u["kbtu"] += kbtu
            total_kbtu += kbtu
            if mo:
                by_month[mo] = by_month.get(mo, 0.0) + kbtu
        if mo:
            months_seen.add(mo)
    months = sorted(by_month)
    trend = [{"month": mo, "kbtu": round(by_month[mo], 0)} for mo in months]
    # EUI: annualize over the months actually covered (avoids penalizing partial years)
    eui = None
    n_months = len(set(by_month))
    if gfa_sf and gfa_sf > 0 and n_months:
        eui = round((total_kbtu / n_months) * 12 / gfa_sf, 1)
    return {
        "total_kbtu": round(total_kbtu, 0), "total_cost": round(total_cost, 2),
        "water_gallons": round(water_gal, 0), "by_utility": {k: {**v, "kbtu": round(v["kbtu"], 0),
                                                                 "cost": round(v["cost"], 2),
                                                                 "consumption": round(v["consumption"], 1)}
                                                             for k, v in by_utility.items()},
        "monthly": trend, "months_covered": n_months,
        "gfa_sf": gfa_sf, "eui_kbtu_sf_yr": eui,
        "note": "Site EUI (kBtu/sf/yr) annualized over the months with readings; standard conversion "
                "factors (kWh 3.412, therm 100). Water is tracked in gallons, not energy.",
        "as_of": date.today().isoformat(),
    }


def project_gfa_sf(db, pid: str) -> float | None:
    """GFA from the properties index space areas when loaded (m² → sf), else None (caller may pass
    an explicit GFA)."""
    try:
        from .model_index import _INDEX
        idx = _INDEX.get(pid) or {}
        m2 = 0.0
        for e in idx.values():
            qs = (e.get("qtos") or {}) if isinstance(e, dict) else {}
            for qset in qs.values():
                v = qset.get("GrossFloorArea")
                if v:
                    m2 += float(v)
        return round(m2 * 10.7639, 0) if m2 else None
    except Exception:                              # noqa: BLE001 — GFA is a convenience, never fatal
        return None
