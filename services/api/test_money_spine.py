"""One rounding convention for retainage, asserted at every site that computes it.

v0.3.927 shipped under the title *"money is Decimal end to end"*. It was right about `payapp.py` and
wrong about the tree: `cost.py` (twice) and `routers/cost.py` (once) kept computing retainage as
`round(amount * pct / 100, 2)` on binary floats. `round()` is ROUND_HALF_EVEN; an invoice rounds half
away from zero. **Two conventions inside one G702.**

The assertion that matters is `the two conventions DISAGREED, and by a penny` — it recomputes the old
arithmetic beside the new, so the fix is a measured difference rather than a claim. A pay application
out by a penny is rejected, which makes this a document defect rather than a rounding curiosity.

The second is `payapp and money agree` — the two modules still carry their own quantize helpers, and
that duality is fine only for as long as they give the same answer. This checks that they do rather
than merging them, because merging a shipped billing path is risk without a defect to justify it.
"""
from __future__ import annotations

from decimal import Decimal

from aec_api import money, payapp

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: Values where the half-cent lands exactly on the boundary — the only place the two rounding modes
#: can differ. `37.50 @ 1%` and `100 @ 10%` are the controls: they agree either way.
CASES = [(2.50, 5), (12.50, 1), (0.25, 50), (37.50, 1), (162.50, 1), (100.00, 10)]


def old_float_retainage(amount: float, pct: float) -> float:
    """`cost.py` before v0.3.969, reproduced exactly. Kept so the claim stays measurable."""
    return round(amount * pct / 100, 2)


def main() -> int:
    # --- THE finding, measured rather than asserted -------------------------------------------
    rows = [(a, p, old_float_retainage(a, p), money.retainage(a, p)) for a, p in CASES]
    disagreed = [r for r in rows if r[2] != r[3]]
    check("the two conventions DISAGREED, and by a penny",
          # Compared in CENTS, not by subtracting floats: `1.63 - 1.62` is 0.010000000000000009,
          # so `abs(old - new) == 0.01` failed on the first run. In a test about float money.
          len(disagreed) >= 3 and all(round(abs(o - n) * 100) == 1 for _, _, o, n in disagreed),
          f"{[(a, f'{p}%', o, n) for a, p, o, n in disagreed]} — float+round() vs half-up. "
          f"{len(disagreed)} of {len(CASES)} sampled cases")

    check("...and the controls agreed, so the difference is the ROUNDING not the arithmetic",
          any(o == n for _, _, o, n in rows),
          f"{[(a, f'{p}%') for a, p, o, n in rows if o == n]} — where the half-cent does not land "
          "on the boundary both modes give the same answer, which is why this went unnoticed")

    check("the accounting convention is HALF-UP: 2.675 becomes 2.68, not 2.67",
          money.q2(2.675) == 2.68 and round(2.675, 2) == 2.67,
          "an invoice rounds half away from zero; round() is HALF-EVEN over a binary float")

    # --- the duality that is allowed only while it agrees ------------------------------------------
    #
    # `payapp` carries its own `_q` / `_retainage` (v0.3.927) and `money` carries `q2` / `retainage`.
    # Two implementations of one convention is exactly the shape that produced "two objects both
    # called an RFI" — tolerable here ONLY because they agree, so the agreement is the assertion.
    mismatch = [(a, p) for a, p in CASES
                if float(payapp._retainage(payapp._money(a), payapp._money(p)))
                != money.retainage(a, p)]
    check("payapp and money agree on every sampled case",
          not mismatch,
          f"{len(CASES)} cases, no disagreement" if not mismatch else f"DIVERGED on {mismatch}")

    # --- every site now uses it, read from the source ------------------------------------------------
    #
    # The point of this file is that ONE site kept the old arithmetic for two releases while the
    # release note said the tree was done. So the population is read, not remembered.
    from pathlib import Path
    src = Path(__file__).resolve().parent / "src" / "aec_api"
    offenders = []
    for rel in ("cost.py", "routers/cost.py", "payapp.py"):
        for i, line in enumerate((src / rel).read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"'):
                continue                  # a comment describing the old form is not the old form
            if "round(" in line and "/ 100" in line and "retain" in line.lower():
                offenders.append(f"{rel}:{i}")
    check("no site computes retainage with float round() any more",
          not offenders,
          f"{offenders}" if offenders else "cost.py, routers/cost.py and payapp.py all quantize")

    planted = "x = round(amt * retainage_pct / 100, 2)"
    check("...and the scan can still SEE that form — the twin",
          "round(" in planted and "/ 100" in planted and "retain" in planted.lower(),
          "a source scan that matches nothing reports every tree as clean")

    # --- the absence rule a truthiness test breaks -----------------------------------------------------
    check("an explicit 0% rate is honoured, not replaced by the default",
          money.rate(0) == Decimal(0) and money.rate("0") == Decimal(0),
          "`or DEFAULT_RETAINAGE` withheld 5% on a line the owner agreed to hold nothing on — "
          "$1,000 on a $20,000 line, and the contractor is underpaid by a plausible-looking number")

    check("...while a MISSING rate still gets the contract default — the twin",
          money.rate(None) == Decimal("5") and money.rate("") == Decimal("5"),
          "a missing amount is zero money, a missing rate is the default, an explicit zero neither")

    # --- exactness, the reason for Decimal at all --------------------------------------------------------
    check("one quantize at the end, not one per operand",
          money.retainage("0.005", 100) == 0.01,
          "quantizing the operands first rounds twice and compounds down a schedule of values")

    check("the allocator still splits to the cent",
          sum(money.allocate(100, [1, 1, 1])) == 100.0,
          f"{money.allocate(100, [1, 1, 1])} — 33.33 x 3 is 99.99, and the penny has to land "
          "somewhere; this module already solved that and it stays solved")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_money_spine OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
