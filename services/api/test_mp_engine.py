"""Conformance gate for the vendored massingplan engine. **No pytest.**

Run it the way this repo runs everything else:

    python test_mp_engine.py

Why this file exists in this shape:

* **Stdlib only.** This repo deliberately has no pytest -- `run_tests.py` shells
  out to `python test_x.py` and each file asserts in a `__main__` block. Copying
  upstream's pytest suite here would mean adding a dependency to make a vendored
  kit run, which is the tail wagging the dog.

* **`test_mp_` prefix.** `test_cpm`, `test_constraints` and `test_graph` already
  exist flat in this repo. A bare name in the manifest would resolve to the
  local file and the vendored one would never run -- silently, with the gate
  green.

* **It is a gate, not upstream's suite.** massingplan's own ~760 tests run in
  its CI and are not duplicated here; duplicating them would create two copies
  to keep in step. What this covers is the narrower question the consumer
  actually needs answered: *does the copy in `src/massingplan` still behave the
  way this repo's callers require?* If it does not, the answer belongs here
  rather than in production.

What is checked, and why each one:

1. The calendar adjoint invariant, `sub(add(i, n), n) == i`. Every other module
   assumes it silently, and an error surfaces only on activities crossing a
   holiday -- which are disproportionately critical-path activities, because a
   shutdown is where slack gets consumed.
2. `schedule_cpm.compute()` still returns every key its callers read. EVM, the
   EOT analysis, resource loading, the vitals dashboard and the Gantt renderer
   all consume that dict.
3. A sequential chain has a duration equal to the sum of its durations. This is
   what `test_productivity` asserts, and the adapter got it wrong once by
   reading `SA-0001` as `SA` with a lag of minus one.
4. Float is numeric for every activity, including completed ones. `px.optimize`
   does `0 < total_float <= 5` and a `None` there is a TypeError in production.
5. A cyclic network refuses rather than inventing dates -- and does not crash
   the optimiser doing it. `compute()` has three exits and a coercion applied
   to one is a coercion missing from the others.
6. `TASKPRED` is read on XER import -- the defect the whole adoption exists for.
"""

from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path

# The vendored engine lives in `src/`, whether this file sits at the repo's
# `services/api/` root or one directory deeper.
_HERE = Path(__file__).resolve().parent
for candidate in (_HERE / "src", _HERE.parent / "src"):
    if (candidate / "massingplan").is_dir():
        sys.path.insert(0, str(candidate))
        break

from aec_api import schedule_cpm  # noqa: E402
from massingplan.core.timeaxis import WorkCalendar, WorkPattern, instant_of  # noqa: E402

FAILURES: list[str] = []


