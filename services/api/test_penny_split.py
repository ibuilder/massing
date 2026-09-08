"""PENNY-SPLIT — a subcontractor billing row must not contradict itself.

v0.3.969 converted this repository's money paths to exact `Decimal` quantized HALF-UP, because
`round()` is ROUND_HALF_EVEN and an invoice rounds half away from zero. In
`routers/cost.py::subcontractor_billing` the fix landed on the `retainage` line and **not on the
`paid` line four lines below it**, so one row of one table carried two conventions:

    retainage = money.q2(money.retainage(amt, ret_pct) + ...)      # HALF-UP
    paid      = round(row["paid"] + amt * (1 - ret_pct / 100), 2)  # HALF-EVEN

Measured before the fix, 4 of 8 sampled amount/rate pairs disagreed. At 2.50 and 5% the row held
**0.13** retainage and paid **2.38** — which implies 0.12. A subcontractor checking the GC's own
summary finds `billed - retainage` and `paid` a penny apart, and neither number is wrong on its own.

**Why the existing coverage could not see it.** `test_project_budget.py` bills 400,000 at 10%:
40,000 exactly, where HALF-UP and HALF-EVEN coincide. Every fixture in the file is a round number.
That is the same blindness `cost.py` records in its own comment — *"every prior test used the
default, where the bug is invisible because the fallback and the real value coincide"* — and it is
why the amounts below are deliberately ugly.

**The gate is the INVARIANT, not the spelling.** Asserting "the code calls `money`" would pass the
moment someone re-derives `paid` some other correct way, and fail on a correct refactor. Asserting
that a row agrees with itself cannot be satisfied by accident: for a subcontract whose every
invoice is paid, `billed - retainage == paid`, whatever the rate does at the half-cent.

**A surviving mutation, recorded rather than papered over.** The same commit moves `billed` and
`remaining` onto `money.q2` too, and reverting *those* to `round()` does not fail this file. That is
correct: both add or subtract two values that are already 2dp, which cannot land on a half-cent, so
the two roundings provably agree — checked exhaustively over 140,000 pairs, 0 disagreements. Only
`paid` was ever wrong. The other two are one-convention tidying, and this note exists so a later
reader does not mistake the surviving mutation for a gap and "strengthen" the gate to catch it.

Run: PYTHONPATH=src:../data/src ./.venv/bin/python test_penny_split.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_penny_split.db"
os.environ["STORAGE_DIR"] = "./test_storage_penny"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_penny_split.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import money  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


# Amount/rate pairs on which the PRE-FIX line produced a different answer. Verified here rather than
# asserted from memory: a fixture that does not actually straddle a half-cent would make every
# assertion below pass on the broken code too, and this file would be decoration.
#
# **The first draft of this precondition asked the wrong question** and failed, correctly. It
# compared the two conventions on the RETAINAGE (`amt * pct / 100`), but the defect was in `paid`,
# computed as `amt * (1 - pct / 100)` — a different expression that straddles on different inputs.
# Only one of the three fixtures splits on retainage; all three split on `paid`. *A precondition has
# to reproduce the defective expression, not one that resembles it.*
SPLITTERS = [(2.50, 5), (57.75, 10), (1000.10, 5)]


def pre_fix_paid(a, p):
    """`routers/cost.py` as it shipped before PENNY-SPLIT: floats, and `round()` is HALF-EVEN."""
    return round(a * (1 - p / 100), 2)


def row_implies(a, p):
    """What the row's OWN reported retainage says `paid` must be."""
    return money.q2(a - money.retainage(a, money.rate(p)))


straddles = [(a, p) for a, p in SPLITTERS if pre_fix_paid(a, p) != row_implies(a, p)]
check("every fixture would have been WRONG before the fix",
      len(straddles) == len(SPLITTERS),
      f"{[(a, p, pre_fix_paid(a, p), row_implies(a, p)) for a, p in SPLITTERS]}"
      " — if these agreed, every assertion below would pass on the broken code too")


