"""Reserve study + capital plan — long-term replacement funding for the operations phase.

The reserve-study discipline (standardized by CAI's National Reserve Study Standards and required
for condo/HOA and institutional assets): inventory the major components (here: the asset register's
install date, expected life, replacement cost), project the 20-30 year replacement schedule, and test
whether the reserve balance + annual contribution stays solvent through the horizon. Deterministic;
capital_plan (CIP) records ride the same projection as explicitly planned items."""
from __future__ import annotations

from datetime import date
from typing import Any

from . import modules as me


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _year(v) -> int | None:
    try:
        return int(str(v)[:4]) if v else None
    except ValueError:
        return None


def study(db, pid: str, horizon_years: int = 25, opening_balance: float = 0.0,
          annual_contribution: float = 0.0, inflation_pct: float = 0.0) -> dict[str, Any]:
    """Replacement schedule + funding adequacy.

    - Every asset with expected_life_years + replacement_cost generates recurring replacement events
      (install year + life, then every life-cycle after) inside the horizon.
    - capital_plan records add their planned_year/cost (skipping completed ones).
    - The reserve balance runs year by year: balance += contribution - outflows, costs escalated by
      inflation_pct from today. First negative year = underfunded; the suggested level contribution
      is the smallest flat annual amount that keeps the balance >= 0 through the horizon.
    """
    this_year = date.today().year
    end_year = this_year + max(1, min(int(horizon_years or 25), 40))
    events: list[dict] = []
    assets = me.list_records(db, "asset_register", pid, limit=10000)
    n_missing = 0
    for a in assets:
        d = _d(a)
        life = int(float(d.get("expected_life_years") or 0) or 0)
        cost = float(d.get("replacement_cost") or 0)
        inst = _year(d.get("install_date"))
        if life <= 0 or cost <= 0:
            n_missing += 1
            continue
        yr = (inst or this_year) + life
        while yr < this_year:                        # already past due — replace now, then cycle
            yr = this_year
            break
        while yr <= end_year:
            events.append({"year": yr, "item": d.get("name") or a.get("ref"), "cost": cost,
                           "source": "asset", "ref": a.get("ref")})
            yr += life
    for c in me.list_records(db, "capital_plan", pid, limit=10000):
        if c.get("workflow_state") == "complete":
            continue
        d = _d(c)
        yr, cost = _year(d.get("planned_year")), float(d.get("cost") or 0)
        if yr and cost > 0 and this_year <= yr <= end_year:
            events.append({"year": yr, "item": d.get("subject") or c.get("ref"), "cost": cost,
                           "source": "cip", "ref": c.get("ref")})

    infl = max(0.0, float(inflation_pct or 0)) / 100.0
    by_year: dict[int, float] = {}
    for e in events:
        esc = e["cost"] * ((1 + infl) ** (e["year"] - this_year))
        e["cost_escalated"] = round(esc, 0)
        by_year[e["year"]] = by_year.get(e["year"], 0.0) + esc

    def run(contrib: float) -> tuple[list[dict], int | None]:
        bal = float(opening_balance or 0)
        rows, first_neg = [], None
        for yr in range(this_year, end_year + 1):
            out = by_year.get(yr, 0.0)
            bal += contrib - out
            if bal < 0 and first_neg is None:
                first_neg = yr
            rows.append({"year": yr, "outflows": round(out, 0), "contribution": round(contrib, 0),
                         "balance": round(bal, 0)})
        return rows, first_neg

    rows, first_neg = run(float(annual_contribution or 0))
    # smallest flat contribution keeping the balance >= 0 (binary search — outflows are fixed)
    lo, hi = 0.0, max(by_year.values(), default=0.0) * len(by_year) + 1
    for _ in range(40):
        mid = (lo + hi) / 2
        if run(mid)[1] is None:
            hi = mid
        else:
            lo = mid
    suggested = round(hi, 0) if by_year else 0.0

    total = sum(e["cost_escalated"] for e in events)
    return {
        "horizon": {"from": this_year, "to": end_year},
        "components": len(assets) - n_missing, "components_missing_data": n_missing,
        "events": sorted(events, key=lambda e: (e["year"], -e["cost"]))[:500],
        "schedule": rows, "total_outflows": round(total, 0),
        "opening_balance": opening_balance, "annual_contribution": annual_contribution,
        "inflation_pct": inflation_pct,
        "first_underfunded_year": first_neg, "adequately_funded": first_neg is None,
        "suggested_level_contribution": suggested,
        "note": "Recurring replacements from the asset register (install + expected life) plus open "
                "capital-plan items; costs escalated at the given inflation rate. Suggested level "
                "contribution is the flat annual amount that keeps the reserve balance non-negative.",
    }