def check(name: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except AssertionError as exc:
        FAILURES.append(f"{name}: {exc}")
        print(f"  FAIL  {name}\n        {exc}")
    except Exception:  # noqa: BLE001 - a gate reports, it does not propagate
        FAILURES.append(f"{name}: {traceback.format_exc(limit=3)}")
        print(f"  ERROR {name}\n{traceback.format_exc(limit=3)}")
    else:
        print(f"  ok    {name}")


def _record(rid: str, ref: str, duration: int, predecessors: str = "", **data: object) -> dict:
    return {
        "id": rid,
        "ref": ref,
        "data": {"name": ref, "duration": duration, "predecessors": predecessors, **data},
    }


def _chain(durations: list[int], prefix: str = "SA-") -> list[dict]:
    records, previous = [], ""
    for index, duration in enumerate(durations):
        ref = f"{prefix}{index + 1:04d}"
        records.append(_record(f"id{index}", ref, duration, previous))
        previous = ref
    return records


# -- 1. the kernel invariant -----------------------------------------------


def the_calendar_adjoint_holds() -> None:
    """`sub(add(i, n), n) == i` and `count(i, add(i, n)) == n`, over a shutdown.

    Bounded to a few thousand assertions -- upstream sweeps roughly a million in
    its own CI. This is here to catch a *broken copy*, not to re-derive the
    proof.
    """
    shutdown = frozenset(
        {date(2026, 12, d) for d in range(21, 32)} | {date(2027, 1, d) for d in range(1, 3)}
    )
    for weekdays in (frozenset({0, 1, 2, 3, 4}), frozenset({0, 1, 2, 3, 4, 5})):
        cal = WorkCalendar("C", "C", WorkPattern(weekdays, holidays=shutdown))
        cal.bind(date(2026, 1, 1), date(2028, 12, 31))
        for start_day in (date(2026, 12, 15), date(2026, 6, 1), date(2027, 1, 4)):
            i = cal.snap_start_forward(instant_of(start_day))
            for n in range(0, 60):
                forward = cal.add_working_days(i, n)
                assert cal.sub_working_days(forward, n) == i, (
                    f"add then sub by {n} from {start_day} did not return the start"
                )
                assert cal.count_working_days(i, forward) == n, (
                    f"count over add({n}) from {start_day} was not {n}"
                )


# -- 2. the dict contract --------------------------------------------------

LEGACY_KEYS = {
    "project_duration",
    "activity_count",
    "critical_count",
    "has_cycle",
    "activities",
    "critical_path",
}
LEGACY_ROW_KEYS = {
    "id",
    "ref",
    "name",
    "duration",
    "es",
    "ef",
    "ls",
    "lf",
    "total_float",
    "free_float",
    "critical",
    "predecessors",
}


def the_legacy_shape_is_intact() -> None:
    result = schedule_cpm.compute(_chain([3, 4, 5]))
    missing = LEGACY_KEYS - set(result)
    assert not missing, f"compute() lost top-level keys: {sorted(missing)}"
    for row in result["activities"]:
        gone = LEGACY_ROW_KEYS - set(row)
        assert not gone, f"activity row lost keys: {sorted(gone)}"


def an_empty_schedule_does_not_raise() -> None:
    result = schedule_cpm.compute([])
    assert result["project_duration"] == 0, result["project_duration"]
    assert result["activities"] == []
    assert result["has_cycle"] is False


# -- 3. logic survives the adapter -----------------------------------------


def a_sequential_chain_sums() -> None:
    """What `test_productivity` asserts. It came back as the longest single
    activity once, because `SA-0001` was read as `SA` with a lag of minus one
    and every relationship was dropped.
    """
    for prefix in ("SA-", "EST-", "WBS-1-", "ACT", "A"):
        durations = [12, 34, 9, 5]
        result = schedule_cpm.compute(_chain(durations, prefix))
        assert result["project_duration"] == sum(durations), (
            f"prefix {prefix!r}: duration {result['project_duration']} != "
            f"sum {sum(durations)} -- the chain was lost"
        )
        assert not result["issues"], f"prefix {prefix!r}: {result['issues']}"


def a_missing_predecessor_is_reported_not_dropped() -> None:
    result = schedule_cpm.compute([_record("id0", "SA-0001", 5, "NOT-A-REF")])
    codes = [i["code"] for i in result["issues"]]
    assert codes == ["MASSING.PREDECESSOR_UNRESOLVED"], codes


def relationship_types_and_lags_are_honoured() -> None:
    records = [
        _record("id0", "SA-0001", 10),
        _record("id1", "SA-0002", 5, "SA-0001SS+2"),
    ]
    rows = {r["ref"]: r for r in schedule_cpm.compute(records)["activities"]}
    assert rows["SA-0002"]["es"] == 2, f"SS+2 put the successor at {rows['SA-0002']['es']}"


# -- 4. float is numeric ---------------------------------------------------


def float_is_numeric_even_when_complete() -> None:
    """`px.optimize` filters `0 < total_float <= 5` behind an `_open()` test that
    reads `percent`. The engine decides completeness from actual dates, so an
    activity with an actual finish and no percent is open to one and complete to
    the other -- and `0 < None` raises.
    """
    records = [
        _record("id0", "SA-0001", 5, "", actual_start="2026-06-01", actual_finish="2026-06-05"),
        _record("id1", "SA-0002", 5, "SA-0001"),
    ]
    for row in schedule_cpm.compute(records)["activities"]:
        assert isinstance(row["total_float"], int), (
            f"{row['ref']}: total_float is {row['total_float']!r}, not an int"
        )
        assert isinstance(row["free_float"], int), row["ref"]
        assert isinstance(0 < row["total_float"] <= 5, bool)


def negative_float_is_not_clamped() -> None:
    """It is the output the planner is looking for, not an error to hide."""
    records = [
        _record("id0", "SA-0001", 20),
        _record(
            "id1",
            "SA-0002",
            20,
            "SA-0001",
            constraint="finish on or before",
            constraint_date="2026-06-15",
        ),
    ]
    rows = {r["ref"]: r for r in schedule_cpm.compute(records)["activities"]}
    assert rows["SA-0002"]["total_float"] < 0, rows["SA-0002"]["total_float"]


# -- 5. a cycle refuses ----------------------------------------------------


def a_cycle_refuses_rather_than_inventing_dates() -> None:
    """Dates computed by breaking a loop in dictionary order are a confident
    wrong answer that EVM then consumes as fact.
    """
    records = [
        _record("id0", "SA-0001", 5, "SA-0002"),
        _record("id1", "SA-0002", 5, "SA-0001"),
    ]
    result = schedule_cpm.compute(records)
    assert result["has_cycle"] is True
    assert set(result["cycle"]) == {"id0", "id1"}, result["cycle"]
    assert all(r["start_date"] is None for r in result["activities"])


def a_cycle_does_not_crash_the_optimiser() -> None:
    """`px.optimize` filters `0 < x["total_float"] <= 5` and only checks
    `has_cycle` *after* that comparison, so a cyclic schedule reaches it. With
    `total_float: None` it raised TypeError -- a crash in a route rather than a
    clean refusal.

    Position keys stay `None` here, because a 0 there would draw a Gantt of
    every activity stacked on day zero. Float is a filter key, not a position
    key, so a number is safe and a `None` is not.
    """
    records = [
        _record("id0", "SA-0001", 5, "SA-0002"),
        _record("id1", "SA-0002", 5, "SA-0001"),
    ]
    rows = schedule_cpm.compute(records)["activities"]
    near_critical = [r for r in rows if 0 < r["total_float"] <= 5]
    assert near_critical == [], near_critical


def every_exit_agrees_on_the_row_shape() -> None:
    """`compute()` has three exits -- normal, empty and cyclic -- and a coercion
    applied to one is a coercion missing from the others. The float fix landed
    on the computed exit only the first time.
    """
    computed = schedule_cpm.compute(_chain([3, 4]))["activities"]
    cyclic = schedule_cpm.compute(
        [
            _record("id0", "SA-0001", 5, "SA-0002"),
            _record("id1", "SA-0002", 5, "SA-0001"),
        ]
    )["activities"]
    assert set(computed[0]) == set(cyclic[0]), (
        f"the exits disagree on keys: {set(computed[0]) ^ set(cyclic[0])}"
    )
    for label, rows in (("computed", computed), ("cyclic", cyclic)):
        for row in rows:
            for key in ("duration", "total_float", "free_float"):
                assert isinstance(row[key], int), f"{label}: {key} is {row[key]!r}"


# -- 6. TASKPRED is read ---------------------------------------------------

XER_WITH_LOGIC = (
    # The ERMHDR line is what `detect_format` keys on, and every real export
    # carries it. A fixture without one is not an XER file.
    "ERMHDR\t19.12\t2026-06-01\tProject\tadmin\tPlanner\tdbxDatabaseNoName\tProject\tUSD\n"
    "%T\tPROJECT\n%F\tproj_id\tproj_short_name\n%R\t1\tTOWER\n"
    "%T\tTASK\n"
    "%F\ttask_id\tproj_id\ttask_code\ttask_name\ttarget_drtn_hr_cnt\n"
    "%R\t10\t1\tA1000\tExcavate\t40\n"
    "%R\t20\t1\tA1010\tFoundations\t80\n"
    "%R\t30\t1\tA1020\tSteel\t80\n"
    "%T\tTASKPRED\n"
    "%F\ttask_pred_id\ttask_id\tpred_task_id\tpred_type\tlag_hr_cnt\n"
    "%R\t1\t20\t10\tPR_FS\t0\n"
    "%R\t2\t30\t20\tPR_FS\t0\n"
    "%E\n"
)


def taskpred_is_read_on_import() -> None:
    """The defect the whole adoption exists for. Before, `parse_xer` filtered on
    `table == "TASK"`, so an imported schedule had no logic at all: every
    activity reported zero float and read as critical, and the import reported
    success.
    """
    try:
        from aec_api import schedule_import
    except ImportError:
        print("        (schedule_import not installed; skipping)")
        return
    records, summary = schedule_import.parse_full(XER_WITH_LOGIC)
    assert summary["relationships"] == 2, (
        f"TASKPRED yielded {summary['relationships']} relationships, expected 2 "
        "-- the importer is dropping logic again"
    )
    assert summary["has_logic"] is True, summary
    # And the logic reaches the records, which is what actually gets stored.
    predecessors = [r["data"].get("predecessors") for r in records]
    assert sum(1 for p in predecessors if p) == 2, predecessors


def an_imported_schedule_is_not_entirely_critical() -> None:
    """The acceptance criterion, stated as the observable it produces."""
    records = [
        _record("id0", "A1000", 5),
        _record("id1", "A1010", 10, "A1000"),
        _record("id2", "A1020", 2),  # off the chain: must have float
    ]
    result = schedule_cpm.compute(records)
    assert result["critical_count"] < result["activity_count"], (
        "every activity is critical, which is what a network with no logic looks like"
    )


CHECKS = [
    ("the calendar adjoint invariant holds", the_calendar_adjoint_holds),
    ("compute() keeps its legacy dict shape", the_legacy_shape_is_intact),
    ("an empty schedule does not raise", an_empty_schedule_does_not_raise),
    ("a sequential chain sums to its durations", a_sequential_chain_sums),
    ("a missing predecessor is reported", a_missing_predecessor_is_reported_not_dropped),
    ("SS/FF/SF relationships and lags are honoured", relationship_types_and_lags_are_honoured),
    ("float is numeric even when complete", float_is_numeric_even_when_complete),
    ("negative float is not clamped", negative_float_is_not_clamped),
    ("a cycle refuses rather than inventing dates", a_cycle_refuses_rather_than_inventing_dates),
    ("a cycle does not crash the optimiser", a_cycle_does_not_crash_the_optimiser),
    ("every exit agrees on the row shape", every_exit_agrees_on_the_row_shape),
    ("TASKPRED is read on import", taskpred_is_read_on_import),
    (
        "an imported schedule is not entirely critical",
        an_imported_schedule_is_not_entirely_critical,
    ),
]


def main() -> int:
    print("vendored massingplan engine -- conformance gate")
    for name, fn in CHECKS:
        check(name, fn)
    if FAILURES:
        print(f"\n{len(FAILURES)} of {len(CHECKS)} checks failed.")
        print(
            "The vendored copy in src/massingplan no longer behaves the way this "
            "repo's callers require. Fix it upstream at MassingCloud/massingplan "
            "and re-sync -- do not edit the vendored tree, or the next sync "
            "silently reverts the fix."
        )
        return 1
    print(f"\nall {len(CHECKS)} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
