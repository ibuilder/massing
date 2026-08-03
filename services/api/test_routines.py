"""R22-ROUTINES — recurring runs, the catch-up it refuses, and the firing it must still do.

Written directly against the blind spot a post-merge review found in three of my merged PRs today:
**a suite that only asserts refusals cannot distinguish a careful feature from a no-op.** So every
"must not fire" below is paired with its twin "must fire", and the governing question while writing
it was: *which of these checks would still pass if `due()` returned nothing, ever?*

The refusals:

1. **catch-up is not replayed.** A routine three windows behind fires ONCE with `missed_windows=3`.
   Replaying closed windows duplicates reports and bills repeat API calls;
2. **a running routine is never re-enqueued** — recurrence plus a slow job is a pile-up that looks
   like a load problem and is a scheduling bug;
3. **cadence is a closed set** — an unknown cadence is refused and listed, never defaulted to daily;
4. **`now` is passed, never read**, so boundaries are testable — and boundaries are the only
   interesting part of a scheduler.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_routines.py
"""
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, "src")

from aec_api.routines import (  # noqa: E402
    CADENCES,
    STATUS_BAD_CADENCE,
    STATUS_DISABLED,
    STATUS_DUE,
    STATUS_NOT_DUE,
    STATUS_RUNNING,
    due,
    evaluate,
    missed_windows,
    window_start,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def at(y, m, d):
    return datetime(y, m, d, 9, 0, tzinfo=timezone.utc)


R = {"id": "r1", "kind": "progress_report", "cadence": "monthly", "project_id": "p1"}

# --- 4. WINDOWS ARE CALENDAR-ALIGNED (the action) ----------------------------------------------------
check("a daily window starts on its own day", window_start("daily", date(2026, 8, 2)) == date(2026, 8, 2))
check("a weekly window starts on MONDAY",
      window_start("weekly", date(2026, 8, 2)) == date(2026, 7, 27),
      window_start("weekly", date(2026, 8, 2)))       # 2026-08-02 is a Sunday
check("a monthly window starts on the 1st",
      window_start("monthly", date(2026, 8, 22)) == date(2026, 8, 1))
check("a quarterly window starts on Jan/Apr/Jul/Oct",
      [window_start("quarterly", date(2026, m, 15)).month for m in (2, 5, 8, 11)] == [1, 4, 7, 10])
check("an unknown cadence has no window", window_start("fortnightly", date(2026, 8, 2)) is None)

# --- THE TWIN OF EVERY REFUSAL: IT MUST ACTUALLY FIRE ------------------------------------------------
e = evaluate(R, at(2026, 8, 2), last_run="2026-07-15")
check("A ROUTINE WHOSE WINDOW HAS NO RUN IS DUE", e["due"] is True and e["status"] == STATUS_DUE, e)
check("  and it names the window it is firing for", e["window_start"] == "2026-08-01", e)
first = evaluate(R, at(2026, 8, 2), last_run=None)
check("A ROUTINE THAT HAS NEVER RUN IS DUE", first["due"] is True, first)
check("  and is NOT reported as behind — a first run is not a missed one",
      first["missed_windows"] == 0 and first["first_run"] is True, first)
check("  with a reason saying so", "has never run is not behind" in first["reason"], first["reason"])
d = due([R], at(2026, 8, 2), last_runs={"r1": "2026-07-15"})
check("due() actually returns it in the fire list", d["due_count"] == 1 and d["due"][0]["id"] == "r1", d)

# --- 1. CATCH-UP IS NOT REPLAYED ----------------------------------------------------------------------
check("three whole months missed are COUNTED",
      missed_windows("monthly", date(2026, 4, 10), date(2026, 8, 2)) == 3,
      missed_windows("monthly", date(2026, 4, 10), date(2026, 8, 2)))
late = evaluate(R, at(2026, 8, 2), last_run="2026-04-10")
check("  the routine fires ONCE, not four times", late["due"] is True, late)
check("  reporting the gap as a number the caller can act on", late["missed_windows"] == 3, late)
check("  and flagging that catch-up was suppressed", late["catch_up_suppressed"] is True, late)
check("  with the cost named — duplicate reports and repeat API calls",
      "bills repeat API calls" in late["reason"], late["reason"])
check("a routine run inside the CURRENT window reports no gap",
      evaluate(R, at(2026, 8, 22), last_run="2026-08-02")["missed_windows"] == 0)
check("the batch total aggregates the gaps of everything it fires",
      due([R], at(2026, 8, 2), last_runs={"r1": "2026-04-10"})["total_missed_windows"] == 3)

# --- ALREADY RAN THIS WINDOW -------------------------------------------------------------------------
same = evaluate(R, at(2026, 8, 22), last_run="2026-08-02")
check("a routine that already ran this window is NOT due",
      same["due"] is False and same["status"] == STATUS_NOT_DUE, same)
check("  and says why", "already ran in the current window" in same["reason"])
check("  but the SAME routine one window later IS due again — recurrence still recurs",
      evaluate(R, at(2026, 9, 1), last_run="2026-08-02")["due"] is True)

# --- boundary: the first instant of a new window ------------------------------------------------------
check("running on the last day of a month does NOT satisfy the next month",
      evaluate(R, at(2026, 9, 1), last_run="2026-08-31")["due"] is True)
check("  and a run ON the 1st satisfies that month",
      evaluate(R, at(2026, 9, 15), last_run="2026-09-01")["due"] is False)
W = {**R, "cadence": "weekly"}
check("a Sunday run does not satisfy the Monday that follows it",
      evaluate(W, at(2026, 8, 3), last_run="2026-08-02")["due"] is True)

# --- 2. AN IN-FLIGHT ROUTINE IS NOT RE-ENQUEUED -------------------------------------------------------
run = evaluate(R, at(2026, 8, 2), last_run="2026-04-10", in_flight=True)
check("a routine already running is NOT re-enqueued",
      run["due"] is False and run["status"] == STATUS_RUNNING, run)
check("  naming the pile-up it prevents", "looks like a load problem" in run["reason"])
check("  and the TWIN: once it is no longer in flight, it fires",
      evaluate(R, at(2026, 8, 2), last_run="2026-04-10", in_flight=False)["due"] is True)
check("due() honours in_flight by id",
      due([R], at(2026, 8, 2), last_runs={"r1": "2026-04-10"}, in_flight={"r1"})["due_count"] == 0)

# --- 3. CADENCE IS A CLOSED SET ------------------------------------------------------------------------
for bad in ("fortnightly", "", None, "DAILY", 7):
    b = evaluate({**R, "cadence": bad}, at(2026, 8, 2))
    check(f"cadence={bad!r} is refused, not defaulted to daily",
          b["due"] is False and b["status"] == STATUS_BAD_CADENCE, b["status"])
check("  the refusal LISTS the cadences, so a caller can choose one",
      set(evaluate({**R, "cadence": "nope"}, at(2026, 8, 2))["cadences_available"]) == set(CADENCES))
check("  and says why defaulting would be worse",
      "schedule nobody chose" in evaluate({**R, "cadence": "nope"}, at(2026, 8, 2))["reason"])

# --- disabled, and its twin ----------------------------------------------------------------------------
off = evaluate({**R, "enabled": False}, at(2026, 8, 2))
check("a disabled routine is skipped", off["due"] is False and off["status"] == STATUS_DISABLED)
check("  and enabling it makes it fire again",
      evaluate({**R, "enabled": True}, at(2026, 8, 2))["due"] is True)

# --- skips are REPORTED, not filtered out ---------------------------------------------------------------
batch = due([R, {**R, "id": "r2", "enabled": False}, {**R, "id": "r3", "cadence": "never"}],
            at(2026, 8, 2), last_runs={"r1": "2026-07-01"})
check("the batch fires only the eligible routine", batch["due_count"] == 1, batch["due_count"])
check("  and RETURNS the skips with their reasons — 'nothing ran' and 'nothing was due' differ",
      len(batch["skipped"]) == 2 and all(s.get("reason") for s in batch["skipped"]),
      batch["skipped"])
check("an empty routine set is a clean no-op, not an error", due([], at(2026, 8, 2))["due_count"] == 0)

print()
if FAILED:
    print(f"routines: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("routines: all checks passed")
