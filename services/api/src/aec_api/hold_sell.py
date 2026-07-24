"""CRE-HOLDSELL (R20) — **hold versus sell, decided on the same arithmetic.**

The question an asset manager is actually asked is not "what is the IRR" but "does another year of
this beat the cheque today". Those are two different cash-flow streams and they are usually argued
with two different spreadsheets, which is how the answer ends up depending on who built which.

Here they share one engine:

* **Sell now** — today's reversion at today's cap, net of selling costs and loan payoff. One number.
* **Hold** — the NOI stream for N more years (growing at the supplied rate), then a reversion at
  the future cap on the grown NOI, less the payoff at that time. The IRR of *incremental* cash
  flows, where the opportunity cost of not selling today is the initial outflow. That framing is
  the point: holding costs you the net proceeds you declined.
* **Breakeven hold period** — the first year whose incremental IRR clears the hurdle, or an honest
  statement that none does inside the horizon.

Cap-rate drift is explicit rather than assumed flat, because "hold" quietly bets on the exit cap,
and a bet nobody wrote down is the one that loses money. Everything reuses the shipped
`proforma.returns` / `operations.reversion` primitives so this cannot disagree with the pro forma.
"""
from __future__ import annotations

from typing import Any

from .proforma import returns as ret
from .proforma.operations import reversion


def _num(v: Any) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def analyze(inputs: dict, hurdle_rate: float = 0.12, max_years: int = 10) -> dict[str, Any]:
    """Compare selling today against holding 1..N more years.

    `inputs` = {noi_annual, exit_cap_now, selling_cost_pct?, loan_balance_now?,
                noi_growth_pct?, cap_drift_bps_per_year?, annual_loan_amortization?,
                capex_per_year?}
    """
    noi = _num(inputs.get("noi_annual"))
    cap_now = _num(inputs.get("exit_cap_now"))
    if noi <= 0 or cap_now <= 0:
        return {"computable": False,
                "reason": "needs a positive noi_annual and exit_cap_now — a hold/sell call cannot "
                          "be made without today's income and today's cap"}
    sell_cost = _num(inputs.get("selling_cost_pct") or 0.02)
    loan = _num(inputs.get("loan_balance_now"))
    growth = _num(inputs.get("noi_growth_pct")) / 100.0
    drift = _num(inputs.get("cap_drift_bps_per_year")) / 10_000.0
    amort = _num(inputs.get("annual_loan_amortization"))
    capex = _num(inputs.get("capex_per_year"))

    sell_now = reversion(noi, cap_now, sell_cost, loan)
    today_net = sell_now["net_proceeds"]

    years: list[dict[str, Any]] = []
    for n in range(1, int(max_years) + 1):
        # NOI grows each year; the exit cap drifts (positive bps = expansion = a worse exit)
        flows = [-today_net]                     # the opportunity cost of not selling today
        noi_n = noi
        for _y in range(n):
            noi_n = noi_n * (1.0 + growth)
            flows.append(noi_n - capex)
        cap_n = max(cap_now + drift * n, 0.0001)
        payoff = max(loan - amort * n, 0.0)
        rev_n = reversion(noi_n, cap_n, sell_cost, payoff)
        flows[-1] += rev_n["net_proceeds"]
        irr = ret.irr(flows) if hasattr(ret, "irr") else None
        if irr is None:                          # fall back to the shipped NPV-root helper
            irr = _irr(flows)
        years.append({
            "hold_years": n, "exit_cap": round(cap_n, 5),
            "noi_at_exit": round(noi_n, 2),
            "gross_sale": round(rev_n["gross_sale"], 2),
            "loan_payoff": round(payoff, 2),
            "net_proceeds_at_exit": round(rev_n["net_proceeds"], 2),
            "incremental_irr": round(irr, 4) if irr is not None else None,
            "beats_hurdle": bool(irr is not None and irr >= hurdle_rate),
        })

    clearing = [y for y in years if y["beats_hurdle"]]
    best = max((y for y in years if y["incremental_irr"] is not None),
               key=lambda y: y["incremental_irr"], default=None)
    return {
        "computable": True,
        "sell_now": {**{k: round(v, 2) for k, v in sell_now.items()},
                     "exit_cap": round(cap_now, 5)},
        "hurdle_rate": hurdle_rate,
        "assumptions": {"noi_growth_pct": round(growth * 100, 3),
                        "cap_drift_bps_per_year": round(drift * 10_000, 2),
                        "selling_cost_pct": sell_cost,
                        "annual_loan_amortization": amort, "capex_per_year": capex},
        "years": years,
        "breakeven_hold_years": clearing[0]["hold_years"] if clearing else None,
        "recommendation": ("hold" if clearing else "sell"),
        "best_year": best,
        "note": ("The hold case is measured as INCREMENTAL cash flows against the net proceeds "
                 "declined today — holding costs you the cheque you did not take. Cap drift is an "
                 "explicit input because 'hold' silently bets on the exit cap; a bet nobody wrote "
                 "down is the one that loses money."
                 + ("" if clearing else
                    " No hold period inside the horizon clears the hurdle on these assumptions.")),
    }


def _irr(flows: list[float], lo: float = -0.95, hi: float = 10.0) -> float | None:
    """Bisection IRR over annual flows (flows[0] is t=0). None when there is no sign change."""
    def npv(r: float) -> float:
        return sum(cf / ((1.0 + r) ** i) for i, cf in enumerate(flows))
    if not flows or all(f >= 0 for f in flows) or all(f <= 0 for f in flows):
        return None
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0
