"""SCHED-RISK — Monte Carlo schedule risk over the CPM network (P50/P80 forecasting).

A deterministic CPM date is a single guess; 2026 CM practice expects a **probabilistic** finish:
"P80 completion is Nov 14" beats "the schedule says Oct 30". This simulates the existing FS network
(same field conventions as `schedule_cpm`) with per-activity duration uncertainty:

  · triangular(optimistic, most-likely, pessimistic) per activity — explicit `duration_optimistic` /
    `duration_pessimistic` fields when the scheduler provides them, else default spread factors;
  · optional **PPC calibration**: the team's own Last Planner reliability (PPC %) widens or narrows the
    default pessimistic tail — a 60%-reliable team's P80 honestly drifts further than a 90% team's
    (this is exactly the calibration signal Last Planner theory says PPC carries).

Outputs: P10/P50/P80/P90 project duration (+ dates when the network carries a start date), the
**criticality index** per activity (share of iterations it sat on the critical path — near-critical
work a single deterministic pass hides), the delay-driver ranking, a duration histogram, and the
deterministic-vs-P50 gap. Pure and dependency-free; `seed` makes runs reproducible.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any

from .schedule_cpm import _duration, _preds

# default triangular spread when the scheduler gives no explicit optimistic/pessimistic durations:
# a task rarely beats its estimate by much, and overruns are fatter than underruns.
_DEF_OPT = 0.90
_DEF_PESS = 1.35


def _f(v, default: float | None = None) -> float | None:
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _network(activities: list[dict]) -> tuple[dict[str, dict], list[str], bool, date | None]:
    """Build the FS network once (same conventions as schedule_cpm.compute): nodes with resolved
    predecessor ids in topological order, plus the earliest activity start date if any."""
    nodes: dict[str, dict] = {}
    alias: dict[str, str] = {}
    start_dates: list[date] = []
    for a in activities:
        data = a.get("data") or {}
        nid = a["id"]
        ml = float(_duration(data))
        nodes[nid] = {
            "id": nid, "ref": a.get("ref"), "name": a.get("title") or data.get("name"),
            "ml": ml,
            "opt": _f(data.get("duration_optimistic")) or round(ml * _DEF_OPT, 2),
            "pess": _f(data.get("duration_pessimistic")) or round(ml * _DEF_PESS, 2),
            "pred_tokens": _preds(data.get("predecessors")), "preds": [],
        }
        for key in (a.get("ref"), data.get("wbs")):
            if key:
                alias[str(key).strip()] = nid
        s = data.get("start")
        if s:
            try:
                start_dates.append(date.fromisoformat(str(s)[:10]))
            except ValueError:
                pass
    for n in nodes.values():
        n["preds"] = [alias[t] for t in n["pred_tokens"] if t in alias and alias[t] != n["id"]]
        # sanity: opt <= ml <= pess
        n["opt"] = min(n["opt"], n["ml"])
        n["pess"] = max(n["pess"], n["ml"])

    indeg = {nid: len(n["preds"]) for nid, n in nodes.items()}
    queue = [nid for nid, d in indeg.items() if d == 0]
    order: list[str] = []
    succ: dict[str, list[str]] = {nid: [] for nid in nodes}
    for nid, n in nodes.items():
        for p in n["preds"]:
            succ[p].append(nid)
    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for s2 in succ[nid]:
            indeg[s2] -= 1
            if indeg[s2] == 0:
                queue.append(s2)
    cyclic = len(order) != len(nodes)
    return nodes, order, cyclic, (min(start_dates) if start_dates else None)


def _pctile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return round(sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo), 1)


def simulate(activities: list[dict], iterations: int = 1000, seed: int | None = None,
             ppc_pct: float | None = None) -> dict[str, Any]:
    """Run the Monte Carlo. `ppc_pct` (the team's Last Planner PPC) calibrates the default pessimistic
    tail: 80% PPC keeps the default; every point below widens it (an unreliable plan slips more), every
    point above narrows it — explicit per-activity optimistic/pessimistic fields are never overridden."""
    nodes, order, cyclic, start0 = _network(activities)
    if not nodes:
        return {"iterations": 0, "message": "No schedule activities yet — add a schedule to simulate."}
    if cyclic:
        return {"iterations": 0, "has_cycle": True,
                "message": "The dependency network has a cycle — fix predecessors before simulating."}

    # PPC calibration of the DEFAULT tail (explicit fields untouched): 80% is the Last Planner target.
    tail_scale = 1.0
    if ppc_pct is not None:
        tail_scale = max(0.5, min(2.0, 1.0 + (80.0 - float(ppc_pct)) / 50.0))
    for n in nodes.values():
        if n["pess"] == round(n["ml"] * _DEF_PESS, 2):        # default tail → calibrate it
            n["pess"] = max(n["ml"], round(n["ml"] * (1.0 + (_DEF_PESS - 1.0) * tail_scale), 2))

    iterations = max(100, min(int(iterations or 1000), 5000))
    rng = random.Random(seed)
    durations: list[float] = []
    crit_hits: dict[str, int] = dict.fromkeys(nodes, 0)
    slip_sum: dict[str, float] = dict.fromkeys(nodes, 0.0)

    for _ in range(iterations):
        ef: dict[str, float] = {}
        driver: dict[str, str | None] = {}                    # who set my early start (critical pred)
        sampled: dict[str, float] = {}
        for nid in order:
            n = nodes[nid]
            d = rng.triangular(n["opt"], n["pess"], n["ml"]) if n["pess"] > n["opt"] else n["ml"]
            sampled[nid] = d
            es, drv = 0.0, None
            for p in n["preds"]:
                if ef[p] > es:
                    es, drv = ef[p], p
            ef[nid] = es + d
            driver[nid] = drv
        total = max(ef.values())
        durations.append(total)
        # walk the critical chain back from the finishing activity
        tail_id = max(ef, key=lambda k: ef[k])
        node: str | None = tail_id
        while node is not None:
            crit_hits[node] += 1
            slip_sum[node] += max(0.0, sampled[node] - nodes[node]["ml"])
            node = driver[node]

    durations.sort()
    det_total = _deterministic_total(nodes, order)
    p50, p80 = _pctile(durations, 0.5), _pctile(durations, 0.8)
    drivers = sorted(
        ({"id": nid, "ref": nodes[nid]["ref"], "name": nodes[nid]["name"],
          "criticality_pct": round(crit_hits[nid] / iterations * 100, 1),
          "mean_slip_days": round(slip_sum[nid] / iterations, 2)}
         for nid in nodes),
        key=lambda r: (-r["criticality_pct"], -r["mean_slip_days"]))
    lo, hi = durations[0], durations[-1]
    bins = 12
    width = max((hi - lo) / bins, 0.001)
    hist = [{"from": round(lo + i * width, 1), "to": round(lo + (i + 1) * width, 1), "count": 0}
            for i in range(bins)]
    for d in durations:
        hist[min(bins - 1, int((d - lo) / width))]["count"] += 1

    out: dict[str, Any] = {
        "method": "Monte Carlo over the FS network — triangular(optimistic, most-likely, pessimistic)",
        "iterations": iterations, "activity_count": len(nodes), "seed": seed,
        "ppc_calibration_pct": ppc_pct, "default_spread": {"optimistic": _DEF_OPT, "pessimistic": _DEF_PESS},
        "deterministic_days": round(det_total, 1),
        "p10_days": _pctile(durations, 0.1), "p50_days": p50, "p80_days": p80,
        "p90_days": _pctile(durations, 0.9),
        "p50_vs_deterministic_days": round(p50 - det_total, 1),
        "buffer_p80_days": round(p80 - det_total, 1),
        "on_time_probability_pct": round(
            sum(1 for d in durations if d <= det_total + 1e-9) / iterations * 100, 1),
        "delay_drivers": drivers[:10], "histogram": hist,
        "note": ("The P80 buffer is the contingency a reliable commitment needs on top of the "
                 "deterministic CPM date. Criticality % = share of iterations an activity sat on the "
                 "critical path — near-critical work a single CPM pass hides."),
    }
    if start0:
        out["start_date"] = start0.isoformat()
        for k in ("deterministic", "p50", "p80", "p90"):
            days = out[f"{k}_days"] if k != "deterministic" else out["deterministic_days"]
            out[f"{k}_finish"] = (start0 + timedelta(days=round(days))).isoformat()
    return out


def _deterministic_total(nodes: dict[str, dict], order: list[str]) -> float:
    ef: dict[str, float] = {}
    for nid in order:
        n = nodes[nid]
        es = max((ef[p] for p in n["preds"]), default=0.0)
        ef[nid] = es + n["ml"]
    return max(ef.values()) if ef else 0.0
