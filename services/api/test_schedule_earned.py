"""R46 ④ — Earned Schedule, and the terminal defect in SPI that it exists to fix.

The assertion to read is **`a FINISHED-LATE project reads SPI(t) below 1.0`**. Classic
`SPI = EV / PV` converges on exactly 1.0 as a project completes, whatever the dates did — it does not
degrade, it arrives at "perfectly on schedule" for a job that finished late. Measured here on a
schedule that ran over, so the claim is a number rather than a citation.

The second is that this method works on a **schema-1** baseline. `compare`, `windows` and `modelled`
all refuse those; Earned Schedule needs only dates, so it is the one method on the baseline library
that covers every snapshot ever captured. Refusing them here would be a refusal the data does not
require.
"""
from __future__ import annotations

import json
from datetime import date

from aec_api import schedule_baselines, schedule_earned

_FAILURES: list[str] = []
_REAL_GET = schedule_baselines._get


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(i: str, days: int, preds: str = "", **extra) -> dict:
    return {"id": i, "ref": i.upper(), "title": f"Activity {i}",
            "data": {"duration": days, "predecessors": preds, "start": "2026-03-02", **extra}}


#: Baseline: three activities across March. Stored as plain dates — no logic, i.e. a schema-1
#: snapshot, which is exactly what this method is able to use.
BASE = {"id": "b1", "name": "GMP", "captured_at": "2026-02-01", "schema": 1, "activities": {
    "a": {"ref": "A", "name": "Mobilise", "start": "2026-03-02", "finish": "2026-03-06"},
    "b": {"ref": "B", "name": "Excavate", "start": "2026-03-09", "finish": "2026-03-20"},
    "c": {"ref": "C", "name": "Foundations", "start": "2026-03-23", "finish": "2026-04-10"},
}}


def stub(base: dict | None) -> None:
    schedule_baselines._get = lambda pid, bid: base          # type: ignore[assignment]