def mk(c, pid, key, data):
    return c.post(f"/projects/{pid}/modules/{key}", json={"data": data}).json()


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Penny Split", "number": "PS-1"}).json()["id"]

    for i, (amt, pct) in enumerate(SPLITTERS):
        sc = mk(c, pid, "subcontract", {"vendor": f"Sub {i}", "trade": "Concrete",
                                        "value": 100_000, "retainage_pct": pct})
        c.post(f"/projects/{pid}/modules/subcontract/{sc['id']}/transition", json={"action": "execute"})
        si = mk(c, pid, "sub_invoice", {"vendor": f"Sub {i}", "subcontract": sc["id"],
                                        "amount": amt, "retainage_pct": pct})
        c.post(f"/projects/{pid}/modules/sub_invoice/{si['id']}/transition", json={"action": "approve"})
        c.post(f"/projects/{pid}/modules/sub_invoice/{si['id']}/transition", json={"action": "pay"})

    sb = c.get(f"/projects/{pid}/subcontractor-billing").json()
    check("the summary returned a row per subcontract", len(sb["subs"]) == len(SPLITTERS),
          f"{len(sb['subs'])} rows")

    # THE invariant. Every invoice here is `paid`, so the row's three money columns are one identity.
    for row in sb["subs"]:
        lhs = money.q2(row["billed"] - row["retainage"])
        check(f"{row['vendor']}: billed - retainage == paid",
              lhs == row["paid"],
              f"billed={row['billed']} retainage={row['retainage']} paid={row['paid']} "
              f"→ billed-retainage={lhs}")

    # ...and the retainage itself agrees with the convention `payapp` bills the owner under, so the
    # GC's two sides of the same penny cannot disagree either.
    for (amt, pct), row in zip(SPLITTERS, sorted(sb["subs"], key=lambda r: r["vendor"])):
        want = money.q2(money.retainage(amt, money.rate(pct)))
        check(f"{row['vendor']}: retainage uses the same HALF-UP convention as payapp",
              row["retainage"] == want, f"got {row['retainage']}, payapp says {want}")

    # The totals row is the same identity one level up: summing quantized floats drifts on its own.
    t = sb["totals"]
    check("totals: billed - retainage == paid",
          money.q2(t["billed"] - t["retainage"]) == t["paid"], f"{t}")
    check("totals equal the sum of the rows",
          all(t[k] == money.q2(sum(r[k] for r in sb["subs"]))
              for k in ("billed", "retainage", "paid")), f"{t}")

    # An APPROVED-but-unpaid invoice must raise `billed` and `retainage` and NOT `paid` — stated so
    # the identity above is not mistaken for a universal law. It holds because everything is paid.
    sc2 = mk(c, pid, "subcontract", {"vendor": "Partly", "trade": "Steel",
                                     "value": 100_000, "retainage_pct": 5})
    c.post(f"/projects/{pid}/modules/subcontract/{sc2['id']}/transition", json={"action": "execute"})
    si2 = mk(c, pid, "sub_invoice", {"vendor": "Partly", "subcontract": sc2["id"],
                                     "amount": 2.50, "retainage_pct": 5})
    c.post(f"/projects/{pid}/modules/sub_invoice/{si2['id']}/transition", json={"action": "approve"})
    sb2 = c.get(f"/projects/{pid}/subcontractor-billing").json()
    partly = next(r for r in sb2["subs"] if r["vendor"] == "Partly")
    check("an approved-but-unpaid invoice bills and holds retainage but pays nothing",
          partly["billed"] == 2.50 and partly["retainage"] == 0.13 and partly["paid"] == 0.0,
          f"{partly} — the identity above is scoped to fully-paid subs, not universal")

# ---- MONEY-SCOPE: a 0% retainage contract, in a second engine ---------------------------------
#
# Lives here rather than in its own file because it is the same claim one layer along — a money row
# must report what the project actually holds. `wip.py` computed
#
#     round(g703_totals.get("retainage", 0.0) or (DEFAULT_RETAINAGE / 100 * billed), 2)
#
# and `or` treats an EXPLICIT 0% as an absent one. `cost.py:49` records this exact shape under the
# name FIN-SUITE-BLIND and fixed it there; this is the instance that survived, in the engine whose
# own comment says `billed` drives over/under-billing and posts back to the ledger. The SOV's answer
# is now used whenever an SOV exists; the estimate is a fallback for having no schedule of values,
# not for a schedule that legitimately holds nothing.
zpid = c.post("/projects", json={"name": "Zero Retainage", "number": "ZR-1"}).json()["id"]
mk(c, zpid, "sov", {"item_no": "01", "description": "Sitework", "scheduled_value": 100_000,
                    "completed_this": 40_000, "retainage_pct": 0})
mk(c, zpid, "owner_invoice", {"number": "INV-1", "amount": 40_000, "period": "2026-01"})
wip = c.get(f"/projects/{zpid}/wip").json()
check("the WIP fixture actually billed something",
      wip.get("billed_to_date") == 40_000.0,
      f"billed_to_date={wip.get('billed_to_date')} — with nothing billed the 5% fallback would be "
      "0 anyway and the assertion below would pass on the broken code")
check("WIP honours an explicit 0% retainage instead of substituting the 5% default",
      wip.get("retainage") == 0.0,
      f"retainage={wip.get('retainage')} on a 0%-retainage contract billing "
      f"{wip.get('billed_to_date')} — the pre-fix `or` would report 5% of billed")

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_penny_split OK")
raise SystemExit(1 if FAILED else 0)
