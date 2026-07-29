"""R22-ENTITLE-RISK — a refused entitlement must not be able to look like a bad IRR.

The finance-math review of this codebase found that `proforma/` tests RANGE-check where they should
VALUE-check — a `0 <= p <= 1` assertion on a probability cannot fail. So the assertions here are
arithmetic: with a seeded RNG and a known approval rate, the denied count, the loss and the clearing
probability are each computed by hand and compared exactly.

The two that matter most:

* a denied draw is **never solved**, so it can never contribute a number to the returns distribution;
* `probability_of_clearing` divides by **every** iteration, so refusals count against the hurdle.

Both have a tempting wrong version that produces a plausible, friendlier number, which is exactly
why they are pinned rather than eyeballed.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_entitlement_risk.py
"""
import sys

sys.path.insert(0, "src")

import numpy as np  # noqa: E402

from aec_api.proforma import entitlement_risk as er  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


ASSUMPTIONS = {
    "timing": {"construction_months": 18, "leaseup_months": 12, "hold_years": 5,
               "start_date": "2026-01-01"},
    "cost_lines": [
        {"category": "land", "name": "Land", "amount": 4_000_000, "curve": "upfront",
         "start_month": 0, "end_month": 0},
        {"category": "hard", "name": "Construction", "amount": 20_000_000, "curve": "scurve",
         "start_month": 1, "end_month": 17},
        {"category": "soft", "name": "Soft costs", "amount": 3_000_000, "curve": "linear",
         "start_month": 0, "end_month": 17},
    ],
    "debt": {"ltc": 0.65, "rate": 0.085, "points": 0.01, "funding": "equity_first"},
    "equity": {"lp_pct": 0.9, "gp_pct": 0.1},
    "operations": {"potential_rent_annual": 3_600_000, "other_income_annual": 120_000,
                   "opex_annual": 1_300_000, "stabilized_occ": 0.94, "credit_loss_pct": 0.02},
    "exit": {"exit_cap": 0.055, "selling_cost_pct": 0.02},
    "waterfall": {"pref_rate": 0.08, "style": "american", "clawback": False,
                  "tiers": [{"hurdle": 0.12, "lp": 0.8, "gp": 0.2},
                            {"hurdle": None, "lp": 0.6, "gp": 0.4}]},
    "discount_rate": 0.10,
}

# GUARD — the fixture must actually solve, asserted before anything else runs.
#
# The first version of this file used invented field names (`max_ltv` for `ltc`, `pref` for
# `pref_rate`), so EVERY solve raised and `solved` was 0. Three of the assertions below still passed:
# "n + undefined == solved" is 0 == 0, "solved < iterations" is 0 < 2000, and
# "solved == approved - failures" is 0 == n - n. A suite that is green on a fixture that never solves
# is measuring nothing, which is precisely the range-check-instead-of-value-check pattern the
# finance-math review found across proforma/. Pin the floor first.
from aec_api.proforma.solve import solve as _solve  # noqa: E402

_probe = _solve(ASSUMPTIONS)
assert _probe["returns"]["equity_irr"] is not None, "fixture does not produce an equity IRR"
assert _probe["returns"]["equity_multiple"] > 1.0, _probe["returns"]
print(f"(fixture solves: equity_irr={_probe['returns']['equity_irr']:.4f})")

ENT = {
    "approval_probability": 0.7,
    "duration_months": {"kind": "triangular", "low": 6, "mode": 12, "high": 30},
    "carry_cost_monthly": 45_000,
    "pursuit_cost": 850_000,
    "land_basis": 6_000_000,
    "land_recovery_pct": 0.9,
}

# --- 1. validation refuses what cannot produce an honest answer -----------------------------------
for label, ent, frag in (
    ("a duration with no carry cost", {**ENT, "carry_cost_monthly": None}, "looks modelled"),
    ("a probability above 1", {**ENT, "approval_probability": 1.4}, "between 0 and 1"),
    ("a negative probability", {**ENT, "approval_probability": -0.1}, "between 0 and 1"),
    ("a land recovery above 1", {**ENT, "land_recovery_pct": 1.5}, "between 0 and 1"),
    ("a missing probability", {k: v for k, v in ENT.items() if k != "approval_probability"},
     "required"),
):
    try:
        er.simulate(ASSUMPTIONS, ent, iterations=100)
        check(f"refuses {label}", False, "no exception")
    except er.EntitlementError as e:
        check(f"refuses {label}", frag in str(e), str(e)[:120])

# A duration that costs nothing is the subtle one: the run would COMPLETE, report a duration
# distribution, and every metric would be identical to a run without it.
try:
    er.simulate(ASSUMPTIONS, {**ENT, "carry_cost_monthly": None}, iterations=100)
    check("  ...and that refusal is about silence, not about a missing field", False)
except er.EntitlementError as e:
    check("  ...and that refusal is about silence, not about a missing field",
          "changes no output" in str(e), str(e)[:150])

