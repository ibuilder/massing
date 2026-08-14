"""R45-SCHED-DEDUPE ② — Monte Carlo schedule risk on the real network.

The one true overlap in the ring: `aec_api/schedule_risk.py` also runs a Monte Carlo. These assertions
cover what the vendored engine gives that ours cannot, and the calibration of ours that must survive
the swap.
"""
from __future__ import annotations

import json
from datetime import date

from aec_api import schedule_risk as ours
from aec_api.schedule_risk_mc import PPC_TARGET, ppc_tail_factor, risk

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    # `duration`, not `duration_days` — see test_schedule_health for the release this cost.
    return {"id": i, "ref": i, "title": i,
            "data": {"duration": days, "start": "2026-03-02", "predecessors": preds}}


#: Five 20-day activities in a chain: 100 working days, which is ~140 calendar days. Long enough that
#: the working-day / calendar-day distinction is unmissable rather than a rounding argument.
CHAIN = [act(c, 20, p) for c, p in (("a", ""), ("b", "a"), ("c", "b"), ("d", "c"), ("e", "d"))]


def main() -> int:
    r = risk(CHAIN, iterations=500)
    check("the chain reaches the vendored simulator",
          r["available"] and r["iterations"] == 500, f"{r['distribution']}, seed {r['seed']}")

    check("the result survives json.dumps", _serialises(r), "a route has to be able to return it")

    # --- what the vendored engine gives that ours cannot -----------------------------------------
    check("percentiles are ordered and distinct — the simulation actually varies",
          r["p10"] < r["p50"] < r["p80"] <= r["p90"],
          f"P10 {r['p10']} < P50 {r['p50']} < P80 {r['p80']} <= P90 {r['p90']}")

    # The direct answer to "how likely is the date on the programme". Ours reports no such number.
    conf = r["confidence_in_deterministic"]
    check("confidence in the CPM date is reported, and it is not 1.0 on a risky chain",
          conf is not None and 0.0 < conf < 0.5,
          f"{conf:.3f} — the programme date has about a {conf * 100:.0f}% chance")

    sens = [a["duration_sensitivity"] for a in r["most_critical"]]
    check("duration sensitivity is reported per activity, not just criticality",
          any(s > 0 for s in sens),
          "criticality says how OFTEN an activity was on the path; sensitivity says whether its "
          "duration MOVES the finish")

    # --- the finding: ours computes its dates on a different calendar ------------------------------
    #
    # `schedule_risk` converts a duration to a date with `start + timedelta(days=...)` — CALENDAR days.
    # The vendored engine walks a work calendar. Both numbers appear in the same portal.
    o = ours.simulate(CHAIN, iterations=500)
    theirs_p80 = date.fromisoformat(r["p80"])
    ours_p80 = date.fromisoformat(o["p80_finish"]) if o.get("p80_finish") else None
    gap = (theirs_p80 - ours_p80).days if ours_p80 else None
    check("the two engines disagree, and the gap is the weekend arithmetic",
          gap is not None and gap > 20,
          f"ours {ours_p80} (calendar days) vs vendored {theirs_p80} (working days) = {gap} days apart")

    check("...and ours is the one that counts Saturdays",
          ours_p80 is not None and ours_p80 < theirs_p80,
          "a P80 that treats weekends as working days is not conservative, it is a different question")

    # --- our PPC calibration, which must survive the swap -------------------------------------------
    check("PPC below target widens the tail; above it narrows",
          ppc_tail_factor(60) > ppc_tail_factor(PPC_TARGET) > ppc_tail_factor(95),
          f"60%={ppc_tail_factor(60):.3f}  80%={ppc_tail_factor(PPC_TARGET):.3f}  "
          f"95%={ppc_tail_factor(95):.3f}")

    check("...and no PPC leaves the engine default untouched",
          ppc_tail_factor(None) == ppc_tail_factor(PPC_TARGET),
          "80% is Last Planner's target, so it is the neutral point by definition")

    check("a wild PPC cannot produce a wild forecast — the scale is clamped",
          0.5 < ppc_tail_factor(-500) < 4.0 and ppc_tail_factor(500) > 1.0,
          f"PPC -500 -> {ppc_tail_factor(-500):.3f}, PPC 500 -> {ppc_tail_factor(500):.3f}")

    unreliable = risk(CHAIN, iterations=500, ppc_pct=50)
    check("a less reliable team gets a later P80 — the calibration reaches the engine",
          unreliable["p80"] > r["p80"],
          f"PPC 50% -> {unreliable['p80']} vs uncalibrated {r['p80']}")

    # --- determinism ---------------------------------------------------------------------------------
    check("a fixed seed gives the same forecast twice",
          risk(CHAIN, iterations=500)["p80"] == r["p80"],
          "a forecast that changes when nobody changed the plan is not one anyone can act on")

    # --- refusals -------------------------------------------------------------------------------------
    empty = risk([])
    check("no activities is refused", empty["available"] is False, empty["reason"])

    bad = risk(CHAIN, distribution="gaussian")
    check("an unknown distribution is refused and the valid ones listed",
          bad["available"] is False and "triangular" in bad["reason"], bad["reason"][:60])

    cyc = risk([act("a", 5, "c"), act("b", 5, "a"), act("c", 5, "b")])
    check("a cyclic network is refused with its cycle",
          cyc["available"] is False and bool(cyc.get("cycle")), f"cycle={cyc.get('cycle')}")

    check("every refusal reports percentiles as None, never a date",
          all(x["p80"] is None and x["confidence_in_deterministic"] is None
              for x in (empty, bad, cyc)),
          "an invented P80 is the whole hazard this module exists to avoid")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_risk_mc OK")
    return 0


def _serialises(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
