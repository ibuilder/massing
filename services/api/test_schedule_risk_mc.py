"""R45-SCHED-DEDUPE ② — Monte Carlo schedule risk on the real network.

The one true overlap in the ring: "aec_api/schedule_risk.py" also ran a Monte Carlo. These assertions
cover what the vendored engine gives that the deleted one could not, and the calibration that had to
survive the swap.

**The second engine was deleted in v0.3.972**, so the comparison below no longer runs live — it is
recorded instead, with the surviving half still measured. `test_schedule_risk_single.py` is the gate
that keeps it at one implementation.
"""
from __future__ import annotations

import json
from datetime import date

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

    # --- the finding that settled the overlap, now recorded rather than re-run ---------------------
    #
    # The deleted engine converted a duration to a date with `start + timedelta(days=...)` — CALENDAR
    # days — while the vendored one walks a work calendar. On THIS fixture it put the deterministic
    # finish on 2026-06-10 against 2026-07-17 here. Both numbers appeared in the same portal.
    #
    # Recorded as a constant because the module it measured no longer exists. Re-running it is not
    # possible and faking it would be worse; what IS still checkable is the surviving half, and that
    # is what the assertion below does — if this date ever moves, the recorded gap is stale too.
    DELETED_ENGINE_FINISH = date(2026, 6, 10)   # "schedule_risk.simulate", removed v0.3.972
    theirs_det = date.fromisoformat(r["deterministic_finish"])
    check("the surviving engine still finishes this chain on a working-day calendar",
          theirs_det == date(2026, 7, 17),
          f"{theirs_det} — 100 working days from 2026-03-02. The deleted engine said "
          f"{DELETED_ENGINE_FINISH}, {(theirs_det - DELETED_ENGINE_FINISH).days} days adrift, "
          "because it counted Saturdays")

    check("...and the recorded gap is the weekend arithmetic, not a rounding difference",
          (theirs_det - DELETED_ENGINE_FINISH).days > 20,
          "a P80 that treats weekends as working days is not conservative, it is a different "
          "question's answer")

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
