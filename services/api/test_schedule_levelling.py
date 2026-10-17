"""R45-SCHED-DEDUPE ② — the resource-levelling adapter.

The engine is `massingplan/core/levelling.py`. These cover the adapter, and above all the two things
that make a levelling result trustworthy enough to put in front of a subcontractor: it is
**deterministic**, and the horizon's cost is **reported rather than absorbed**.
"""
from __future__ import annotations

from aec_api.schedule_levelling import levelling

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, trade: str, days: int, crew: float, preds: str = "") -> dict:
    return {"id": i, "ref": i, "title": i,
            "data": {"trade": trade, "duration": days, "crew_size": crew,
                     "predecessors": preds, "start": "2026-03-01"}}


#: Three parallel carpentry tasks at 4 crews each = 12/day, against a cap of 8. No float between them,
#: so `within_float` cannot fix it and `extend_finish` can — which is the whole point of the parameter.
OVER = [act("t1", "Carpentry", 5, 4), act("t2", "Carpentry", 5, 4), act("t3", "Carpentry", 5, 4)]
CAP = {"Carpentry": 8}


def main() -> int:
    r = levelling(OVER, caps=CAP)
    check("a real over-allocation reaches the vendored levelling engine",
          r["available"], f"peak {r['peak_before']} against cap {CAP}")

    # --- the horizon's cost, reported rather than absorbed ------------------------------------------
    #
    # `within_float` promises never to move the finish. Honouring that promise on a schedule with no
    # float means leaving conflicts unsolved — and SAYING SO is the feature. A leveller that reported
    # "0 unresolved" here would be claiming it fixed something it did not touch.
    check("within_float keeps the finish and REPORTS what it could not solve",
          r["finish_moved_days"] == 0 and r["unresolved_count"] > 0,
          f"finish +{r['finish_moved_days']}d, {r['unresolved_count']} unresolved")

    ext = levelling(OVER, caps=CAP, horizon="extend_finish")
    check("...and extend_finish resolves them by accepting a later finish",
          ext["available"] and ext["finish_moved_days"] > 0,
          f"finish +{ext['finish_moved_days']}d vs +{r['finish_moved_days']}d within float")

    check("the two horizons genuinely differ — otherwise the parameter is decoration",
          ext["finish_moved_days"] != r["finish_moved_days"],
          "a job with liquidated damages wants the first; one that has blown its float wants the second")

    # --- determinism, which is what makes it defensible ---------------------------------------------
    #
    # The priority key ends in the activity id so set/dict iteration order cannot leak into placement.
    # An optimiser whose answer changes between runs cannot be reviewed, approved, or defended in a
    # claim. Running it repeatedly in one process shares a hash seed, so this is a floor not a proof —
    # but a non-deterministic implementation would usually fail even this.
    runs = [levelling(OVER, caps=CAP, horizon="extend_finish") for _ in range(4)]
    same = all(x["moves"] == runs[0]["moves"] and x["finish_after"] == runs[0]["finish_after"]
               for x in runs)
    check("the same input produces the same answer, run after run",
          same, f"{len(runs)} runs, identical moves and finish")

    # --- refusals, and each names what is missing ----------------------------------------------------
    no_caps = levelling(OVER)
    check("no caps is refused — levelling against unlimited supply returns the input",
          no_caps["available"] is False and "caps" in no_caps["reason"], no_caps["reason"][:70])

    check("...and the refusal lists the trades it saw, so the caller can name them",
          no_caps.get("trades") == ["Carpentry"], f"{no_caps.get('trades')}")

    mismatch = levelling(OVER, caps={"Plumbing": 4})
    check("a cap naming a trade nobody works is refused, not silently ignored",
          mismatch["available"] is False and "spelling" in mismatch["reason"],
          mismatch["reason"][:60])

    no_crew = levelling([{"id": "x", "data": {"trade": "Carpentry", "duration": 3}}], caps=CAP)
    check("activities with no crew size are refused, naming both fields",
          no_crew["available"] is False and "crew size" in no_crew["reason"],
          no_crew["reason"][:60])

    bad = levelling(OVER, caps=CAP, horizon="nope")
    check("an unknown horizon is refused and the valid ones are listed",
          bad["available"] is False and "within_float" in bad["reason"], bad["reason"][:60])

    empty = levelling([])
    check("no activities is refused", empty["available"] is False, empty["reason"])

    check("unavailable reports counts as None, never 0 — 'no moves' and 'did not run' differ",
          all(x["move_count"] is None and x["unresolved_count"] is None
              for x in (no_caps, mismatch, no_crew, bad, empty)),
          "a zero move count would read as a schedule that needed no levelling")

    # --- an uncapped trade is unconstrained, not infinitely over-allocated ---------------------------
    mixed = OVER + [act("p1", "Plumbing", 5, 9)]
    m = levelling(mixed, caps=CAP)
    check("an uncapped trade is left alone rather than treated as a violation",
          m["available"] and "Plumbing" not in m["peak_before"],
          f"levelled against {sorted(m['caps'])} only; Plumbing has no cap so no limit was invented")

    # --- LEVEL-UNREAD: did the cap actually end up met? ---------------------------------------------
    #
    # The response reported the moves it made and the peaks before and after, and nothing compared
    # the second peak to the cap — so the one question levelling exists to answer was left for a
    # caller to assemble, and the only caller rendered `move_count`, `unresolved_count` and
    # `finish_moved_days` instead. On THIS fixture those three are 0, >0 and 0 under `within_float`:
    # two of the three read exactly as a schedule already inside its caps.
    check("within_float leaves the cap UNMET, and the response says so",
          r["within_caps"] is False and len(r["over_cap"]) == 1, r["over_cap"])
    over = r["over_cap"][0]
    # The RELATION, not literals — the fixture's crew sizes may change and this still says what the
    # field means. (`test_unit_rate_route` had to learn that a constant inferred from a neighbouring
    # assertion is a guess wearing an assertion's clothes.)
    check("  over_cap states the trade, its cap, the peak it ended at and the excess",
          over["trade"] == "Carpentry"
          and over["cap"] == CAP["Carpentry"]
          and over["peak_after"] == r["peak_after"]["Carpentry"]
          and round(over["over_by"], 4) == round(over["peak_after"] - over["cap"], 4),
          over)
    check("  ...and the two zeros beside it are what make the verdict load-bearing",
          r["move_count"] == 0 and r["finish_moved_days"] == 0,
          "a card reading only these three figures cannot tell 'nothing needed doing' from "
          "'nothing could be done'")

    check("extend_finish MEETS the cap, and the response says that too",
          ext["within_caps"] is True and ext["over_cap"] == [],
          f"peak {ext['peak_after']} against cap {CAP}, finish +{ext['finish_moved_days']}d")
    check("  the two verdicts disagree, which is the horizon trade-off made explicit",
          r["within_caps"] != ext["within_caps"])
    # The verdict is a REAL comparison, not a restatement of `unresolved_count`: mutating the cap
    # upward must flip it with the same moves.
    loose = levelling(OVER, caps={"Carpentry": 99})
    check("  a cap above the peak is met without moving anything",
          loose["within_caps"] is True and loose["move_count"] == 0 and loose["over_cap"] == [],
          f"peak {loose['peak_after']} under a cap of 99")

    # --- the coverage the verdict is silent about ----------------------------------------------------
    cov = m["coverage"]
    check("coverage names the UNCAPPED trades the verdict says nothing about",
          cov["uncapped_trades"] == ["Plumbing"] and cov["capped_trades"] == ["Carpentry"], cov)
    check("  and reconciles: with_demand + without_demand == activities",
          cov["activities"] == len(mixed)
          and cov["with_demand"] + cov["without_demand"] == cov["activities"], cov)

    # An activity missing either field draws on nothing, so it is outside the levelling. Counted AND
    # named — a count alone cannot be acted on, and these are data-entry gaps rather than schedule
    # facts.
    partial = OVER + [
        {"id": "nt", "data": {"crew_size": 4, "duration": 3, "start": "2026-03-01",
                              "name": "No trade"}},
        {"id": "nc", "data": {"trade": "Carpentry", "duration": 3, "start": "2026-03-01",
                              "name": "No crew"}},
    ]
    pc = levelling(partial, caps=CAP)["coverage"]
    check("activities with no trade or no crew size are counted out and NAMED",
          pc["without_demand"] == 2 and sorted(pc["without_demand_sample"]) == ["No crew", "No trade"],
          pc)
    check("  the names come from the module data, not the row id",
          all(not x.startswith("nt") and not x.startswith("nc")
              for x in pc["without_demand_sample"]),
          f"{pc['without_demand_sample']} — `list_records` keeps module fields under `data`, so a "
          f"bare row.get('name') returned the UUID and the sample read as populated nonsense")

    check("a refusal reports within_caps as None, never False",
          all(x["within_caps"] is None and x["coverage"] is None and x["over_cap"] == []
              for x in (no_caps, mismatch, no_crew, bad, empty)),
          "a levelling that did not run has not met the caps AND has not failed to meet them")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_levelling OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
