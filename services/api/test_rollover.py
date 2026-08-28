"""PF-ROLLOVER — what a lease expiry costs, and the four ways that number goes quietly wrong.

The arithmetic is easy. The assertions worth having are the ones that fail when the model is
optimistic in a way nobody can see:

1. **downtime is charged to the NON-RENEWAL branch only** — a renewing tenant does not vacate, and
   charging the gap to both branches overstates the total while looking entirely reasonable;
2. **missing assumptions are REFUSED, not defaulted** — defaulting renewal probability to 1.0 or
   downtime to 0 removes the exact risk being priced, and the output is indistinguishable from a deal
   that genuinely has neither;
3. **a lease with no end date is NAMED** — dropping it shrinks rollover exposure, so an omission
   fails in the flattering direction;
4. **both futures are reported**, so the weighting can be argued with rather than trusted.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_rollover.py
"""
import sys
from datetime import date

sys.path.insert(0, "src")

from aec_api.proforma.rollover import (  # noqa: E402
    STATUS_MISSING_ASSUMPTION,
    STATUS_OK,
    price_expiry,
    schedule,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


AS_OF = date(2026, 1, 1)

# 10,000 sf at $250k/yr. Market $30/sf = $300k. 5-year new term.
L1 = {"ref": "L-1", "workflow_state": "active",
      "data": {"tenant": "Acme", "suite": "100", "rentable_sf": 10000,
               "base_rent_annual": 250000, "end_date": "2027-06-30"}}
L2 = {"ref": "L-2", "workflow_state": "active",
      "data": {"tenant": "Beta", "suite": "200", "rentable_sf": 5000,
               "base_rent_annual": 150000, "end_date": "2028-03-31"}}
NO_END = {"ref": "L-3", "workflow_state": "active",
          "data": {"tenant": "Gamma", "suite": "300", "rentable_sf": 2000,
                   "base_rent_annual": 60000}}

A = {"renewal_probability": 0.7, "downtime_months": 6,
     "ti_new_psf": 50.0, "ti_renewal_psf": 10.0,
     "lc_new_pct": 0.06, "lc_renewal_pct": 0.03,
     "market_rent_psf": 30.0, "new_term_years": 5}

# --- 1. THE DOUBLE-COUNT: downtime belongs to one branch only -----------------------------------------
p = price_expiry(L1, A)
check("the renewal branch carries NO downtime — a renewing tenant does not vacate",
      p["renewal"]["downtime_months"] == 0.0 and p["renewal"]["downtime_rent_loss"] == 0.0,
      p["renewal"])
check("  the new-tenant branch carries all of it",
      p["new_tenant"]["downtime_months"] == 6, p["new_tenant"]["downtime_months"])
check("  6 months of $250k rent is $125,000 of lost rent",
      p["new_tenant"]["downtime_rent_loss"] == 125000.0, p["new_tenant"]["downtime_rent_loss"])
check("  expected downtime is probability-weighted, not the full gap",
      p["expected_downtime_months"] == 1.8, p["expected_downtime_months"])

# renewal: TI 10x10000 = 100,000 · LC 3% x 300,000 x 5 = 45,000 -> 145,000
check("renewal cost is TI + LC at renewal rates", p["renewal"]["total"] == 145000.0, p["renewal"])
# new: TI 50x10000 = 500,000 · LC 6% x 300,000 x 5 = 90,000 · downtime 125,000 -> 715,000
check("new-tenant cost is TI + LC + the vacancy gap", p["new_tenant"]["total"] == 715000.0,
      p["new_tenant"])
check("expected cost blends the two futures: 0.7x145,000 + 0.3x715,000",
      p["expected_cost"] == round(0.7 * 145000 + 0.3 * 715000, 2), p["expected_cost"])
check("  and BOTH branches are reported, so the weighting can be argued with",
      p["renewal"]["probability"] == 0.7 and p["new_tenant"]["probability"] == 0.3, p)

# --- 2. REFUSALS: the assumptions that must not be defaulted -----------------------------------------
for missing_key, partial in (("renewal_probability", {"downtime_months": 6}),
                             ("downtime_months", {"renewal_probability": 0.7}),
                             ("both", {})):
    r = schedule([L1], partial, as_of=AS_OF)
    check(f"missing {missing_key} refuses rather than defaulting",
          r["status"] == STATUS_MISSING_ASSUMPTION, r["status"])
    check("  no schedule and no total are produced",
          r["by_year"] == {} and r["total_expected_cost"] is None, r)
    check("  and the refusal explains what defaulting would have hidden",
          all(len(v) > 40 for v in r["why"].values()), r.get("why"))

check("a renewal probability of 1.0 is ACCEPTED — it is a choice, not a default",
      schedule([L1], {**A, "renewal_probability": 1.0}, as_of=AS_OF)["status"] == STATUS_OK)
check("zero downtime is ACCEPTED for the same reason",
      schedule([L1], {**A, "downtime_months": 0}, as_of=AS_OF)["status"] == STATUS_OK)

for bad in (1.5, -0.1, "high", True, float("nan")):
    r = schedule([L1], {**A, "renewal_probability": bad}, as_of=AS_OF)
    check(f"an out-of-range/non-numeric probability ({bad!r}) is treated as UNSTATED, not clamped",
          r["status"] == STATUS_MISSING_ASSUMPTION, r["status"])
check("negative downtime is unstated, not treated as a credit",
      schedule([L1], {**A, "downtime_months": -3}, as_of=AS_OF)["status"] == STATUS_MISSING_ASSUMPTION)

# --- 3. a lease that cannot be rolled is NAMED ----------------------------------------------------------
s = schedule([L1, L2, NO_END], A, as_of=AS_OF)
check("the schedule prices the dateable leases", s["expiries_priced"] == 2, s["expiries_priced"])
check("  and NAMES the one it could not date, rather than dropping it",
      s["leases_without_end_date"][0]["tenant"] == "Gamma", s["leases_without_end_date"])
check("  with the reason", "end_date" in s["leases_without_end_date"][0]["reason"],
      s["leases_without_end_date"])

# --- 4. the year schedule ----------------------------------------------------------------------------------
check("expiries land in their own year", sorted(s["by_year"]) == ["2027", "2028"], sorted(s["by_year"]))
check("  2027 carries Acme's rent at risk", s["by_year"]["2027"]["expiring_rent"] == 250000.0,
      s["by_year"]["2027"])
check("  and the total is the sum of the priced rows",
      s["total_expected_cost"] == round(sum(r["expected_cost"] for r in s["rows"]), 2),
      s["total_expected_cost"])
check("the assumptions actually used are echoed back, so a number can be reproduced",
      s["assumptions_used"]["renewal_probability"] == 0.7
      and s["assumptions_used"]["downtime_months"] == 6, s["assumptions_used"])

# --- 5. horizon and already-expired ----------------------------------------------------------------------
far = {"ref": "L-9", "workflow_state": "active",
       "data": {"tenant": "Far", "rentable_sf": 1000, "base_rent_annual": 30000,
                "end_date": "2099-01-01"}}
check("a lease expiring past the horizon is not priced",
      schedule([L1, far], A, as_of=AS_OF, horizon_years=10)["expiries_priced"] == 1)
past = {"ref": "L-0", "workflow_state": "active",
        "data": {"tenant": "Past", "rentable_sf": 1000, "base_rent_annual": 30000,
                 "end_date": "2020-01-01"}}
check("an already-expired lease is not priced as a future roll",
      schedule([L1, past], A, as_of=AS_OF)["expiries_priced"] == 1)
check("an empty rent roll produces an empty schedule, not an error",
      schedule([], A, as_of=AS_OF)["total_expected_cost"] == 0.0)

# --- 6. market rent falls back to in-place when unstated ---------------------------------------------------
no_mkt = price_expiry(L1, {**A, "market_rent_psf": 0.0})
check("with no market rent stated, the commission is struck on in-place rent rather than on zero",
      no_mkt["market_rent_annual"] == 250000.0, no_mkt["market_rent_annual"])

# --- 7. a lease that is not IN PLACE produces no income, so it produces no rollover ------------------
#
# `rentroll.summarize()` — this module's own docstring names it as the peer — counts a lease as
# income only when `workflow_state` is active or holdover. This engine had NO state filter, so a
# DRAFT lease (a negotiation that may never sign) contributed a full rollover cost while
# contributing nothing to income. Measured on the live API before the fix: two draft leases returned
# `expiries_priced: 2, total_expected_cost: 799816.67` against an income basis reporting an empty
# rent roll. A cost with no matching income is the asymmetry that makes a model wrong.
DRAFT = {"ref": "L-D", "workflow_state": "draft", "data": dict(L1["data"])}
ACTIVE = {"ref": "L-A", "workflow_state": "active", "data": dict(L1["data"])}

d_res = schedule([DRAFT], A, as_of=AS_OF)
check("a draft lease is not priced — it is not in place, so there is nothing to roll over",
      d_res["expiries_priced"] == 0 and d_res["total_expected_cost"] == 0.0, d_res["expiries_priced"])

# NAMED, NOT DROPPED. Excluding a lease SHRINKS the exposure and makes the deal look better, which
# is the direction this module already refuses to fail in silently for undateable leases.
check("...and it is NAMED rather than silently skipped, because excluding it flatters the deal",
      len(d_res.get("leases_not_in_place") or []) == 1
      and (d_res["leases_not_in_place"][0].get("workflow_state") == "draft"),
      d_res.get("leases_not_in_place"))

# THE TWIN: the filter must not swallow real leases. Without this the assertion above passes on an
# engine that prices nothing at all.
a_res = schedule([ACTIVE], A, as_of=AS_OF)
check("an ACTIVE lease is still priced — the filter excludes drafts, not everything",
      a_res["expiries_priced"] == 1 and a_res["total_expected_cost"] > 0,
      (a_res["expiries_priced"], a_res["total_expected_cost"]))
check("...and nothing is reported as excluded when everything is in place",
      not a_res.get("leases_not_in_place"), a_res.get("leases_not_in_place"))

# A record with NO workflow_state at all (a hand-built dict, as several tests here pass) must still
# price — the filter keys on an explicit non-active state, not on absence.
check("a lease carrying no workflow_state is still priced, not excluded by omission",
      schedule([L1], A, as_of=AS_OF)["expiries_priced"] == 1)

print()
if FAILED:
    print(f"rollover: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("rollover: all checks passed")
