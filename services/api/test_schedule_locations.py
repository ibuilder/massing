"""R45-SCHED-REACH ① — the location-based (flowline) adapter.

The engine is `massingplan/core/locations.py` and has its own correctness upstream. These assertions
are about the **adapter**, and specifically about the two ways it could produce a confident wrong
answer, both of which it did before these tests existed.
"""
from __future__ import annotations

from aec_api.schedule_locations import flowline, parse_buffer_pairs

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

    # The NO-BUFFER call still runs tight, which is the right default: a planner who asked for
    # nothing gets the line-of-balance's own answer rather than a spacing somebody guessed. The
    # check is kept exactly as written, now scoped to the default call — FLOW-BUFFER made a buffer
    # settable and the cases below are where it is set.
    check("gap_days is 0 everywhere when no buffer is requested",
          all(i["gap_days"] == 0 for i in r["interferences"]),
          f"{[i['gap_days'] for i in r['interferences']]} — the DEFAULT must stay tight; a spacing "
          f"nobody asked for is a schedule nobody agreed to")
    check("...and overlap_count is 0 there, which is now a measurement rather than a constant",
          r["overlap_count"] == 0 and r["buffer_days_requested"] == {},
          f"{r['overlap_count']} / {r['buffer_days_requested']}")
    # ...and the engine DOES report an overlap when a buffer makes one, so the path is live and only
    # unreachable from here. Proved against the vendored engine directly, not inferred.
    from massingplan.core.locations import LinearTask, Location, compute
    _locs = [Location(id=f"L{i}", name=f"L{i}", sequence=i) for i in (1, 2, 3)]
    _neg = compute([LinearTask(id="A", duration_days=5, buffer_days=0),
                    LinearTask(id="B", duration_days=5, buffer_days=-3)], _locs)
    check("a NEGATIVE buffer does produce a negative clearance and a LOB.OVERLAP error",
          _neg.interferences[0].gap_days == -3 and "LOB.OVERLAP" in _neg.issues.codes(),
          f"gap {_neg.interferences[0].gap_days}, codes {_neg.issues.codes()}")

    # ── FLOW-BUFFER: the buffer is requestable, so that branch is reachable from the ADAPTER ──
    #
    # The check above proved the engine honours a negative buffer; these prove the route can ask for
    # one. *A live engine branch no caller can reach is the same as a dead one*, which is the whole
    # of what FLOW-BUFFER was.
    flat = flowline(DATED, buffer_days=2)
    check("a flat buffer spaces every handover by it",
          all(i["gap_days"] == 2 for i in flat["interferences"]),
          f"{[i['gap_days'] for i in flat['interferences']]}")
    check("...and the response states what was ASKED for, not only what came out",
          flat["buffer_days_requested"] == dict.fromkeys(flat["trades"][1:], 2),
          f"{flat['buffer_days_requested']} for trades {flat['trades']}")

    # THE FIRST TRADE'S VALUE IS INERT, and that is the engine's shape rather than a choice here:
    # `buffer_days` is the lag on the link INTO a task, so the first has no predecessor. The field's
    # own docstring says the opposite ("between this task finishing and the next task starting"), so
    # a caller following it sets exactly this trade — hence the value is REPORTED as ignored rather
    # than dropped. Measured: 3 on the first of two trades moves nothing at all.
    check("a buffer on the FIRST trade is named as ignored, not silently dropped",
          flat["buffer_days_ignored_first"] == [flat["trades"][0]],
          f"{flat['buffer_days_ignored_first']} vs first trade {flat['trades'][0]!r}")

    per = flowline(DATED, buffer_days={flat["trades"][1]: 3, "Nonesuch": 1})
    check("a per-trade map applies only to the trade it names",
          per["buffer_days_requested"] == {flat["trades"][1]: 3},
          f"{per['buffer_days_requested']}")
    check("...and an unknown trade name is reported as a TYPO, kept apart from the first-trade case",
          per["buffer_days_ignored_unknown"] == ["Nonesuch"]
          and per["buffer_days_ignored_first"] == [],
          f"unknown={per['buffer_days_ignored_unknown']} first={per['buffer_days_ignored_first']}")

    # THE REQUEST AND THE RESULT ARE TWO DIFFERENT NUMBERS. The realised overlap saturates at the
    # predecessor's per-location duration, because a successor cannot start before its predecessor
    # did. Measured against the engine at 2/4/6/10 crew-days per location, a request of −5 returns
    # −2/−4/−5/−5. *A planner who asked for five and got two has been told nothing by a response
    # that reports only the two* — which is why `buffer_days_unmet` exists.
    neg = flowline(DATED, buffer_days=-5)
    check("a negative buffer reaches LOB.OVERLAP THROUGH THE ADAPTER for the first time",
          "LOB.OVERLAP" in {i["code"] for i in neg["issues"]},
          f"codes {sorted({i['code'] for i in neg['issues']})}")
    check("...and overlap_count counts the crossings rather than the trades",
          neg["overlap_count"] == sum(1 for i in neg["interferences"] if i["gap_days"] < 0)
          and neg["overlap_count"] > 0,
          f"{neg['overlap_count']} vs {[i['gap_days'] for i in neg['interferences']]}")
    check("a request the engine could not honour is NAMED, with both numbers",
          neg["buffer_days_unmet"]
          and all(u["requested"] == -5 and u["realised"] > -5 for u in neg["buffer_days_unmet"]),
          f"{neg['buffer_days_unmet']} — the realised overlap saturates at the predecessor's "
          f"per-location duration, and a response carrying only the clearance hides the shortfall")

    # The clamp is reported rather than silent, for the same reason: a flowline is a planning view
    # and one silly number should not cost the diagram, but it must not look honoured either.
    big = flowline(DATED, buffer_days=10_000)
    check("an absurd buffer is clamped and SAYS so",
          big["buffer_days_clamped"] == sorted(big["buffer_days_requested"])
          and all(v == big["max_buffer_days"] for v in big["buffer_days_requested"].values()),
          f"clamped={big['buffer_days_clamped']} requested={big['buffer_days_requested']}")

    # ── the TRANSPORT shape, parsed in the engine so it needs no server ──────────────────────────
    #
    # `buffer=<trade>:<days>`, repeatable. The first draft parsed this in the router, which left the
    # one part of the feature a user actually TYPES reachable only by a live request — and there is
    # no route suite for the flowline at all. *A parser only a live request can exercise is a parser
    # nobody exercises.*
    pairs, bad = parse_buffer_pairs(["Drywall:2", "Paint:-1", " Tiling : 3 "])
    check("a repeated `<trade>:<days>` pair parses, trimmed",
          pairs == {"Drywall": 2, "Paint": -1, "Tiling": 3} and bad == [],
          f"{pairs} / {bad}")
    # Split on the LAST colon, so a trade whose NAME contains one survives the round trip. A first
    # draft splitting on the first colon would have turned "Co:Ltd:5" into trade "Co" — a confident
    # wrong answer about a trade that exists.
    check("...and the split is on the LAST colon, so a colon in the trade name survives",
          parse_buffer_pairs(["Co:Ltd:5"])[0] == {"Co:Ltd": 5},
          f"{parse_buffer_pairs(['Co:Ltd:5'])[0]}")
    bad_pairs, bad_list = parse_buffer_pairs(["x", ":4", "A:notanumber", "B:1"])
    check("an unreadable pair is RETURNED rather than dropped, and the good ones still land",
          bad_pairs == {"B": 1} and bad_list == ["x", ":4", "A:notanumber"],
          f"{bad_pairs} / {bad_list} — a typo in a query string is otherwise indistinguishable "
          f"from a buffer the engine declined, and those have different fixes")

    both = flowline(DATED, buffer_days=1, buffer_pairs=["Paint:-3", "bad"])
    check("a per-trade pair OVERRIDES the flat number for the trade it names",
          both["buffer_days_requested"] == {"Drywall": 1, "Paint": -3},
          f"{both['buffer_days_requested']}")
    check("...and the malformed pair rides back with it",
          both["buffer_malformed"] == ["bad"], f"{both['buffer_malformed']}")
    # A pair must not smuggle past the bound the flat path respects.
    check("a pair is clamped by the same rule as a flat request",
          flowline(DATED, buffer_pairs=["Paint:9999"])["buffer_days_requested"]
          == {"Paint": flowline(DATED)["max_buffer_days"]},
          f"{flowline(DATED, buffer_pairs=['Paint:9999'])['buffer_days_requested']}")

    # A TYPO IS REPORTED EVEN WHEN THERE IS NO FLOW TO COMPUTE. An empty `buffer_malformed` on a
    # refusal says "nothing was malformed", which is a different claim from "we never got that
    # far" — and it is the one a consumer acts on.
    check("a malformed pair is reported on the UNAVAILABLE path too",
          flowline([], buffer_pairs=["oops"])["buffer_malformed"] == ["oops"],
          f"{flowline([], buffer_pairs=['oops'])['buffer_malformed']}")

    # Every key the computed shape carries is present on the REFUSAL too — the contract
    # `_unavailable` states in its own docstring. A key that appears only on the available path is
    # one a consumer reads as `undefined` and renders as nothing-was-requested.
    _gone = flowline([])
    check("the refusal carries every buffer key, so no consumer sees `undefined`",
          all(k in _gone for k in ("buffer_days_requested", "buffer_days_unmet", "overlap_count",
                                   "buffer_days_ignored_first", "buffer_days_ignored_unknown",
                                   "buffer_days_clamped", "max_buffer_days")),
          f"missing {[k for k in ('buffer_days_requested', 'buffer_days_unmet', 'overlap_count') if k not in _gone]}")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_locations OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
