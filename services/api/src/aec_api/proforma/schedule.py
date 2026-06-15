"""Cost schedule — spread each cost line across construction months (S-curve / linear /
upfront), then sum to a single monthly 'uses' vector the loan draws against."""
from __future__ import annotations

import numpy as np


def scurve_weights(n_months: int, steepness: float = 6.0) -> np.ndarray:
    """Monthly spend weights summing to 1.0, S-shaped (cumulative logistic)."""
    if n_months <= 1:
        return np.ones(max(n_months, 1))
    t = np.linspace(-1, 1, n_months)
    cum = 1.0 / (1.0 + np.exp(-steepness * t))
    cum = (cum - cum[0]) / (cum[-1] - cum[0])
    monthly = np.diff(np.concatenate([[0.0], cum]))
    return monthly / monthly.sum()


def line_weights(n: int, curve: str) -> np.ndarray:
    if n <= 0:
        return np.zeros(0)
    if curve == "scurve":
        return scurve_weights(n)
    if curve == "linear":
        return np.ones(n) / n
    if curve == "upfront":
        w = np.zeros(n); w[0] = 1.0
        return w
    raise ValueError(f"unknown curve {curve!r}")


def spread_line(amount: float, start_month: int, end_month: int, curve: str,
                total_months: int) -> np.ndarray:
    sched = np.zeros(total_months)
    s = max(0, start_month)
    e = min(total_months - 1, end_month)
    if e < s:
        return sched
    sched[s:e + 1] = amount * line_weights(e - s + 1, curve)
    return sched


def monthly_uses(cost_lines: list[dict], total_months: int) -> np.ndarray:
    """Sum every cost line's monthly schedule into one uses vector (length total_months)."""
    total = np.zeros(total_months)
    for ln in cost_lines:
        total += spread_line(
            float(ln.get("amount", 0)),
            int(ln.get("start_month", 0)),
            int(ln.get("end_month", total_months - 1)),
            ln.get("curve", "scurve"),
            total_months,
        )
    return total
