"""R46 ⑤ — compression, and the recovery figure that cannot see the path behind it.

`px.optimize` reports `days_potential = duration × _CRASH_FACTOR` for each long critical activity — a
fixed fraction of the activity's own length. It never re-schedules, so it cannot know how much room
there is behind the activity before another path takes over.

The assertion that matters is **`px.optimize's advisory OVERSTATES what the finish actually moves`**,
and it is measured on a network built to expose it: a driving activity with a near-parallel path
three days behind it. Compression buys those three days and then stops; the advisory keeps counting.
"""
from __future__ import annotations

import json

from aec_api import schedule_compression

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02"}}


#: `a` -> `b` (20d) -> `d`, with `a` -> `c` (17d) -> `d` running almost alongside. `b` drives by
#: three days. Crash `b` as hard as you like: after three days `c` takes over and the finish stops
#: moving. That gap is invisible to any figure derived from `b`'s duration alone.
NEAR_PARALLEL = [act("a", 5), act("b", 20, "a"), act("c", 17, "a"), act("d", 5, "b,c")]

COSTS = [{"activity_id": "b", "cost_per_day": 1000, "max_days": 10}]


def main() -> int:
    r = schedule_compression.compress(NEAR_PARALLEL, target_days=10, costs=COSTS)
    check("the schedule and its crash costs reach the vendored planner",
          r["available"] and r["options"],
          f"{r['finish_before']} -> {r['best_finish']}, {r['days_available']}d for "
          f"{r['total_cost']}")

    check("the result survives json.dumps", _ser(r), "a route has to return it")

    # --- THE finding ------------------------------------------------------------------------------
    #
    # `b` can be crashed 10 days and the plan is allowed to spend all 10. What it BUYS is bounded by
    # the parallel path. `days_saved` per option is the project-finish movement; summing the days
    # taken off the activity would report the larger, wrong number.
    saved = sum(o.get("days_saved", 0) for o in r["options"])
    check("px.optimize's advisory OVERSTATES what the finish actually moves",
          r["days_available"] < 10 and saved == r["days_available"],
          f"crashing `b` by up to 10d moves the finish {r['days_available']}d — `c` takes over. "
          "px.optimize reports duration x a fixed factor and never re-schedules, so it cannot see "
          "the path three days behind")

    # The advisory's own arithmetic, imported rather than recalled, so the comparison is between
    # two numbers this repo actually produces.
    from aec_api.px import _CRASH_FACTOR
    advisory = round(20 * _CRASH_FACTOR)
    check("...and the gap is measurable: the advisory says 5d, the finish moves 3d",
          advisory == 5 and r["days_available"] == 3,
          f"px.optimize reports duration x {_CRASH_FACTOR} = {advisory}d for `b`; re-scheduling "
          f"each day shows {r['days_available']}d before `c` takes over — a {advisory - r['days_available']}d "
          "overstatement on a four-activity network, and the error grows with the number of "
          "near-parallel paths")

    check("...and the plan stops paying once the days stop arriving",
          all(o.get("days_saved", 0) > 0 for o in r["options"]),
          f"{[(o['activity_id'], o.get('days_shortened'), o.get('days_saved')) for o in r['options']]}"
          " — every option bought at least one day; an option that bought nothing would be money "
          "spent on an activity that stopped driving")

    check("...and it reports honestly that it could not reach the target",
          r["meets_target"] is False and r["target_days"] == 10,
          f"asked for 10d, found {r['days_available']}d. Returned as the answer rather than raised "
          "— a caller should not have to find the number by bisection")

    check("each option carries its cost per day ACTUALLY saved",
          all(o.get("cost_per_day_saved") is not None and o["cost_per_day_saved"] > 0
              for o in r["options"] if o.get("kind") == "crash"),
          "cost / days_saved, not cost / days_shortened — the second flatters every option")

    # --- the twin: a clean chain buys what you pay for ---------------------------------------------
    chain = [act("a", 5), act("b", 20, "a"), act("c", 5, "b")]
    clean = schedule_compression.compress(chain, target_days=5, costs=COSTS)
    check("on a chain with no parallel path, the target IS met — the twin",
          clean["available"] and clean["meets_target"] and clean["days_available"] >= 5,
          f"{clean['days_available']}d of 5 asked. Without this, a planner that always fell short "
          "would look like a finding on every project")

    # --- what it refuses to invent -------------------------------------------------------------------
    no_costs = schedule_compression.compress(NEAR_PARALLEL, target_days=10)
    check("no crash costs is REFUSED, not defaulted",
          no_costs["available"] is False and "only a wish" in no_costs["reason"],
          "max_days is a fact about the work — a pour cures in the time it cures. A default of "
          "'as far as you like' produces a plan that finishes on any date somebody asks for")

    partial = schedule_compression.compress(NEAR_PARALLEL, target_days=10, costs=COSTS + [
        {"activity_id": "c", "cost_per_day": 500},
        {"cost_per_day": 100, "max_days": 3},
        {"activity_id": "d", "cost_per_day": -5, "max_days": 2}])
    check("malformed cost rows are NAMED and excluded, not silently defaulted",
          partial["available"] and len(partial["rejected_costs"]) == 3,
          f"{partial['rejected_costs']}")

    check("...and activities with no cost entry are counted",
          partial["activities_without_costs"] >= 2,
          f"{partial['activities_without_costs']} of 4 were never candidates — 'we could only find "
          "3 days' reads differently once you know how many were ineligible")

    # --- refusals ---------------------------------------------------------------------------------------
    empty = schedule_compression.compress([], 5, COSTS)
    check("no activities is refused", empty["available"] is False, empty["reason"])

    neg = schedule_compression.compress(NEAR_PARALLEL, -3, COSTS)
    check("a negative target is refused",
          neg["available"] is False and "finish later" in neg["reason"], neg["reason"])

    cyc = schedule_compression.compress(
        [act("a", 5, "c"), act("b", 5, "a"), act("c", 5, "b")], 3,
        [{"activity_id": "a", "cost_per_day": 100, "max_days": 2}])
    check("a cyclic network is refused", cyc["available"] is False and "loop" in cyc["reason"],
          cyc["reason"])

    check("...and no refusal relays an exception's text",
          all("CompressionError" not in x["reason"] and "Traceback" not in x["reason"]
              for x in (empty, neg, cyc, no_costs)),
          "the v0.3.962 rule: a response path never carries what the library said")

    check("every refusal reports counts as None, never 0",
          all(x["days_available"] is None and x["total_cost"] is None and x["meets_target"] is None
              for x in (empty, neg, cyc, no_costs)),
          "'no time can be recovered' and 'nothing was computed' must not render alike")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_compression OK")
    return 0


def _ser(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
