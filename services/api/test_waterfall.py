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

# --- Fixture 2b: the promote SPLIT, by value -------------------------------------------------------
# `gp_distributions > 0` above is a range check, and it was the only assertion on the promote: the
# tier split could be wrong by 100% and every check in this file still passed. Found by mutation —
# `split = min(remaining, cap)` could be flipped to `max` with no test failing.
#
# Hand-derived: pref 72 + RoC 900 = 972 to the LP on 900 invested over exactly one year, which is an
# 8.0% IRR — i.e. the LP has *already reached* the 8% hurdle before any tier pays. So tier 1 (the
# below-hurdle 90/10 tier) must take essentially nothing, and the residual 80/20 tier must take the
# remaining 1028: LP 972 + 822.4 = 1794.4, GP 205.6.
#
# The bisection in solve_cash_for_irr_hurdle stops at a $1 interval, so tier 1 absorbs a fraction of
# a dollar and the split lands a few cents off the ideal — hence a tolerance rather than equality.
assert abs(w2["gp_distributions"] - 205.6) < 0.5, w2["gp_distributions"]
assert abs(w2["lp_distributions"] - 1794.4) < 0.5, w2["lp_distributions"]
# The sharp form: the GP's share of the post-pref/RoC residual is the RESIDUAL tier's 20%, not the
# below-hurdle tier's 10%. Those differ by exactly a factor of two, which is what makes a wrong
# answer here look entirely plausible.
residual = 2000.0 - 72.0 - 900.0
assert abs(w2["gp_distributions"] / residual - 0.20) < 0.001, w2["gp_distributions"] / residual

# --- Fixture 2c: the hurdle is measured INCLUDING the cash paid in the same period ------------------
# Regression guard for a real defect. The hurdle test ran against `lp_cf`, which did not yet contain
# the pref and return-of-capital paid in the *same* period — those were accumulated locally and only
# appended after the tier loop. So the LP's measured IRR was understated at the moment the hurdle was
# evaluated, and the below-hurdle tier absorbed cash that belonged to the residual tier.
#
# Measured before the fix: GP 102.78 against 205.57 here — the GP received half its promote. Nothing
# failed, because dollars still conserved and the GP still got "something".
#
# The clearest symptom: with the same-period cash omitted, the LP's XIRR at that instant is computed
# from contributions only and comes back None, so `(None or -1.0) >= hurdle` is False and the tier
# proceeds as though the LP had earned nothing at all.
from aec_api.proforma.waterfall import _lp_irr_with  # noqa: E402

assert _lp_irr_with([-900.0], [D0], D1, 0.0) is None                 # contributions-only: undefined
assert abs(_lp_irr_with([-900.0], [D0], D1, 972.0) - 0.08) < 1e-6    # with the period's cash: 8%

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

# --- Clawback: exercised here for the first time ---------------------------------------------------
# `clawback=True` appeared in no test on the platform — all ten call sites passed False — so the whole
# restitution branch was dead code as far as the suite was concerned, and a mutation of its
# `min(owed, p["gp"])` survived untouched.
#
# It needs a case where the GP took promote early and the LP's FINAL IRR still lands under the pref:
# a later capital call does it. Note `lp_irr` must also be solvable — across a 729-pattern sweep it
# came back None 26% of the time (XIRR is undefined for many sign patterns), and the guard
# `if lp_irr is not None` means clawback silently does nothing in those deals. Worth knowing before
# relying on it.
CB = [-200.0, 2000.0, -900.0]
CB_DATES = [date(2021 + i, 1, 1) for i in range(4)]
cb_off = run_waterfall(CB, CB_DATES, LP, GP, PREF, TIERS, style="american", clawback=False)
cb_on = run_waterfall(CB, CB_DATES, LP, GP, PREF, TIERS, style="american", clawback=True)

assert cb_off["lp_irr"] is not None and cb_off["lp_irr"] < PREF, cb_off["lp_irr"]
assert cb_off["gp_distributions"] > 0.0, cb_off          # the GP promoted before the LP fell short
# restitution moves money GP -> LP, and it is PARTIAL here (105.49 of 151.13), which is what
# distinguishes `min(owed, gp)` from `max`: a wrong extreme would move more than the period holds.
assert abs(cb_on["gp_distributions"] - 45.64) < 0.01, cb_on["gp_distributions"]
assert abs(cb_on["lp_distributions"] - 1954.36) < 0.01, cb_on["lp_distributions"]
assert cb_on["gp_distributions"] < cb_off["gp_distributions"], (cb_on, cb_off)
assert cb_on["lp_distributions"] > cb_off["lp_distributions"], (cb_on, cb_off)
# conservation survives the transfer, and no period is left owing more than it holds
assert abs((cb_on["lp_distributions"] + cb_on["gp_distributions"])
           - (cb_off["lp_distributions"] + cb_off["gp_distributions"])) < 0.01, (cb_on, cb_off)
assert all(p["gp"] >= -0.01 for p in cb_on["periods"]), cb_on["periods"]
# and it improves the LP's return rather than merely shuffling labels
assert cb_on["lp_irr"] > cb_off["lp_irr"], (cb_on["lp_irr"], cb_off["lp_irr"])

# --- Clawback STATUS: "we could not tell" is reported, never inferred as "nothing owed" -------------
# `lp_irr is None` means XIRR did not converge — 26% of cash-flow shapes in a 729-pattern sweep. That
# case used to be silently indistinguishable from "no restitution due": same payload, same
# distributions, a GP quietly keeping money a clawback might have recovered. No fallback is picked
# here on purpose — inventing a restitution figure out of a failed solve is how a plausible dollar
# amount gets cited. Whether a non-converging IRR is a zero-clawback case is a DEAL-TERMS decision.
assert cb_on["clawback"]["status"] == "applied", cb_on["clawback"]
assert cb_off["clawback"]["status"] == "not_requested", cb_off["clawback"]

_healthy = run_waterfall([2000.0], [D0, D1], LP, GP, PREF, TIERS, style="american", clawback=True)
assert _healthy["clawback"]["status"] == "not_owed", _healthy["clawback"]
assert "achieved its preferred return" in _healthy["clawback"]["reason"], _healthy["clawback"]

# a sign pattern XIRR cannot solve: requested, and honestly unresolvable
_unsolvable = run_waterfall([2000.0, -1800.0], [date(2021, 1, 1), date(2022, 1, 1), date(2023, 1, 1)],
                            LP, GP, PREF, TIERS, style="american", clawback=True)
assert _unsolvable["lp_irr"] is None, _unsolvable["lp_irr"]
assert _unsolvable["clawback"]["status"] == "unavailable", _unsolvable["clawback"]
assert "NOT a finding that none is owed" in _unsolvable["clawback"]["reason"], _unsolvable["clawback"]
# the distinction that matters: unavailable and not_owed must never collapse into each other
assert _unsolvable["clawback"]["status"] != _healthy["clawback"]["status"]

print("WATERFALL OK - promote split value-checked (the residual tier's 20%, not the below-hurdle "
      "tier's 10%); the IRR hurdle is measured INCLUDING the pref + RoC paid in the same period "
      "(GP was under-promoted 102.78 vs 205.57 before); clawback exercised for the first time "
      "(partial restitution, GP 151.13 -> 45.64). "
      "pref accrual + return-of-capital exact to the dollar (72 pref + 428 RoC = 500, "
      "472 unreturned); large distribution fully returns capital + pays a real GP promote; dollar "
      "conservation holds across arbitrary multi-period cash; European style withholds promote until "
      "the LP is made whole.")
