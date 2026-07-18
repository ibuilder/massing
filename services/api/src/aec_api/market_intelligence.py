"""Market intelligence & cost escalation (Track M).

Turns a project's **region + construction timeline + sector** into the numbers an estimate/proforma needs:
a **regional escalation rate** (escalate a base cost to the *midpoint of construction*, not just "next
year"), a **location cost index**, a **regional labour rate**, and the **warm/cold two-speed market**
signal (tech-led sectors — data centres, advanced manufacturing — running hot while residential /
commercial run cold).

The seed values are the **public headline figures** from Turner & Townsend's *Global Construction Market
Intelligence 2026* (global cost inflation ~4.5% for 2026; regional average labour US$/hr — North America
79.5, Europe 75.6, Australia/NZ 68.0; the data-centre / advanced-manufacturing-led warm market vs the
cold residential/commercial market). They are **illustrative, editable defaults** — a deployment
overrides them with its own current rates (or a `market_assumption` record per project). We embed only
the public headline values as starting points, attributed to T&T GCMI 2026; not their proprietary
dataset.
"""
from __future__ import annotations

from typing import Any

BASE_YEAR = 2026
SOURCE = "Seed defaults: Turner & Townsend Global Construction Market Intelligence 2026 (public headline " \
         "figures) — editable; override with your own current rates."

# region -> annual escalation %, average labour US$/hr, location index (1.0 = US average), label.
REGIONS: dict[str, dict[str, Any]] = {
    "global_average":  {"escalation_pct": 4.5, "labour_usd_hr": 60.0, "location_index": 1.00, "label": "Global average"},
    "north_america":   {"escalation_pct": 4.6, "labour_usd_hr": 79.5, "location_index": 1.05, "label": "North America"},
    "europe":          {"escalation_pct": 4.3, "labour_usd_hr": 75.6, "location_index": 0.98, "label": "Europe"},
    "australia_nz":    {"escalation_pct": 5.2, "labour_usd_hr": 68.0, "location_index": 1.00, "label": "Australia / New Zealand"},
    "asia":            {"escalation_pct": 4.0, "labour_usd_hr": 28.0, "location_index": 0.72, "label": "Asia"},
    "middle_east":     {"escalation_pct": 4.2, "labour_usd_hr": 24.0, "location_index": 0.78, "label": "Middle East"},
    "latin_america":   {"escalation_pct": 5.5, "labour_usd_hr": 18.0, "location_index": 0.68, "label": "Latin America"},
    "africa":          {"escalation_pct": 5.0, "labour_usd_hr": 15.0, "location_index": 0.65, "label": "Africa"},
}

# sector -> market temperature (demand). "Two-speed market": tech-led warm, traditional cold.
SECTORS: dict[str, str] = {
    "data_center": "hot", "advanced_manufacturing": "hot", "semiconductor": "hot",
    "life_sciences": "warm", "lab": "warm", "infrastructure": "warm", "energy": "warm",
    "healthcare": "warm", "hospital": "warm", "education": "neutral", "school": "neutral",
    "hotel": "neutral", "mixed_use": "neutral", "industrial": "neutral", "warehouse": "warm",
    "residential": "cold", "multifamily": "cold", "office": "cold", "commercial": "cold",
    "retail": "cold",
}
_TEMP_NOTE = {
    "hot": "Accelerating — tech/AI-driven demand; expect tighter capacity, longer lead times, premium bids.",
    "warm": "Steady demand; watch labour availability and long-lead equipment.",
    "neutral": "Balanced market conditions.",
    "cold": "Slower momentum — softer investor confidence; more competitive bidding may be available.",
}


def _norm(s: str | None, default: str) -> str:
    return (s or default).strip().lower().replace(" ", "_").replace("/", "_").replace("-", "_")


def region_data(region: str | None) -> dict[str, Any]:
    key = _norm(region, "global_average")
    data = REGIONS.get(key) or REGIONS["global_average"]
    return {"region": key if key in REGIONS else "global_average", **data}


def sector_temp(sector: str | None) -> dict[str, Any]:
    key = _norm(sector, "")
    temp = SECTORS.get(key, "neutral")
    return {"sector": key or "(unspecified)", "temperature": temp, "note": _TEMP_NOTE[temp]}


