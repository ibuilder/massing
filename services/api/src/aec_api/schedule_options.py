"""SCHED-OPT (SPRINT B phase-1) — deterministic **schedule optioneering** over the Takt line-of-balance
model: permute crew loading and work-face zoning across a bounded option grid, score every scenario on
makespan / cost / peak-congestion, and return the ranked list with the Pareto frontier and a recommended
option.

This is the de-risking first slice of the ALICE-style optioneer: our inputs (the Takt trade train + a
per-floor production rate) are already present offline, so we can enumerate a small, *defensible* option
set exactly — no solver, no randomness — and widen the search later (finer zoning, sequence permutation,
CPM-driven crew shifts). Pure over a ``base`` scenario dict, so it unit-tests without fixtures.

Levers (phase-1, bounded):
  * **crew loading** — a second crew on a *bottleneck* trade (the slowest few) halves that trade's
    days-per-floor (throughput doubles) at a mobilisation/coordination premium.
  * **zoning** — splitting each floor into Z work-face zones lets the train pipeline finer (shorter
    makespan) at the cost of more concurrent crews on site (congestion) + a per-zone setup.

Work content is conserved across scenarios (splitting a floor into Z zones makes each 1/Z the size), so
the enumerated tradeoff is *time & peak-congestion vs. a mobilisation premium* — the real buyout question.
"""
from __future__ import annotations

import itertools
from typing import Any

_DEFAULT_RATE = 2000.0          # $ per crew-day (a blended trade crew) — overridable per call
_CREW2_PREMIUM = 0.15           # a 2nd crew carries a 15% coordination/overtime premium on its trade
_ZONE_SETUP_CREWDAYS = 3.0      # crew-days of mobilisation per extra work-face zone


def _lob(locations: int, takts: list[int]) -> tuple[int, list[tuple[float, float]]]:
    """Line-of-balance recurrence (same rule as ``takt.plan``): a trade can't start a location until it
    finished the previous location *and* the preceding trade finished this location. Returns the makespan
    and the flat list of (start, finish) work intervals (one per trade × location)."""
    nt = len(takts)
    finish = [[0.0] * locations for _ in range(nt)]
    start = [[0.0] * locations for _ in range(nt)]
    for i in range(nt):
        td = takts[i]
        for f in range(locations):
            prev_loc = finish[i][f - 1] if f > 0 else 0.0
            prev_trade = finish[i - 1][f] if i > 0 else 0.0
            s = max(prev_loc, prev_trade)
            start[i][f] = s
            finish[i][f] = s + td
    makespan = max((finish[i][locations - 1] for i in range(nt)), default=0)
    intervals = [(start[i][f], finish[i][f]) for i in range(nt) for f in range(locations)]
    return round(makespan), intervals


