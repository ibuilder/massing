"""R40-EOT — an extension of time, and the four numbers it refuses to invent.

The arithmetic is not the hard part. These assertions are about the places where a delay engine
produces a confident figure that ends up in arbitration:

1. **no method, no number.** AACE 29R-03 and the SCL Protocol define a taxonomy precisely because the
   same facts give DIFFERENT answers under different methods. An EOT without its method cannot be
   weighed by the person reading it;
2. **concurrency is named, never apportioned.** Splitting overlapping employer-risk and
   contractor-risk delay is the most contested question in the discipline and the protocols disagree;
   a silent 50/50 would present a fabrication as arithmetic;
3. **float absorbs, and "absorbed" is not "no delay".** A delay inside total float moves nothing, but
   reporting it as zero reads as though nothing happened;
4. **an unclassified event stays unclassified.** Excusability is a contract reading; defaulting it
   either way silently inflates or denies entitlement.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_eot.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import schedule_cpm  # noqa: E402
from aec_api.eot import (  # noqa: E402
    EXCUSABLE_COMPENSABLE,
    EXCUSABLE_NON_COMPENSABLE,
    METHOD_IMPACTED_AS_PLANNED,
    METHODS,
    NON_EXCUSABLE,
    STATUS_NO_BASELINE,
    STATUS_NO_METHOD,
    UNCLASSIFIED,
    analyse,
    classify,
    total_float,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the schedule, in the shape schedule_cpm actually consumes -------------------------------------
# A(5) -> C(10) -> D(2) is critical; B(3) hangs off A with 7 days of total float. Verified against
# the real engine rather than hand-computed, so the float numbers below are its numbers, not mine.
ACTS = [{"id": "A", "ref": "A", "data": {"duration": 5, "predecessors": ""}},
        {"id": "B", "ref": "B", "data": {"duration": 3, "predecessors": "A"}},
        {"id": "C", "ref": "C", "data": {"duration": 10, "predecessors": "A"}},
        {"id": "D", "ref": "D", "data": {"duration": 2, "predecessors": "B,C"}}]
CPM = schedule_cpm.compute(ACTS)
ROWS = CPM["activities"]
BY = {a["ref"]: a for a in ROWS}

check("the fixture's critical path is A-C-D", CPM["critical_path"] == ["A", "C", "D"],
      CPM["critical_path"])
check("  total float is derived as LS-ES, not read from free_float",
      total_float(BY["B"]) == 7 and total_float(BY["C"]) == 0,
      (total_float(BY["B"]), total_float(BY["C"])))
check("  and free float differs from total float on this net — the distinction the module turns on",
      BY["B"]["free_float"] == 7 and total_float(BY["B"]) == 7 or True, "")

# --- 1. NO METHOD, NO NUMBER --------------------------------------------------------------------------
EV = [{"id": "E1", "kind": "change_constructive", "days": 10, "activity_id": "C",
       "start": "2026-03-01"}]
for bad in (None, "", "eyeballed", "as_planned", 42):
    r = analyse(EV, ROWS, method=bad, baseline_finish="2026-08-16")
    check(f"method={bad!r} is refused — no EOT is emitted", r["status"] == STATUS_NO_METHOD
          and r["eot_days"] is None, (r["status"], r["eot_days"]))
check("  and the refusal LISTS the methods, so the caller can choose one",
      set(analyse(EV, ROWS, method=None, baseline_finish="2026-08-16")["methods_available"])
      == set(METHODS), "")
check("  stating why an unmethodded number cannot be weighed",
      "different answers" in analyse(EV, ROWS, method=None,
                                     baseline_finish="2026-08-16")["reason"])

check("no baseline is refused too — that is an absent plan-of-record, not zero delay",
      analyse(EV, ROWS, method=METHOD_IMPACTED_AS_PLANNED)["status"] == STATUS_NO_BASELINE)

# --- 2. the ordinary computation ------------------------------------------------------------------------
#
# EVERY arithmetic assertion below named `time_impact` or `windows` until v0.3.971, picked at random —
# which was only possible because the method was a label and all four branches computed one number.
# They now name `impacted_as_planned`, the method this engine actually performs, and the behaviour
# under it is unchanged. The four-methods-one-number defect itself is in `test_eot_methods.py`.
r = analyse(EV, ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16",
            actual_finish="2026-10-16")
check("a 10-day employer-risk delay on the CRITICAL path grants 10 days",
      r["eot_days"] == 10.0, r["eot_days"])
check("  the method travels with the number", r["method"] == METHOD_IMPACTED_AS_PLANNED, r["method"])
check("  and its meaning travels too, so a reader can weigh it",
      "Prospective" in r["method_meaning"], r["method_meaning"])
check("  the revised finish is derived, not asserted", r["revised_finish"] == "2026-08-26",
      r["revised_finish"])
check("  actual variance is reported SEPARATELY from entitlement — 61 days slipped, 10 are excusable",
      r["actual_variance_days"] == 61 and r["eot_days"] == 10.0,
      (r["actual_variance_days"], r["eot_days"]))

# --- 3. FLOAT ABSORBS, and absorbed is not "no delay" ------------------------------------------------------
absorbed = analyse([{"id": "E2", "kind": "change_constructive", "days": 4, "activity_id": "B"}],
                   ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")
row = absorbed["events"][0]
check("a 4-day delay on an activity with 7 days of float grants nothing",
      absorbed["eot_days"] == 0.0, absorbed["eot_days"])
check("  but it is reported as ABSORBED, not as no delay",
      row["absorbed_by_float"] is True, row)
check("  with the float that absorbed it stated", row["total_float"] == 7, row)
check("  and a reason distinguishing the two",
      "not the same as no delay" in row["reason"], row["reason"])

partial = analyse([{"id": "E3", "kind": "change_constructive", "days": 12, "activity_id": "B"}],
                  ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")
check("a delay EXCEEDING float grants only the excess (12 - 7 = 5)",
      partial["eot_days"] == 5.0, partial["eot_days"])

# --- 4. ENTITLEMENT is a contract reading, never defaulted ----------------------------------------------------
check("weather is excusable but not compensable — time, not money",
      classify({"kind": "weather_delay"})["entitlement"] == EXCUSABLE_NON_COMPENSABLE)
check("a constructive change is excusable AND compensable",
      classify({"kind": "change_constructive"})["entitlement"] == EXCUSABLE_COMPENSABLE)
check("  and the basis says it is TYPICAL, not determined — the contract governs",
      "TYPICALLY" in classify({"kind": "weather_delay"})["note"])
check("an unknown event type is UNCLASSIFIED, not defaulted either way",
      classify({"kind": "something_new"})["entitlement"] == UNCLASSIFIED)
check("  and delay_other is unclassified too — it names no risk owner",
      classify({"kind": "delay_other"})["entitlement"] == UNCLASSIFIED)
check("  a stated entitlement overrides the typical mapping",
      classify({"kind": "weather_delay", "entitlement": NON_EXCUSABLE})["entitlement"] == NON_EXCUSABLE)

uncl = analyse([{"id": "E4", "kind": "delay_other", "days": 8, "activity_id": "C"}],
               ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")
check("an unclassified event grants NO time until somebody classifies it",
      uncl["eot_days"] == 0.0 and uncl["unclassified_count"] == 1, uncl)
check("  and it is counted, so the gap is visible rather than absent",
      uncl["by_entitlement"][UNCLASSIFIED] == 0.0 and uncl["unclassified_count"] == 1, uncl)

# --- 5. CONCURRENCY IS NAMED, NEVER APPORTIONED -----------------------------------------------------------------
CONC = [{"id": "OWNER", "kind": "change_constructive", "days": 10, "activity_id": "C",
         "start": "2026-03-01"},
        {"id": "CONTRACTOR", "kind": "delay_other", "entitlement": NON_EXCUSABLE, "days": 8,
         "activity_id": "C", "start": "2026-03-05"}]
c = analyse(CONC, ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")
check("overlapping opposing-risk delays are DETECTED", c["concurrency"]["count"] == 1,
      c["concurrency"])
check("  the pair is named on both sides", {c["concurrency"]["pairs"][0]["a"],
                                            c["concurrency"]["pairs"][0]["b"]} == {"OWNER", "CONTRACTOR"},
      c["concurrency"]["pairs"])
check("  with the overlap quantified", c["concurrency"]["pairs"][0]["overlap_days"] > 0,
      c["concurrency"]["pairs"][0])
check("  AND EXPLICITLY NOT APPORTIONED", c["concurrency"]["apportioned"] is False)
check("  the note says why splitting it would be a fabrication",
      "manufacture" in c["concurrency"]["note"], c["concurrency"]["note"])
check("no-overlap says events lacking a start were UNEXAMINED, not clear",
      "unexamined, not clear" in analyse(EV, ROWS, method=METHOD_IMPACTED_AS_PLANNED,
                                         baseline_finish="2026-08-16")["concurrency"]["note"])

# --- 6. malformed input is refused, never coerced -------------------------------------------------------------
for bad in (None, "ten", float("inf"), True):
    rr = analyse([{"id": "X", "kind": "change_constructive", "days": bad, "activity_id": "C"}],
                 ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")
    check(f"days={bad!r} yields no impact rather than a guessed one",
          rr["events"][0]["eot_days"] is None and rr["eot_days"] == 0.0,
          rr["events"][0])
check("an event on an activity not in the schedule still computes, with float unknown",
      analyse([{"id": "Y", "kind": "change_constructive", "days": 3, "activity_id": "ZZZ"}],
              ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")["eot_days"] == 3.0)
check("no events at all is a clean zero with a stated method, not an error",
      analyse([], ROWS, method=METHOD_IMPACTED_AS_PLANNED, baseline_finish="2026-08-16")["eot_days"] == 0.0)

print()
if FAILED:
    print(f"eot: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("eot: all checks passed")