def escalation_factor(region: str | None = None, *, from_year: int | None = None,
                      start_year: int | None = None, duration_months: int | None = None,
                      to_year: int | None = None, rate_pct: float | None = None) -> dict[str, Any]:
    """The compound escalation **factor** from `from_year` (default BASE_YEAR) to a target year, using the
    region's annual rate.

    The target is a fixed `to_year`, else the **midpoint** of a build starting `start_year` (+ optional
    `duration_months`, default 18), else `from_year` (no escalation). `rate_pct` overrides the region rate.
    Reused by `escalate` (a dollar amount) and by the cost-DB rate resolver (a vintage's per-class rates,
    with `from_year` = the vintage year), so a cost is only ever escalated over the years it actually spans.
    """
    rd = region_data(region)
    base = float(from_year if from_year is not None else BASE_YEAR)
    rate = (rate_pct if rate_pct is not None else rd["escalation_pct"]) / 100.0
    if to_year is not None:
        target = float(to_year)
        basis = f"target year {to_year}"
    elif start_year is not None:
        months = duration_months if duration_months and duration_months > 0 else 18
        target = start_year + (months / 12.0) / 2.0        # midpoint of construction
        basis = f"midpoint of a {months}-month build starting {start_year}"
    else:
        target = base
        basis = "no timeline given — no escalation"
    years = target - base
    return {
        "region": rd["region"], "from_year": round(base, 2), "target_year": round(target, 2),
        "years": round(years, 2), "annual_rate_pct": round(rate * 100, 2),
        "factor": (1 + rate) ** years, "basis": basis,   # full precision; callers round for display
    }


def escalate(amount: float, region: str | None = None, *, start_year: int | None = None,
             duration_months: int | None = None, to_year: int | None = None,
             rate_pct: float | None = None) -> dict[str, Any]:
    """Escalate `amount` from BASE_YEAR to the **midpoint of construction**.

    Provide either `start_year` (+ optional `duration_months`, default 18) to escalate to the schedule
    midpoint, or `to_year` for a fixed target year. `rate_pct` overrides the region's annual rate.
    """
    ef = escalation_factor(region, from_year=BASE_YEAR, start_year=start_year,
                           duration_months=duration_months, to_year=to_year, rate_pct=rate_pct)
    factor = ef["factor"]
    return {
        "base_year": BASE_YEAR, "region": ef["region"], "annual_rate_pct": ef["annual_rate_pct"],
        "escalation_basis": ef["basis"], "midpoint_year": ef["target_year"], "years": ef["years"],
        "escalation_factor": round(factor, 4), "base_amount": round(amount, 2),
        "escalated_amount": round(amount * factor, 2),
        "note": "Escalated to the construction midpoint using the regional annual rate. " + SOURCE,
    }


def snapshot() -> dict[str, Any]:
    """The full market table — regions (escalation / labour / location) + the warm/cold sector board."""
    warm = sorted([s for s, t in SECTORS.items() if t in ("hot", "warm")])
    cold = sorted([s for s, t in SECTORS.items() if t == "cold"])
    return {
        "base_year": BASE_YEAR,
        "regions": [{"key": k, **v} for k, v in REGIONS.items()],
        "sectors": [{"sector": s, "temperature": t} for s, t in sorted(SECTORS.items())],
        "market_signal": {"hot": [s for s, t in SECTORS.items() if t == "hot"],
                          "warm_or_hot": warm, "cold": cold,
                          "headline": "Two-speed market — data centres & advanced manufacturing hot; "
                                      "residential & commercial cold."},
        "source": SOURCE,
    }


def project_context(region: str | None, sector: str | None, *, start_year: int | None = None,
                    duration_months: int | None = None) -> dict[str, Any]:
    """A compact market read for one project: its region economics + sector temperature + the escalation
    factor to its construction midpoint (factor of 1.0 when no timeline is given)."""
    rd = region_data(region)
    st = sector_temp(sector)
    esc = escalate(1.0, region, start_year=start_year, duration_months=duration_months)
    return {
        "region": rd, "sector": st,
        "escalation_factor": esc["escalation_factor"], "escalation_basis": esc["escalation_basis"],
        "midpoint_year": esc["midpoint_year"], "source": SOURCE,
    }
