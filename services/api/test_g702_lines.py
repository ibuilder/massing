"""FIN-SUITE-BLIND — G702 lines 5, 7 and 8 are VALUE-checked, on a fixture that distinguishes.

WHY THIS EXISTS
    A 10%-retainage contract shipped reporting a **negative payment due**, and `closeout.py` reads
    line 8 for the final-payment amount, so the wrong number had a consumer. The suite was green
    throughout — not because it tested the behaviour weakly, but because **`retainage_prev` was
    asserted in zero tests**, in any file, at the time this was written. Line 7 could be computed any
    way at all and nothing would have noticed.

    That is the FIN-SUITE-BLIND shape: the question is not "are the finance tests good" but "what are
    they structurally unable to see". Here the answer was a whole line of the certificate.

WHAT MAKES THIS FIXTURE DISTINGUISHING, AND WHY THE DEFAULT ONE IS NOT
    The defect needed a line whose retainage rate differs from `DEFAULT_RETAINAGE`. Line 5 sums
    retainage PER LINE; the old line 7 applied the DEFAULT rate to the aggregate. When every line uses
    the default the two agree **by coincidence**, the arithmetic is self-consistent, and any test built
    on a default-rate fixture passes against both the correct and the broken implementation.

    So the SOV below deliberately mixes rates: one line at 10%, one at 5%, one at 0%. That is the
    cheapest fixture in which "sum the per-line rates" and "apply the default to the total" produce
    different numbers — which is the only thing that makes the assertion mean anything.

    Values are hand-computed in the comments and asserted exactly. A range check (`assert due >= 0`)
    would pass on a wrong-but-positive number, and repo memory already records range-checking as the
    reason `proforma/` is the highest-yield bug area.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
os.environ.setdefault("AEC_TEST", "1")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from aec_api import cost  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402

init_db()
db = SessionLocal()

PID = "g702lines"

#: Mixed retainage rates — the whole point. With a single default rate the broken and the correct
#: line 7 agree and the fixture proves nothing.
#:
#:  item  scheduled   prev    this   ret%    completed  retainage  retainage_prev
#:   A      100000   50000   10000    10%      60000      6000.00      5000.00
#:   B       80000   40000        0     5%      40000      2000.00      2000.00
#:   C       20000   20000        0     0%      20000         0.00         0.00
#:  totals  200000  110000   10000            120000      8000.00      7000.00
SOV = [
    {"item_no": "A", "description": "Concrete", "scheduled_value": 100000,
     "completed_prev": 50000, "completed_this": 10000, "retainage_pct": 10},
    {"item_no": "B", "description": "Steel", "scheduled_value": 80000,
     "completed_prev": 40000, "completed_this": 0, "retainage_pct": 5},
    {"item_no": "C", "description": "Sitework", "scheduled_value": 20000,
     "completed_prev": 20000, "completed_this": 0, "retainage_pct": 0},
]


def seed():
    """Seed the SOV, clearing first — the SQLite file persists between runs.

    Without this the second run reports totals that are the sum of two seedings, every value
    assertion fails, and the failure looks like an arithmetic defect rather than a dirty fixture.
    That misreading costs more than the cleanup does."""
    from aec_api import modules as me
    for r in me.list_records(db, "sov", PID, limit=1000):
        me.delete_record(db, "sov", PID, r["id"], "test@g702", None)
    db.commit()
    for row in SOV:
        me.create_record(db, "sov", PID, {"data": row}, "test@g702", None)
    db.commit()
    n = len(me.list_records(db, "sov", PID, limit=1000))
    assert n == len(SOV), f"fixture is dirty: {n} rows for {len(SOV)} seeded"


# The fixture only distinguishes the two implementations while at least one line's rate differs from
# DEFAULT_RETAINAGE. If the default ever moves to 10 this must fail LOUDLY rather than quietly
# downgrade every assertion below into a coincidence.
#
# (The first draft of this check read `X not in (0, 5, 10) or True`, which cannot fail — a vacuous
# guard written into the file whose entire subject is assertions that cannot see their target.)
_overrides = [r["retainage_pct"] for r in SOV if r["retainage_pct"] != cost.DEFAULT_RETAINAGE]
check("at least one fixture line overrides DEFAULT_RETAINAGE — otherwise this fixture proves nothing",
      len(_overrides) >= 1,
      f"rates {[r['retainage_pct'] for r in SOV]} vs default {cost.DEFAULT_RETAINAGE}; "
      f"overriding: {_overrides}")

seed()

# ---------------------------------------------------------------- G703: the per-line arithmetic
sov = cost.g703(db, PID)
t = sov["totals"]
check("G703 total completed", t["completed"] == 120000.0, t["completed"])
check("G703 total retainage is the SUM OF PER-LINE rates, not the default on the total",
      t["retainage"] == 8000.0,
      f"{t['retainage']} (a default-{cost.DEFAULT_RETAINAGE}% aggregate would be "
      f"{round(120000 * cost.DEFAULT_RETAINAGE / 100, 2)})")
check("G703 retainage_prev — the value that was asserted NOWHERE before this file",
      t["retainage_prev"] == 7000.0, t["retainage_prev"])

# Per-line, so a defect in one rate cannot hide inside a correct total.
by_item = {ln["item_no"]: ln for ln in sov["lines"]}
check("line A retainage 10% of 60000", by_item["A"]["retainage"] == 6000.0, by_item["A"]["retainage"])
check("line A retainage_prev 10% of 50000", by_item["A"]["retainage_prev"] == 5000.0,
      by_item["A"]["retainage_prev"])
check("line B retainage 5% of 40000", by_item["B"]["retainage"] == 2000.0, by_item["B"]["retainage"])
check("line C at 0% holds nothing — an explicit zero rate is not 'unset'",
      by_item["C"]["retainage"] == 0.0 and by_item["C"]["retainage_prev"] == 0.0,
      f"{by_item['C']['retainage']} / {by_item['C']['retainage_prev']}")

# ---------------------------------------------------------------- G702: lines 5, 6, 7, 8
app = cost.g702(db, PID, app_no=2)
#   line 5 retainage                       = 8000
#   line 6 earned less retainage           = 120000 - 8000            = 112000
#   line 7 less previous certificates      = 110000 - 7000            = 103000
#   line 8 current payment due             = 112000 - 103000          =   9000
check("line 5 retainage", app["line5_retainage"] == 8000.0, app["line5_retainage"])
check("line 6 total earned less retainage", app["line6_total_earned_less_retainage"] == 112000.0,
      app["line6_total_earned_less_retainage"])
check("line 7 less previous certificates — prev MINUS prior retainage, not prev alone",
      app["line7_less_previous_certificates"] == 103000.0,
      f"{app['line7_less_previous_certificates']} (using prev alone would give 110000.0)")
check("line 8 current payment due", app["line8_current_payment_due"] == 9000.0,
      app["line8_current_payment_due"])

# The defect's actual signature. A sign check alone would be satisfied by any positive wrong number,
# so it sits BESIDE the exact value above rather than instead of it.
check("line 8 is not negative — the shipped defect's signature",
      app["line8_current_payment_due"] > 0, app["line8_current_payment_due"])

# Lines 5-8 must be internally consistent, so a future edit cannot fix one line by breaking another.
check("line 6 == line 4 - line 5",
      app["line6_total_earned_less_retainage"]
      == round(app["line4_total_completed_stored"] - app["line5_retainage"], 2))
check("line 8 == line 6 - line 7",
      app["line8_current_payment_due"]
      == round(app["line6_total_earned_less_retainage"]
               - app["line7_less_previous_certificates"], 2))

# ---------------------------------------------------------------- the zero-work period
# The exact shape that produced the negative: a period where nothing new was completed. Line 8 must be
# 0, never negative — the contractor is owed nothing, not owed a refund.
from aec_api import modules as me  # noqa: E402

for r in me.list_records(db, "sov", PID, limit=100):
    d = dict(r["data"]); d["completed_this"] = 0
    me.update_record(db, "sov", PID, r["id"], d, "test@g702", None)
db.commit()
flat = cost.g702(db, PID, app_no=3)
check("a period with no new work bills ZERO, never a negative",
      flat["line8_current_payment_due"] == 0.0, flat["line8_current_payment_due"])

# ---------------------------------------------------------------- retainage release (final app)
# Re-seed: the zero-work section above mutated the fixture, so the amount held is no longer the 8000
# the table at the top computes. Asserting against a stale expectation here would have been a test
# failure that reads as an engine defect — the same misdirection the fixture-cleanup guards against.
seed()
normal = cost.g702(db, PID, app_no=4)
final = cost.g702(db, PID, app_no=4, release_retainage=True)

check("the final application releases retainage — line 5 goes to zero",
      final["line5_retainage"] == 0.0, final["line5_retainage"])

# The release is asserted as a DIFFERENCE, which isolates it. An absolute expectation here also
# depends on the period's own work, so it would fail for two unrelated reasons and could pass by
# their cancelling out.
released = round(final["line8_current_payment_due"] - normal["line8_current_payment_due"], 2)
check("releasing retainage adds exactly the held amount to what is due, not merely zeroing line 5",
      released == 8000.0,
      f"released {released} vs held {normal['line5_retainage']}")
check("the released amount equals the retainage line 5 was holding",
      released == normal["line5_retainage"],
      f"{released} vs {normal['line5_retainage']}")

db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_g702_lines OK")