# --- 2. the approval coin is exactly as biased as it was told to be --------------------------------
# Reproduce the engine's own draw: same seed, same generator, same first call.
rng = np.random.default_rng(42)
expected_denied = int((rng.random(2000) >= 0.7).sum())
r = er.simulate(ASSUMPTIONS, ENT, iterations=2000, seed=42)
check("the denied count matches the seeded Bernoulli draw exactly",
      r["denied"] == expected_denied, (r["denied"], expected_denied))
check("  approved + denied == iterations", r["approved"] + r["denied"] == 2000)
check("  and the denied share is reported", r["denied_share"] == round(expected_denied / 2000, 4))
check("a 70% approval rate lands near 70%", 0.66 <= (r["approved"] / 2000) <= 0.74,
      r["approved"] / 2000)

# --- 3. THE assertion: a denied draw is never solved ------------------------------------------------
n_summary = r["metrics_given_approval"]["returns.equity_irr"]
# Non-zero FIRST. Every assertion after this is satisfiable at zero, so without this one a fixture
# that stopped solving would leave the suite green while measuring nothing.
check("draws actually solved — the floor these assertions rest on",
      r["solved"] > 0 and n_summary["n"] > 0, (r["solved"], n_summary["n"], r["solve_failures"]))
check("the returns distribution covers only the SOLVED approved draws",
      n_summary["n"] + n_summary.get("undefined", 0) == r["solved"],
      (n_summary["n"], n_summary.get("undefined"), r["solved"]))
check("  which is strictly fewer than the iterations", 0 < r["solved"] < 2000)
check("  and the result says the distribution is conditional",
      "GRANTED" in r["metrics_are_conditional"])
check("no denied draw contributed a return",
      r["solved"] == r["approved"] - r["solve_failures"] and r["solve_failures"] == 0,
      (r["solved"], r["approved"], r["solve_failures"]))

# --- 4. the denial branch has its own arithmetic ----------------------------------------------------
# Hand-computed: 12 months refusal → 850k pursuit + 12*45k carry + 6M land, recovering 90% of land.
d = er.denial_outcome(ENT, 12.0)
check("denial: capital deployed = pursuit + carry + land",
      d["capital_deployed"] == 850_000 + 12 * 45_000 + 6_000_000, d["capital_deployed"])
check("denial: land recovered = 90% of basis", d["land_recovered"] == 5_400_000)
check("denial: net loss = recovered - deployed",
      d["net_loss"] == 5_400_000 - (850_000 + 540_000 + 6_000_000), d["net_loss"])
check("  which is negative, i.e. money lost", d["net_loss"] < 0)
check("denial reports NO irr — a refusal has no holding period to annualise",
      "irr" not in {k.lower() for k in d})
check("a longer refusal costs more carry",
      er.denial_outcome(ENT, 24.0)["net_loss"] < d["net_loss"])
check("full land recovery still loses the pursuit + carry",
      er.denial_outcome({**ENT, "land_recovery_pct": 1.0}, 12.0)["net_loss"] == -(850_000 + 540_000))

ds = r["denial"]
check("the denial summary counts every refused draw", ds["n"] == r["denied"])
check("  and its mean loss is negative", ds["mean_net_loss"] < 0)
check("  worst is at least as bad as best", ds["worst_net_loss"] <= ds["best_net_loss"])

# --- 5. clearing a hurdle counts the refusals ---------------------------------------------------------
r2 = er.simulate(ASSUMPTIONS, ENT, iterations=1000, seed=7,
                 targets={"returns.equity_irr": 0.15})
pc = r2["probability_of_clearing"]["returns.equity_irr"]
check("the hurdle probability divides by EVERY iteration", pc["of_iterations"] == 1000)
check("  probability == hits / iterations", pc["probability"] == round(pc["hits"] / 1000, 4),
      (pc["probability"], pc["hits"]))
check("  the conditional figure is reported beside it, not instead",
      pc["probability_given_approval"] is not None)
check("  and the unconditional one is never the larger of the two",
      pc["probability"] <= pc["probability_given_approval"],
      (pc["probability"], pc["probability_given_approval"]))
check("  with the reason stated", "cannot clear a return hurdle" in pc["note"])

# With certain approval the two figures must coincide — the denial branch is empty.
sure = er.simulate(ASSUMPTIONS, {**ENT, "approval_probability": 1.0}, iterations=400, seed=3,
                   targets={"returns.equity_irr": 0.15})
sp = sure["probability_of_clearing"]["returns.equity_irr"]
check("at 100% approval, conditional and unconditional agree",
      sp["probability"] == sp["probability_given_approval"], (sp["probability"],
                                                              sp["probability_given_approval"]))
check("  and nothing is denied", sure["denied"] == 0 and sure["denial"]["n"] == 0)

never = er.simulate(ASSUMPTIONS, {**ENT, "approval_probability": 0.0}, iterations=200, seed=3,
                    targets={"returns.equity_irr": 0.15})
check("at 0% approval nothing is solved", never["solved"] == 0 and never["denied"] == 200)
check("  the hurdle probability is exactly zero, not undefined",
      never["probability_of_clearing"]["returns.equity_irr"]["probability"] == 0.0)
check("  and the duration summary says no draw was approved",
      never["entitlement_months"]["n"] == 0)