def _peak_crews(intervals: list[tuple[float, float]], weights: list[int], nt: int, locations: int) -> int:
    """Max concurrent crews across the run — a sweep over interval endpoints, each active trade counted
    with its crew multiplier. ``weights`` is the per-trade crew count; ``intervals`` are trade-major."""
    events: list[tuple[float, int, int]] = []       # (time, delta, +1 for start sorts after -1 end)
    for idx, (s, e) in enumerate(intervals):
        if e <= s:
            continue
        w = weights[idx // locations]
        events.append((s, 1, w))
        events.append((e, 0, -w))                    # ends (flag 0) processed before starts (flag 1) at a tie
    events.sort(key=lambda ev: (ev[0], ev[1]))
    cur = peak = 0
    for _, _, delta in events:
        cur += delta
        peak = max(peak, cur)
    return peak


def _score_one(floors: int, trades: list[dict], crews: tuple[int, ...], zone: int, rate: float) -> dict:
    """Evaluate one scenario (a crew-count per trade + a zone count) → its metrics."""
    nt = len(trades)
    locations = floors * zone
    takts = [max(1, round(int(t["takt_days"]) / (zone * crews[i]))) for i, t in enumerate(trades)]
    makespan, intervals = _lob(locations, list(takts))
    peak = _peak_crews(intervals, list(crews), nt, locations)
    # cost: conserved base labor + a premium for every 2nd crew + per-extra-zone setup
    base_crew_days = sum(int(t["takt_days"]) * floors for t in trades)
    premium_crew_days = sum(_CREW2_PREMIUM * int(t["takt_days"]) * floors
                            for i, t in enumerate(trades) if crews[i] >= 2)
    setup_crew_days = _ZONE_SETUP_CREWDAYS * (zone - 1) * nt
    total_crew_days = base_crew_days + premium_crew_days + setup_crew_days
    loaded = [{"name": t["name"], "takt_days": max(1, round(int(t["takt_days"]) / (zone * crews[i]))),
               "crews": crews[i]} for i, t in enumerate(trades)]
    doubled = [trades[i]["name"] for i in range(nt) if crews[i] >= 2]
    return {"zones": zone, "crews": list(crews), "crews_doubled": doubled,
            "duration_days": makespan, "duration_weeks": round(makespan / 7, 1),
            "crew_peak": peak, "labor_crew_days": round(total_crew_days, 1),
            "cost": round(total_crew_days * rate), "trades": loaded,
            "is_baseline": zone == 1 and all(c == 1 for c in crews)}


def optimize(base: dict, *, max_crew_trades: int = 3, zone_options: tuple[int, ...] = (1, 2),
             weight_time: float = 0.6, weight_cost: float = 0.4) -> dict[str, Any]:
    """Enumerate the bounded crew/zoning option grid over ``base`` = ``{floors, trades:[{name,takt_days}],
    crew_day_rate?}`` and rank the scenarios.

    Only the slowest ``max_crew_trades`` trades (the bottlenecks) are crew-doubling candidates — throwing
    crews at the bottleneck, ALICE-style — which keeps the grid small and the moves meaningful. Score is a
    min-max-normalised weighted sum of duration + cost (lower is better); the Pareto-optimal scenarios
    (not beaten on *both* time and cost) are flagged, and the best-scoring one is recommended.
    """
    floors = max(1, int(base.get("floors", 1)))
    rate = float(base.get("crew_day_rate") or _DEFAULT_RATE)
    trades = [t for t in (base.get("trades") or []) if t.get("name") and int(t.get("takt_days", 0)) > 0]
    if not trades:
        return {"scenarios": [], "note": "no trades to optimise"}
    nt = len(trades)
    # bottleneck candidates for a 2nd crew: the slowest trades (ties broken by original order → deterministic)
    by_takt = sorted(range(nt), key=lambda i: (-int(trades[i]["takt_days"]), i))
    crew_candidates = set(by_takt[: max(0, min(max_crew_trades, nt))])
    crew_axes = [[1, 2] if i in crew_candidates else [1] for i in range(nt)]

    seen: set[tuple] = set()
    scenarios: list[dict] = []
    for zone in sorted({z for z in zone_options if z >= 1}) or [1]:
        for crews in itertools.product(*crew_axes):
            key = (zone, crews)
            if key in seen:
                continue
            seen.add(key)
            scenarios.append(_score_one(floors, trades, crews, zone, rate))

    # normalise + score (min-max over the enumerated set; degenerate spread → 0)
    durs = [s["duration_days"] for s in scenarios]
    costs = [s["cost"] for s in scenarios]
    dlo, dhi = min(durs), max(durs)
    clo, chi = min(costs), max(costs)
    for s in scenarios:
        nd = (s["duration_days"] - dlo) / (dhi - dlo) if dhi > dlo else 0.0
        nc = (s["cost"] - clo) / (chi - clo) if chi > clo else 0.0
        s["score"] = round(weight_time * nd + weight_cost * nc, 4)
    # Pareto frontier: a scenario is dominated if another is <= on both duration and cost and < on one
    for s in scenarios:
        s["pareto"] = not any(
            o is not s and o["duration_days"] <= s["duration_days"] and o["cost"] <= s["cost"]
            and (o["duration_days"] < s["duration_days"] or o["cost"] < s["cost"])
            for o in scenarios)
    scenarios.sort(key=lambda s: (s["score"], s["duration_days"], s["cost"]))
    for rank, s in enumerate(scenarios, 1):
        s["rank"] = rank

    baseline = next((s for s in scenarios if s["is_baseline"]), None)
    best = scenarios[0]
    saving = None
    if baseline:
        saving = {"days": baseline["duration_days"] - best["duration_days"],
                  "cost": best["cost"] - baseline["cost"],
                  "pct_faster": round(100.0 * (baseline["duration_days"] - best["duration_days"])
                                      / baseline["duration_days"], 1) if baseline["duration_days"] else 0.0}
    return {
        "floors": floors, "trade_count": nt, "crew_day_rate": rate,
        "scenario_count": len(scenarios),
        "weights": {"time": weight_time, "cost": weight_cost},
        "crew_candidates": [trades[i]["name"] for i in sorted(crew_candidates)],
        "recommended": best, "baseline": baseline,
        "recommended_vs_baseline": saving,
        "pareto_count": sum(1 for s in scenarios if s["pareto"]),
        "scenarios": scenarios,
        "note": "Deterministic crew/zoning optioneering over the Takt line-of-balance model. Work content "
                "is conserved; the tradeoff is schedule compression + peak congestion vs. a crew-mobilisation "
                "premium. Recommended = lowest weighted time+cost score; Pareto = not beaten on both. "
                "Phase-1 bounded grid (bottleneck crew-doubling + zoning); widen with sequence permutation.",
    }
