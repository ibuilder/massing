"""Specialty assets — on-site energy generation and vertical-farm (PFAL) revenue, beyond rent.

Ties a project's *physical* program to its economics: solar/wind/battery/rainwater drive capex and
an annual energy-cost offset; a Plant-Factory-Artificial-Lighting (PFAL) tower farm drives produce
revenue and a lighting-electricity opex load. The differentiator from the thesis model — feasibility
flows model area → tower/panel counts → a specialty proforma. Pure functions over plain dicts.

`summarize()` returns capex + annual revenue/opex/energy-offset; `to_proforma_deltas()` expresses
those as adjustments to the proforma's cost line + operations block (other income / opex)."""
from __future__ import annotations

from typing import Any


def energy(p: dict[str, Any]) -> dict[str, Any]:
    """On-site generation. Inputs: solar_sf or solar_panels, sf_per_panel, cost_per_panel,
    watt_per_panel, sun_hours_day, price_per_kwh; wind_turbines/wind_cost/wind_kwh_yr_each;
    battery_units/battery_cost; rainwater_capex."""
    sf_per_panel = float(p.get("sf_per_panel", 20) or 20)
    panels = float(p.get("solar_panels") or (float(p.get("solar_sf", 0) or 0) / sf_per_panel if sf_per_panel else 0))
    cost_per_panel = float(p.get("cost_per_panel", 330))
    price_kwh = float(p.get("price_per_kwh", 0.12))
    solar_capex = panels * cost_per_panel
    solar_kwh_yr = panels * float(p.get("watt_per_panel", 400)) / 1000 * float(p.get("sun_hours_day", 4.5)) * 365

    wind = float(p.get("wind_turbines", 0) or 0)
    wind_capex = wind * float(p.get("wind_cost", 5000))
    wind_kwh_yr = wind * float(p.get("wind_kwh_yr_each", 3000))

    battery_capex = float(p.get("battery_units", 0) or 0) * float(p.get("battery_cost", 15000))
    rainwater_capex = float(p.get("rainwater_capex", 0) or 0)

    gen_kwh_yr = solar_kwh_yr + wind_kwh_yr
    return {
        "solar_panels": round(panels),
        "capex": round(solar_capex + wind_capex + battery_capex + rainwater_capex),
        "generation_kwh_yr": round(gen_kwh_yr),
        "annual_energy_offset": round(gen_kwh_yr * price_kwh),
        "breakdown": {"solar": round(solar_capex), "wind": round(wind_capex),
                      "battery": round(battery_capex), "rainwater": round(rainwater_capex)},
    }


def pfal(p: dict[str, Any]) -> dict[str, Any]:
    """Vertical farm. Inputs: pfal_sf or towers, sf_per_tower, green_pct, green/herb lbs_per_tower_yr
    and $/lb, watt_per_tower, light_hours_day, price_per_kwh, startup_per_tower, labor_per_tower_yr."""
    sf_per_tower = float(p.get("sf_per_tower", 1.7) or 1.7)
    towers = float(p.get("towers") or (float(p.get("pfal_sf", 0) or 0) / sf_per_tower if sf_per_tower else 0))
    green_pct = float(p.get("green_pct", 0.4))
    greens, herbs = towers * green_pct, towers * (1 - green_pct)
    green_rev = greens * float(p.get("green_lbs_per_tower_yr", 60)) * float(p.get("green_price_lb", 5))
    herb_rev = herbs * float(p.get("herb_lbs_per_tower_yr", 45)) * float(p.get("herb_price_lb", 16))
    revenue = green_rev + herb_rev

    price_kwh = float(p.get("price_per_kwh", 0.12))
    light_kwh_yr = towers * float(p.get("watt_per_tower", 60)) / 1000 * float(p.get("light_hours_day", 18)) * 365
    opex = light_kwh_yr * price_kwh + towers * float(p.get("labor_per_tower_yr", 0) or 0)
    return {
        "towers": round(towers),
        "annual_revenue": round(revenue),
        "annual_opex": round(opex),
        "lighting_kwh_yr": round(light_kwh_yr),
        "startup_capex": round(towers * float(p.get("startup_per_tower", 370))),
    }


