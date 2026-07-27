"""SCHED-STATUS — a schedule without a data date is a plan, not a status report.

`schedule_cpm` computes float and the critical path; `schedule_activity` records planned and actual
dates. What none of it could answer is what a superintendent actually asks: **what is late?** That
needs an "as of" line, and building `risk_calibrate` ran straight into its absence — every
not-yet-started activity had to be treated as future work, because there was nothing to compare to.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_schedule_status.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_schedule_status.db"
os.environ["STORAGE_DIR"] = "./test_storage_schedule_status"
if os.path.exists("./test_schedule_status.db"):
    os.remove("./test_schedule_status.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import schedule_status as ss  # noqa: E402

DD = "2026-06-15"          # the data date every case below is measured from


def a(ref, start, finish, a_start=None, a_finish=None, forecast=None):
    return {"ref": ref, "data": {"start": start, "finish": finish, "actual_start": a_start,
                                 "actual_finish": a_finish, "expected_finish": forecast}}


# --- the first rule: no data date, no judgement ------------------------------------------------------
def test_without_a_data_date_NOTHING_is_called_late():
    # Defaulting to today would be wrong on every historical snapshot and archived project — and
    # wrong SILENTLY, painting a job that finished two years ago entirely red.
    r = ss.status([a("A1", "2026-01-01", "2026-01-10")], None)
    assert r["checked"] is False and r["data_date"] is None, r
    assert r["late_to_start"] == [] and r["overdue"] == [], r
    assert all(x["state"] == "unknown" for x in r["activities"]), r["activities"]
    assert "wrong silently" in r["note"], r["note"]

def test_an_unreadable_data_date_is_the_same_as_none_not_a_guess():
    assert ss.status([a("A1", "2026-01-01", "2026-01-10")], "not a date")["checked"] is False


# --- what "late" actually means -------------------------------------------------------------------------
def test_work_that_should_have_begun_and_has_not_is_LATE_TO_START():
    r = ss.status([a("A1", "2026-05-01", "2026-05-20")], DD)
    row = r["activities"][0]
    assert row["state"] == "not_started" and row["late_to_start"] is True, row
    assert row["days_late_to_start"] == 45, row
    assert r["late_to_start"] == ["A1"], r["late_to_start"]

def test_future_work_is_NOT_late_and_this_is_the_distinction_that_was_missing():
    # Before a data date existed, this and the case above were indistinguishable.
    r = ss.status([a("A1", "2026-08-01", "2026-08-20")], DD)
    assert r["activities"][0]["late_to_start"] is False, r["activities"]
    assert r["late_to_start"] == [], r

def test_an_activity_in_progress_is_not_late_to_start_whenever_it_began():
    r = ss.status([a("A1", "2026-05-01", "2026-05-20", "2026-05-03")], DD)
    row = r["activities"][0]
    assert row["state"] == "in_progress" and row["late_to_start"] is False, row

def test_past_its_finish_and_not_done_is_OVERDUE():
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-03")], DD)
    row = r["activities"][0]
    assert row["overdue"] is True and row["days_overdue"] == 14, row
    assert r["overdue"] == ["A1"], r

def test_an_activity_that_FINISHED_LATE_is_complete_not_overdue():
    # Its slip already happened. Calling a finished activity overdue confuses a fact with a risk, and
    # puts work on a chase list that nobody can act on.
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-03", "2026-06-10")], DD)
    row = r["activities"][0]
    assert row["state"] == "complete" and row["overdue"] is False, row
    assert row["actual_slip_days"] == 9, row
    assert r["overdue"] == [], r


# --- a forecast is a CLAIM, and stays separate from a fact --------------------------------------------------
def test_a_crew_forecast_past_plan_is_reported_SEPARATELY_from_overdue():
    # P6's Expected Finish is entered by the person doing the work. It is intent, not evidence — a
    # claim that they WILL be late, which is categorically different from a date that has passed.
    r = ss.status([a("A1", "2026-05-01", "2026-07-01", "2026-05-03", None, "2026-07-20")], DD)
    row = r["activities"][0]
    assert row["overdue"] is False, "the planned finish has not passed yet"
    assert row["forecast_slip_days"] == 19, row
    assert r["forecast_slipping"] == ["A1"] and r["overdue"] == [], r

def test_forecast_slip_and_actual_slip_are_never_added_together():
    # One has happened; the other is somebody's stated expectation. Merging them would let a claim
    # masquerade as a condition.
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-03", "2026-06-10", "2026-06-30")], DD)
    row = r["activities"][0]
    assert row["actual_slip_days"] == 9, row
    assert row["forecast_slip_days"] is None, "a finished activity has no forecast left to make"

def test_a_forecast_that_beats_plan_is_not_a_slip():
    r = ss.status([a("A1", "2026-05-01", "2026-07-01", "2026-05-03", None, "2026-06-20")], DD)
    assert r["activities"][0]["forecast_slip_days"] == -11
    assert r["forecast_slipping"] == [], r


# --- degenerate input is an answer ------------------------------------------------------------------------------
def test_an_activity_with_no_dates_at_all_is_unknown_not_on_time():
    r = ss.status([{"ref": "A1", "data": {}}], DD)
    assert r["activities"][0]["state"] == "unknown", r["activities"]
    assert r["counts"]["unknown"] == 1 and r["late_to_start"] == [], r

def test_counts_cover_every_state_and_sum_to_the_input():
    r = ss.status([a("A1", "2026-05-01", "2026-05-10", "2026-05-01", "2026-05-09"),
                   a("A2", "2026-05-01", "2026-07-01", "2026-05-03"),
                   a("A3", "2026-05-01", "2026-05-20"),
                   {"ref": "A4", "data": {}}], DD)
    assert r["counts"] == {"complete": 1, "in_progress": 1, "not_started": 1, "unknown": 1}, r["counts"]
    assert sum(r["counts"].values()) == len(r["activities"]) == 4

def test_empty_input():
    r = ss.status([], DD)
    assert r["activities"] == [] and r["checked"] is True and r["overdue"] == []

def test_every_state_explains_itself():
    for s in ss.STATES:
        assert len(ss.MEANS[s]) > 15, s


# --- REGRESSIONS from the v0.3.710 code review ---------------------------------------------------------
def test_state_is_evaluated_AS_OF_the_data_date_not_from_whether_actuals_exist():
    # THE bug the review caught, and the one this module's docstring says the data date exists to
    # prevent. An activity finishing 2026-06-10 read as `complete` at a data date of 2026-01-01 —
    # when as of that date it was in progress and five months from done.
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-01", "2026-06-10")], "2026-01-01")
    row = r["activities"][0]
    assert row["state"] == "not_started", row       # neither actual had happened by 2026-01-01
    assert row["actual_start"] is None and row["actual_finish"] is None, row
    assert row["future_actual_ignored"] is True, "disregarding recorded data is stated, not silent"

def test_a_future_actual_START_leaves_the_activity_not_started():
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-01")], "2026-01-01")
    assert r["activities"][0]["state"] == "not_started", r["activities"]

def test_a_future_actual_FINISH_leaves_it_in_progress_not_complete():
    r = ss.status([a("A1", "2026-01-01", "2026-06-01", "2026-01-02", "2026-06-10")], "2026-03-01")
    row = r["activities"][0]
    assert row["state"] == "in_progress", row       # it HAD started by 2026-03-01, but not finished
    assert row["actual_slip_days"] is None, "nothing has slipped yet as of this date"

def test_an_actual_ON_the_data_date_counts():
    # The boundary belongs to the past: work finished on the data date is finished.
    r = ss.status([a("A1", "2026-05-01", "2026-06-01", "2026-05-01", "2026-06-15")], "2026-06-15")
    assert r["activities"][0]["state"] == "complete", r["activities"]

def test_every_row_carries_the_same_keys_whatever_branch_produced_it():
    # A row missing eight keys makes `row["days_overdue"]` a KeyError the moment one dateless
    # activity appears — a trap for every consumer rather than a fact about the row.
    with_dd = ss.status([a("A1", "2026-05-01", "2026-05-10"), {"ref": "A2", "data": {}}], DD)
    keys = [set(x) for x in with_dd["activities"]]
    assert keys[0] >= keys[1] and keys[1] >= set(ss._ROW_KEYS) | {"ref", "state", "detail"}, keys
    no_dd = ss.status([a("A1", "2026-05-01", "2026-05-10")], None)
    assert set(no_dd["activities"][0]) >= set(ss._ROW_KEYS), no_dd["activities"]
    assert no_dd["activities"][0]["days_overdue"] is None      # present and None, not absent

def test_a_record_answers_to_the_same_name_with_or_without_a_data_date():
    rec = {"data": {"name": "Pour slab", "start": "2026-05-01", "finish": "2026-05-10"}}
    assert ss.status([rec], DD)["activities"][0]["ref"] == "Pour slab"
    assert ss.status([rec], None)["activities"][0]["ref"] == "Pour slab"


def test_the_crew_s_expected_finish_does_not_collide_with_the_EVM_forecast():
    # `evm.py` already emits a `forecast_finish` EXTRAPOLATED from IEAC(t). This field is STATED by
    # whoever is doing the work. Same name for a computed inference and a human claim is exactly the
    # confusion claim_type exists to prevent, so this one carries P6's own term instead.
    r = ss.status([a("A1", "2026-05-01", "2026-07-01", "2026-05-03", None, "2026-07-20")], DD)
    row = r["activities"][0]
    assert "expected_finish" in row and "forecast_finish" not in row, sorted(row)
    assert row["expected_finish"] == "2026-07-20", row
    assert row["forecast_slip_days"] == 19, "the computed delta keeps its own name"


for name, fn in sorted(list(globals().items())):
    if name.startswith("test_") and callable(fn):
        fn()

print("SCHED-STATUS OK - a schedule without a DATA DATE is a plan, not a status report. schedule_cpm "
      "computes float and the critical path and schedule_activity records planned and actual dates, "
      "but nothing could answer what a superintendent actually asks: WHAT IS LATE. That needs an 'as "
      "of' line, and building risk_calibrate ran straight into its absence - every not-yet-started "
      "activity had to be treated as future work because there was nothing to compare against. THE "
      "FIRST RULE: with no data date, NOTHING is called late. Defaulting to today would be wrong on "
      "every historical snapshot and archived project, and wrong SILENTLY, painting a job that "
      "finished two years ago entirely red. With one, the distinction that was previously impossible "
      "becomes trivial: work that should have begun and has not is LATE TO START, while work planned "
      "for August simply is not. An activity that FINISHED LATE is complete, NOT overdue - its slip "
      "already happened, and calling it overdue confuses a fact with a risk and puts work on a chase "
      "list nobody can act on. And a crew's FORECAST finish is a CLAIM, not a measurement: P6's "
      "Expected Finish is entered by the person doing the work, so it is intent rather than evidence "
      "(the distinction claim_type shipped), and forecast slip is reported SEPARATELY and never added "
      "to actual slip - merging them would let a claim masquerade as a condition.")
