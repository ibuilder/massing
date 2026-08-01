"""R31-PIPELINE-ALLOCATE — allocate constrained capital **across** the pipeline, not within one deal.

We already score options *inside* a project (`option_score`, `schedule_options`) and *report* across
projects (`fca.portfolio`, `benchmarking`). The missing step was the decision itself: given N candidate
projects with a cost and a value, and a capital constraint, **which subset**.

`fca.portfolio` ranks projects worst-first and its note says *"fund those first"*. That is a greedy
heuristic, and greedy is the thing that is *nearly* right on a knapsack: it is quietly wrong whenever
one large high-ratio project crowds out two smaller ones that together beat it. **Ranking is not
selection**, and the distance between them is this module.

## The refusal that defines this module

**You cannot fund 60% of a building.** The single most likely way a capital allocator ships a
confidently wrong number is by relaxing the integer problem to a linear one: the LP converges, returns
a plausible total, and nothing in the output says the answer was fractional. So the solve is an exact
**integer** program (`scipy.optimize.milp`, `integrality=1`) and every failure mode is reported rather
than smoothed:

* no solver available            -> `unavailable`, never a silent greedy fallback
* the optimiser does not converge -> `no_solution` with the solver's own status text
* a candidate that cannot fit even alone -> named as `never_fundable`, not silently dropped
* a candidate with no value stated -> **refused**, because assuming zero silently guarantees it is
  never selected, and assuming anything else invents a return

## Why the greedy answer is reported alongside the optimal one

Two reasons, and the second is the important one:

1. a capital committee currently reasons with `fca.portfolio`'s worst-first note, so the comparison
   makes the change in decision legible rather than asking them to trust a black box;
2. it is a **self-check on this module**. If the optimum never beats greedy across real inputs, either
   the inputs lack the crowding-out shape this exists for, or the solver is not doing what we think.
   **A difference of zero is suspicious, not reassuring.**

Pure arithmetic over candidate rows the caller supplies — deterministic and unit-testable. `scipy` is
already a dependency (`requirements.in:27`, used today only for `scipy.spatial.cKDTree`), so no new
package is introduced.
"""
from __future__ import annotations

from typing import Any

STATUS_OK = "allocated"
STATUS_UNAVAILABLE = "unavailable"
STATUS_NO_SOLUTION = "no_solution"
STATUS_NOTHING_FEASIBLE = "nothing_feasible"

#: What each status asserts, carried in the payload rather than left for a reader to infer.
STATUS_MEANING = {
    STATUS_OK: "an exact integer optimum was found under the capital constraint",
    STATUS_UNAVAILABLE: "no integer solver is available — NO allocation was computed. This is the "
                        "absence of an answer, not a recommendation to fund nothing",
    STATUS_NO_SOLUTION: "the solver ran and did not reach an optimal integer solution; the selection "
                        "is withheld rather than reported from a relaxed or partial solve",
    STATUS_NOTHING_FEASIBLE: "no candidate fits the constraint at all — every one costs more than the "
                             "capital available",
}

SOLVER_MISSING = ("scipy.optimize.milp is unavailable, so no integer allocation was computed. A "
                  "greedy ranking is NOT substituted: it is a different decision and would carry "
                  "this function's authority without its guarantee.")


def _num(v: Any) -> float | None:
    """Strictly numeric and finite. `bool` is rejected before `int` — `True` is not a cost of 1."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _prepare(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split candidates into usable and refused, naming the reason for each refusal.

    A candidate is refused rather than defaulted. Assuming a missing value is 0 silently guarantees it
    is never funded — an invisible decision made by a `.get()` rather than by the committee."""
    usable: list[dict] = []
    refused: list[dict] = []
    for i, c in enumerate(candidates or []):
        d = c.get("data") or c
        cid = str(d.get("id") or d.get("project_id") or d.get("name") or f"#{i}")
        cost, value = _num(d.get("cost")), _num(d.get("value"))
        if cost is None:
            refused.append({"id": cid, "reason": "cost is not a finite number"})
        elif cost < 0:
            refused.append({"id": cid, "reason": "cost is negative"})
        elif value is None:
            refused.append({"id": cid, "reason": "no value stated — refused rather than assumed zero, "
                                                 "which would silently guarantee it is never funded"})
        else:
            usable.append({"id": cid, "name": d.get("name") or cid, "cost": cost, "value": value})
    return usable, refused