def summarize(params: dict[str, Any]) -> dict[str, Any]:
    """Combine the enabled specialty assets into capex + annual revenue/opex/energy-offset."""
    e = energy(params.get("energy", {})) if params.get("energy_enabled") else None
    f = pfal(params.get("pfal", {})) if params.get("pfal_enabled") else None
    capex = (e["capex"] if e else 0) + (f["startup_capex"] if f else 0)
    annual_revenue = (f["annual_revenue"] if f else 0)
    annual_opex = (f["annual_opex"] if f else 0)
    energy_offset = (e["annual_energy_offset"] if e else 0)
    # U4: specialty assets are operating businesses, not de-risked real estate — underwrite their
    # revenue with a risk discount (default 35% haircut) so the blended deal IRR isn't overstated.
    # Energy offset (a cost avoided, contracted-ish) is discounted lightly; produce revenue heavily.
    rd = float(params.get("risk_discount", 0.35))
    uw_revenue = annual_revenue * (1 - rd)
    uw_offset = energy_offset * (1 - rd * 0.4)        # savings are more certain than produce sales
    return {
        "energy": e, "pfal": f, "risk_discount": rd,
        "capex_total": round(capex),
        "annual_revenue": round(annual_revenue),
        "annual_opex": round(annual_opex),
        "annual_energy_offset": round(energy_offset),
        # gross (potential) first-year operating contribution
        "annual_net_contribution": round(annual_revenue + energy_offset - annual_opex),
        # risk-adjusted figures that actually flow into the underwriting
        "annual_revenue_underwritten": round(uw_revenue),
        "annual_offset_underwritten": round(uw_offset),
        "annual_net_underwritten": round(uw_revenue + uw_offset - annual_opex),
    }


def proforma(params: dict[str, Any], years: int = 10, ramp_years: int = 3,
             ramp_start: float = 0.4, terminal_cap: float = 0.10,
             start_year: int = 2027) -> dict[str, Any]:
    """Multi-year specialty P&L with a production **ramp**. A new energy/farm business doesn't reach
    full output in year 1 — revenue and on-site generation ramp linearly from `ramp_start` to 100 %
    over `ramp_years`, while opex (grow-lights, labour) runs at full load from day one, so the early
    years earn less (or lose money) before the business stabilises. Cash flows use the **risk-adjusted**
    (underwritten) revenue/offset from `summarize()`, not the gross potential. Returns per-year rows +
    a **specialty-only IRR** (capex at t0, net cash years 1…N, plus a terminal value = stabilised net ÷
    `terminal_cap`) so the specialty return is separable from — and blendable with — the real estate."""
    from datetime import date

    from .proforma.returns import xirr

    s = summarize(params)
    rev_full = float(s["annual_revenue_underwritten"])
    off_full = float(s["annual_offset_underwritten"])
    opex_full = float(s["annual_opex"])
    capex = float(s["capex_total"])
    years = max(1, int(years)); ramp_years = max(1, int(ramp_years))

    rows: list[dict[str, Any]] = []
    cum = -capex
    payback_year: int | None = None
    for y in range(1, years + 1):
        frac = min(1.0, ramp_start + (1 - ramp_start) * (y - 1) / max(1, ramp_years - 1))
        rev, off = rev_full * frac, off_full * frac
        net = rev + off - opex_full                    # opex is full from year 1 (lights on, staffed)
        cum += net
        if payback_year is None and cum >= 0:
            payback_year = y
        rows.append({"year": start_year + y - 1, "op_year": y, "ramp": round(frac, 3),
                     "revenue": round(rev), "energy_offset": round(off), "opex": round(opex_full),
                     "net": round(net), "cumulative": round(cum)})

    stabilized_net = rev_full + off_full - opex_full
    terminal = stabilized_net / terminal_cap if terminal_cap > 0 else 0.0
    # dated annual cash flows for a robust IRR (capex at t0, nets thereafter, terminal in the last year)
    cfs: list[tuple[date, float]] = [(date(start_year, 1, 1), -capex)]
    for r in rows:
        cfs.append((date(r["year"], 1, 1), float(r["net"])))
    cfs[-1] = (cfs[-1][0], cfs[-1][1] + terminal)      # add terminal sale to the final year
    irr = xirr(cfs)

    return {
        "years": years, "ramp_years": ramp_years, "ramp_start": round(ramp_start, 3),
        "terminal_cap": terminal_cap, "capex_total": round(capex),
        "stabilized_net_annual": round(stabilized_net), "terminal_value": round(terminal),
        "rows": rows, "cumulative_net": round(rows[-1]["cumulative"]) if rows else round(-capex),
        "specialty_irr": round(irr, 4) if irr is not None else None,
        "payback_op_year": payback_year,
    }


