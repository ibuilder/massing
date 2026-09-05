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

from aec_api import routines as routines_mod  # noqa: E402
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

# --- PERSISTENCE (R22-ROUTINES slice 2) ---------------------------------------------------------------
# The register and the engine must agree on the CADENCE VOCABULARY. If module.json offered a cadence
# the engine does not know, a user could save a routine that is then refused every time it is
# evaluated — valid to store, impossible to run, and nothing would report the mismatch.
import json as _json  # noqa: E402
import os as _os  # noqa: E402

_mj = _json.load(open(_os.path.join(_os.path.dirname(__file__), "modules", "routine",
                                        "module.json"), encoding="utf-8"))
_opts = [f for f in _mj["fields"] if f["name"] == "cadence"][0]["options"]
check("the register offers EXACTLY the cadences the engine knows — set equality both ways",
      sorted(_opts) == sorted(CADENCES), (sorted(_opts), sorted(CADENCES)))
_states = set(_mj["workflow"]["states"])
check("  and the register has the ACTIVE state the loader filters on",
      routines_mod.ACTIVE_STATE in _states, (routines_mod.ACTIVE_STATE, sorted(_states)))
check("  with draft and retired distinguishable from it",
      {"draft", "retired"} <= _states, sorted(_states))
# `enabled` was removed, not merely un-defaulted: it duplicated `paused`, so two switches governed
# one concept with nothing stating which won. test_field_attrs refused its default and finding out
# why exposed the redundancy. The workflow is the single authority for a STORED routine.
check("the register carries NO `enabled` field — the workflow is the only switch",
      "enabled" not in {f["name"] for f in _mj["fields"]},
      sorted(f["name"] for f in _mj["fields"]))
check("  and `paused` is what 'disabled' means for a stored routine", "paused" in _states)
check("  while the STATELESS engine still honours a caller-supplied enabled",
      evaluate({**R, "enabled": False}, at(2026, 8, 2))["status"] == STATUS_DISABLED)

_os.environ["DATABASE_URL"] = "sqlite:///./test_routines.db"
_os.environ["STORAGE_DIR"] = "./test_storage_routines"
_os.environ.pop("AEC_RBAC", None)
for _f in ("./test_routines.db",):
    if _os.path.exists(_f):
        _os.remove(_f)

from aec_api import modules as _me  # noqa: E402
from aec_api import modules_registry as _mr  # noqa: E402

_mr.load_registry()   # the app does this at startup; a bare import leaves TABLES empty
from aec_api.db import Base as _Base  # noqa: E402
from aec_api.db import SessionLocal as _SL
from aec_api.db import engine as _eng
from aec_api.models import Project as _P  # noqa: E402

_Base.metadata.create_all(_eng)
with _SL() as _db:
    _db.add(_P(id="proj1", name="Routines"))
    _db.commit()

    def _mk(name, cadence, state, last_run=None):
        # create_record takes {"data": {...}} — only POST-create wraps; PATCH takes the field map.
        rec = _me.create_record(_db, "routine", "proj1",
                                {"data": {"name": name, "kind": "progress_report",
                                          "cadence": cadence,
                                          **({"last_run": last_run} if last_run else {})}},
                                actor="t@test", party="GC")
        rid = rec["id"] if isinstance(rec, dict) else rec
        _db.execute(_me.TABLES["routine"].update()
                    .where(_me.TABLES["routine"].c.id == rid).values(workflow_state=state))
        _db.commit()
        return rid

    _active_id = _mk("monthly report", "monthly", "active", last_run="2026-04-10")
    _mk("draft one", "monthly", "draft")
    _mk("retired one", "weekly", "retired")

    P = routines_mod.from_project(_db, "proj1", now=at(2026, 8, 2))

check("from_project reads the STORED routines", P["stored"] == 3, P.get("stored"))
check("  but evaluates only the ACTIVE one — a draft was never switched on",
      P["evaluated"] == 1, P.get("evaluated"))
check("  and says so rather than letting the other two vanish",
      "not active" in P["note"], P["note"])
