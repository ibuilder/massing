"""A JV distribution statement's parts must sum to its own total, to the cent.

## The defect

`run_waterfall` emits one row per period: `distributable`, and the `lp` / `gp` shares it was split
into. Each was rounded on its own::

    "distributable": round(cash, 2), "lp": round(lp_take, 2), "gp": round(gp_take, 2)

Three independent roundings of numbers that are arithmetically one identity — every tier allocates
out of `cash`, so `lp_take + gp_take == cash` before rounding. Rounding the parts separately breaks
it. **Measured over 399 distribution periods across awkward fractions: 52 of them — 13% — had
`lp + gp != distributable`**, a penny out in both directions::

    distributable 1051.33   lp 1051.10 + gp 0.24 = 1051.34    (+0.01)
    distributable 1053.67   lp 1052.97 + gp 0.69 = 1053.66    (-0.01)

**A partner reading a distribution statement whose parts do not add up to its own total has found
an error in the document.** Being a penny is not a defence — it is the same class as the retainage
convention `test_money_spine` pins, whose docstring says *"a pay application out by a penny is
rejected, which makes this a document defect rather than a rounding curiosity"*. The waterfall
distributes real money to real partners and is what a promote is argued from.

`money.allocate` splits a total by largest-remainder so the parts sum to it exactly, and
`test_money_wire` already says it exists for this — *"the parts sum to the whole, and the leftover
cents are distributed by a defensible rule rather than dumped on whoever sorts last."* It had no
caller here.

## Why the money axis needed a different kind of sweep

The authz and concurrency sweeps each had a population you could enumerate and read. This one does
not: `round(x, 2)` appears **732 times** under `services/api/src`, and converting them all would be
the mistake R39-UPLOAD-CAP-APP's entry names — *"a count is not a work list"*. Most are display
figures where half-even versus half-up changes nothing anyone can act on.

So the axis was swept by a property rather than by a population: **where money is SPLIT, do the
parts still add up?** That question has a yes/no answer, it is checkable without reading 732 sites,
and it is the shape in which a rounding difference stops being cosmetic and becomes a wrong
document. This file asserts it for the waterfall; `test_money_wire` asserts it for the generic
splitter.

## The shape of the assertions

Not a fixed expected-value table. A frozen figure would pin today's arithmetic and say nothing about
the identity — and the identity is the claim. Each case therefore recomputes `lp + gp` from the
emitted row and requires it to equal the row's own `distributable`, across a **sweep** of amounts
chosen to land on awkward fractions, because a single round number cannot produce the defect at all
(the first draft of the fix looked fine on 1000.00).

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_waterfall_cents.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

os.environ.setdefault("DATABASE_URL", "sqlite:///./_waterfall_cents.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_waterfall_cents")

from aec_api import money  # noqa: E402
from aec_api.proforma.waterfall import run_waterfall  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


TIERS = [{"hurdle": 0.08, "lp": 0.90, "gp": 0.10}, {"hurdle": None, "lp": 0.80, "gp": 0.20}]
DATES = [date(2024, 1, 1), date(2025, 1, 1), date(2026, 1, 1)]


def _sweep(amounts):
    """Every emitted period, across a range of deliberately awkward distributable amounts."""
    for amt in amounts:
        r = run_waterfall([0.0, amt, amt * 1.37], DATES,
                          lp_contrib=900.0, gp_contrib=100.0, pref_rate=0.08, tiers=TIERS)
        yield from r["periods"]


# Thirds and sevenths: the fractions that put a .xx5 boundary between the two shares. A sweep of
# round numbers would be green against the defect — which is how it survived until 2026-08-25.
AMOUNTS = [1000.0 + c / 3.0 for c in range(1, 400)] + [500.0 + c / 7.0 for c in range(1, 200)]

dist_rows = [p for p in _sweep(AMOUNTS) if p["distributable"] > 0]

# Anti-vacuity first: every assertion below is over this list, and an empty list satisfies all of
# them. This is the check that says "the waterfall stopped emitting distributions" rather than
# letting three silent OKs report success over nothing.
check("the sweep produced distribution periods to check", len(dist_rows) >= 300,
      f"{len(dist_rows)} periods with distributable > 0")

off = [p for p in dist_rows
       if abs(round(p["lp"] + p["gp"], 2) - p["distributable"]) >= 0.005]
check("every period's lp + gp equals its own distributable", not off,
      "" if not off else
      f"{len(off)} of {len(dist_rows)} periods are off by a cent, e.g. "
      f"distributable={off[0]['distributable']} lp={off[0]['lp']} gp={off[0]['gp']}")

# The shares must also be cents — an unrounded float here would satisfy the sum check above while
# putting 1051.0999999999999 on a statement.
ragged = [p for p in dist_rows
          if p["lp"] != round(p["lp"], 2) or p["gp"] != round(p["gp"], 2)]
check("the shares are whole cents, not raw floats", not ragged,
      "" if not ragged else f"{len(ragged)} ragged, e.g. lp={ragged[0]['lp']!r}")

# ---- the capital-call branch has the identical shape, and the identical fix ----------------------
call_rows = [p for p in _sweep([-300.0 - c / 3.0 for c in range(1, 60)]) if p["distributable"] < 0]
check("the sweep produced capital-call periods too", len(call_rows) >= 20,
      f"{len(call_rows)} periods with distributable < 0")
off_calls = [p for p in call_rows
             if abs(round(p["lp_call"] + p["gp_call"], 2) + p["distributable"]) >= 0.005]
check("every call period's lp_call + gp_call equals the amount called", not off_calls,
      "" if not off_calls else
      f"{len(off_calls)} off, e.g. distributable={off_calls[0]['distributable']} "
      f"lp_call={off_calls[0]['lp_call']} gp_call={off_calls[0]['gp_call']}")

# ---- the inverse: the split must still be the RIGHT split, not merely a summing one --------------
# Without this, `lp = distributable, gp = 0` passes every assertion above. `allocate` is proportional
# to the weights it is given, so a period whose tiers hand the GP a real promote must show one.
promoted = [p for p in dist_rows if p["gp"] > 0]
check("the GP still receives its share — summing is not the only property", len(promoted) >= 100,
      f"{len(promoted)} of {len(dist_rows)} periods pay the GP something")

# ---- and the helper itself, so a green run here cannot mean `allocate` degenerated ---------------
parts = money.allocate(100.0, [1, 1, 1])
check("money.allocate still splits without losing a cent", sum(parts) == 100.0 and len(parts) == 3,
      f"100 three ways -> {parts}")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"WATERFALL CENTS OK - across {len(dist_rows)} distribution periods and {len(call_rows)} "
    "capital-call periods on deliberately awkward fractions, every row's parts sum to the row's own "
    "total to the cent, the shares are whole cents, and the GP still gets a real promote — so the "
    "sum property is not being satisfied by collapsing the split."
)