def blended_irr(re_equity_cashflows: list[dict[str, Any]], params: dict[str, Any],
                years: int = 10, ramp_years: int = 3, ramp_start: float = 0.4,
                terminal_cap: float = 0.10) -> dict[str, Any]:
    """Blend the specialty business into the real-estate **equity** cash flows and report the deal IRR
    with vs without it. `re_equity_cashflows` is [{"date": "YYYY-MM-DD", "amount": float}, …] (the LP/
    equity stream from the proforma solve). The specialty capex is added at the first (invest) date and
    each specialty net year is folded into the matching calendar year; the terminal value lands with the
    real-estate exit (last date). Returns real-estate-only IRR, blended IRR, and the lift."""
    from datetime import date

    from .proforma.returns import xirr

    def _d(s: str) -> date:
        y, m, dd = (int(x) for x in str(s)[:10].split("-"))
        return date(y, m, dd)

    re_cf = [(_d(c["date"]), float(c["amount"])) for c in re_equity_cashflows if c.get("date")]
    re_cf.sort()
    re_irr = xirr(re_cf) if re_cf else None
    if not re_cf:
        return {"re_only_irr": None, "blended_irr": None, "irr_lift": None, "error": "no equity cash flows"}

    invest_date, exit_date = re_cf[0][0], re_cf[-1][0]
    sp = proforma(params, years=years, ramp_years=ramp_years, ramp_start=ramp_start,
                  terminal_cap=terminal_cap, start_year=invest_date.year + 1)
    # merge specialty into the RE stream by calendar year
    merged: dict[date, float] = dict(re_cf)
    merged[invest_date] = merged.get(invest_date, 0.0) - float(sp["capex_total"])
    for r in sp["rows"]:
        d = date(r["year"], invest_date.month, invest_date.day)
        d = min(d, exit_date)                          # don't extend past the RE exit; pile late nets on exit
        merged[d] = merged.get(d, 0.0) + float(r["net"])
    merged[exit_date] = merged.get(exit_date, 0.0) + float(sp["terminal_value"])
    blended_cf = sorted(merged.items())
    bl_irr = xirr(blended_cf)
    return {
        "re_only_irr": round(re_irr, 4) if re_irr is not None else None,
        "blended_irr": round(bl_irr, 4) if bl_irr is not None else None,
        "irr_lift": (round(bl_irr - re_irr, 4) if (bl_irr is not None and re_irr is not None) else None),
        "specialty": {"specialty_irr": sp["specialty_irr"], "capex_total": sp["capex_total"],
                      "stabilized_net_annual": sp["stabilized_net_annual"],
                      "terminal_value": sp["terminal_value"], "payback_op_year": sp["payback_op_year"]},
    }


def to_proforma_deltas(params: dict[str, Any]) -> dict[str, Any]:
    """How the specialty assets adjust a proforma: a hard-cost capex line, plus operations deltas.
    Uses the **risk-adjusted** (underwritten) revenue/offset — not the gross potential — so the deal
    pencils on credible numbers (U4)."""
    s = summarize(params)
    return {
        "cost_line": {"category": "hard", "name": "Specialty assets (energy + farm)",
                      "amount": s["capex_total"], "curve": "scurve"} if s["capex_total"] else None,
        "other_income_annual_add": s["annual_revenue_underwritten"] + s["annual_offset_underwritten"],
        "opex_annual_add": s["annual_opex"],
        "summary": s,
    }


def starter() -> dict[str, Any]:
    """Thesis-grounded starter parameters (editable)."""
    return {
        "energy_enabled": True, "pfal_enabled": True,
        "energy": {"solar_sf": 500_000, "sf_per_panel": 20, "cost_per_panel": 330, "watt_per_panel": 400,
                   "sun_hours_day": 4.5, "price_per_kwh": 0.12, "wind_turbines": 0, "wind_cost": 5000,
                   "battery_units": 7, "battery_cost": 15000, "rainwater_capex": 780_000},
        "pfal": {"pfal_sf": 40_000, "sf_per_tower": 1.7, "green_pct": 0.4,
                 "green_lbs_per_tower_yr": 60, "green_price_lb": 5,
                 "herb_lbs_per_tower_yr": 45, "herb_price_lb": 16,
                 "watt_per_tower": 60, "light_hours_day": 18, "price_per_kwh": 0.12,
                 "startup_per_tower": 370, "labor_per_tower_yr": 0},
    }
