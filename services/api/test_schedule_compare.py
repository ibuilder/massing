"""R45-SCHED-REACH ③ — the baseline-comparison adapter, and the refusal that makes it safe.

The R45 table recorded `compare` as blocked: the engine needs two *schedules* and a captured
baseline held two dates and a budget. The fix was in the snapshot, so the assertions that matter
here are about the snapshot boundary, not about the engine's diffing.

The one to read first is `a v1 baseline is REFUSED`. A pre-logic snapshot rebuilds without error —
into a set of 1-day tasks with no predecessors, i.e. a fully-parallel plan finishing almost
immediately — and the diff against the real schedule then reports a large delay, attributed with
complete confidence to logic nobody removed. Its twin below measures exactly how wrong that would
have been, so the refusal cannot be quietly relaxed by someone who thinks it is over-cautious.
"""
from __future__ import annotations

import json

from aec_api import schedule_baselines, schedule_compare

_FAILURES: list[str] = []
_REAL_GET = schedule_baselines._get


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "") -> dict:
    # `duration`, not `duration_days` — see test_schedule_health for the releases that cost.
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02"}}


#: The plan as committed: a 5-day, a 10-day and a 15-day activity in a chain.
BASE_ACTS = [act("a", 5), act("b", 10, "a"), act("c", 15, "b")]
#: The same chain today, with `b` grown from 10 days to 20. Ten working days later, and the cause is
#: a single activity's duration — the answer the whole module exists to produce.
CURR_ACTS = [act("a", 5), act("b", 20, "a"), act("c", 15, "b")]


def snapshot(records: list[dict], schema: int) -> dict:
    """A stored baseline in either schema, built the way `capture` builds one."""
    acts = {}
    for r in records:
        data = r["data"]
        frozen = {"ref": r["ref"], "name": r["title"], "start": data.get("start"),
                  "finish": None, "budget": None}
        if schema >= schedule_baselines.SCHEMA:
            frozen.update({k: data[k] for k in ("duration", "predecessors")
                           if data.get(k) not in (None, "")})
        acts[r["id"]] = frozen
    return {"id": "b1", "name": f"Bid (schema {schema})", "captured_at": "2026-02-01",
            "schema": schema, "activities": acts}


def stub(base: dict | None) -> None:
    schedule_baselines._get = lambda pid, bid: base  # type: ignore[assignment]


