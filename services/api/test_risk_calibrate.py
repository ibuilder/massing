"""R27-RISK-CALIBRATE — the spread comes from this project's own history, not from a guess.

`schedule_risk.simulate` already runs Monte Carlo and reports P10–P90; the shape was never the
problem. What it multiplies is: three-point estimates, which on most jobs is one person's opinion
entered three times. Percentiles from that are precise about an opinion.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_risk_calibrate.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_risk_calibrate.db"
os.environ["STORAGE_DIR"] = "./test_storage_risk_calibrate"
if os.path.exists("./test_risk_calibrate.db"):
    os.remove("./test_risk_calibrate.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import risk_calibrate as rc  # noqa: E402


def act(ref, trade, p_start, p_finish, a_start=None, a_finish=None):
    return {"ref": ref, "data": {"trade": trade, "start": p_start, "finish": p_finish,
                                 "actual_start": a_start, "actual_finish": a_finish}}

def ontime(ref, trade, mult=1.0, planned=10):
    """A finished activity whose actual duration is `mult` × its planned duration."""
    from datetime import date, timedelta
    s = date(2026, 3, 1)
    pf = s + timedelta(days=planned - 1)
    af = s + timedelta(days=int(planned * mult) - 1)
    return act(ref, trade, s.isoformat(), pf.isoformat(), s.isoformat(), af.isoformat())


# --- the refusal that matters most ------------------------------------------------------------------
def test_an_activity_started_but_not_finished_is_NOT_a_data_point():
    # Its measured duration is however far it has got — always shorter than the truth. Including it
    # would drag every ratio down and produce risk that flatters the project, which is the direction
    # of error that gets people hurt.
    s = rc.samples([act("A1", "Concrete", "2026-03-01", "2026-03-10", "2026-03-01", None)])
    assert s["n"] == 0, s
    assert s["in_progress"] == ["A1"], s["in_progress"]
    assert "shorter than its true one" in s["note"]

def test_in_progress_is_distinguished_from_never_started():
    s = rc.samples([act("A1", "C", "2026-03-01", "2026-03-10", "2026-03-01", None),
                    act("A2", "C", "2026-03-01", "2026-03-10")])
    assert s["in_progress"] == ["A1"], s["in_progress"]
    assert s["unusable"] == [] and s["n"] == 0, s      # A2 simply has not begun; nothing to report

# --- ordinary calibration -----------------------------------------------------------------------------
def test_a_trade_with_enough_history_is_calibrated_from_its_own_activities():
    acts = [ontime(f"C{i}", "Concrete", m) for i, m in enumerate([1.0, 1.2, 1.1, 1.4, 1.3])]
    c = rc.calibrate(acts, trade="Concrete")
    assert c["basis"] == "trade" and c["n"] == 5, c
    assert c["likely"] > 1.0, c                        # this crew runs over, and the number says so
    assert "finished Concrete activities" in c["detail"]

def test_the_optimistic_bound_is_the_best_ACTUALLY_ACHIEVED_not_an_invention():
    # Manufacturing a best case nobody on this job has hit is how a forecast becomes a wish.
    acts = [ontime(f"C{i}", "Concrete", m) for i, m in enumerate([1.1, 1.2, 1.3, 1.4, 1.5])]
    c = rc.calibrate(acts, trade="Concrete")
    assert c["optimistic"] >= 1.0, c                    # nobody beat plan, so nothing claims they did
    assert c["pessimistic"] >= c["likely"] >= c["optimistic"], c

def test_trades_are_calibrated_separately():
    acts = ([ontime(f"C{i}", "Concrete", 1.5) for i in range(5)]
            + [ontime(f"E{i}", "Electrical", 1.0) for i in range(5)])
    assert rc.calibrate(acts, trade="Concrete")["likely"] > rc.calibrate(acts, trade="Electrical")["likely"]

# --- the fallback ladder, and saying which rung -----------------------------------------------------------
def test_too_few_for_a_trade_falls_back_to_the_project_and_says_so():
    acts = ([ontime(f"C{i}", "Concrete", 1.2) for i in range(2)]
            + [ontime(f"E{i}", "Electrical", 1.3) for i in range(5)])
    c = rc.calibrate(acts, trade="Concrete")
    assert c["basis"] == "project", c
    assert f"fewer than {rc.MIN_SAMPLES}" in c["detail"], c["detail"]

def test_too_few_for_the_project_falls_back_to_the_supplied_estimate_and_flags_it_as_one():
    c = rc.calibrate([ontime("C1", "Concrete", 1.2)], trade="Concrete",
                     fallback={"optimistic": 0.9, "likely": 1.0, "pessimistic": 1.5})
    assert c["basis"] == "three-point" and c["likely"] == 1.0, c
    assert "carries no evidence from this job" in c["detail"], c["detail"]

def test_with_no_history_and_no_estimate_it_REFUSES_rather_than_returning_one():
    # Returning 1.0 would read as "no risk", which is a claim, and a false one.
    c = rc.calibrate([], trade="Concrete")
    assert c["basis"] is None and c["likely"] is None, c
    assert "would read as 'no risk'" in c["detail"], c["detail"]

def test_every_result_names_the_rung_it_landed_on():
    acts = [ontime(f"C{i}", "Concrete", 1.2) for i in range(5)]
    assert rc.calibrate(acts, trade="Concrete")["basis"] in rc.BASES
    assert list(rc.BASES) == ["trade", "project", "three-point"]

# --- data errors are excluded AND reported ------------------------------------------------------------------
def test_an_absurd_ratio_is_a_data_error_not_risk_and_is_reported():
    # 40x plan is a typo or a re-baselined scope. Letting it in would swamp every honest observation;
    # dropping it silently would hide a data problem worth fixing.
    acts = [ontime(f"C{i}", "Concrete", 1.2) for i in range(5)] + [ontime("BAD", "Concrete", 40)]
    s = rc.samples(acts)
    assert [o["ref"] for o in s["outliers"]] == ["BAD"], s["outliers"]
    assert s["n"] == 5, s
    assert "not as risk" in s["outliers"][0]["why"]

def test_incomplete_dates_are_reported_not_silently_skipped():
    s = rc.samples([act("A1", "C", "2026-03-01", None, "2026-03-01", "2026-03-05")])
    assert [u["ref"] for u in s["unusable"]] == ["A1"], s["unusable"]

def test_a_backwards_date_range_is_not_a_duration():
    s = rc.samples([act("A1", "C", "2026-03-10", "2026-03-01", "2026-03-10", "2026-03-01")])
    assert s["n"] == 0, s

# --- degenerate input is an answer -------------------------------------------------------------------------------
def test_empty_input():
    s = rc.samples([])
    assert s["n"] == 0 and s["by_trade"] == {} and s["outliers"] == []
    assert rc.calibrate([])["basis"] is None

def test_activities_with_no_trade_group_together_rather_than_vanishing():
    acts = [ontime(f"X{i}", "", 1.2) for i in range(5)]
    c = rc.calibrate(acts, trade=None)
    assert c["basis"] == "trade" and c["trade"] == "(no trade)", c


# --- REGRESSION from the v0.3.710 code review -----------------------------------------------------------
def test_an_absurdly_SHORT_ratio_is_a_data_error_too_and_never_becomes_the_optimistic_bound():
    # The high guard alone left the exact failure this module's contract forbids. A typo — actual
    # finish equal to actual start on a 60-day activity — gave optimistic = 0.0167 inside a
    # `basis="trade"` result, a 1.7%-of-plan best case backed by nothing.
    typo = {"ref": "BAD", "data": {"trade": "Concrete", "start": "2026-03-01", "finish": "2026-04-29",
                                   "actual_start": "2026-03-01", "actual_finish": "2026-03-01"}}
    acts = [ontime(f"C{i}", "Concrete", 1.0, planned=60) for i in range(5)] + [typo]
    s = rc.samples(acts)
    assert [o["ref"] for o in s["outliers"]] == ["BAD"], s["outliers"]
    assert s["n"] == 5, s
    assert "manufacture a best case nobody achieved" in s["outliers"][0]["why"]
    c = rc.calibrate(acts, trade="Concrete")
    assert c["optimistic"] >= rc.MIN_RATIO, c

def test_the_two_guards_are_asymmetric_on_purpose():
    # Finishing in a tenth of the plan is far less believable than taking ten times it.
    assert rc.MIN_RATIO == 0.1 and rc.MAX_RATIO == 10.0
    assert rc.MIN_RATIO * rc.MAX_RATIO == 1.0, "reciprocal bounds, different believability"


for name, fn in sorted(globals().items()):
    if name.startswith("test_") and callable(fn):
        fn()

print("R27-RISK-CALIBRATE OK - schedule risk is now drawn from THIS PROJECT'S OWN finished work "
      "rather than from a three-point guess. schedule_risk already ran Monte Carlo and reported "
      "P10-P90; the shape was never the problem - what it multiplied was one person's opinion entered "
      "three times, so the percentiles were precise about an opinion. schedule_activity already "
      "carries planned start/finish beside actual_start/actual_finish, so every FINISHED activity is "
      "a measured planned-vs-actual ratio, grouped by trade. THE REFUSAL THAT MATTERS MOST: an "
      "activity that has STARTED BUT NOT FINISHED is not a data point - its measured duration is "
      "however far it has got, always shorter than the truth, and including it would drag every ratio "
      "down and produce a forecast that flatters the project, which is the direction of error that "
      "gets people hurt. `n` IS REPORTED AND TOO SMALL MEANS FALL BACK - trade to project to the "
      "caller's estimate - and the result NAMES THE RUNG, because a forecast whose provenance is "
      "invisible cannot be argued with. With no history and no estimate it REFUSES rather than "
      "returning 1.0, which would read as 'no risk' - a claim, and a false one. The optimistic bound "
      "is the best ratio ACTUALLY ACHIEVED, never a fraction below it, since manufacturing a best "
      "case nobody on this job has hit is how a forecast becomes a wish. And a 40x-plan activity is "
      "excluded as a data error AND reported, because letting it in would swamp every honest "
      "observation while dropping it silently would hide a data problem worth fixing.")
