"""R45-SCHED-DEDUPE ② — the schedule-progress adapter.

Two things these assertions exist for, beyond "it runs":

* **The result must survive `json.dumps`.** The first draft returned `report.worst_slippage` straight
  through under a key named `worst_slippage_days`. That property returns an `ActivityProgress`
  dataclass, not a number — a route would have serialised it to garbage or 500'd, and no type
  annotation would have caught it because the adapter returns `dict[str, Any]`.
* **The engine's two honest-answer rules must survive the adapter**: BEI is `None` when nothing was
  due, and `behind` counts an activity that was due to start and never did.
"""
from __future__ import annotations

import json
from datetime import date

from aec_api import schedule_baselines, schedule_progress

_FAILURES: list[str] = []
_REAL_GET = schedule_baselines._get


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def stub_baseline(acts: dict | None) -> None:
    """Swap the baseline store. Restored in `main` so this file cannot leak into another suite."""
    schedule_baselines._get = (  # type: ignore[assignment]
        (lambda pid, bid: None) if acts is None else
        (lambda pid, bid: {"id": "b1", "name": "Bid", "captured_at": "2026-02-01",
                           "activities": acts}))


BASE = {
    "a": {"ref": "A10", "name": "Mobilise", "start": "2026-03-02", "finish": "2026-03-06"},
    "b": {"ref": "A20", "name": "Excavate", "start": "2026-03-09", "finish": "2026-03-20"},
}
#: `a` finished five days late; `b` was due to start on the 9th and never did.
ACTS = [
    {"id": "a", "ref": "A10", "title": "Mobilise",
     "data": {"duration": 5, "start": "2026-03-02",
              "actual_start": "2026-03-02", "actual_finish": "2026-03-11"}},
    {"id": "b", "ref": "A20", "title": "Excavate",
     "data": {"duration": 10, "predecessors": "a", "start": "2026-03-09"}},
]
DD = date(2026, 3, 25)


def main() -> int:
    try:
        stub_baseline(BASE)
        r = schedule_progress.progress(ACTS, "p1", data_date=DD)
        check("a project with a baseline reaches the engine",
              r["available"] and r["activity_count"] == 2,
              f"BEI {r['baseline_execution_index']}, {r['behind']} behind")

        # Same guard as test_schedule_health: `duration_days` is not the key schedule_engine reads,
        # and a fixture that silently defaults to 1-day tasks measures a schedule nobody described.
        # `a` is a 5-day task finishing 3 working days late; a defaulted fixture cannot produce that.
        check("the fixture's durations are actually read — not silently defaulted to 1 day",
              r["worst_slippage_days"] == 3,
              f"{r['worst_slippage_days']}d slip on a 5-day task with a 5-day baseline window")

        # The defect the first draft shipped: a dataclass under a key promising a number.
        try:
            json.dumps(r)
            ok = True
        except TypeError:
            ok = False
        check("the whole result survives json.dumps — a route can actually return it",
              ok, "worst_slippage is an ActivityProgress, not a number, and must be unpacked")

        check("...and the worst slip names its activity, not just a number",
              r["worst_slippage_days"] == 3 and r["worst_slippage_activity"] == "a",
              f"{r['worst_slippage_days']}d on {r['worst_slippage_activity']} — "
              "'3 days, and it is A10' is actionable where '3 days' is not")

        # --- the engine's honesty rules, preserved through the adapter --------------------------
        check("an activity due to start and never started counts as behind",
              r["not_started_but_due"] >= 1 and r["behind"] >= r["not_started_but_due"],
              f"{r['not_started_but_due']} due-not-started inside {r['behind']} behind — "
              "broader than DCMA 11, which only looks at finishes")

        # BEI = completed / should-have-completed. Nothing due yet => None, NOT 1.0.
        early = schedule_progress.progress(ACTS, "p1", data_date=date(2026, 1, 1))
        check("BEI is None when nothing was due — never 1.0",
              early["baseline_execution_index"] is None,
              "an empty ratio is no information; 1.0 puts a green tile on a project "
              "that has not started")

        check("...and it is a real number once work was due",
              isinstance(r["baseline_execution_index"], float) and 0 <= r["baseline_execution_index"] <= 1,
              f"{r['baseline_execution_index']} — the twin: without this, returning None always would pass above")

        # --- refusals ---------------------------------------------------------------------------
        stub_baseline(None)
        none = schedule_progress.progress(ACTS, "p1")
        check("a project with NO baseline is refused, not measured against itself",
              none["available"] is False and "against" in none["reason"],
              "comparing a schedule to its own current dates reports every activity on programme")

        stub_baseline({})
        empty_base = schedule_progress.progress(ACTS, "p1")
        check("an empty baseline is refused too", empty_base["available"] is False,
              empty_base["reason"][:60])

        stub_baseline(BASE)
        no_acts = schedule_progress.progress([], "p1")
        check("no activities is refused", no_acts["available"] is False, no_acts["reason"])

        check("every refusal reports counts as None, never 0",
              all(x["behind"] is None and x["baseline_execution_index"] is None
                  for x in (none, empty_base, no_acts)),
              "'nothing behind' and 'not measured' must not render alike")

        # --- the classification this module corrects ------------------------------------------------
        #
        # `progress_rollup` measures the BUILDING (as-built element presence by GlobalId); this
        # measures the SCHEDULE (activities against baseline dates). The R45 table called them one
        # overlap. If they ever really did overlap, this import would be the place it showed.
        import aec_api.progress_rollup as rollup
        check("the two 'progress' modules share no function name — they measure different objects",
              not ({n for n in dir(rollup) if not n.startswith("_")}
                   & {"baseline_execution_index", "build_report"}),
              "one is percent-complete of the building, the other is BEI of the schedule")
    finally:
        schedule_baselines._get = _REAL_GET  # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_progress OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
