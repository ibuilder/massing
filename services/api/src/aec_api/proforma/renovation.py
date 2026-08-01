"""PF-RENOVATION — a value-add renovation programme, unit by unit, over time.

Scope item 4 from the CRE model survey: three of the six surveyed models are multifamily value-add,
and all three turn on the same mechanic — buy a property at in-place rents, renovate units as they
turn, and earn a premium on each unit **once it is back online**.

Nothing here models that today. `test_fit.layout` and `routers/generate` carry `unit_types`, but that
is *design* unit mix — how many 1BRs fit on a plate — a different domain that happens to share a
word. This is the economics.

## The refusal this module exists for

**A renovation premium must not begin before the unit turns.** It is the single most common way a
value-add deal is overstated, and it is invisible in the output: applying the premium from day one
produces a smooth, plausible income curve that is simply too high, too early, for the whole hold. The
correct curve has three phases per unit and this module models all three:

1. the unit earns its **in-place** rent until renovation starts;
2. it earns **nothing** while it is being renovated — that vacancy is the cost of the programme;
3. it earns the **renovated** rent only from the month it comes back online.

Skipping phase 2 is the second overstatement, and skipping the *lag* in phase 3 is the first.

## What is refused rather than defaulted

* **`units_per_month`** — the renovation pace. Unstated, a model either renovates everything instantly
  (all premium, no phasing) or nothing at all. Both are legitimate *inputs*; neither is a default.
* **`downtime_months_per_unit`** — with no downtime a unit earns in-place rent one month and renovated
  rent the next, so the programme appears to cost only its capex. Stating `0` is allowed; it is then
  a choice somebody made.
* **A unit type with no renovated rent is NOT renovated.** Inventing a premium is inventing the entire
  investment thesis; the type is carried at its in-place rent and named as unimproved.

Sequencing is deterministic and stated: types are renovated in the order supplied, consuming each
month's pace. Real programmes pick an order for real reasons (worst units first, or a stack), and a
silent proportional split would produce fractional units nobody can schedule.

Pure arithmetic over the supplied unit types — no DB, deterministic, unit-testable.
"""
from __future__ import annotations

import math
from typing import Any

STATUS_OK = "scheduled"
STATUS_MISSING_ASSUMPTION = "assumptions_incomplete"

REQUIRED = ("units_per_month", "downtime_months_per_unit")

REQUIRED_WHY = {
    "units_per_month": "the renovation pace. Unstated, the model either renovates everything at once "
                       "(all premium, no phasing) or nothing — both are legitimate inputs, neither is "
                       "a legitimate default",
    "downtime_months_per_unit": "with no downtime a unit earns in-place rent one month and renovated "
                                "rent the next, so the programme appears to cost only its capex. Zero "
                                "is allowed — but chosen",
}


