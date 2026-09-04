"""RESOURCE-PORTFOLIO — weekly resource demand summed ACROSS projects, the last R22-PIPELINE item.

## What the roadmap asked for, and what it turned out to be

That entry asks for "resource allocation by department", and says it needs a new dimension plus a
portfolio axis. Half of that survives contact with the schema:

* **The dimension already exists and is not called `department`.** `modules/resource_assignment/module.json`
  carries `trade`, labelled **"Trade / discipline"**, and the word "department" appears nowhere in
  the backend except a comment in `rooms.py` and a fire-department scope clause. So a separate
  department axis is a *product decision* about what a department would be that a trade is not —
  field-vs-office for a GC, or Architecture/Structural/MEP for a design firm — not a build task. It
  is raised rather than invented here: a dimension nobody has defined cannot be reported honestly.
* **The portfolio axis is real, and is the half that matters.** `resource_loading.loading` answers
  one project, and **a trade over-committed across three jobs looks comfortable on every one of
  them.** That is the same shape as the cross-project Gantt's finding — a project can look fine
  alone and be critical to the programme — and it is the actual question a resourcing conversation
  starts from: *are my ironworkers promised to two sites in the same week?*

## Fidelity is reported, not blended

`resource_loading._loads` prefers real `resource_assignment` records and **falls back to
`schedule_activity.crew_size`** when a project has none. Those are not the same quality of number:
one is a resourced plan, the other is a crew count on an activity. Summing them into one book-wide
histogram without saying so would let a portfolio built mostly of fallbacks read as though it were
resourced. So every project row carries its `source`, and `fidelity` reports the split — the same
rule the risk heat map applies to an unmeasured cell, one step along: *do not let a lower-fidelity
value wear the costume of a higher-fidelity one.*

A project contributing no loads at all is listed in `projects_without_loads`, never silently absent.
"""
from __future__ import annotations

from typing import Any

DEFAULT_LIMIT = 25
#: Weeks returned around the peak when the caller does not ask for the whole span. A book can span
#: years; the answer to "where am I over-committed" lives in a handful of weeks.
DEFAULT_WEEKS = 26


