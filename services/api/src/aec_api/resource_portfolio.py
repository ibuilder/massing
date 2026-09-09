"""RESOURCE-PORTFOLIO — weekly resource demand summed ACROSS projects, the last R22-PIPELINE item.

## What the roadmap asked for, and what it turned out to be

That entry asks for "resource allocation by department", and says it needs a new dimension plus a
portfolio axis. Half of that survives contact with the schema:

* **The dimension already exists and is not called `department`.** `modules/resource_assignment/module.json`
  carries `trade`, labelled **"Trade / discipline"**, and the word "department" appears nowhere in
  the backend except a comment in `rooms.py` and a fire-department scope clause.

  **ANSWERED 2026-09-09, and the answer is that "department" is not a field — it is a GROUPING the
  firm declares.** Checked against how the industry's own tools model it rather than decided here:
  Deltek Vantagepoint, the dominant AEC ERP, does not ship a `department` dimension at all. It gives
  a configurable organisation breakdown of up to five levels whose labels the firm chooses — the
  documented examples being *company, region, branch, discipline, principal*. The axis is
  firm-defined, not vendor-defined, and that is the whole finding.

  It also resolves the two readings the entry could not choose between, because they are different
  POPULATIONS rather than different labels. For a **general contractor**, departments are the
  office functions — preconstruction, estimating, operations, safety, business development — and
  the people in them are salaried staff, not the field trades `resource_assignment` records; a
  department axis over field labour has no members. For a **design firm**, the axis is *discipline*
  — Architecture, Structural, MEP, Civil — which is already exactly what this field holds, since
  the schema labels it "Trade / **discipline**".

  So no field is added. `portfolio` takes an optional `groups` mapping — a caller-declared name to
  the trades it covers — and rolls the book up by it. That serves the GC (*Structure*, *MEP*,
  *Finishes* over real trades) and the design firm (discipline is already the trade value) without
  inventing a dimension nobody has defined, which is what the entry rightly refused to do.
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

import re
from typing import Any

DEFAULT_LIMIT = 25
#: Weeks returned around the peak when the caller does not ask for the whole span. A book can span
#: years; the answer to "where am I over-committed" lives in a handful of weeks.
DEFAULT_WEEKS = 26


class GroupingError(ValueError):
    """A declared grouping that cannot be rolled up honestly. Raised BEFORE any aggregation."""


def check_groups(groups: dict[str, list[str]]) -> dict[str, list[str]]:
    """Normalise a declared grouping, refusing the shapes whose totals would be a lie.

    Separate from the rollup on purpose, so a mutation can be aimed at the RULE rather than at the
    arithmetic that consumes it — the lesson `test_audit_commit` had to learn about analysers that
    find and classify in one pass.

    Refused rather than resolved:

    * **A trade in two groups.** The group totals would then sum to more than the book, and there is
      no correct answer for which group owns the double-booked crew — picking one silently
      understates the other. Same shape as the responsibility rename that merged two roles onto one
      cell, and refused for the same reason.
    * **An empty group.** A name with no trades reports a confident zero, which is the unmeasured
      cell wearing a measured cell's costume — the rule the risk heat map already applies.
    """
    out: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for name, trades in groups.items():
        name = str(name).strip()
        if not name:
            raise GroupingError("a group needs a name")
        clean = sorted({str(t).strip() for t in trades if str(t).strip()})
        if not clean:
            raise GroupingError(f"group {name!r} names no trades — an empty group reports a "
                                "confident zero rather than nothing")
        for t in clean:
            if t in seen and seen[t] != name:
                raise GroupingError(
                    f"trade {t!r} is in both {seen[t]!r} and {name!r} — the group totals would then "
                    "sum to more than the book, and neither group is the right one to charge it to")
            seen[t] = name
        out[name] = clean
    return out


def parse_groups(specs: list[str]) -> dict[str, list[str]]:
    """Parse `["Structure:ironworker,concrete", "MEP:electrician"]` into the mapping `portfolio`
    takes. One grammar, two callers — the `?group=` query parameter and the install-wide default an
    admin configures — because a grouping that parses in the URL and not in the settings box (or the
    reverse) is a difference nobody would think to test for.

    Malformed input raises `GroupingError` like every other refusal here, so a caller has one
    exception to catch rather than one per stage.
    """
    out: dict[str, list[str]] = {}
    for spec in specs:
        name, sep, trades = str(spec).partition(":")
        if not sep:
            raise GroupingError(f"group {spec!r} must be 'Name:trade1,trade2'")
        out.setdefault(name.strip(), []).extend(trades.split(","))
    return out


def parse_group_config(raw: str) -> dict[str, list[str]]:
    """The same grammar from one configured string: groups separated by `;` or newlines.

    `Structure:ironworker,concrete; MEP:electrician,plumber`

    Returns `{}` for an empty/blank setting — an unconfigured install is not an error.
    """
    specs = [s.strip() for s in re.split(r"[;\n]", raw or "") if s.strip()]
    return check_groups(parse_groups(specs)) if specs else {}


def portfolio(db: Any, projects: list[tuple[str, str]], *, cap: float | None = None,
              limit: int = DEFAULT_LIMIT, weeks: int = DEFAULT_WEEKS,
              groups: dict[str, list[str]] | None = None,
              group_cap: float | None = None) -> dict[str, Any]:
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

    # BEFORE the sweep: a grouping that cannot be rolled up honestly must cost nothing, and a
    # refusal after scanning 25 projects is the same answer an hour later.
    grouping = check_groups(groups) if groups else {}

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
                "groups": [], "ungrouped_trades": [], "unknown_trades": {},
                "group_cap": group_cap, "group_over_allocation": [],
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

    # --- group rollup ---------------------------------------------------------------------------
    # Computed from `grid`, never from `trade_rows`, for the reason the risk heat map calls `board`
    # unchanged: a second aggregation of the same numbers is a second thing that can disagree.
    group_rows: list[dict[str, Any]] = []
    ungrouped: list[str] = []
    unknown: dict[str, list[str]] = {}
    group_over: list[dict[str, Any]] = []
    if grouping:
        owner = {t: g for g, ts in grouping.items() for t in ts}
        in_book = set(totals)
        # A trade the book has and no group claims. Reported, because group totals that quietly
        # omit it understate the book while looking complete.
        ungrouped = sorted(in_book - set(owner))
        # ...and the mirror: a trade a group declares that the book does not have. A typo in a
        # grouping would otherwise shrink a group silently, which is the same defect pointed the
        # other way.
        for g, ts in grouping.items():
            missing = sorted(t for t in ts if t not in in_book)
            if missing:
                unknown[g] = missing

        gweeks: dict[str, dict[str, dict[str, Any]]] = {}
        for wk, by_trade in grid.items():
            for tr, cell in by_trade.items():
                g = owner.get(tr)
                if g is None:
                    continue
                acc = gweeks.setdefault(g, {}).setdefault(
                    wk, {"units": 0.0, "cost": 0.0, "projects": {}})
                acc["units"] += cell["units"]
                acc["cost"] += cell["cost"]
                for pid_, u in cell["projects"].items():
                    acc["projects"][pid_] = round(acc["projects"].get(pid_, 0.0) + u, 2)

        for g in grouping:
            per_week = gweeks.get(g, {})
            if not per_week:
                # Declared, present in the response, and explicitly carrying NO counts — the
                # unmeasured-cell rule again: a group whose trades are all absent must not read as
                # a group with zero demand.
                group_rows.append({"group": g, "trades": grouping[g], "state": "no_demand",
                                   "reason": "no trade in this group appears in the book"})
                continue
            pk_wk, pk = max(((w, c["units"]) for w, c in per_week.items()),
                            key=lambda x: (x[1], x[0]))
            projs: set[str] = set()
            for c in per_week.values():
                projs.update(c["projects"])
            group_rows.append({
                "group": g, "state": "measured", "trades": grouping[g],
                "peak_units": round(pk, 1), "peak_week": pk_wk,
                "unit_weeks": round(sum(c["units"] for c in per_week.values()), 1),
                "cost": round(sum(c["cost"] for c in per_week.values()), 2),
                "project_count": len(projs), "cross_project": len(projs) > 1})
            if group_cap:
                for wk in sorted(per_week):
                    c = per_week[wk]
                    if c["units"] > group_cap:
                        group_over.append({"week": wk, "group": g, "units": round(c["units"], 1),
                                           "cap": group_cap,
                                           "projects": dict(sorted(c["projects"].items()))})
        group_rows.sort(key=lambda r: (-(r.get("peak_units") or 0.0), r["group"]))
        group_over.sort(key=lambda r: (r["week"], r["group"]))

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
        # The "by department" half, as a grouping the caller declares rather than a field nobody
        # defined. `ungrouped` and `unknown_trades` are what stop the rollup from looking complete
        # when it is not: the first is demand no group claimed, the second is a group naming a trade
        # the book does not have.
        "groups": group_rows,
        "ungrouped_trades": ungrouped,
        "unknown_trades": unknown,
        "group_cap": group_cap,
        "group_over_allocation": group_over,
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
