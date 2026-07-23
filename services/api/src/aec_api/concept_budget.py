"""CONCEPT-BUDGET (R17 Sprint C) — a parametric conceptual budget from **massing inputs** priced against the
firm's **own completed-project history**, not industry averages.

Two deterministic halves:

- **derive_rates(history)** — the firm's completed projects (`{building_type, gfa, actual_cost, year?}`)
  → per-building-type $/area statistics (n · p25 · median · p75), each project's rate optionally escalated
  to a target year at a given annual rate, so old jobs price forward honestly.
- **budget(program, rates)** — a massing program (`{use, gfa, stories?}` — the inputs a blank-IFC massing
  already carries) priced at the own-history **median** with a **p25–p75 range**, falling back to a supplied
  default rate when a use has no history. Every line is tagged with its **source** ("own-history (n=…)" vs
  "default rate"), which composes directly with EST-CONFIDENCE (historical > manual) and BOE-LEDGER.

The front-of-funnel: a defensible first number before a detailed model exists.
"""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _pct(sorted_vals: list[float], p: float) -> float:
    import math
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def derive_rates(history: list[dict], to_year: int | None = None,
                 escalation_pct: float = 0.0) -> dict[str, Any]:
    """Own-history $/area rates per building type, each project escalated to `to_year` at `escalation_pct`."""
    by_type: dict[str, list[float]] = {}
    used = skipped = 0
    for h in history or []:
        if not isinstance(h, dict):
            continue
        gfa = _num(h.get("gfa") or h.get("gfa_sf") or h.get("gfa_m2"))
        cost = _num(h.get("actual_cost") or h.get("cost"))
        t = _norm(h.get("building_type") or h.get("use"))
        if gfa <= 0 or cost <= 0 or not t:
            skipped += 1
            continue
        rate = cost / gfa
        yr = int(_num(h.get("year"))) or None
        if to_year and yr and escalation_pct:
            rate *= (1.0 + escalation_pct / 100.0) ** max(0, to_year - yr)
        by_type.setdefault(t, []).append(rate)
        used += 1
    rates = {}
    for t, vals in by_type.items():
        s = sorted(vals)
        rates[t] = {"n": len(s), "p25": round(_pct(s, 25), 2), "median": round(_pct(s, 50), 2),
                    "p75": round(_pct(s, 75), 2), "min": round(s[0], 2), "max": round(s[-1], 2)}
    return {"projects_used": used, "projects_skipped": skipped, "escalated_to": to_year,
            "escalation_pct": escalation_pct or None, "rates": rates,
            "note": "Own-history $/area rates by building type (each project escalated to the target year "
                    "before aggregation). Price against YOUR completed work, not an industry average."}


def budget(program: list[dict], rates: dict[str, Any], default_rate: float | None = None,
           contingency_pct: float = 0.0) -> dict[str, Any]:
    """Price a massing program at the own-history median (p25–p75 range), defaulting when no history."""
    rate_map = rates.get("rates", rates) if isinstance(rates, dict) else {}
    lines = []
    total = lo = hi = 0.0
    unpriced = 0
    for p in program or []:
        if not isinstance(p, dict):
            continue
        use = _norm(p.get("use") or p.get("building_type"))
        gfa = _num(p.get("gfa") or p.get("gfa_sf") or p.get("gfa_m2"))
        r = rate_map.get(use)
        if r:
            rate, rlo, rhi = r["median"], r["p25"], r["p75"]
            source = f"own-history (n={r['n']})"
        elif default_rate:
            rate = rlo = rhi = _num(default_rate)
            source = "default rate"
        else:
            lines.append({"use": use or "—", "gfa": gfa, "rate": None, "cost": None,
                          "range": None, "source": "UNPRICED — no history and no default"})
            unpriced += 1
            continue
        cost = round(gfa * rate, 0)
        lines.append({"use": use, "gfa": gfa, "rate": round(rate, 2), "cost": cost,
                      "range": {"low": round(gfa * rlo, 0), "high": round(gfa * rhi, 0)},
                      "stories": p.get("stories"), "source": source})
        total += cost
        lo += gfa * rlo
        hi += gfa * rhi
    cont = round(total * contingency_pct / 100.0, 0) if contingency_pct else 0.0
    return {
        "line_count": len(lines), "unpriced": unpriced,
        "subtotal": round(total, 0), "contingency_pct": contingency_pct or None, "contingency": cont or None,
        "total": round(total + cont, 0),
        "range": {"low": round(lo + cont, 0), "high": round(hi + cont, 0)},
        "lines": lines,
        "note": "Conceptual budget: massing program × own-history median rates (p25–p75 range per line), "
                "default rate where a use has no history, UNPRICED surfaced rather than guessed. Every line "
                "carries its source — feed the lines to /estimate/confidence (source=historical) and the "
                "assumptions to /estimate/boe.",
    }