check("THE STORED last_run DRIVES RECURRENCE — this is what persistence buys",
      P["due_count"] == 1 and P["due"][0]["missed_windows"] == 3, P["due"])
check("  the due routine is the active one, by id", P["due"][0]["id"] == _active_id, P["due"][0])
check("  and catch-up is still suppressed across the restart boundary",
      P["due"][0]["catch_up_suppressed"] is True, P["due"][0])

with _SL() as _db:
    P2 = routines_mod.from_project(_db, "no-such-project", now=at(2026, 8, 2))
check("a project with no routines is a clean empty evaluation, not an error",
      P2["due_count"] == 0 and P2["stored"] == 0, P2)

# --- 5. THE PICKLIST A USER ACTUALLY SEES MUST NAME KINDS THAT RUN -----------------------------
#
# This file's own header says a suite that only asserts refusals cannot tell a careful feature from a
# no-op, and pairs every "must not fire" with a "must fire". Check 3 above asserts an unknown kind is
# REFUSED. Nothing asserted that the kinds a user can actually CHOOSE are not all unknown — and they
# were. `modules/routine/module.json` offered progress_report, schedule_risk_scan, cost_variance_scan,
# provenance_check and custom; `jobs.KINDS` registers none of those. The intersection was EMPTY, so
# every routine anyone created through the Routines module was refused at sweep time with
# `unknown_kind`, on a module that ships a full workflow — draft/active/paused/retired, activate,
# pause, retire — and a persisted register. **A refusal test passes just as happily when everything
# is refused.**
#
# The picklist and the registry are two copies of one list, and a copy is what drifts. So this asserts
# the set relationship rather than a count, with both exemptions named:
#
#   * `echo` is the queue's own smoke-test kind and is deliberately not offered to users;
#   * `report_package` IS registered — it is R24-REPORTS-BY-MOMENT's assemble half — but it REQUIRES
#     a `reports: [id, ...]` list, and `routines_run.evaluate_and_enqueue` enqueues only
#     `{routine_id, window_start}` plus the project id. Offering it would move the failure from
#     `unknown_kind` at enqueue to "no reports in the package" at run, which is the same defect one
#     layer down. Scheduled report packages need routines to carry their job's params; that is the
#     real remaining work behind "scheduling still open", and it is not a scheduler change.
#
# Every other registered kind reads its non-project params through `params.get(... ) or <default>`, so
# it runs from the project alone — verified by reading all twelve handlers, not by sampling.
import json as _cfg_json  # noqa: E402
from pathlib import Path as _CfgPath  # noqa: E402

from aec_api import jobs as _jobs  # noqa: E402

NOT_OFFERED = {
    "echo": "the queue's smoke-test kind, deliberately not user-facing",
    "report_package": "needs a reports[] list the sweep does not pass; see the note above",
}

_mod = _cfg_json.loads(
    (_CfgPath(__file__).resolve().parent / "modules" / "routine" / "module.json").read_text("utf-8"))
_offered = [f for f in _mod["fields"] if f["name"] == "kind"][0]["options"]

check("every routine kind a user can pick is a registered job kind",
      [k for k in _offered if k not in _jobs.KINDS] == [],
      f"unrunnable options: {[k for k in _offered if k not in _jobs.KINDS]}")

check("the picklist is not empty, so the check above cannot pass vacuously",
      len(_offered) >= 5, f"{len(_offered)} option(s)")

check("every registered kind is either offered or exempt BY NAME",
      sorted(set(_jobs.KINDS) - set(_offered)) == sorted(NOT_OFFERED),
      f"unaccounted: {sorted(set(_jobs.KINDS) - set(_offered) - set(NOT_OFFERED))}; "
      f"exempt-but-gone: {sorted(set(NOT_OFFERED) - set(_jobs.KINDS))}")


_eng.dispose()
for _f in ("./test_routines.db",):
    if _os.path.exists(_f):
        try:
            _os.remove(_f)
        except OSError:
            pass

print()
if FAILED:
    print(f"routines: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("routines: all checks passed")
