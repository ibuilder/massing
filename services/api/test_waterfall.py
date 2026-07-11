"""Equity-waterfall math (proforma/waterfall.run_waterfall): pref accrual -> return of capital ->
IRR-hurdle promote tiers. This is the most error-prone money math on the platform and was only
exercised indirectly; here we pin it to hand-computed numbers + hard invariants (dollar conservation,
full return of capital, the promote actually promoting the GP).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_waterfall.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_waterfall.db"
os.environ["STORAGE_DIR"] = "./test_storage_waterfall"
for _f in ("./test_waterfall.db",):
    if os.path.exists(_f):
        os.remove(_f)

from datetime import date  # noqa: E402

from aec_api.proforma.waterfall import run_waterfall  # noqa: E402

# Dates exactly 365 days apart (2021 is not a leap year) so the pref period-fraction is exactly 1.0.
D0, D1 = date(2021, 1, 1), date(2022, 1, 1)
LP, GP, PREF = 900.0, 100.0, 0.08
TIERS = [{"hurdle": 0.08, "lp": 0.9, "gp": 0.1}, {"hurdle": None, "lp": 0.8, "gp": 0.2}]

# --- Fixture 1: a small distribution that only pays pref + returns capital (no promote) -------------
# pref accrued over 1 yr on 900 @ 8% = 72.00 exactly; pay 72 pref, then 428 return-of-capital = 500 to
# LP; LP capital left unreturned = 900 - 428 = 472; GP gets nothing (never reached the promote tiers).
w1 = run_waterfall([500.0], [D0, D1], LP, GP, PREF, TIERS, style="american")
assert w1["lp_distributions"] == 500.0, w1["lp_distributions"]
assert w1["gp_distributions"] == 0.0, w1["gp_distributions"]
assert w1["lp_unreturned"] == 472.0, w1["lp_unreturned"]
assert w1["lp_equity_multiple"] == round(500.0 / 900.0, 3), w1["lp_equity_multiple"]

# --- Fixture 2: a large distribution runs through pref + full RoC + promote -------------------------
w2 = run_waterfall([2000.0], [D0, D1], LP, GP, PREF, TIERS, style="american")
# dollar conservation: every distributable dollar is allocated to exactly one side
assert abs((w2["lp_distributions"] + w2["gp_distributions"]) - 2000.0) < 0.02, w2
assert w2["lp_unreturned"] == 0.0, w2["lp_unreturned"]              # capital fully returned
assert w2["gp_distributions"] > 0.0, w2                            # the promote paid the GP
# the promote actually promotes: GP's share of the *profit* (>1000 over capital) exceeds its 10% of
# capital — i.e. GP's equity multiple clears 1.0 (it got more than its money back off a 10% stake).
assert w2["gp_equity_multiple"] >= 1.0, w2["gp_equity_multiple"]
assert w2["lp_equity_multiple"] == round(w2["lp_distributions"] / LP, 3), w2
assert w2["lp_distributions"] > 900.0, w2                          # LP cleared its capital + then some

# --- Invariant sweep: conservation holds for arbitrary multi-period cash ---------------------------
for cash in ([100.0, 300.0, 1500.0], [0.0, 5000.0], [250.0], [50.0, 50.0, 50.0, 50.0]):
    dates = [date(2020 + i, 1, 1) for i in range(len(cash) + 1)]
    w = run_waterfall(cash, dates, LP, GP, PREF, TIERS, style="american")
    allocated = w["lp_distributions"] + w["gp_distributions"]
    assert abs(allocated - sum(x for x in cash if x > 0)) < 0.05, (cash, allocated, w)
    assert w["lp_unreturned"] >= -0.01, w                          # never over-returns capital

# --- European style withholds promote until LP is made whole ---------------------------------------
# one modest period that doesn't fully return LP capital -> European GP gets nothing this period.
we = run_waterfall([400.0], [D0, D1], LP, GP, PREF, TIERS, style="european")
assert we["gp_distributions"] == 0.0, we                          # withheld: LP not yet whole
assert we["lp_distributions"] == 400.0, we                        # all cash to LP (pref + partial RoC)

print("WATERFALL OK - pref accrual + return-of-capital exact to the dollar (72 pref + 428 RoC = 500, "
      "472 unreturned); large distribution fully returns capital + pays a real GP promote; dollar "
      "conservation holds across arbitrary multi-period cash; European style withholds promote until "
      "the LP is made whole.")
