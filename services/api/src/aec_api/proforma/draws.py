"""Actuals / draws bridge (Phase 5) — the differentiator.

Carries the underwriting cost tree forward into committed + actual on the SAME tree, so the
IRR you underwrote is continuously re-forecast against what's actually getting drawn:
  underwritten budget  →  committed (POs/subcontracts)  →  actual (drawn to date)
Re-forecast = actual-to-date + cost-to-complete per line, re-solved through the full engine."""
from __future__ import annotations

import copy

import numpy as np

from .schedule import _end_month, spread_line
from .solve import solve

#: Minimum share of a line's budget that must be SCHEDULED to date before a CPI-based EAC is
#: meaningful. Below this, percent-complete is near zero and dividing by it produces a forecast
#: that is arithmetically faithful and financially absurd (a $9M spend against a $1.9M plan
#: projects to $96M). The standard EVM caution against CPI early in a curve, made explicit.
_CPI_MIN_COMPLETE = 0.20


def budget_to_date(cost_lines: list[dict], as_of_month: int, total_months: int) -> list[float]:
    """Budgeted cumulative spend per line through as_of_month (from its S-curve)."""
    out = []
    for ln in cost_lines:
        # `_end_month`, not a second inline default: an absent end_month means "to the end of
        # construction", and it now arrives as None from the schema. `int(None)` would raise here
        # exactly as it did in `monthly_uses` before the two defaults were unified.
        sched = spread_line(float(ln.get("amount", 0)), int(ln.get("start_month", 0)),
                            _end_month(ln, total_months),
                            ln.get("curve", "scurve"), total_months)
        out.append(float(np.sum(sched[:as_of_month + 1])))
    return out


def reforecast(assumptions: dict, actuals: list[dict], as_of_month: int,
               method: str = "remaining_budget") -> dict:
    """actuals: per cost line (aligned by index) — {actual_to_date, committed?, cost_to_complete?}.
    Returns the underwritten vs re-forecast returns and a budget-vs-actual variance table.

    A line's forecast at completion is `actual_to_date + cost_to_complete` when the estimator supplies
    one. Otherwise `method` decides, and BOTH options actually use the performance to date:

    * `"remaining_budget"` (default) — actual-to-date plus the budget still scheduled to be spent.
      This is what this function always documented.
    * `"cpi"` — earned-value EAC, `budget / (budget_to_date / actual_to_date)`: projects the current
      cost performance across the whole line, so it reacts harder to an early overrun.

    Neither is `max(budget, actual)`, which is what the code used to do: that returns the ORIGINAL
    budget for any line not yet over it, forecasting no overrun on a line 20% over at the halfway
    point and no saving on one running under.
    """
    cost_lines = assumptions["cost_lines"]
    C = int(assumptions["timing"]["construction_months"])
    btd = budget_to_date(cost_lines, as_of_month, C)
    baseline = solve(assumptions)

    fc = copy.deepcopy(assumptions)
    lines_out = []
    for i, ln in enumerate(cost_lines):
        budget = float(ln.get("amount", 0))
        act = actuals[i] if i < len(actuals) else {}
        actual = float(act.get("actual_to_date", 0) or 0)
        committed = float(act.get("committed", 0) or 0)
        ctc = act.get("cost_to_complete")
        if ctc is not None:
            forecast = actual + float(ctc)          # the estimator's own number always wins
        elif method == "cpi" and btd[i] >= _CPI_MIN_COMPLETE * budget and actual > 0 and budget > 0:
            # Earned-value EAC: project the performance to date across the whole line. CPI is
            # budget-to-date over actual-to-date, so a line running hot forecasts hot.
            forecast = budget / (btd[i] / actual)
        elif method == "cpi":
            # Too early for CPI to mean anything. Dividing by a near-zero percent-complete is what
            # turns $9M spent against a $1.9M plan into a $96M forecast — arithmetically faithful and
            # useless. Fall back to the remaining-budget view and say so per line.
            forecast = actual + max(0.0, budget - btd[i])
        else:                                        # "remaining_budget" — the documented default
            # What the docstring always promised: what has been spent, plus the budget still
            # scheduled to be spent. `max(budget, actual)` forecast NO overrun on a line already
            # 20% over at the halfway point, and no saving on one running under — for any line
            # without an explicit cost-to-complete it simply returned the original budget, so the
            # "re-forecast" did not re-forecast at all.
            forecast = actual + max(0.0, budget - btd[i])
        fc["cost_lines"][i]["amount"] = forecast
        lines_out.append({
            "name": ln.get("name"), "category": ln.get("category"),
            "budget": round(budget, 2), "committed": round(committed, 2),
            "actual_to_date": round(actual, 2), "budget_to_date": round(btd[i], 2),
            "forecast_at_completion": round(forecast, 2),
            "variance_to_budget": round(forecast - budget, 2),
            "forecast_basis": ("cost_to_complete" if ctc is not None else
                               "cpi" if (method == "cpi"
                                         and btd[i] >= _CPI_MIN_COMPLETE * budget
                                         and actual > 0 and budget > 0)
                               else "remaining_budget"),
            "pct_drawn": round(actual / budget * 100, 1) if budget else 0.0,
        })

    forecast_res = solve(fc)
    tot_budget = sum(L["budget"] for L in lines_out)
    tot_forecast = sum(L["forecast_at_completion"] for L in lines_out)
    base_irr = baseline["returns"]["equity_irr"]
    fc_irr = forecast_res["returns"]["equity_irr"]
    return {
        "as_of_month": as_of_month,
        "method": method,
        "lines": lines_out,
        "totals": {
            "budget": round(tot_budget, 2),
            "committed": round(sum(L["committed"] for L in lines_out), 2),
            "actual_to_date": round(sum(L["actual_to_date"] for L in lines_out), 2),
            "forecast_at_completion": round(tot_forecast, 2),
            "variance_to_budget": round(tot_forecast - tot_budget, 2),
        },
        "underwritten_returns": baseline["returns"],
        "forecast_returns": forecast_res["returns"],
        "irr_delta": (None if base_irr is None or fc_irr is None
                      else round(fc_irr - base_irr, 4)),
    }