def portfolio(db: Any, projects: list[tuple[str, str]], *, cap: float | None = None,
              limit: int = DEFAULT_LIMIT, weeks: int = DEFAULT_WEEKS) -> dict[str, Any]:
    """Weekly demand per trade, summed across `projects` — a list of `(id, name)` already scoped to
    the caller. `cap` flags weeks where a single trade's concurrent units across the whole book
    exceed it. Bounded by `limit`; `truncated` says when the sweep did not cover everything."""
    # `_loads` and `_weeks` are `resource_loading`'s own helpers, reached across the module
    # boundary deliberately. Re-implementing the normalisation here is the alternative, and it is
    # the worse one: the fallback rule, the rate-vs-budgeted-cost choice and the Monday-aligned week
    # buckets would then exist twice and could drift, so the portfolio total and the project's own
    # histogram could disagree about the same crew. Same reason the risk heat map calls `board`
    # unchanged. The leading underscore marks them private to the package, not unusable within it.
    from . import resource_loading

    scanned = projects[:max(0, int(limit))]
    rows: list[dict[str, Any]] = []
    without: list[dict[str, str]] = []
    # week -> trade -> {units, cost, projects:{pid}}
    grid: dict[str, dict[str, dict[str, Any]]] = {}
    by_source: dict[str, int] = {}

    for pid, name in scanned:
        try:
            loads, source = resource_loading._loads(db, pid)
        except Exception:  # noqa: BLE001 — one unreadable project must not blank the book
            without.append({"id": pid, "name": name, "reason": "loads could not be read"})
            continue
        if not loads:
            without.append({"id": pid, "name": name, "reason": "no resource assignments or crew-loaded activities"})
            continue
        by_source[source] = by_source.get(source, 0) + 1
        p_units = p_cost = 0.0
        trades: set[str] = set()
        for ld in loads:
            wk_list = resource_loading._weeks(ld["start"], ld["finish"])
            if not wk_list:
                continue
            per_week_cost = (ld["cost"] or 0.0) / len(wk_list)
            for wk in wk_list:
                cell = grid.setdefault(wk.isoformat(), {}).setdefault(
                    ld["trade"], {"units": 0.0, "cost": 0.0, "projects": {}})
                # Units are CONCURRENT: a resource on two projects in one week is demanded twice,
                # which is the entire point of summing across the book rather than per project.
                cell["units"] += ld["units"]
                cell["cost"] += per_week_cost
                cell["projects"][pid] = round(cell["projects"].get(pid, 0.0) + ld["units"], 2)
                trades.add(ld["trade"])
            p_units += ld["units"] * len(wk_list)
            p_cost += ld["cost"] or 0.0
        rows.append({"id": pid, "name": name, "source": source, "loads": len(loads),
                     "trades": sorted(trades), "unit_weeks": round(p_units, 1),
                     "cost": round(p_cost, 2)})

    if not grid:
        return {"available": False,
                "reason": "no project in range has resource assignments or crew-loaded activities",
                "projects": rows, "projects_without_loads": without,
                "weeks": [], "trades": [], "peak": None, "over_allocation": [],
                "fidelity": {"by_source": by_source, "assigned": 0, "fallback": 0},
                "cap": cap, "project_count": len(scanned), "projects_available": len(projects),
                "truncated": len(projects) > len(scanned)}

    all_weeks = sorted(grid)
    # Per-trade peak first, because the window is chosen around the book's busiest week and a
    # window chosen before the peak is known can exclude the answer.
    totals: dict[str, dict[str, Any]] = {}
    for wk, by_trade in grid.items():
        for tr, cell in by_trade.items():
            t = totals.setdefault(tr, {"trade": tr, "peak_units": 0.0, "peak_week": None,
                                       "unit_weeks": 0.0, "cost": 0.0, "projects": set()})
            t["unit_weeks"] += cell["units"]
            t["cost"] += cell["cost"]
            t["projects"].update(cell["projects"])
            if cell["units"] > t["peak_units"]:
                t["peak_units"] = cell["units"]; t["peak_week"] = wk

    book = [(wk, round(sum(c["units"] for c in by_trade.values()), 1))
            for wk, by_trade in ((w, grid[w]) for w in all_weeks)]
    peak_wk, peak_units = max(book, key=lambda x: (x[1], x[0]))
    i = all_weeks.index(peak_wk)
    half = max(1, int(weeks) // 2)
    lo, hi = max(0, i - half), min(len(all_weeks), i + half)
    window = all_weeks[lo:hi]

    over = []
    if cap:
        for wk in all_weeks:
            for tr, cell in sorted(grid[wk].items()):
                if cell["units"] > cap:
                    over.append({"week": wk, "trade": tr, "units": round(cell["units"], 1),
                                 "cap": cap,
                                 # Named, because "who is double-booked" is the actionable half.
                                 "projects": dict(sorted(cell["projects"].items()))})

    trade_rows = sorted(
        ({"trade": t["trade"], "peak_units": round(t["peak_units"], 1), "peak_week": t["peak_week"],
          "unit_weeks": round(t["unit_weeks"], 1), "cost": round(t["cost"], 2),
          "project_count": len(t["projects"]),
          # A trade on more than one project is the one that can be double-booked.
          "cross_project": len(t["projects"]) > 1} for t in totals.values()),
        key=lambda r: (-r["peak_units"], r["trade"]))
    assigned = by_source.get("resource_assignment", 0)
    fallback = by_source.get("schedule_activity.crew_size", 0)
    return {
        "available": True,
        "projects": sorted(rows, key=lambda r: (-r["unit_weeks"], r["name"])),
        "projects_without_loads": without,
        "trades": trade_rows,
        "weeks": [{"week": wk, "total": round(sum(c["units"] for c in grid[wk].values()), 1),
                   "by_trade": {t: round(c["units"], 1) for t, c in sorted(grid[wk].items())}}
                  for wk in window],
        "week_span": {"start": all_weeks[0], "finish": all_weeks[-1], "count": len(all_weeks),
                      "shown": len(window)},
        "peak": {"week": peak_wk, "units": peak_units},
        "over_allocation": over,
        "cap": cap,
        "fidelity": {"by_source": by_source, "assigned": assigned, "fallback": fallback,
                     "note": "`resource_assignment` is a resourced plan; `schedule_activity.crew_size` "
                             "is a crew count on an activity. Both are summed, and the split is "
                             "reported rather than blended — a book of fallbacks must not read as "
                             "a resourced one."},
        "project_count": len(scanned),
        "projects_available": len(projects),
        "truncated": len(projects) > len(scanned),
        "note": "Weekly CONCURRENT demand per trade summed across projects. A trade committed to "
                "several jobs in one week is over-committed even when every project looks "
                "comfortable alone, which is what a per-project view cannot show. `trade` is the "
                "dimension the schema carries (labelled 'Trade / discipline'); there is no "
                "department field, so department reporting is a product decision, not a filter.",
    }