def main() -> int:
    try:
        # --- the reachability this item exists for ------------------------------------------------
        stub(snapshot(BASE_ACTS, 2))
        r = schedule_compare.compare(CURR_ACTS, "p1")
        check("a logic-carrying baseline is re-scheduled and reaches the vendored comparator",
              r["available"] and r["activity_count"] == 3,
              f"{r['baseline_finish']} -> {r['current_finish']}, "
              f"{r['finish_move_days']}d, match by {r['match_key']}")

        check("the result survives json.dumps — a route can return it",
              _serialises(r), "the whole Comparison, nested dataclasses and enums included")

        # --- the answer -------------------------------------------------------------------------
        check("the finish moved by the ten working days `b` grew by",
              r["finish_move_days"] == 14,
              f"{r['finish_move_days']} calendar days = 10 working days + 2 weekends")

        drive = r["driving_path"]
        check("THE INVARIANT: the contributions sum exactly to the finish move",
              drive["attribution_sums"]
              and sum(c["days"] for c in drive["attribution"]) == drive["finish_move_days"],
              f"{[(c['cause'], c['days']) for c in drive['attribution']]} = "
              f"{drive['finish_move_days']}d — parts that do not sum to the whole are an opinion "
              "with numbers attached, not evidence")

        check("...and it names the activity and the cause, not just a number",
              any(c["activity_id"] == "b" and c["cause"] == "duration_growth"
                  for c in drive["attribution"]),
              f"{[(c['activity_id'], c['cause']) for c in drive['attribution']]} — "
              "'14 days, and it is B, and it grew' is actionable where '14 days' is not")

        # --- the unit seam the invariant hides --------------------------------------------------
        #
        # The invariant above holds — but only because an UNEXPLAINED bucket absorbs the residual,
        # and "unexplained" is read by a human as a cause nobody has found. Here the residual is
        # four days of weekend: the engine's contributions are in working days and its total is in
        # calendar days. A planner would spend an afternoon looking for the missing four days.
        unexplained = sum(c["days"] for c in drive["attribution"] if c["cause"] == "unexplained")
        check("the UNEXPLAINED residual is exactly the calendar/working-day gap — not a mystery",
              unexplained == r["calendar_vs_working_gap_days"] == 4
              and r["finish_move_working_days"] == 10,
              f"{r['finish_move_days']}d calendar vs {r['finish_move_working_days']}d working = "
              f"{r['calendar_vs_working_gap_days']}d of weekend, reported as {unexplained}d "
              "'unexplained'; both numbers are now on the response so the reader can subtract it")

        b = next(a for a in r["activities"] if a["activity_id"] == "b")
        check("the changed activity is reported with both durations",
              b["baseline_duration"] == 10 and b["current_duration"] == 20
              and "duration_changed" in b["kinds"],
              f"{b['baseline_duration']}d -> {b['current_duration']}d, kinds {b['kinds']}")

        a = next(x for x in r["activities"] if x["activity_id"] == "a")
        check("...and an untouched activity is reported as unchanged, not omitted",
              a["kinds"] == ["unchanged"] and a["finish_shift_days"] == 0,
              "a diff that lists only what moved cannot show what was checked and did not")

        # --- THE REFUSAL, and the twin that measures what it prevents ------------------------------
        #
        # Read these two together. The first is the guard; the second is the number the guard is
        # worth. Without the second, "it refuses" is unfalsifiable — a refusal that costs nothing is
        # indistinguishable from over-caution, and the next reader relaxes it.
        stub(snapshot(BASE_ACTS, 1))
        v1 = schedule_compare.compare(CURR_ACTS, "p1")
        check("a v1 baseline is REFUSED — it carries dates but no logic",
              v1["available"] is False and "captured before logic" in v1["reason"],
              v1["reason"][:88])

        check("...and the refusal says the baseline is still good for variance",
              "variance" in v1["reason"],
              "the fix is 'capture a new one', not 'this baseline is broken'")

        check("...and it still reports WHICH baseline was refused",
              (v1.get("baseline") or {}).get("id") == "b1" and v1["baseline"]["has_logic"] is False,
              f"{v1.get('baseline')} — a caller can name it in the message it shows")

        # The twin. `to_records` is bypassed deliberately to build the network the refusal prevents.
        forced = [{"id": rid, "ref": a2["ref"], "title": a2["name"],
                   "data": {"name": a2["name"], "start": a2["start"]}}
                  for rid, a2 in snapshot(BASE_ACTS, 1)["activities"].items()]
        stub({**snapshot(BASE_ACTS, 1), "schema": 2,
              "activities": {r2["id"]: {"ref": r2["ref"], "name": r2["title"],
                                        "start": r2["data"]["start"], "finish": None,
                                        "budget": None} for r2 in forced}})
        wrong = schedule_compare.compare(CURR_ACTS, "p1")
        check("...and the twin: forced through, a v1 baseline reports a LARGE confident delay",
              wrong["available"] and wrong["finish_move_days"] > 40,
              f"{wrong['finish_move_days']}d against the real {r['finish_move_days']}d — "
              "every activity comes back as a 1-day task with no predecessors, so the plan 'finished' "
              "in a day and the whole job reads as slip")

        check("...attributed, with total confidence, to logic nobody added",
              any(c["cause"] in ("logic_added", "duration_growth")
                  for c in wrong["driving_path"]["attribution"])
              and wrong["driving_path"]["attribution_sums"],
              f"{[(c['activity_id'], c['cause'], c['days']) for c in wrong['driving_path']['attribution']]}"
              " — it sums, it names activities, and it is entirely an artefact of missing data")

        # --- matching -----------------------------------------------------------------------------
        stub(snapshot(BASE_ACTS, 2))
        by_code = schedule_compare.compare(CURR_ACTS, "p1", match="code")
        check("matching by the planner's code gives the same answer as by id here",
              by_code["available"] and by_code["match_key"] == "code"
              and by_code["finish_move_days"] == r["finish_move_days"],
              "both sides come from our own store, so ids are stable — the code path is for the "
              "activity that was deleted and re-created")

        bad_match = schedule_compare.compare(CURR_ACTS, "p1", match="name_and_wbs")
        check("an unsupported match key is refused and the valid ones listed",
              bad_match["available"] is False and "code" in bad_match["reason"],
              bad_match["reason"])

        # --- refusals -------------------------------------------------------------------------------
        stub(None)
        no_base = schedule_compare.compare(CURR_ACTS, "p1")
        check("no baseline at all is refused", no_base["available"] is False, no_base["reason"])

        stub({**snapshot(BASE_ACTS, 2), "activities": {}})
        empty_base = schedule_compare.compare(CURR_ACTS, "p1")
        check("an empty baseline is refused", empty_base["available"] is False,
              empty_base["reason"][:60])

        stub(snapshot(BASE_ACTS, 2))
        no_acts = schedule_compare.compare([], "p1")
        check("no current activities is refused", no_acts["available"] is False, no_acts["reason"])

        cyc = schedule_compare.compare([act("a", 5, "c"), act("b", 5, "a"), act("c", 5, "b")], "p1")
        check("a cyclic CURRENT schedule is refused with its cycle",
              cyc["available"] is False and bool(cyc.get("cycle")), f"cycle={cyc.get('cycle')}")

        stub(snapshot([act("a", 5, "c"), act("b", 5, "a"), act("c", 5, "b")], 2))
        cyc_base = schedule_compare.compare(CURR_ACTS, "p1")
        check("...and so is a cyclic BASELINE, named as the baseline's loop",
              cyc_base["available"] is False and "baseline" in cyc_base["reason"]
              and bool(cyc_base.get("cycle")),
              cyc_base["reason"])

        check("every refusal reports counts as None, never 0",
              all(x["finish_move_days"] is None and x["activity_count"] is None
                  and x["driving_path"] is None
                  for x in (v1, bad_match, no_base, empty_base, no_acts, cyc, cyc_base)),
              "'the schedule did not move' and 'nothing was compared' must not render alike")

        # --- the snapshot contract this item changed --------------------------------------------------
        check("a v2 snapshot round-trips back into records build_network can read",
              all(rec["data"].get("duration") for rec in
                  schedule_baselines.to_records(snapshot(BASE_ACTS, 2))),
              "the durations survive capture -> storage -> rebuild; without this the refusal above "
              "is the only branch that ever runs")

        check("...and progress is deliberately NOT frozen into a baseline",
              not (set(schedule_baselines._LOGIC_FIELDS)
                   & {"actual_start", "actual_finish", "percent", "remaining_duration"}),
              "a baseline that already knows how the job went under-reports every later slip by "
              "exactly the progress recorded on the day it was captured")
    finally:
        schedule_baselines._get = _REAL_GET  # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_compare OK")
    return 0


def _serialises(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
