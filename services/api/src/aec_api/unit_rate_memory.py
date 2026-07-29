"""R22-MEMORY ② — what a cost code actually cost **per unit**, across your own projects.

`benchmarking.cost_benchmarks()` already answers "what has code 03 30 00 cost us", cross-project, from
`direct_cost`. That is a cost-code distribution, and it is what anyone with an accounting export can
build. It cannot tell you whether a project was expensive because concrete is dear or because there
was a lot of concrete.

This is the other half the ring called the differentiator: **cost ÷ installed quantity**, keyed to
the codes the field actually reports against. It joins two record types nothing had joined —
`direct_cost` (cost_code, amount) and `production_quantity` (cost_code, quantity, unit) — and neither
engine that owns them looks at the other.

**The rate is computed per project, then distributed.** Not `Σcost ÷ Σquantity` across the portfolio.
That second number is a weighted average wearing a distribution's clothes: one large project would
set the median, and the spread — which is the entire reason to look — would be invented rather than
observed. Both figures are useful and they are different, so the portfolio-wide blend is reported
alongside as `pooled_rate`, labelled, never as the headline.

**Units are grouped, never converted.** m² and SF for one code are two populations. There is no
conversion here on purpose: a silent unit conversion is indistinguishable from a correct number and
gets quoted at somebody. If ONE project records a single cost code under two different units, that
project is **excluded for that code** — its cost cannot be attributed between them, and splitting it
pro-rata would be a guess with a plausible shape.

**Every exclusion is reported, never dropped.** Cost with no quantity, quantity with no cost, and the
mixed-unit case each come back with a count and a reason. A project that could not be measured is not
a project that cost zero — the same rule the entitlement expectation had to be corrected for.

**Known limitation, stated because it moves the number in a knowable direction.** `direct_cost` and
`production_quantity` accumulate independently. A code whose invoices are booked ahead of the field's
quantity reporting reads as expensive, and the reverse reads as cheap. Nothing here can detect that
from the records alone, so the per-project rates are published individually rather than only
summarised — a reader can see an outlier and go and look. `spread_ratio` (high ÷ low) is the cheap
signal: a code where one project is 10× another is usually a reporting-lag artefact, not a price.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import modules as me

#: A distribution needs a population. Below this many projects a code reports its rates but is
#: flagged `below_threshold` rather than summarised, so a single job cannot look like a benchmark.
DEFAULT_MIN_PROJECTS = 3


def _num(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split()).strip()


def _rows(db: Session, key: str, project_ids: set[str] | None) -> list[tuple[str, dict]]:
    """`(project_id, data)` for every record of a module across the caller's projects.

    `benchmarking._rows` exists and is not reused here because it does not select `project_id` — it
    aggregates across the portfolio and never needs to know which project a row came from. A unit
    rate is computed PER PROJECT and then distributed, so the project is the grouping key, not an
    implementation detail. Same tenant scoping: `project_ids=None` means unrestricted (RBAC off or
    admin), otherwise the roll-up is limited to the caller's projects.
    """
    t = me.TABLES.get(key)
    if t is None:
        return []
    stmt = select(t.c.project_id, t.c.data)
    if project_ids is not None:
        stmt = stmt.where(t.c.project_id.in_(project_ids))
    return [(pid, data or {}) for pid, data in db.execute(stmt).all()]


def _pctile(vals: list[float], q: float) -> float:
    """Linear-interpolated percentile over a sorted list — same method as `benchmarking._pctile`, so
    a unit-rate p75 and a cost p75 are computed the same way and can sit beside each other."""
    if not vals:
        return 0.0
    if len(vals) == 1:
        return vals[0]
    pos = q * (len(vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def per_project_rates(costs: list[tuple[str, dict]],
                      quantities: list[tuple[str, dict]]) -> dict[str, Any]:
    """One actual unit rate per (project, cost_code, unit), plus everything that could not produce one.

    Pure — takes the rows rather than a session, so the arithmetic is testable without a database.
    """
    cost_by: dict[tuple[str, str], float] = {}
    for pid, d in costs:
        code = _norm(d.get("cost_code"))
        amt = _num(d.get("amount"))
        if code and amt is not None:
            cost_by[(pid, code)] = cost_by.get((pid, code), 0.0) + amt

    # (project, code) -> {unit: qty}. The nested unit map is what makes the mixed-unit case visible
    # instead of silently summing across units.
    qty_by: dict[tuple[str, str], dict[str, float]] = {}
    for pid, d in quantities:
        code = _norm(d.get("cost_code"))
        qty = _num(d.get("quantity"))
        unit = _norm(d.get("unit")).lower()
        if not code or qty is None or qty <= 0:
            continue
        per_unit = qty_by.setdefault((pid, code), {})
        per_unit[unit or "(no unit)"] = per_unit.get(unit or "(no unit)", 0.0) + qty

    rates: list[dict[str, Any]] = []
    mixed_units: list[dict[str, Any]] = []
    cost_no_qty: list[dict[str, Any]] = []
    qty_no_cost: list[dict[str, Any]] = []

    for (pid, code), units in sorted(qty_by.items()):
        cost = cost_by.get((pid, code))
        if cost is None or cost <= 0:
            qty_no_cost.append({"project_id": pid, "cost_code": code,
                                "units": sorted(units), "quantity": round(sum(units.values()), 4),
                                "reason": "installed quantity recorded but no direct cost posted "
                                          "against this code"})
            continue
        if len(units) > 1:
            mixed_units.append({
                "project_id": pid, "cost_code": code, "units": sorted(units),
                "reason": "one cost code recorded under more than one unit in the same project; the "
                          "cost cannot be attributed between them, and splitting it pro-rata would "
                          "be a guess"})
            continue
        unit, qty = next(iter(units.items()))
        rates.append({"project_id": pid, "cost_code": code, "unit": unit,
                      "cost": round(cost, 2), "quantity": round(qty, 4),
                      "rate": round(cost / qty, 4)})

    for (pid, code), cost in sorted(cost_by.items()):
        if (pid, code) not in qty_by and cost > 0:
            cost_no_qty.append({"project_id": pid, "cost_code": code, "cost": round(cost, 2),
                                "reason": "cost posted but no installed quantity recorded against "
                                          "this code — no rate can be computed"})

    return {"rates": rates, "excluded": {
        "mixed_units": mixed_units, "cost_without_quantity": cost_no_qty,
        "quantity_without_cost": qty_no_cost,
        "note": "excluded rows are reported, never dropped — a project that could not be measured is "
                "not a project that cost zero"}}


def summarise(rates: list[dict[str, Any]], min_projects: int = DEFAULT_MIN_PROJECTS) -> list[dict]:
    """Distribution of the PER-PROJECT rates, grouped by (cost_code, unit)."""
    by_key: dict[tuple[str, str], list[dict]] = {}
    for r in rates:
        by_key.setdefault((r["cost_code"], r["unit"]), []).append(r)

    out = []
    for (code, unit), rows in by_key.items():
        vals = sorted(r["rate"] for r in rows)
        total_cost = sum(r["cost"] for r in rows)
        total_qty = sum(r["quantity"] for r in rows)
        lo, hi = vals[0], vals[-1]
        out.append({
            "cost_code": code, "unit": unit,
            "projects": len(vals),
            "below_threshold": len(vals) < min_projects,
            "low": round(lo, 4), "p25": round(_pctile(vals, 0.25), 4),
            "median": round(_pctile(vals, 0.5), 4), "p75": round(_pctile(vals, 0.75), 4),
            "high": round(hi, 4),
            # The portfolio-wide blend, reported ALONGSIDE and never as the headline. It answers a
            # different question — "what did this code cost us overall per unit" — and one large
            # project sets it.
            "pooled_rate": round(total_cost / total_qty, 4) if total_qty else None,
            "total_cost": round(total_cost, 2), "total_quantity": round(total_qty, 4),
            # high/low. A code where one project is an order of magnitude off another is usually a
            # reporting-lag artefact rather than a price difference — the cheapest signal available
            # for the limitation named in the module docstring.
            "spread_ratio": round(hi / lo, 2) if lo > 0 else None,
            "per_project": sorted(rows, key=lambda r: r["rate"]),
        })
    out.sort(key=lambda c: (-c["projects"], c["cost_code"]))
    return out


def unit_rates(db: Session, *, min_projects: int = DEFAULT_MIN_PROJECTS,
               project_ids: set[str] | None = None) -> dict[str, Any]:
    """Cross-project actual unit rates: `direct_cost` ÷ `production_quantity`, per cost code and unit."""
    joined = per_project_rates(_rows(db, "direct_cost", project_ids),
                               _rows(db, "production_quantity", project_ids))
    codes = summarise(joined["rates"], min_projects)
    usable = [c for c in codes if not c["below_threshold"]]
    return {
        "cost_codes": codes,
        "code_count": len(codes),
        "usable_count": len(usable),
        "min_projects": min_projects,
        "excluded": joined["excluded"],
        "basis": ("each rate is one PROJECT's cost divided by that project's installed quantity for "
                  "one cost code and unit; the distribution is over projects. `pooled_rate` is the "
                  "portfolio-wide blend and answers a different question"),
        "limitation": ("direct_cost and production_quantity accumulate independently, so a code whose "
                       "invoices lead its field quantity reporting reads as expensive and the reverse "
                       "reads as cheap. Check `spread_ratio` and `per_project` before quoting a "
                       "median"),
        "message": (None if usable else
                    f"Not enough history yet — a cost code needs installed quantities AND posted "
                    f"costs on ≥{min_projects} projects before its unit rate is a distribution "
                    f"rather than an anecdote."),
    }
