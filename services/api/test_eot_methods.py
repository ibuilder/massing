"""R40-EOT ③ — the four methods gave one number, and the label said otherwise.

`eot.analyse()` validated `method` against a closed set, echoed it back in `method`,
`method_meaning` and `note`, and **never read it again**. Every branch computed the same sum, so
as-planned-vs-as-built and windows returned identical figures on identical facts — while the module's
own docstring says the taxonomy exists *because* they do not.

A required field that changes nothing is worse than no field: it tells the reader the number came
from a windows analysis when it came from adding up event durations. And this is the number the
entry itself says ends up in arbitration.

`test_eot.py` was the evidence rather than the guard. It reached for `METHOD_TIME_IMPACT` and
`METHOD_WINDOWS` at random for its arithmetic checks — which is only possible because the choice
could not matter.

The assertion that carries this file is **`the four methods do not all return one number`**. The
second is its twin: on a job where nothing was mitigated the two computed methods AGREE, so the
difference is the cap and not the arithmetic. Without the twin, a version that simply returned
different garbage per method would pass.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_eot_methods.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import schedule_cpm  # noqa: E402
from aec_api.eot import (  # noqa: E402
    BASIS_ADDITIVE,
    BASIS_END_STATES,
    BASIS_SERIES,
    METHOD_AS_PLANNED_VS_AS_BUILT,
    METHOD_BASIS,
    METHOD_IMPACTED_AS_PLANNED,
    METHOD_TIME_IMPACT,
    METHOD_WINDOWS,
    METHODS,
    STATUS_NEEDS_SERIES,
    STATUS_NO_ACTUAL,
    STATUS_OK,
    analyse,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail else ''}")
    if not ok:
        FAILED.append(label)


# A(5) -> C(10) -> D(2) critical; B(3) carries 7 days of total float. The engine's numbers, not mine.
ACTS = [{"id": "A", "ref": "A", "data": {"duration": 5, "predecessors": ""}},
        {"id": "B", "ref": "B", "data": {"duration": 3, "predecessors": "A"}},
        {"id": "C", "ref": "C", "data": {"duration": 10, "predecessors": "A"}},
        {"id": "D", "ref": "D", "data": {"duration": 2, "predecessors": "B,C"}}]
ROWS = schedule_cpm.compute(ACTS)["activities"]

#: One 10-day employer-risk event on the critical path. The job finished 4 days late, so the
#: contractor mitigated 6 of the 10 — the case the taxonomy exists for.
MITIGATED = [{"id": "E1", "kind": "change_constructive", "days": 10, "activity_id": "C",
              "start": "2026-03-01"}]
BASE, ACTUAL = "2026-08-16", "2026-08-20"


def main() -> int:
    # ================= THE DEFECT =================
    answers = {m: analyse(MITIGATED, ROWS, method=m, baseline_finish=BASE, actual_finish=ACTUAL)
               for m in METHODS}
    numbers = {m: r.get("eot_days") for m, r in answers.items()}

    check("the four methods do NOT all return one number",
          len({v for v in numbers.values() if v is not None}) > 1,
          f"{numbers} — until v0.3.971 every one of these was 10.0 and the method was a label")

    check("...and the two that this engine cannot perform return NO number rather than that one",
          all(numbers[m] is None for m in (METHOD_WINDOWS, METHOD_TIME_IMPACT)),
          "an additive sum wearing a windows label is the defect, not a fallback")

    # ================= THE TWO IT DOES PERFORM =================
    add = answers[METHOD_IMPACTED_AS_PLANNED]
    apab = answers[METHOD_AS_PLANNED_VS_AS_BUILT]

    check("impacted-as-planned grants the full inserted impact — 10 days",
          add["status"] == STATUS_OK and add["eot_days"] == 10.0
          and add["method_basis"] == BASIS_ADDITIVE,
          f"{add['eot_days']}d additive")

    check("as-planned-vs-as-built grants 4 — the job only moved 4",
          apab["status"] == STATUS_OK and apab["eot_days"] == 4.0
          and apab["method_basis"] == BASIS_END_STATES,
          f"{apab['eot_days']}d, capped at the actual slip of {apab['actual_variance_days']}d")

    check("...and the cap is REPORTED, not silent",
          apab["capped_by_actual_slip"] is True and apab["over_claimed_days"] == 6.0,
          f"6 of the 10 inserted days did not reach the finish — {apab['over_claimed_days']}d "
          "over-claimed. A contractor who mitigates is the ordinary case, and the additive method "
          "not seeing it is the published criticism of MIP 3.6, not a bug here")

    check("the additive method names its own over-claim rather than hiding it",
          add["over_claimed_days"] == 6.0 and add["capped_by_actual_slip"] is False,
          f"{add['over_claimed_days']}d claimed beyond what the job actually moved — reported so a "
          "reviewer can see the method's weakness on THIS job instead of reading it in a textbook")

    # --- THE TWIN: the difference is the CAP, not different arithmetic ------------------------------
    unmitigated = {m: analyse(MITIGATED, ROWS, method=m, baseline_finish=BASE,
                              actual_finish="2026-10-16")
                   for m in (METHOD_IMPACTED_AS_PLANNED, METHOD_AS_PLANNED_VS_AS_BUILT)}
    check("on a job that was NOT mitigated the two methods AGREE — the twin",
          unmitigated[METHOD_IMPACTED_AS_PLANNED]["eot_days"]
          == unmitigated[METHOD_AS_PLANNED_VS_AS_BUILT]["eot_days"] == 10.0,
          "61 days of slip, 10 of them attributed: the cap does not bind, so both give 10. Without "
          "this, a version returning different garbage per method would pass the check above")

    check("...and the unattributed slip is named, never granted",
          unmitigated[METHOD_AS_PLANNED_VS_AS_BUILT]["unattributed_slip_days"] == 51.0,
          "51 of the 61 days have no event explaining them. Handing them to either party would be "
          "an entitlement finding nobody demonstrated")

    # ================= THE TWO IT REFUSES =================
    for m in (METHOD_WINDOWS, METHOD_TIME_IMPACT):
        r = answers[m]
        check(f"{m} is refused, with the reason it cannot be run from one snapshot",
              r["status"] == STATUS_NEEDS_SERIES and r["method_basis"] == BASIS_SERIES
              and "series" in r["reason"], r["reason"][:90])

    check("windows names the route that DOES perform it",
          "schedule/windows" in (answers[METHOD_WINDOWS]["performed_by"] or ""),
          answers[METHOD_WINDOWS]["performed_by"])

    check("...and time-impact admits nothing performs it yet, rather than pointing somewhere wrong",
          answers[METHOD_TIME_IMPACT]["performed_by"] is None,
          "a route that does not do what its name says is how this defect started")

    # ================= the input each method actually needs =================
    no_actual = analyse(MITIGATED, ROWS, method=METHOD_AS_PLANNED_VS_AS_BUILT, baseline_finish=BASE)
    check("as-planned-vs-as-built without an as-built finish is refused, not defaulted to additive",
          no_actual["status"] == STATUS_NO_ACTUAL and no_actual["eot_days"] is None,
          "falling back would answer the additive question under this method's name — which is "
          "exactly the substitution being fixed")

    check("...while impacted-as-planned needs no actual finish, because it is prospective",
          analyse(MITIGATED, ROWS, method=METHOD_IMPACTED_AS_PLANNED,
                  baseline_finish=BASE)["eot_days"] == 10.0,
          "the two methods differ in their INPUTS as well as their arithmetic; that is what makes "
          "them different methods rather than different labels")

    # ================= the basis map is closed over the method set =================
    check("every declared method states what this engine does under it",
          set(METHOD_BASIS) == set(METHODS),
          "a method with no declared basis would fall through to whatever the last branch was")

    check("the method still travels with the number",
          all(r.get("method") == m for m, r in answers.items()),
          "the original design was right that the label must travel; the defect was that it was "
          "ONLY a label")

    print()
    if FAILED:
        print(f"eot_methods: {len(FAILED)} FAILED — {FAILED}")
        return 1
    print("eot_methods: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
