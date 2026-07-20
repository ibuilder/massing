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
_OVERLAP_PREMIUM = 0.10         # fast-tracking carries a rework-risk premium (× the overlap fraction)
_MAX_REORDER = 4                # cap on order-flexible trades permuted (beyond this → identity only)
_MAX_SEQUENCES = 6              # cap on sequence variants kept (identity always first)
_MAX_SCENARIOS = 800            # hard cap on the enumerated grid (bounded; truncation is reported)
_MAX_FLOORS = 2000              # value clamp: a scenario allocates floors×zone cells, so bound floors…
_MAX_ZONES = 24                 # …and zones, before any grid enumeration (keeps allocation sane)


def _takt_days(v: Any) -> int:
    """Coerce a caller-supplied ``takt_days`` (int, float, or numeric string) to a non-negative int;
    a null / non-numeric value yields 0 so the trade is dropped rather than raising."""
    try:
        return max(0, int(float(v)))
    except (TypeError, ValueError):
        return 0


def _lob(locations: int, takts: list[int], overlap: float = 0.0) -> tuple[int, list[tuple[float, float]]]:
    """Line-of-balance recurrence (same rule as ``takt.plan``): a trade can't start a location until it
    finished the previous location *and* the preceding trade is far enough along on this location. With
    ``overlap`` (fast-tracking), the successor may start when the predecessor is ``1-overlap`` complete on a
    location — but never *finishes* a location before its predecessor does. ``overlap=0`` reproduces the
    strict finish-to-start line-of-balance exactly. Returns the makespan + the flat (start, finish) intervals
    (one per trade × location, in the given trade/sequence order)."""
    nt = len(takts)
    finish = [[0.0] * locations for _ in range(nt)]
    start = [[0.0] * locations for _ in range(nt)]
    for i in range(nt):
        td = takts[i]
        for f in range(locations):
            prev_loc = finish[i][f - 1] if f > 0 else 0.0
            if i == 0:
                prev_trade = 0.0
            elif overlap <= 0:
                prev_trade = finish[i - 1][f]                    # strict FS — exact phase-1 behaviour
            else:
                prev_trade = start[i - 1][f] + takts[i - 1] * (1.0 - overlap)
            s = max(prev_loc, prev_trade)
            start[i][f] = s
            fin = s + td
            if i > 0 and overlap > 0:
                fin = max(fin, finish[i - 1][f])                 # can't finish a location before predecessor
            finish[i][f] = fin
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


def _sequence_variants(nt: int, reorderable: list[int]) -> tuple[list[tuple[int, ...]], bool]:
    """Sequence orders to try: always the identity, plus permutations of the ``reorderable`` trades placed
    back into their own slots (fixed trades stay put). Bounded — beyond ``_MAX_REORDER`` flexible trades we
    keep the identity only (returns ``truncated=True``); the kept set is capped at ``_MAX_SEQUENCES``."""
    identity = tuple(range(nt))
    if not (2 <= len(reorderable) <= _MAX_REORDER):
        return [identity], len(reorderable) > _MAX_REORDER
    out: list[tuple[int, ...]] = [identity]
    seen = {identity}
    for perm in itertools.permutations(reorderable):
        order = list(range(nt))
        for slot, val in zip(reorderable, perm):
            order[slot] = val
        t = tuple(order)
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:_MAX_SEQUENCES], False


def _score_one(floors: int, trades: list[dict], crews: tuple[int, ...], zone: int, rate: float,
               overlap: float = 0.0, order: tuple[int, ...] | None = None) -> dict:
    """Evaluate one scenario (crew-count per trade + zone count + fast-track overlap + execution order)."""
    nt = len(trades)
    locations = floors * zone
    order = order if order is not None else tuple(range(nt))
    per_takt = [max(1, round(int(t["takt_days"]) / (zone * crews[i]))) for i, t in enumerate(trades)]
    seq_takts = [per_takt[j] for j in order]                     # takts in execution order
    seq_weights = [crews[j] for j in order]
    makespan, intervals = _lob(locations, seq_takts, overlap)
    peak = _peak_crews(intervals, seq_weights, nt, locations)
    # cost: conserved base labor + a premium for every 2nd crew + per-extra-zone setup + fast-track risk
    base_crew_days = sum(int(t["takt_days"]) * floors for t in trades)
    premium_crew_days = sum(_CREW2_PREMIUM * int(t["takt_days"]) * floors
                            for i, t in enumerate(trades) if crews[i] >= 2)
    setup_crew_days = _ZONE_SETUP_CREWDAYS * (zone - 1) * nt
    overlap_crew_days = _OVERLAP_PREMIUM * overlap * base_crew_days
    total_crew_days = base_crew_days + premium_crew_days + setup_crew_days + overlap_crew_days
    loaded = [{"name": trades[j]["name"], "takt_days": per_takt[j], "crews": crews[j]} for j in order]
    doubled = [trades[i]["name"] for i in range(nt) if crews[i] >= 2]
    is_identity = order == tuple(range(nt))
    return {"zones": zone, "crews": list(crews), "crews_doubled": doubled,
            "overlap": round(overlap, 3), "sequence": [trades[j]["name"] for j in order],
            "resequenced": not is_identity,
            "duration_days": makespan, "duration_weeks": round(makespan / 7, 1),
            "crew_peak": peak, "labor_crew_days": round(total_crew_days, 1),
            "cost": round(total_crew_days * rate), "trades": loaded,
            "is_baseline": zone == 1 and all(c == 1 for c in crews) and overlap == 0 and is_identity}


