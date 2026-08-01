"""PF-RENOVATION — a value-add programme, and the three ways its income curve goes quietly wrong.

The arithmetic is easy; the assertions worth having are about *timing*. A unit has three phases and
every overstatement skips one:

1. in-place rent until it starts;
2. **nothing** while it is being renovated — skipping this makes the programme look like capex only;
3. renovated rent **only from the month it comes back online** — skipping the lag is the single most
   common way a value-add deal is overstated, and it produces a smooth, plausible, too-high curve.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_renovation.py
"""
import sys

sys.path.insert(0, "src")

from aec_api.proforma.renovation import (  # noqa: E402
    STATUS_MISSING_ASSUMPTION,
    STATUS_OK,
    schedule,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# 10 units at $1,000 -> $1,300 after a $15,000 renovation. Premium $300/unit/month.
T1 = {"type": "1BR", "count": 10, "current_rent_monthly": 1000,
      "renovated_rent_monthly": 1300, "renovation_cost": 15000}
A = {"units_per_month": 2, "downtime_months_per_unit": 1}

s = schedule([T1], A, months=12)
by = {r["month"]: r for r in s["by_month"]}

# --- 1. THE LAG: the premium starts when the unit comes BACK, not when work starts -------------------
check("a programme is produced", s["status"] == STATUS_OK, s["status"])
check("month 0 starts 2 units", by[0]["units_started"] == 2, by[0])
check("  and earns NO premium — the units are being renovated, not re-let",
      by[0]["premium_income"] == 0.0, by[0]["premium_income"])
check("  while losing their in-place rent: 2 x $1,000",
      by[0]["downtime_rent_loss"] == 2000.0, by[0]["downtime_rent_loss"])
check("  and incurring their capex: 2 x $15,000", by[0]["renovation_capex"] == 30000.0, by[0])

check("month 1 is when the first two come back online",
      by[1]["units_completed"] == 2 and by[1]["units_online_renovated"] == 2, by[1])
check("  NOW the premium appears: 2 x $300", by[1]["premium_income"] == 600.0,
      by[1]["premium_income"])
check("  and the next two are offline, so the loss continues",
      by[1]["downtime_rent_loss"] == 2000.0, by[1]["downtime_rent_loss"])

check("by month 4, 8 units are back and earning", by[4]["units_online_renovated"] == 8,
      by[4]["units_online_renovated"])
check("  premium is 8 x $300", by[4]["premium_income"] == 2400.0, by[4]["premium_income"])

# The whole point, stated as one assertion: at NO month does the premium exceed what the units
# actually back online can produce. A day-one-premium model fails this at month 0.
worst = max((r["premium_income"] - r["units_online_renovated"] * 300.0) for r in s["by_month"])
check("THE REFUSAL: premium never exceeds units actually back online, in any month",
      abs(worst) < 1e-9, worst)
check("  and month 0 in particular earns nothing, which a day-one-premium model would not",
      by[0]["premium_income"] == 0.0)

# --- 2. the programme completes, and stops -----------------------------------------------------------
check("all 10 units are renovated within the window", s["units_renovated_in_window"] == 10,
      s["units_renovated_in_window"])
check("  none are left unreached", s["units_not_reached"] == 0, s["units_not_reached"])
check("  total capex is 10 x $15,000", s["total_renovation_cost"] == 150000.0,
      s["total_renovation_cost"])
check("  stabilised premium is 10 x $300/month", s["stabilised_premium_monthly"] == 3000.0,
      s["stabilised_premium_monthly"])
check("once complete, no units remain in renovation", by[11]["units_in_renovation"] == 0, by[11])
check("  and the premium is the full stabilised figure", by[11]["premium_income"] == 3000.0, by[11])

# --- 3. THE SHARED-OBJECT TRAP -------------------------------------------------------------------------
# Units of one type are identical dicts. If completions are removed by VALUE rather than by identity,
# finishing one unit removes every unit of that type from the in-renovation set, and the programme
# appears to finish far too early with no error anywhere.
slow = schedule([{"type": "2BR", "count": 6, "current_rent_monthly": 1000,
                  "renovated_rent_monthly": 1200, "renovation_cost": 1000}],
                {"units_per_month": 1, "downtime_months_per_unit": 3}, months=12)
sb = {r["month"]: r for r in slow["by_month"]}
check("with a 3-month downtime and 1 unit/month, three units are in renovation at once",
      sb[2]["units_in_renovation"] == 3, sb[2])
check("  and NONE has completed yet at month 2", sb[2]["units_online_renovated"] == 0, sb[2])
check("  the first completes at month 3, leaving three still in progress",
      sb[3]["units_online_renovated"] == 1 and sb[3]["units_in_renovation"] == 3, sb[3])
check("  downtime loss tracks units in renovation, not units of that TYPE",
      sb[3]["downtime_rent_loss"] == 3000.0, sb[3]["downtime_rent_loss"])

# --- 4. refusals ------------------------------------------------------------------------------------------
for partial, name in (({"downtime_months_per_unit": 1}, "units_per_month"),
                      ({"units_per_month": 2}, "downtime_months_per_unit"),
                      ({}, "both")):
    r = schedule([T1], partial, months=12)
    check(f"missing {name} refuses rather than defaulting", r["status"] == STATUS_MISSING_ASSUMPTION,
          r["status"])
    check("  no schedule and no cost are produced",
          r["by_month"] == [] and r["total_renovation_cost"] is None, r)
    check("  and the refusal says what defaulting would have hidden",
          all(len(v) > 40 for v in r["why"].values()), r.get("why"))

check("zero downtime is ACCEPTED — it is a choice, not a default",
      schedule([T1], {**A, "downtime_months_per_unit": 0}, months=12)["status"] == STATUS_OK)
for bad in (-1, "fast", True, float("nan")):
    check(f"a non-numeric/negative pace ({bad!r}) is UNSTATED, not coerced",
          schedule([T1], {**A, "units_per_month": bad})["status"] == STATUS_MISSING_ASSUMPTION)

# --- 5. a type with no renovated rent is NOT renovated, and is NAMED ------------------------------------------
mixed = schedule([T1, {"type": "3BR", "count": 4, "current_rent_monthly": 1500}], A, months=12)
check("a type with no renovated rent is excluded from the programme",
      mixed["renovatable_units"] == 10, mixed["renovatable_units"])
check("  and is NAMED with the reason, not silently dropped",
      any(e["type"] == "3BR" and "not renovated" in e["reason"]
          for e in mixed["excluded_unit_types"]), mixed["excluded_unit_types"])
check("  its unit count is retained so nobody thinks the property is smaller",
      any(e.get("count") == 4 for e in mixed["excluded_unit_types"]), mixed["excluded_unit_types"])

for bad, why in (({"type": "X", "count": 0, "current_rent_monthly": 1, "renovated_rent_monthly": 2},
                  "zero units is not a unit type"),
                 ({"type": "Y", "count": 5, "renovated_rent_monthly": 2},
                  "no in-place rent means no premium can be computed")):
    r = schedule([bad], A, months=6)
    check(f"excluded: {why}", r["renovatable_units"] == 0 and r["excluded_unit_types"], r)

# --- 6. a premium can legitimately be negative, and is not silently floored --------------------------------------
down = schedule([{"type": "Z", "count": 2, "current_rent_monthly": 1200,
                  "renovated_rent_monthly": 1100, "renovation_cost": 500}],
                {"units_per_month": 2, "downtime_months_per_unit": 0}, months=3)
check("a renovated rent BELOW the in-place rent produces a negative premium, not zero",
      down["stabilised_premium_monthly"] == -200.0, down["stabilised_premium_monthly"])

# --- 7. the window can be too short, and says so ---------------------------------------------------------------
short = schedule([T1], {"units_per_month": 1, "downtime_months_per_unit": 1}, months=4)
check("a window too short to finish reports the units it did not reach",
      short["units_not_reached"] == 6, short["units_not_reached"])
check("  and does not claim the full stabilised premium as achieved",
      short["by_month"][-1]["premium_income"] < short["stabilised_premium_monthly"],
      (short["by_month"][-1]["premium_income"], short["stabilised_premium_monthly"]))
check("an empty unit list schedules nothing rather than erroring",
      schedule([], A, months=6)["renovatable_units"] == 0)

print()

# ---------------------------------------------------------------------------------------------------
# FIN-SUITE-BLIND follow-up (2026-08-01) — two inputs the original fixture could not distinguish.
#
# Both were found by asking what this suite is structurally unable to see, not by reading the code:
# every existing case used an INTEGER pace and an INTEGER downtime, and at integer values the correct
# implementation and the broken one agree exactly. The defects lived entirely in the fractional gap.
# ---------------------------------------------------------------------------------------------------

_UT = [{"type": "1BR", "count": 10, "current_rent_monthly": 1500,
        "renovated_rent_monthly": 1900, "renovation_cost": 20000}]


def _sched(pace, downtime, months=36):
    return schedule(_UT, {"units_per_month": pace,
                                     "downtime_months_per_unit": downtime}, months=months)


# --- a FRACTIONAL pace must accumulate, not floor to nothing every month --------------------------
# `int(min(pace, remaining))` floored each month independently, so ANY pace below 1 took zero units
# every month and renovated NOTHING across the whole window — while still returning
# status="scheduled" and a full by_month table of zeros. "One unit every two months" is an ordinary
# pace for a small property; it produced a silently empty programme that reads like a completed one.
_half = _sched(0.5, 1)
check("a pace of 0.5/month renovates units — it does not silently floor to zero",
      _half["units_renovated_in_window"] == 10,
      f"{_half['units_renovated_in_window']} of 10 (a flooring bug gives 0)")
check("  and earns a premium rather than reporting a zero-income programme",
      _half["total_premium_income"] > 0, _half["total_premium_income"])

# Half the pace must take about twice as long, so it earns strictly LESS than the integer pace over
# the same window — an ordering assertion, which a wrong-but-nonzero number cannot satisfy by luck.
_one = _sched(1, 1)
check("half the pace earns strictly less premium than double the pace in the same window",
      0 < _half["total_premium_income"] < _one["total_premium_income"],
      f"0.5/mo={_half['total_premium_income']} vs 1/mo={_one['total_premium_income']}")

# A pace too slow to finish must under-run and SAY so, rather than quietly reporting zero.
_slow = _sched(0.25, 1)
check("a pace of 0.25/month reaches some but not all units in 36 months",
      0 < _slow["units_renovated_in_window"] < 10,
      f"{_slow['units_renovated_in_window']} renovated, {_slow['units_not_reached']} not reached")

# --- an explicit zero pace is a legitimate input, and must be LABELLED, not just zero-valued -------
_none = _sched(0, 1)
check("a stated pace of 0 renovates nothing AND says so explicitly",
      _none["units_renovated_in_window"] == 0 and _none["nothing_renovated"] is True,
      f"nothing_renovated={_none['nothing_renovated']}")
check("  a working programme is NOT flagged as having done nothing",
      _half["nothing_renovated"] is False)

# --- downtime rounds UP and never silently to zero -------------------------------------------------
# `int(round(x))` was banker's rounding: 0.5 -> 0 (deleting phase 2 entirely), 1.5 -> 2, 2.5 -> 2.
# A stated half-month of vacancy becoming NO vacancy understates the exact carrying cost this module
# exists to surface.
for _raw, _want in ((0, 0), (0.5, 1), (1, 1), (1.5, 2), (2.5, 3)):
    _got = _sched(2, _raw)["assumptions_used"]["downtime_months_per_unit"]
    check(f"downtime {_raw} -> {_want} month(s)", _got == _want, f"got {_got}")

# An explicit 0 must survive: it is a stated choice, not an absence. (Same defect shape as the
# explicit-0% retainage in cost.py, found the same day.)
_z = _sched(2, 0)
check("an explicit downtime of 0 stays 0 and loses no rent",
      _z["assumptions_used"]["downtime_months_per_unit"] == 0
      and _z["total_downtime_rent_loss"] == 0.0,
      f"{_z['total_downtime_rent_loss']}")
check("a positive downtime DOES lose rent — so the zero case above is not vacuous",
      _sched(2, 1)["total_downtime_rent_loss"] > 0)

# --- the invariant that would have caught the ordering defect on its own --------------------------
# A unit is online, or in renovation, or neither — never both. Completions were applied BEFORE starts,
# so at downtime == 0 a unit landed in both sets permanently: earning the premium while still being
# charged downtime rent, for the whole schedule. Both counters read plausibly in isolation; only their
# SUM against the unit count exposes it, and nothing summed them.
for _dt in (0, 1, 2):
    _s = _sched(2, _dt)
    _bad = [(r["month"], r["units_online_renovated"], r["units_in_renovation"])
            for r in _s["by_month"]
            if r["units_online_renovated"] + r["units_in_renovation"] > _s["renovatable_units"]]
    check(f"downtime {_dt}: no unit is online AND in renovation at once",
          not _bad, f"months where online+in_renovation exceeds {_s['renovatable_units']}: {_bad[:3]}")

_z0 = _sched(2, 0)
check("zero downtime charges no rent loss at all",
      _z0["total_downtime_rent_loss"] == 0.0, _z0["total_downtime_rent_loss"])
check("  and still earns the premium — zero downtime is fast, not inert",
      _z0["total_premium_income"] > 0, _z0["total_premium_income"])

if FAILED:
    print(f"renovation: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("renovation: all checks passed")