def _num(v: Any) -> float | None:
    """Strictly numeric and finite. `bool` is rejected before `int`."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _assumptions(a: dict | None) -> tuple[dict, list[str]]:
    a = a or {}
    clean: dict[str, float] = {}
    missing: list[str] = []
    for k in REQUIRED:
        v = _num(a.get(k))
        if v is None or v < 0:
            missing.append(k)
        else:
            clean[k] = v
    return clean, sorted(set(missing))


def _prepare(unit_types: list[dict] | None) -> tuple[list[dict], list[dict]]:
    """Split unit types into renovatable and not, naming the reason for each exclusion."""
    ok: list[dict] = []
    excluded: list[dict] = []
    for i, t in enumerate(unit_types or []):
        d = t.get("data") or t
        name = str(d.get("type") or d.get("name") or f"#{i}")
        count = _num(d.get("count"))
        cur = _num(d.get("current_rent_monthly"))
        new = _num(d.get("renovated_rent_monthly"))
        cost = _num(d.get("renovation_cost"))
        if count is None or count <= 0:
            excluded.append({"type": name, "reason": "no positive unit count"})
            continue
        if cur is None:
            excluded.append({"type": name, "reason": "no in-place rent stated"})
            continue
        if new is None:
            # Not an error — a type nobody intends to renovate. It keeps earning in-place rent and is
            # NAMED, because inventing a premium here would invent the investment thesis itself.
            excluded.append({"type": name, "count": int(count), "reason":
                             "no renovated rent stated — carried at in-place rent, not renovated"})
            continue
        ok.append({"type": name, "count": int(count), "current_rent_monthly": cur,
                   "renovated_rent_monthly": new, "renovation_cost": cost or 0.0,
                   "premium_monthly": new - cur})
    return ok, excluded


def schedule(unit_types: list[dict] | None, assumptions: dict | None = None,
             months: int = 60) -> dict[str, Any]:
    """Month-by-month renovation programme: capex, downtime cost, and premium once units are back."""
    a, missing = _assumptions(assumptions)
    if missing:
        return {"status": STATUS_MISSING_ASSUMPTION, "missing": missing,
                "why": {k: REQUIRED_WHY[k] for k in missing},
                "note": "no schedule was produced. Defaulting these would apply the full premium with "
                        "no phasing and no vacancy, which is the standard way a value-add deal is "
                        "overstated and is indistinguishable in the output from a correct one.",
                "by_month": [], "total_renovation_cost": None}

    renovatable, excluded = _prepare(unit_types)
    pace = a["units_per_month"]
    # Downtime rounds UP, and never silently to zero. `int(round(x))` was banker's rounding: 0.5 -> 0,
    # 1.5 -> 2, 2.5 -> 2. The first of those is the damaging one — a stated half-month of downtime
    # became NO downtime, deleting phase 2 entirely, which is the exact cost this module exists to
    # surface. In a monthly model a unit that is offline at all is offline for the month; rounding a
    # stated positive downtime down to nothing understates the programme's carrying cost while the
    # output still reads as a complete schedule. An explicit 0 is preserved — that is a choice.
    raw_downtime = a["downtime_months_per_unit"]
    downtime = 0 if raw_downtime == 0 else max(1, math.ceil(raw_downtime))
    months = max(0, int(months))

    # Expand to a per-unit queue, in the order the caller supplied. Explicit rather than proportional:
    # a fractional unit cannot be scheduled, and a silent split would produce them.
    # Each queue entry is (index, type). The index makes every unit DISTINCT: expanding with
    # `[t] * count` would put N references to one dict in the queue, and removing a completed unit by
    # value would then drop every unit of that type at once — a bug that shows up as a renovation
    # programme finishing far too early, with no error anywhere.
    queue: list[tuple[int, dict]] = []
    for t in renovatable:
        for _ in range(t["count"]):
            queue.append((len(queue), t))

    started: list[int] = []          # completion month per started unit
    rows: list[dict] = []
    cursor = 0
    in_place_total = sum(t["current_rent_monthly"] * t["count"] for t in renovatable)

    completions: dict[int, list[tuple[int, dict]]] = {}
    capex_by_month: dict[int, float] = {}
    starts_by_month: dict[int, list[tuple[int, dict]]] = {}

    m = 0
    budget = 0.0
    # A FRACTIONAL pace accumulates rather than truncating. `int(min(pace, ...))` floored each month
    # independently, so any pace below 1 took `int(0.5) == 0` units every single month and renovated
    # NOTHING — for all 60 months, while still returning `status: "scheduled"` with a full by_month
    # table of zeros. "One unit every two months" is an ordinary pace for a small property, and it
    # produced a silently empty programme that reads exactly like a completed one.
    #
    # Carrying the remainder makes 0.5 mean what it says: 0, 1, 0, 1 ... The module's stated purpose is
    # to stop a value-add deal being OVERstated; this failed in the other direction and was no less
    # wrong for it.
    allowance = 0.0
    while cursor < len(queue) and m < months:
        allowance += pace
        take = int(min(int(allowance), len(queue) - cursor))
        allowance -= take
        for _ in range(take):
            idx, t = queue[cursor]
            cursor += 1
            starts_by_month.setdefault(m, []).append((idx, t))
            capex_by_month[m] = capex_by_month.get(m, 0.0) + t["renovation_cost"]
            completions.setdefault(m + downtime, []).append((idx, t))
            started.append(m + downtime)
        m += 1

    online: list[dict] = []
    offline: dict[int, dict] = {}          # keyed by unit index, so completions remove exactly one
    cum_capex = 0.0
    for month in range(months):
        for idx, t in completions.get(month, []):
            offline.pop(idx, None)
            online.append(t)
        for idx, t in starts_by_month.get(month, []):
            offline[idx] = t

        capex = capex_by_month.get(month, 0.0)
        cum_capex += capex
        # Phase 2: a unit under renovation earns NOTHING. The rent it would have earned is the
        # programme's carrying cost and is reported, not netted into the premium.
        downtime_rent_loss = sum(t["current_rent_monthly"] for t in offline.values())
        # Phase 3: the premium applies ONLY to units already back online.
        premium = sum(t["premium_monthly"] for t in online)
        rows.append({
            "month": month,
            "units_started": len(starts_by_month.get(month, [])),
            "units_completed": len(completions.get(month, [])),
            "units_online_renovated": len(online),
            "units_in_renovation": len(offline),
            "renovation_capex": round(capex, 2),
            "cumulative_capex": round(cum_capex, 2),
            "downtime_rent_loss": round(downtime_rent_loss, 2),
            "premium_income": round(premium, 2),
            "net_effect": round(premium - downtime_rent_loss - capex, 2),
        })
        budget += capex

    total_units = sum(t["count"] for t in renovatable)
    # A zero-unit programme is a legitimate answer only when the caller asked for one (pace 0, or no
    # renovatable types). Reported explicitly so a silently-empty schedule cannot be mistaken for a
    # completed one — the failure mode that a fractional pace used to produce.
    nothing_done = total_units > 0 and not started
    return {
        "status": STATUS_OK,
        "nothing_renovated": nothing_done,
        "nothing_renovated_why": (
            f"pace is {pace} unit(s)/month over {months} month(s) — no unit completed a start"
            if nothing_done else None),
        "assumptions_used": {"units_per_month": pace, "downtime_months_per_unit": downtime},
        "months": months,
        "renovatable_units": total_units,
        "units_renovated_in_window": len(started),
        "units_not_reached": max(0, total_units - len(started)),
        "in_place_rent_monthly": round(in_place_total, 2),
        "total_renovation_cost": round(budget, 2),
        "total_downtime_rent_loss": round(sum(r["downtime_rent_loss"] for r in rows), 2),
        "total_premium_income": round(sum(r["premium_income"] for r in rows), 2),
        "stabilised_premium_monthly": round(
            sum(t["premium_monthly"] * t["count"] for t in renovatable), 2),
        "unit_types": renovatable,
        "excluded_unit_types": excluded,
        "by_month": rows,
        "note": "a unit earns in-place rent until it starts, NOTHING while it is being renovated, and "
                "the renovated rent only from the month it comes back online. Applying the premium "
                "from day one is the standard overstatement and is invisible in the output.",
    }