def optimize(base: dict, *, max_crew_trades: int = 3, zone_options: tuple[int, ...] = (1, 2),
             overlap_options: tuple[float, ...] = (0.0,), permute_sequence: bool = False,
             weight_time: float = 0.6, weight_cost: float = 0.4) -> dict[str, Any]:
    """Enumerate the bounded option grid over ``base`` = ``{floors, trades:[{name,takt_days,reorderable?}],
    crew_day_rate?}`` and rank the scenarios.

    Levers: **crews** — only the slowest ``max_crew_trades`` trades (the bottlenecks) are crew-doubling
    candidates; **zoning** — ``zone_options`` work-face splits; **fast-track** — ``overlap_options`` (a
    successor starts when its predecessor is ``1-overlap`` done, at a rework-risk premium); **sequence** —
    when ``permute_sequence`` is set, trades flagged ``reorderable`` are permuted among their slots (bounded).
    Score is a min-max-normalised weighted sum of duration + cost (lower is better); the Pareto-optimal
    scenarios (not beaten on *both* time and cost) are flagged, and the best-scoring one is recommended.
    The enumerated grid is hard-capped at ``_MAX_SCENARIOS`` (truncation is reported, never silent).
    """
    try:
        floors = max(1, min(int(base.get("floors", 1)), _MAX_FLOORS))
    except (TypeError, ValueError):
        floors = 1
    rate = float(base.get("crew_day_rate") or _DEFAULT_RATE)
    # normalise trades up front — a caller-supplied trade with a null / non-numeric / non-int takt_days is
    # coerced or dropped (never a 500), and every downstream read gets a real int takt_days.
    trades = []
    for t in (base.get("trades") or []):
        if not isinstance(t, dict) or not t.get("name"):
            continue
        td = _takt_days(t.get("takt_days"))
        if td > 0:
            trades.append({**t, "takt_days": td})
    if not trades:
        return {"scenarios": [], "note": "no trades to optimise"}
    nt = len(trades)
    # bottleneck candidates for a 2nd crew: the slowest trades (ties broken by original order → deterministic)
    by_takt = sorted(range(nt), key=lambda i: (-int(trades[i]["takt_days"]), i))
    crew_candidates = set(by_takt[: max(0, min(max_crew_trades, nt))])
    crew_axes = [[1, 2] if i in crew_candidates else [1] for i in range(nt)]
    zones = sorted({min(int(z), _MAX_ZONES) for z in zone_options if z >= 1}) or [1]
    overlaps = sorted({round(min(0.9, max(0.0, o)), 3) for o in overlap_options}) or [0.0]
    reorderable = [i for i, t in enumerate(trades) if t.get("reorderable")] if permute_sequence else []
    sequences, seq_truncated = _sequence_variants(nt, reorderable)

    seen: set[tuple] = set()
    scenarios: list[dict] = []
    truncated = False
    for zone in zones:
        for overlap in overlaps:
            for order in sequences:
                for crews in itertools.product(*crew_axes):
                    key = (zone, crews, overlap, order)
                    if key in seen:
                        continue
                    if len(scenarios) >= _MAX_SCENARIOS:
                        truncated = True
                        break
                    seen.add(key)
                    scenarios.append(_score_one(floors, trades, crews, zone, rate, overlap, order))
                if truncated:
                    break
            if truncated:
                break
        if truncated:
            break

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
        "levers": {"zones": zones, "overlaps": overlaps, "sequence_variants": len(sequences),
                   "crew_candidates": [trades[i]["name"] for i in sorted(crew_candidates)]},
        "crew_candidates": [trades[i]["name"] for i in sorted(crew_candidates)],
        "recommended": best, "baseline": baseline,
        "recommended_vs_baseline": saving,
        "pareto_count": sum(1 for s in scenarios if s["pareto"]),
        "truncated": truncated or seq_truncated,
        "scenarios": scenarios,
        "note": "Deterministic optioneering over the Takt line-of-balance model — levers: bottleneck "
                "crew-doubling, work-face zoning, fast-track overlap, and (opt-in) sequence permutation of "
                "order-flexible trades. Work content is conserved; the tradeoff is schedule compression + "
                "peak congestion vs. crew-mobilisation + fast-track-rework premiums. Recommended = lowest "
                "weighted time+cost score; Pareto = not beaten on both. "
                + ("Grid truncated at the scenario cap — widen the levers deliberately." if
                   (truncated or seq_truncated) else "Full bounded grid enumerated."),
    }
