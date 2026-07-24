"""FIN-CALC — residual land value: the inverse solve the pipeline was missing.

Given a full assumption set and a target return, find the land price that hits the target —
the number a developer can *pay* for the site. Deterministic bisection over the land cost line
(returns fall monotonically as land cost rises), reusing the exact forward `solve()` so the
answer is consistent with every other number the platform reports.

Supported targets: `equity_irr` · `project_irr` · `equity_multiple` · `yield_on_cost` ·
`profit_margin` (project profit ÷ total cost).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .solve import solve

_TARGETS = ("equity_irr", "project_irr", "equity_multiple", "yield_on_cost", "profit_margin")
_MAX_ITER = 80
_TOL = 1e-4          # on the metric, not the dollars


def _metric(result: dict, target: str) -> float | None:
    r = result.get("returns") or {}
    if target == "profit_margin":
        total = (result.get("sources_uses") or {}).get("total_uses") or 0
        if not total:
            return None
        profit = (r.get("total_distributions") or 0) - (r.get("total_contributions") or 0)
        return profit / total
    return r.get(target)


def _with_land(assumptions: dict, land: float) -> dict:
    a = deepcopy(assumptions)
    lines = a.get("cost_lines") or []
    land_lines = [ln for ln in lines if ln.get("category") == "land"]
    if not land_lines:
        raise ValueError("assumptions carry no cost line with category 'land'")
    # scale the first land line to the trial value; zero any additional land lines so the trial
    # is the TOTAL land basis (multiple land lines would double-count the unknown)
    land_lines[0]["amount"] = land
    for ln in land_lines[1:]:
        ln["amount"] = 0.0
    return a


def residual_land_value(assumptions: dict, target: str = "equity_irr",
                        target_value: float = 0.15,
                        max_land: float | None = None) -> dict[str, Any]:
    """Bisect the land price until the chosen return metric hits the target.

    Returns {land_value, achieved, target, target_value, iterations, converged, bounds,
    at_zero_land} — `at_zero_land` carries the metric with free land, so an infeasible target
    (unreachable even at $0 land) reports honestly instead of returning a fake number."""
    if target not in _TARGETS:
        raise ValueError(f"target must be one of {_TARGETS}")
    base = deepcopy(assumptions)
    non_land = sum(float(ln.get("amount") or 0) for ln in (base.get("cost_lines") or [])
                   if ln.get("category") != "land")
    hi = float(max_land) if max_land else max(non_land * 2.0, 1_000_000.0)
    lo = 0.0

    m_lo = _metric(solve(_with_land(base, lo)), target)      # best case: free land
    if m_lo is None or m_lo < target_value:
        return {"land_value": None, "achieved": m_lo, "target": target,
                "target_value": target_value, "iterations": 0, "converged": False,
                "bounds": [lo, hi], "at_zero_land": m_lo,
                "note": "target is not achievable even at $0 land — the deal, not the dirt"}
    m_hi = _metric(solve(_with_land(base, hi)), target)
    it = 0
    # widen hi until the target brackets (metric at hi below target), capped
    while m_hi is not None and m_hi >= target_value and it < 8:
        hi *= 2.0
        m_hi = _metric(solve(_with_land(base, hi)), target)
        it += 1

    land = (lo + hi) / 2.0
    achieved = m_lo
    converged = False
    for _ in range(_MAX_ITER):
        it += 1
        land = (lo + hi) / 2.0
        achieved = _metric(solve(_with_land(base, land)), target)
        if achieved is None:                 # metric vanished (e.g. IRR undefined) → land too high
            hi = land
            continue
        if abs(achieved - target_value) < _TOL:
            converged = True
            break
        if achieved > target_value:
            lo = land                        # can afford more land
        else:
            hi = land
        if hi - lo < 1.0:                    # dollar-level convergence
            converged = True
            break
    return {"land_value": round(land, 2), "achieved": achieved, "target": target,
            "target_value": target_value, "iterations": it, "converged": converged,
            "bounds": [lo, hi], "at_zero_land": m_lo}
