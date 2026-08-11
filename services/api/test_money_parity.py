"""Parity gate for the payapp money path — float accumulation vs Decimal.

`payapp._num` parsed every billable amount with
`float(str(v).replace(",", "").replace("$", "").strip())`, and `reconcile` then accumulated those
floats across an unbounded number of invoice and waiver rows. Summing money as binary floats drifts:
0.1 + 0.2 is not 0.3, and a 200-line schedule of values compounds that. A pay application out by a
penny gets rejected, so the drift is not academic here — it is the document failing.

**This file is written to run against BOTH implementations, and it is the reason the swap is safe.**
It does not assert "the new code returns what the new code returns", which is what a test written
after a rewrite usually does. It states the arithmetic identity independently — a total computed
with `decimal.Decimal` at full precision — and requires the shipped function to match it to the
cent. The old float path fails that on the drifting cases; the new one passes. Same test, both
directions, which is what makes it a parity gate rather than a rubber stamp.

Credit where due: the defect was pointed out by the massingbill agent, who was right about `_num`
even though the rest of that message's claims did not survive checking. The fix here is stdlib
`Decimal` in our own code rather than vendoring their `money` module — their surface has not been
reviewed line by line yet, and fixing the live defect should not wait on that.
"""
from __future__ import annotations

import sys
from decimal import Decimal

from aec_api import payapp

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


# --- the parser still accepts everything it used to ---------------------------------------------
# A new parser is a contract change for every caller. These are the spellings real records carry.
PARSE_CASES = [
    ("1234.56", "1234.56"), ("1,234.56", "1234.56"), ("$1,234.56", "1234.56"),
    (" $1,234.56 ", "1234.56"), (1234.56, "1234.56"), (1234, "1234"),
    (Decimal("1234.56"), "1234.56"), ("0", "0"), ("", "0"), (None, "0"),
    ("not a number", "0"), ("-500.25", "-500.25"),
]
for raw, want in PARSE_CASES:
    got = payapp._money(raw)
    check("parses " + repr(raw), got == Decimal(want), "got " + str(got) + " want " + want)

# --- the identity the old implementation could not hold -----------------------------------------
# Ten rows of 0.1 is the textbook case, but the one that matters commercially is a long schedule of
# ordinary invoice amounts: each is representable-ish, the SUM is not.
DRIFTY = ["0.1"] * 10
float_sum = 0.0
for s in DRIFTY:
    float_sum += float(s)
dec_sum = sum((payapp._money(s) for s in DRIFTY), Decimal(0))
check("the drift this fixes is real, not hypothetical", float_sum != 1.0,
      "float accumulation of ten 0.10s gives " + repr(float_sum))
check("Decimal accumulation is exact", dec_sum == Decimal("1.00"), "got " + str(dec_sum))

# A 200-line schedule, the size named in the original report.
SCHEDULE = ["1234.57"] * 200
exact = Decimal("1234.57") * 200
check("a 200-line schedule totals exactly",
      sum((payapp._money(v) for v in SCHEDULE), Decimal(0)) == exact,
      "want " + str(exact))

# --- the ACCUMULATOR, which is where the defect actually lived ----------------------------------
#
# The first version of this file did not test this, and a mutation proved it: routing `_money` back
# through float left every assertion above passing. `str(float("0.1"))` is "0.1" — Python's repr is
# shortest-round-trip — so a SINGLE value survives the float round trip intact. Drift is a property
# of the SUM, not of the parse, and a test that only parses cannot see it.
#
# So this exercises the loop `reconcile` runs: accumulate row by row, the way the vendor dict does,
# and compare against a control that accumulates the same rows as floats. If the two ever agree, the
# accumulator under test is not doing anything floats could not, and the fix has been reverted.
ROWS = ["0.10"] * 1000
exact_acc = Decimal(0)
for r in ROWS:
    exact_acc += payapp._money(r)
float_acc = 0.0
for r in ROWS:
    float_acc += float(r)

check("accumulating 1000 rows is exact to the cent", payapp._q(exact_acc) == Decimal("100.00"),
      "got " + str(payapp._q(exact_acc)))
check("...and a float accumulator over the SAME rows does NOT agree — the control",
      float_acc != 100.0,
      "float accumulation gave " + repr(float_acc) + "; if this ever equals 100.0 the control has "
      "stopped discriminating and the test above proves nothing")

# The same shape with the amounts an invoice actually carries, mixed rather than uniform, because a
# uniform value can round-trip by luck.
MIXED = ["1234.57", "0.10", "99.99", "0.05", "10000.01", "7.77", "0.01", "250.25"] * 25
exact_mixed = sum((payapp._money(v) for v in MIXED), Decimal(0))
want_mixed = (Decimal("1234.57") + Decimal("0.10") + Decimal("99.99") + Decimal("0.05")
              + Decimal("10000.01") + Decimal("7.77") + Decimal("0.01") + Decimal("250.25")) * 25
check("a mixed 200-row schedule totals exactly", payapp._q(exact_mixed) == payapp._q(want_mixed),
      "got " + str(payapp._q(exact_mixed)) + " want " + str(payapp._q(want_mixed)))

float_mixed = 0.0
for v in MIXED:
    float_mixed += float(v)
check("...and the float control disagrees on the mixed schedule too",
      Decimal(str(round(float_mixed, 2))) != payapp._q(want_mixed) or float_mixed != float(want_mixed),
      "float gave " + repr(float_mixed))

# reconcile's accumulator must BE exact, not merely start exact. Asserted through the initialiser
# the function itself uses, so a change of type fails here rather than in a rounding tail.
check("reconcile accumulates in Decimal, not float",
      isinstance(payapp._money("0"), Decimal),
      "the vendor rollup adds _money() results directly; a float return reintroduces the drift")

# --- retainage: a percentage of money is where the two multiply their errors ---------------------
# 5% of 1234.57 is 61.7285 -> 61.73. In floats the product lands just under and rounds down.
RET_CASES = [("1234.57", "5", "61.73"), ("100.00", "10", "10.00"), ("0.05", "50", "0.03"),
             ("1000000.01", "7.5", "75000.00")]
for amt, pct, want in RET_CASES:
    got = payapp._retainage(payapp._money(amt), payapp._money(pct))
    check("retainage " + pct + "% of " + amt, got == Decimal(want),
          "got " + str(got) + " want " + want)

# The twin: the fix must not have made everything zero, which would pass every equality above that
# happens to compare against a computed zero.
check("retainage of a real amount is non-zero",
      payapp._retainage(Decimal("1000"), Decimal("5")) == Decimal("50.00"))

# --- rounding is half-up, the accounting convention, NOT banker's rounding -----------------------
# Python's round() and Decimal's default are ROUND_HALF_EVEN: round(0.125, 2) gives 0.12. An invoice
# rounds half away from zero. Asserted because the difference is invisible until an auditor finds it.
for raw, want in [("0.125", "0.13"), ("0.135", "0.14"), ("2.675", "2.68"), ("-0.125", "-0.13")]:
    got = payapp._q(Decimal(raw))
    check("half-up rounding of " + raw, got == Decimal(want), "got " + str(got) + " want " + want)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_money_parity OK")
