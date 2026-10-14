"""R45-SCHED-REACH ① — the location-based (flowline) adapter.

The engine is `massingplan/core/locations.py` and has its own correctness upstream. These assertions
are about the **adapter**, and specifically about the two ways it could produce a confident wrong
answer, both of which it did before these tests existed.
"""
from __future__ import annotations

from aec_api.schedule_locations import flowline

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(trade: str, loc: str, days: float, start: str | None = None) -> dict:
    data: dict = {"trade": trade, "location": loc, "duration": days}
    if start:
        data["start"] = start
    return {"id": f"{trade}-{loc}", "ref": f"{trade}-{loc}", "title": trade, "data": data}


#: Framing → Drywall → Paint. Alphabetically that is Drywall, Framing, Paint — so this fixture
#: distinguishes "ordered by the schedule" from "ordered by the alphabet", which is the whole point.
DATED = [
    act(t, lv, d, f"2026-{m}-{off}")
    for lv, m in (("Level 1", "03"), ("Level 2", "03"), ("Level 10", "04"))
    for t, d, off in (("Framing", 4, "01"), ("Drywall", 6, "05"), ("Paint", 3, "09"))
]


def main() -> int:
    r = flowline(DATED)
    check("a real project reaches the vendored flowline engine",
          r["available"] and r["segments"], f"{len(r['segments'])} segments, {r['duration_days']} days")

    # --- the defect this file exists for -------------------------------------------------------
    #
    # The engine takes tasks in HANDOVER order. The first adapter sorted them alphabetically, which
    # put Drywall ahead of Framing and produced a complete, plausible, entirely wrong flowline —
    # right down to per-trade continuity costs. Nothing errored. That is the shape worth a test.
    check("handover order comes from the SCHEDULE, not the alphabet",
          r["trades"] == ["Framing", "Drywall", "Paint"], f"{r['trades']}")
    check("...and the alphabet would have given a different, wrong answer",
          sorted(r["trades"]) != r["trades"], f"alphabetical would be {sorted(r['trades'])}")

    # The twin. Refusing is the correct behaviour when the order cannot be known — falling back to
    # alphabetical would satisfy every other assertion here while inventing the answer.
    undated = [act(t, lv, 4) for lv in ("L1", "L2") for t in ("Framing", "Drywall")]
    u = flowline(undated)
    check("with no dates to derive the order from, it REFUSES rather than guessing",
          u["available"] is False and "alphabetical" in u["reason"],
          u["reason"][:70])

    ordered = flowline(undated, trade_order=["Framing", "Drywall"])
    check("...and an explicit trade_order is accepted, because the sequence is a planner's call",
          ordered["available"] and ordered["trades"] == ["Framing", "Drywall"],
          f"{ordered['trades']}, {ordered['duration_days']} days")

    # --- the other confident-wrong: location order ------------------------------------------------
    check("locations sort naturally — Level 10 after Level 2, not between 1 and 2",
          [x["id"] for x in r["locations"]] == ["Level 1", "Level 2", "Level 10"],
          f"{[x['id'] for x in r['locations']]}")

    seq = flowline(DATED, sequence=["Level 10", "Level 1", "Level 2"])
    check("...and an explicit location sequence overrides it — flow direction is a decision",
          [x["id"] for x in seq["locations"]] == ["Level 10", "Level 1", "Level 2"],
          f"{[x['id'] for x in seq['locations']]}")

    # --- work content is per location, not averaged ------------------------------------------------
    #
    # The adapter encodes crew-days as quantity at rate 1.0 precisely so a trade can take 4 days in one
    # place and 9 in another. If it collapsed to a flat duration this would come back uniform, and a
    # flowline whose whole job is showing where work bunches would be showing nothing.
    uneven = [act("Framing", "L1", 2, "2026-03-01"), act("Framing", "L2", 9, "2026-03-04"),
              act("Drywall", "L1", 3, "2026-03-10"), act("Drywall", "L2", 3, "2026-03-14")]
    un = flowline(uneven)
    fram = sorted(s["duration_days"] for s in un["segments"] if s["task_id"] == "Framing")
    check("per-location work content survives — a trade may take longer in one place",
          len(set(fram)) > 1, f"Framing durations by location: {fram}")

    # --- the refusals -------------------------------------------------------------------------------
    one = flowline([act("Framing", "Level 1", 4, "2026-03-01")])
    check("one location is refused — a flowline through a single place is a bar chart",
          one["available"] is False and "bar chart" in one["reason"], one["reason"][:60])

    bare = flowline([{"id": "x", "data": {"duration": 3}}])
    check("activities with no trade/location are refused, naming the two fields",
          bare["available"] is False and "trade" in bare["reason"] and "location" in bare["reason"],
          bare["reason"][:60])

    empty = flowline([])
    check("no activities is refused", empty["available"] is False, empty["reason"])

    check("an unavailable flowline reports duration as None, never 0",
          all(x["duration_days"] is None for x in (u, one, bare, empty)),
          "a zero-day flowline reads as a project that takes no time")

    check("...and every unavailable shape carries the full key set",
          all(set(x) >= {"segments", "trades", "locations", "continuity_cost_days",
                         "interference_count", "interferences", "converging_count", "issues"}
              for x in (u, one, bare, empty)),
          "callers branch on `available` without special-casing the rest")

    # --- the number that decides whether any of this is worth it ------------------------------------
    check("continuity cost is reported per trade — the price of keeping a gang whole",
          isinstance(r["continuity_cost_days"], dict) and set(r["continuity_cost_days"]) == set(r["trades"]),
          f"{r['continuity_cost_days']}")

    # --- FLOW-CLEAR: the whole Interference, not one field of it -----------------------------------
    #
    # The adapter projected the dataclass with
    # `{k: getattr(i, k) for k in ("task_id", "location_id") if hasattr(i, k)}`, and `task_id` is
    # not a field of `Interference` at all — it belongs to `Segment`. So `hasattr` skipped it in
    # silence and the whole record left the server as `{"location_id": "L01"}`: both trade ids, the
    # clearance and the converging flag discarded by the adapter before any client could decline to
    # read them. *A defensive projection fails silently by design, which is the wrong failure mode
    # for a field list* — `to_dict()`, which the `issues` line beside it had always called, would
    # have raised the day the shape changed.
    _FIELDS = {"predecessor_id", "successor_id", "location_id", "gap_days", "converging"}
    check("every interference carries all five of the dataclass's fields",
          r["interferences"] and all(set(i) == _FIELDS for i in r["interferences"]),
          f"{r['interferences'][:1] if r['interferences'] else r['interferences']}")
    check("  the two trade ids are the pair in HANDOVER order, not the alphabet",
          all(i["predecessor_id"] in r["trades"] and i["successor_id"] in r["trades"]
              for i in r["interferences"])
          and all(r["trades"].index(i["predecessor_id"]) < r["trades"].index(i["successor_id"])
                  for i in r["interferences"]),
          f"trades {r['trades']}, pairs "
          f"{[(i['predecessor_id'], i['successor_id']) for i in r['interferences']]}")

    # `interference_count` IS NOT A COUNT OF COLLISIONS, and a careful consumer reading it as one is
    # wrong in the ALARMING direction — the opposite of every other instance of this class today.
    # `compute()` appends one per consecutive pair unconditionally, so it is `len(trades) - 1`.
    check("interference_count is the PAIR population, not a finding",
          r["interference_count"] == len(r["interferences"]) == len(r["trades"]) - 1,
          f"{r['interference_count']} for {len(r['trades'])} trades — if these ever diverge, a "
          f"consumer rendering the count as a problem count becomes defensible, and it is not")

    # `converging_count` is the figure that actually VARIES from this route, and the engine says why
    # it is the one worth showing: the successor is catching up, and that is invisible on a bar
    # chart. Asserted as a RELATION so it cannot drift from the list it summarises.
    check("converging_count agrees with the records it summarises",
          r["converging_count"] == sum(1 for i in r["interferences"] if i["converging"]),
          f"{r['converging_count']} vs {[i['converging'] for i in r['interferences']]}")

    # WHY THERE IS NO `overlap_count` OR `touching_count`, measured rather than reasoned.
    # `compute()` places each line at `max(0, max(requirements))`, so the clearance at the binding
    # location is exactly the declared `buffer_days` — and this adapter never sets it. Both counts
    # would therefore be constants from this route: 0, and `len(trades) - 1`. FLOW-BUFFER holds the
    # real gap, which is that nobody can REQUEST a buffer.
    check("gap_days is 0 everywhere, because the adapter requests no buffer",
          all(i["gap_days"] == 0 for i in r["interferences"]),
          f"{[i['gap_days'] for i in r['interferences']]} — if this ever fails, a buffer became "
          f"settable and `overlap_count` stopped being a constant: publish it then")
    # ...and the engine DOES report an overlap when a buffer makes one, so the path is live and only
    # unreachable from here. Proved against the vendored engine directly, not inferred.
    from massingplan.core.locations import LinearTask, Location, compute
    _locs = [Location(id=f"L{i}", name=f"L{i}", sequence=i) for i in (1, 2, 3)]
    _neg = compute([LinearTask(id="A", duration_days=5, buffer_days=0),
                    LinearTask(id="B", duration_days=5, buffer_days=-3)], _locs)
    check("a NEGATIVE buffer does produce a negative clearance and a LOB.OVERLAP error",
          _neg.interferences[0].gap_days == -3 and "LOB.OVERLAP" in _neg.issues.codes(),
          f"gap {_neg.interferences[0].gap_days}, codes {_neg.issues.codes()}")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_locations OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
