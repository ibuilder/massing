"""ESG rollup + post-occupancy evaluation — the asset's sustainability scorecard, fully offline.

Institutional reporting frameworks organize asset ESG around measured performance (energy intensity,
operational GHG by scope, water) plus certifications and management practices. This engine rolls the
platform's own data into that shape: meter readings (energy.py) -> EUI + Scope 1/2 emissions from a
transparent local factor table (carbon.py pattern — override the grid factor per deployment), water,
LEED credit tracking, and POE records comparing actual vs design EUI (the RIBA Stage 7 feedback
loop). Deterministic; nothing is fetched or fabricated."""
from __future__ import annotations

import os
from typing import Any

from . import energy
from . import modules as me
from . import resilience

# kgCO2e per unit of site energy, by (utility). Scope 1 = fuel burned on site; Scope 2 = purchased
# energy. Defaults: EPA emission factors for natural gas (5.3 kgCO2e/therm) and a US-average grid
# electricity factor (~0.386 kgCO2e/kWh) — set AEC_GRID_KGCO2E_PER_KWH to the local eGRID subregion.
SCOPE1_UTILITIES = {"Natural Gas": 5.30}                 # per therm
SCOPE2_UTILITIES = {"Electric": 0.386,                   # per kWh (grid average; override via env)
                    "Steam": 0.0886,                     # per kBtu purchased steam
                    "Chilled Water": 0.0526}             # per ton-hour purchased cooling


def _grid_factor() -> float:
    try:
        return float(os.environ.get("AEC_GRID_KGCO2E_PER_KWH") or SCOPE2_UTILITIES["Electric"])
    except ValueError:
        return SCOPE2_UTILITIES["Electric"]


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def summary(db, pid: str, gfa_sf: float | None = None) -> dict[str, Any]:
    """GRESB-shaped asset rollup: energy (EUI), GHG Scope 1/2 + intensity, water + intensity,
    certification tracking (leed_credit), and the POE actual-vs-design EUI comparison."""
    e = energy.summary(db, pid, gfa_sf=gfa_sf)

    scope1 = scope2 = 0.0
    for util, v in e["by_utility"].items():
        qty = _f(v.get("consumption"))
        if util in SCOPE1_UTILITIES:
            scope1 += qty * SCOPE1_UTILITIES[util]
        elif util == "Electric":
            scope2 += qty * _grid_factor()
        elif util in SCOPE2_UTILITIES:
            scope2 += qty * SCOPE2_UTILITIES[util]
    t1, t2 = scope1 / 1000.0, scope2 / 1000.0            # kg -> tCO2e
    ghg_intensity = round((scope1 + scope2) / gfa_sf, 2) if gfa_sf else None

    # certifications — leed_credit tracking (points targeted vs achieved)
    creds = me.list_records(db, "leed_credit", pid, limit=10000)
    targeted = sum(_f(_d(c).get("points_targeted")) for c in creds)
    achieved = sum(_f(_d(c).get("points_achieved")) for c in creds)

    # POE — latest reported evaluation: actual (metered) vs design EUI
    poes = me.list_records(db, "poe", pid, limit=1000)
    latest = None
    for r in sorted(poes, key=lambda r: str(_d(r).get("survey_date") or ""), reverse=True):
        d = _d(r)
        actual = e["eui_kbtu_sf_yr"]
        design = _f(d.get("design_eui")) or None
        gap_pct = (round(100 * (actual - design) / design, 1)
                   if actual is not None and design else None)
        latest = {"ref": r.get("ref"), "level": d.get("level"), "state": r.get("workflow_state"),
                  "survey_date": d.get("survey_date"),
                  "satisfaction_score": _f(d.get("satisfaction_score")) or None,
                  "design_eui": design, "actual_eui": actual, "eui_gap_pct": gap_pct}
        break

    return {
        "performance": {
            "energy": {"total_kbtu": e["total_kbtu"], "eui_kbtu_sf_yr": e["eui_kbtu_sf_yr"],
                       "months_covered": e["months_covered"], "gfa_sf": e["gfa_sf"]},
            "ghg": {"scope1_tco2e": round(t1, 1), "scope2_tco2e": round(t2, 1),
                    "total_tco2e": round(t1 + t2, 1),
                    "intensity_kgco2e_sf": ghg_intensity,
                    "grid_factor_kgco2e_kwh": _grid_factor(),
                    "note": "Scope 1 = on-site fuel (natural gas); Scope 2 = purchased "
                            "electricity/steam/cooling at the configured grid factor. Set "
                            "AEC_GRID_KGCO2E_PER_KWH to your eGRID subregion."},
            "water": {"gallons": e["water_gallons"],
                      "intensity_gal_sf": round(e["water_gallons"] / gfa_sf, 1) if gfa_sf else None},
        },
        "certifications": {"credits_tracked": len(creds), "points_targeted": round(targeted, 0),
                           "points_achieved": round(achieved, 0)},
        "physical_risk": resilience.climate_risk(db, pid),
        "poe": {"count": len(poes), "reported": sum(1 for r in poes
                                                    if r.get("workflow_state") == "reported"),
                "latest": latest},
        "data_coverage": {"meter_months": e["months_covered"]},
        "as_of": e["as_of"],
    }
