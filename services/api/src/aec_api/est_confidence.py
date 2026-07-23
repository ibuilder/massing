"""EST-CONFIDENCE (R17 Sprint C) — per-line estimate **maturity + confidence**, so a number carries how much
to trust it, not just its value.

Continuity-of-cost tools score an estimate by *where each line came from* and *how far the design has matured*.
This is pure deterministic scoring over lines we already hold: each line's confidence is a function of its
**source** (a quantity measured off the IFC or a returned quote is firm; a parametric assembly is softer; a
manual allowance is soft) and the **design phase** (CD > DD > SD > concept). Rolled up cost-weighted, it
yields a project **confidence score**, a **"% of budget still assumption-based"** KPI, and the worst-value
least-grounded lines to firm up next.

No model, no LLM — arithmetic over the estimate lines the caller supplies (from the estimate module, a QTO
export, or a manual set).
"""
from __future__ import annotations

from typing import Any

# how firm is a line whose quantity/price came from this source (1.0 = measured/contracted)
_SOURCE_CONF = {"model": 0.95, "measured": 0.95, "ifc": 0.95, "quote": 0.9, "contract": 0.95,
                "assembly": 0.72, "parametric": 0.66, "historical": 0.6, "benchmark": 0.6,
                "manual": 0.5, "allowance": 0.4, "placeholder": 0.3, "": 0.5}
# design maturity modulates confidence (a measured quantity at SD is still less certain than at CD)
_PHASE_CONF = {"cd": 1.0, "gmp": 1.0, "dd": 0.8, "sd": 0.6, "concept": 0.45, "pre": 0.4, "": 0.6}
# sources that are NOT grounded in a measured quantity or a real price → "assumption-based"
_ASSUMPTION = {"assembly", "parametric", "historical", "benchmark", "manual", "allowance", "placeholder", ""}
_HIGH_CONTINGENCY = 20.0   # a line carrying > this % contingency is flagged as priced-for-uncertainty


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _band(conf: float) -> str:
    return "high" if conf >= 0.8 else "medium" if conf >= 0.6 else "low"


def score(lines: list[dict]) -> dict[str, Any]:
    """Score each estimate line's confidence from source + phase → cost-weighted rollup + the
    assumption-based % + the worst-value least-grounded lines."""
    scored = []
    total = 0.0
    conf_cost = 0.0
    assumption_cost = 0.0
    cont_cost = 0.0
    by_band = {"high": 0.0, "medium": 0.0, "low": 0.0}
    by_source: dict[str, float] = {}
    for ln in lines or []:
        if not isinstance(ln, dict):
            continue
        cost = _num(ln.get("cost")) or _num(ln.get("total")) or (_num(ln.get("qty")) * _num(ln.get("unit_cost")))
        src = _norm(ln.get("source"))
        ph = _norm(ln.get("phase"))
        sc = _SOURCE_CONF.get(src, 0.5)
        pc = _PHASE_CONF.get(ph, 0.6)
        conf = round(sc * (0.6 + 0.4 * pc), 3)         # phase modulates the source firmness
        cont = _num(ln.get("contingency_pct"))
        assumption = src in _ASSUMPTION
        band = _band(conf)
        scored.append({
            "description": ln.get("description") or ln.get("item") or "",
            "cost_code": ln.get("cost_code"), "cost": round(cost, 2),
            "source": src or "unspecified", "phase": ph or "unspecified",
            "contingency_pct": cont or None, "confidence": conf, "band": band,
            "assumption_based": assumption, "high_contingency": cont > _HIGH_CONTINGENCY,
        })
        total += cost
        conf_cost += conf * cost
        by_band[band] += cost
        by_source[src or "unspecified"] = by_source.get(src or "unspecified", 0.0) + cost
        if assumption:
            assumption_cost += cost
        if cost:
            cont_cost += cont * cost

    weighted = round(conf_cost / total, 3) if total else 0.0
    # worst = highest-value, least-grounded lines to firm up next (assumption first, then low confidence, then $)
    worst = sorted(scored, key=lambda r: (not r["assumption_based"], r["confidence"], -r["cost"]))[:15]
    return {
        "line_count": len(scored), "total_cost": round(total, 2),
        "confidence": weighted, "band": _band(weighted),
        "pct_assumption_based": round(assumption_cost / total, 3) if total else 0.0,
        "assumption_based_cost": round(assumption_cost, 2),
        "avg_contingency_pct": round(cont_cost / total, 2) if total else 0.0,
        "cost_by_band": {k: round(v, 2) for k, v in by_band.items()},
        "cost_by_source": sorted(({"source": k, "cost": round(v, 2)} for k, v in by_source.items()),
                                 key=lambda r: -r["cost"]),
        "worst_lines": worst,
        "lines": scored,
        "note": "Per-line confidence = source firmness (measured/quote > parametric/assembly > allowance/"
                "manual) modulated by design phase (CD > DD > SD). Cost-weighted to a project confidence + a "
                "'% of budget still assumption-based' KPI; worst_lines are the highest-value least-grounded "
                "lines to firm up next. Bands: ≥0.8 high · 0.6–0.8 medium · <0.6 low.",
    }