# --- 6. duration actually costs money ------------------------------------------------------------------
# The whole point: a longer entitlement must show up in the returns. Same seed, same coin, only the
# duration distribution differs.
short = er.simulate(ASSUMPTIONS, {**ENT, "duration_months": {"kind": "uniform", "low": 6, "high": 6}},
                    iterations=300, seed=11)
long = er.simulate(ASSUMPTIONS, {**ENT, "duration_months": {"kind": "uniform", "low": 36, "high": 36}},
                   iterations=300, seed=11)
check("the same seed approves the same draws either way", short["approved"] == long["approved"])
sm = short["metrics_given_approval"]["returns.equity_irr"]["mean"]
lm = long["metrics_given_approval"]["returns.equity_irr"]["mean"]
check("a 36-month entitlement returns LESS than a 6-month one", lm < sm, (sm, lm))
check("  and the duration summary reflects the input",
      short["entitlement_months"]["p50"] == 6.0 and long["entitlement_months"]["p50"] == 36.0)
check("a longer refusal also costs more", long["denial"]["mean_net_loss"] < short["denial"]["mean_net_loss"])

# --- 7. expected value blends only what can be blended ---------------------------------------------------
ev = r["expected_value"]
check("an expected value is available", ev["available"] is True)
check("  it blends NPV only", ev["blended"] == "npv only" and ev["metric"] == "returns.npv")
check("  IRR and multiple are explicitly excluded",
      "returns.equity_irr" in ev["excluded_metrics"]
      and "returns.equity_multiple" in ev["excluded_metrics"], ev["excluded_metrics"])
check("  with the reason: a ratio over a project that does not exist",
      "fabrication" in ev["why_only_npv"])
check("  and the denied mean loss is carried into it", ev["denied_mean_loss"] < 0)

# --- 8. determinism ------------------------------------------------------------------------------------
again = er.simulate(ASSUMPTIONS, ENT, iterations=500, seed=99)
once = er.simulate(ASSUMPTIONS, ENT, iterations=500, seed=99)
check("the same seed gives the same denied count", again["denied"] == once["denied"])
check("  and the same returns", again["metrics_given_approval"] == once["metrics_given_approval"])
diff_seed = er.simulate(ASSUMPTIONS, ENT, iterations=500, seed=100)
check("a different seed gives a different draw", diff_seed["denied"] != again["denied"]
      or diff_seed["metrics_given_approval"] != again["metrics_given_approval"])

# --- 9. the assumptions are not mutated -------------------------------------------------------------------
before = len(ASSUMPTIONS["cost_lines"])
er.simulate(ASSUMPTIONS, ENT, iterations=120, seed=5)
check("the caller's assumptions are untouched — carry is added to a COPY",
      len(ASSUMPTIONS["cost_lines"]) == before, len(ASSUMPTIONS["cost_lines"]))

# --- 10. solve failures are EXCLUDED, never priced at zero (qodo review of PR #99) ------------------
# Both defects had the same shape: an approved draw that could not be solved silently left the
# NUMERATOR while staying in the DENOMINATOR. That prices an unvaluable project at zero and drags
# every headline number toward it, with nothing in the payload saying so.
#
# Value-checked against hand arithmetic, not range-checked. The prior finance review found 17 defects
# in this package precisely because its tests asserted "between 0 and 1" — which both the right and
# the wrong answer satisfy.
ev = er._expected_value({"returns.npv": [100.0, 200.0]},
                        [{"net_loss": -50.0}], n_total=10, metrics=["returns.npv"], failures=7)
check("EV divides by the draws it VALUED, not by every iteration",
      ev["expected_npv"] == round((100.0 + 200.0 - 50.0) / 3, 2), ev["expected_npv"])
check("  the old denominator would have been 25.0 — a 3.3x understatement",
      ev["expected_npv"] != round((100.0 + 200.0 - 50.0) / 10, 2))
check("  and the exclusion is stated, not implied", ev["excluded_solve_failures"] == 7)
check("  with the basis named", ev["valued_draws"] == 3 and "solved" in ev["basis"])

ev0 = er._expected_value({"returns.npv": [10.0]}, [], n_total=1, metrics=["returns.npv"], failures=0)
check("with no failures the wording says so rather than warning about nothing",
      "nothing was excluded" in ev0["excluded_note"])

nothing = er._expected_value({"returns.npv": []}, [], n_total=5, metrics=["returns.npv"], failures=5)
check("all-failed refuses instead of reporting 0.0", nothing["available"] is False)

# conditional probability: denominator is APPROVED draws, not the ones that happened to solve
t = er._unconditional_target([100.0, 100.0], target=50.0, n_total=10, n_approved=8)
check("P[clear | approved] divides by every APPROVED draw", t["probability_given_approval"] == 0.25,
      t["probability_given_approval"])
check("  the old denominator (solved only) would have said 1.0 — a certainty that is not there",
      t["probability_given_approval"] != 1.0)
check("  and the denominator is published so the reader can check it",
      t["given_approval_denominator"] == 8)

print()
if FAILED:
    print(f"entitlement_risk: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("entitlement_risk: all checks passed")