def main() -> int:
    try:
        # --- a project part-done and running late --------------------------------------------------
        stub(BASE)
        late = [
            act("a", 5, actual_start="2026-03-02", actual_finish="2026-03-06", percent=100),
            act("b", 10, "a", actual_start="2026-03-09", percent=50),
            act("c", 15, "b"),
        ]
        r = schedule_earned.earned(late, "p1", data_date=date(2026, 4, 3))
        check("the live schedule and a captured baseline reach the engine",
              r["available"] and r["planned_duration_days"] > 0,
              f"AT {r['actual_time_days']}d, ES {r['earned_days']}d of "
              f"{r['planned_duration_days']}d planned")

        check("the result survives json.dumps", _ser(r), "a route has to return it")

        check("...and it works on a SCHEMA-1 baseline, unlike every other method built this week",
              r["baseline"]["schema"] == 1 and r["baseline"]["has_logic"] is False,
              "compare, windows and modelled all refuse these; Earned Schedule needs only dates, "
              "so it covers every snapshot ever captured")

        # --- THE defect this exists to fix ------------------------------------------------------------
        check("a project that has earned less than the elapsed time reads BEHIND",
              r["schedule_variance_days"] < 0 and r["performance_index"] < 1.0,
              f"SV(t) {r['schedule_variance_days']}d, SPI(t) {r['performance_index']} — "
              "ES is where the baseline curve says this much earned work sits; AT is how long it "
              "has actually taken")

        # The terminal case. Everything complete, but finished after the baseline ran out: classic
        # SPI = EV/PV is exactly 1.0 here because EV converges on PV at completion regardless of
        # dates. SPI(t) does not, and that is the whole argument for the metric.
        done_late = [
            act("a", 5, actual_start="2026-03-02", actual_finish="2026-03-06", percent=100),
            act("b", 10, "a", actual_start="2026-03-09", actual_finish="2026-04-03", percent=100),
            act("c", 15, "b", actual_start="2026-04-06", actual_finish="2026-05-15", percent=100),
        ]
        fin = schedule_earned.earned(done_late, "p1", data_date=date(2026, 5, 15))
        check("a FINISHED-LATE project reads SPI(t) below 1.0",
              fin["available"] and fin["performance_index"] < 1.0
              and fin["schedule_variance_days"] < 0,
              f"SPI(t) {fin['performance_index']} on a job that finished {abs(fin['schedule_variance_days'])} "
              "working days past its baseline. Classic SPI = EV/PV is exactly 1.0 here, because EV "
              "converges on PV at completion whatever the dates did — it does not degrade, it "
              "arrives at 'perfectly on schedule'")

        # --- the twin: on plan reads on plan -----------------------------------------------------------
        on_time = [
            act("a", 5, actual_start="2026-03-02", actual_finish="2026-03-06", percent=100),
            act("b", 10, "a", actual_start="2026-03-09", actual_finish="2026-03-20", percent=100),
            act("c", 15, "b", actual_start="2026-03-23", actual_finish="2026-04-10", percent=100),
        ]
        ok = schedule_earned.earned(on_time, "p1", data_date=date(2026, 4, 10))
        check("...and a project that ran to plan does NOT read behind — the twin",
              ok["available"] and ok["performance_index"] >= 0.98,
              f"SPI(t) {ok['performance_index']} — without this, an index that was always below 1.0 "
              "would look like a finding on every project")

        # --- scope not in the baseline is excluded and counted -------------------------------------------
        with_extra = late + [act("z", 8, "c", percent=100)]
        ex = schedule_earned.earned(with_extra, "p1", data_date=date(2026, 4, 3))
        check("work added after the baseline is EXCLUDED, and counted",
              ex["available"] and ex["unbaselined_activities"] == 1
              and ex["earned_days"] == r["earned_days"],
              "counting progress on work the plan never contained inflates the index for doing "
              "unplanned things; the count says how much was set aside")

        # --- units --------------------------------------------------------------------------------------
        check("everything is in WORKING days, and says so",
              r["unit"] == "working days",
              "a schedule metric in calendar days rewards a project for where its weekends fell — "
              "the same axis error that made concurrency go negative in schedule_modelled")

        # --- refusals -----------------------------------------------------------------------------------
        stub(None)
        no_base = schedule_earned.earned(late, "p1")
        check("no baseline is refused", no_base["available"] is False and "without a plan" in no_base["reason"],
              no_base["reason"][:70])

        stub(BASE)
        no_acts = schedule_earned.earned([], "p1")
        check("no activities is refused", no_acts["available"] is False, no_acts["reason"])

        stub({**BASE, "activities": {"x": {"ref": "X", "name": "n", "start": None, "finish": None}}})
        undated = schedule_earned.earned(late, "p1")
        check("a baseline whose activities carry no dates is refused, and counts them",
              undated["available"] is False and undated.get("undated") == 1,
              undated["reason"][:72])

        stub(BASE)
        disjoint = schedule_earned.earned([act("q", 5), act("r", 5, "q")], "p1")
        check("a schedule sharing no ids with the baseline is refused, with the likely cause",
              disjoint["available"] is False and "re-imported" in disjoint["reason"],
              disjoint["reason"][:88])

        check("...and the refusal is OUR sentence, not the exception's text",
              "EarnedScheduleError" not in disjoint["reason"],
              "`str(exc)` on a response path is the shape gated in v0.3.962")

        check("every refusal reports the index as None, never 1.0",
              all(x["performance_index"] is None and x["schedule_variance_days"] is None
                  for x in (no_base, no_acts, undated, disjoint)),
              "1.0 means 'exactly on schedule' — the single most misleading value to invent here")
    finally:
        schedule_baselines._get = _REAL_GET                  # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_earned OK")
    return 0


def _ser(obj: object) -> bool:
    try:
        json.dumps(obj)
    except TypeError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
