"""Portfolio prioritization matrix — score and rank projects on weighted criteria so a portfolio
owner can see where to put capital and attention. Scores each project 0–100 on financial return,
on-budget, on-schedule and delivery-risk, then a weighted composite. Pure over the executive-portfolio
row shape (id/name/status/spi/cpi/pct_complete/milestones_late/equity_irr/variance_at_completion...)."""
from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS = {"return": 0.3, "budget": 0.25, "schedule": 0.25, "risk": 0.2}
_STATUS_SCORE = {"on_track": 90.0, "at_risk": 50.0, "behind": 20.0}


def _band(v: float | None, points: list[tuple[float, float]], default: float = 50.0) -> float:
    """Map a value to a 0–100 score via descending (threshold, score) bands."""
    if v is None:
        return default
    for thr, sc in points:
        if v >= thr:
            return sc
    return points[-1][1]


def _return_score(irr: float | None) -> float:
    return _band(irr, [(0.20, 100), (0.15, 82), (0.12, 65), (0.08, 45), (0.0, 20), (-1, 5)])


def _budget_score(cpi: float | None, variance: float | None) -> float:
    if cpi is not None:
        return _band(cpi, [(1.05, 100), (1.0, 88), (0.97, 70), (0.93, 45), (0.88, 25), (-1, 10)])
    # no CPI — fall back to variance-at-completion sign (positive = under budget)
    if variance is None:
        return 50.0
    return 80.0 if variance >= 0 else 35.0


def _schedule_score(spi: float | None, pct: float | None, late: int) -> float:
    base = _band(spi, [(1.02, 100), (1.0, 88), (0.97, 70), (0.93, 45), (0.88, 25), (-1, 10)]) if spi is not None \
        else _band(pct, [(90, 85), (50, 65), (10, 50), (0, 40)])
    return max(0.0, base - min(late, 5) * 6)     # each late milestone shaves the score


def rank(rows: list[dict], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Score + rank projects best-first. Returns each project with its per-criterion scores + weighted
    composite, plus the (normalized) weights used and the top/bottom picks."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    wsum = sum(w.values()) or 1.0
    w = {k: v / wsum for k, v in w.items()}
    scored = []
    for p in rows:
        sc = {
            "return": round(_return_score(p.get("equity_irr")), 1),
            "budget": round(_budget_score(p.get("cpi"), p.get("variance_at_completion")), 1),
            "schedule": round(_schedule_score(p.get("spi"), p.get("pct_complete"), p.get("milestones_late") or 0), 1),
            "risk": _STATUS_SCORE.get(p.get("status"), 50.0),
        }
        composite = round(sum(sc[k] * w[k] for k in w), 1)
        scored.append({"id": p.get("id"), "name": p.get("name"), "status": p.get("status"),
                       "scores": sc, "composite": composite,
                       "equity_irr": p.get("equity_irr"), "gmp": p.get("gmp")})
    scored.sort(key=lambda x: x["composite"], reverse=True)
    for i, p in enumerate(scored, 1):
        p["rank"] = i
    return {
        "weights": {k: round(v, 3) for k, v in w.items()},
        "criteria": ["return", "budget", "schedule", "risk"],
        "projects": scored,
        "top": scored[0] if scored else None,
        "bottom": scored[-1] if len(scored) > 1 else None,
        "note": "Weighted 0–100 prioritization: financial return (equity IRR), on-budget (CPI/variance), "
                "on-schedule (SPI / % complete, penalized for late milestones), delivery-risk (status).",
    }