def greedy(usable: list[dict], capital: float) -> dict[str, Any]:
    """The value-per-cost ranking a committee reasons with today — reported for comparison, never as
    the answer. Zero-cost items rank first: they add value for nothing."""
    ranked = sorted(usable, key=lambda c: (-(c["value"] / c["cost"]) if c["cost"] > 0 else float("-inf"),
                                           c["cost"]))
    picked, spent = [], 0.0
    for c in ranked:
        if spent + c["cost"] <= capital:
            picked.append(c["id"])
            spent += c["cost"]
    return {"selected": picked, "cost": round(spent, 2),
            "value": round(sum(c["value"] for c in usable if c["id"] in set(picked)), 2)}


def allocate(candidates: list[dict], capital: float) -> dict[str, Any]:
    """Choose the subset of `candidates` maximising total value within `capital`.

    Each candidate: `{id|project_id|name, cost, value}`. `value` is whatever the caller is maximising
    — NPV, profit, risk-adjusted return — and this function does not care which, only that it was
    **stated**. Returns the selected set, what it displaced and why, and the greedy comparison."""
    cap = _num(capital)
    if cap is None or cap < 0:
        raise ValueError("capital must be a finite, non-negative number")

    usable, refused = _prepare(candidates)
    # A candidate too expensive to fund even with the whole budget can never be selected. Naming it
    # separates "the optimiser rejected this on merit" from "it was never eligible" — different facts,
    # and only the second is a data problem the caller can fix.
    never = [c for c in usable if c["cost"] > cap]
    eligible = [c for c in usable if c["cost"] <= cap]

    base = {"capital": round(cap, 2), "candidates": len(candidates or []),
            "refused": refused, "status_meaning": STATUS_MEANING,
            "never_fundable": [{"id": c["id"], "cost": c["cost"],
                                "over_by": round(c["cost"] - cap, 2)} for c in never]}

    if not eligible:
        return {**base, "status": STATUS_NOTHING_FEASIBLE, "selected": [], "displaced": [],
                "total_cost": 0.0, "total_value": 0.0, "slack": round(cap, 2), "greedy": None}

    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
    except Exception:                                   # noqa: BLE001 — absence is reported, not filled
        return {**base, "status": STATUS_UNAVAILABLE, "selected": None, "displaced": None,
                "total_cost": None, "total_value": None, "slack": None,
                "greedy": None, "note": SOLVER_MISSING}

    costs = np.array([c["cost"] for c in eligible], dtype=float)
    values = np.array([c["value"] for c in eligible], dtype=float)
    res = milp(
        c=-values,                                      # milp minimises; maximise value by negating
        constraints=LinearConstraint(costs, -np.inf, cap),
        integrality=np.ones(len(eligible)),             # EXACT 0/1 — never a relaxed fractional solve
        bounds=Bounds(0, 1),
    )
    if not res.success or res.x is None:
        return {**base, "status": STATUS_NO_SOLUTION, "selected": None, "displaced": None,
                "total_cost": None, "total_value": None, "slack": None, "greedy": None,
                "solver_status": str(getattr(res, "message", "") or "no message")}

    # Round the integer solution rather than truncating: a solver returns 0.9999999997 for a 1.
    take = [i for i, x in enumerate(res.x) if round(float(x)) == 1]
    chosen = [eligible[i] for i in take]
    chosen_ids = {c["id"] for c in chosen}
    spent = sum(c["cost"] for c in chosen)

    g = greedy(eligible, cap)
    return {
        **base,
        "status": STATUS_OK,
        "selected": [{"id": c["id"], "name": c["name"], "cost": c["cost"], "value": c["value"]}
                     for c in chosen],
        # Not just WHICH was left out — what it would have cost and added. An allocation that returns
        # a list of ids is unauditable, and this is a capital-committee output.
        "displaced": [{"id": c["id"], "name": c["name"], "cost": c["cost"], "value": c["value"],
                       "reason": ("would not fit in the remaining capital"
                                  if c["cost"] > cap - spent else
                                  "fits, but displacing selected work would lower total value")}
                      for c in eligible if c["id"] not in chosen_ids],
        "total_cost": round(spent, 2),
        "total_value": round(sum(c["value"] for c in chosen), 2),
        "slack": round(cap - spent, 2),
        "greedy": {**g, "value_forgone": round(sum(c["value"] for c in chosen) - g["value"], 2),
                   "note": "the value-per-cost ranking a committee reasons with today. A difference of "
                           "zero means these inputs have no crowding-out shape — it is not evidence "
                           "the optimiser is working."},
    }
