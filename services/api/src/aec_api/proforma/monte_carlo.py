"""Monte Carlo risk simulation (Phase 4+) — the probabilistic counterpart to the
deterministic two-variable sensitivity table. Sample probability distributions over chosen
assumption drivers (exit cap, cost overrun, rent, rate, …), solve the deal on each draw, and
aggregate the resulting distribution of output metrics: percentiles (P5…P95), mean/std,
probability of clearing a target (e.g. P[equity IRR ≥ 15%]), and a histogram for charting.

Pure + reproducible: a fixed `seed` gives identical output. Drivers are sampled independently
(no correlation matrix yet). Reuses sensitivity's dotted-path get/set so the same paths work
in both tools, e.g. 'exit.exit_cap', 'operations.potential_rent_annual', 'cost_lines.1.amount'."""
from __future__ import annotations

import copy
from typing import Any

import numpy as np

from .sensitivity import _get_metric, _set_path
from .solve import solve

DEFAULT_METRICS = ["returns.equity_irr", "returns.equity_multiple",
                   "returns.project_irr", "returns.npv"]
_PCTS = (5, 10, 25, 50, 75, 90, 95)


def _sample(rng: np.random.Generator, dist: dict, n: int) -> np.ndarray:
    """Draw n values from a named distribution, optionally clamped to [min, max]."""
    kind = dist.get("kind")
    if kind == "normal":
        x = rng.normal(dist["mean"], dist["std"], n)
    elif kind == "uniform":
        x = rng.uniform(dist["low"], dist["high"], n)
    elif kind == "triangular":
        x = rng.triangular(dist["low"], dist["mode"], dist["high"], n)
    else:
        raise ValueError(f"unknown distribution kind {kind!r}")
    lo, hi = dist.get("min"), dist.get("max")
    if lo is not None or hi is not None:
        x = np.clip(x, -np.inf if lo is None else lo, np.inf if hi is None else hi)
    return x


def _summary(vals: np.ndarray, target: float | None) -> dict:
    vals = vals[~np.isnan(vals)]
    if vals.size == 0:
        return {"n": 0}
    out: dict[str, Any] = {
        "mean": round(float(vals.mean()), 6), "std": round(float(vals.std()), 6),
        "min": round(float(vals.min()), 6), "max": round(float(vals.max()), 6),
        "n": int(vals.size),
    }
    for p, v in zip(_PCTS, np.percentile(vals, _PCTS)):
        out[f"p{p}"] = round(float(v), 6)
    if target is not None:
        out["target"] = target
        out["prob_at_least"] = round(float((vals >= target).mean()), 4)
    counts, edges = np.histogram(vals, bins=20)
    out["histogram"] = {"counts": counts.tolist(), "edges": [round(float(e), 6) for e in edges]}
    return out


def monte_carlo(assumptions: dict, variables: list[dict], iterations: int = 1000,
                seed: int = 42, metrics: list[str] | None = None,
                targets: dict[str, float] | None = None) -> dict:
    """Run `iterations` solves with each driver in `variables` (path + distribution) sampled,
    and summarize the distribution of each metric. `targets` maps a metric → threshold for a
    probability-of-clearing readout."""
    rng = np.random.default_rng(seed)
    metrics = metrics or DEFAULT_METRICS
    targets = targets or {}
    # vectorize the draws up front: one column of samples per driver
    samples = {v["path"]: _sample(rng, v["dist"], iterations) for v in variables}

    collected: dict[str, list[float]] = {m: [] for m in metrics}
    failures = 0
    for i in range(iterations):
        a = copy.deepcopy(assumptions)
        for path, arr in samples.items():
            _set_path(a, path, float(arr[i]))
        try:
            res = solve(a)
        except Exception:
            failures += 1
            continue
        for m in metrics:
            val = _get_metric(res, m)
            collected[m].append(float(val) if val is not None else float("nan"))

    return {
        "iterations": iterations,
        "solved": iterations - failures,
        "failures": failures,
        "seed": seed,
        "variables": [{"path": v["path"], "dist": v["dist"]} for v in variables],
        "metrics": {m: _summary(np.array(vals, dtype=float), targets.get(m))
                    for m, vals in collected.items()},
    }
