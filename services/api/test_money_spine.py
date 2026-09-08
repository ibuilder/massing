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

    # --- every site now uses it, DERIVED from the source ---------------------------------------
    #
    # The point of this file is that ONE site kept the old arithmetic for two releases while the
    # release note said the tree was done. So the population is read, not remembered — and until
    # MONEY-SCOPE it was remembered anyway, twice over:
    #
    #   1. It scanned a HARDCODED list of three files. Five more sites lived outside them —
    #      `evm.py`, `project_budget.py` (x3) and `wip.py`, the last of them computing retainage,
    #      which is this file's own subject.
    #   2. Its predicate required the literal substring "retain" ON THE LINE. The site PENNY-SPLIT
    #      fixed reads `round(row["paid"] + amt * (1 - ret_pct / 100), 2)` — it matched `round(`
    #      and `/ 100` and was MISSED, because `ret_pct` does not contain "retain".
    #
    # **The third term was a spelling, and the site that survived used an abbreviation.** The scan
    # is now structural: `round(<expression containing a division by 100>, 2)`, over every file,
    # naming nothing. A variable rename cannot hide from it.
    import ast
    from pathlib import Path

    def _divides_by_100(node: ast.AST) -> bool:
        return any(isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)
                   and isinstance(n.right, ast.Constant) and n.right.value == 100
                   for n in ast.walk(node))

    def _ndigits(call: ast.Call):
        """`round()`'s second argument, however it was PASSED — positionally or as `ndigits=`.

        `round(x, ndigits=2)` is valid Python and returns the same HALF-EVEN answer as
        `round(x, 2)` (measured: `round(2.675, ndigits=2)` is 2.67). The first version of this scan
        read `n.args[1]` and missed it — **which is this file's own lesson one turn later.** The old
        predicate depended on a NAME and the surviving site used an abbreviation; the replacement
        dropped the name and still depended on a syntactic FORM. A reviewer caught it.
        """
        for kw in call.keywords:
            if kw.arg == "ndigits":
                return kw.value
        return call.args[1] if len(call.args) >= 2 else None

    def scan(text: str) -> list[int]:
        """Line numbers where money is quantized to cents by `round()` over a percentage."""
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        out = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "round" and n.args):
                continue
            nd = _ndigits(n)
            if isinstance(nd, ast.Constant) and nd.value == 2 and _divides_by_100(n.args[0]):
                out.append(n.lineno)
        return out

    # **Prove the scan before believing it.** A clean report over a clean tree is indistinguishable
    # from a broken detector, and this exact file already shipped one that could not see the defect
    # it was named for. Both historical forms must be found; a display percentage must not be.
    PRE_FIX_PAID = 'x = round(paid + amt * (1 - ret_pct / 100), 2)'      # PENNY-SPLIT, no "retain"
    PRE_FIX_RETAINAGE = 'x = round(completed * retainage_pct / 100, 2)'  # what the old scan caught
    DISPLAY_PCT = 'x = round(100 * done / total, 1)'                     # a percentage, not money
    KEYWORD_FORM = 'x = round(amt * pct / 100, ndigits=2)'               # same result, other spelling
    check("the scan finds the form that DEFEATED the old lexical one",
          scan(PRE_FIX_PAID) == [1],
          "`ret_pct` contains no 'retain'; the old predicate required that substring and missed it")
    check("...and the KEYWORD form, which the first structural draft also missed",
          scan(KEYWORD_FORM) == [1],
          "round(x, ndigits=2) is valid Python and returns the same HALF-EVEN answer — "
          "a reviewer caught this file repeating its own lesson one layer along")
    check("...and still finds the form the old one did catch — the twin",
          scan(PRE_FIX_RETAINAGE) == [1])
    check("...and does NOT flag a display percentage rounded to 1dp",
          scan(DISPLAY_PCT) == [],
          "a scan that matches everything is as useless as one that matches nothing")

    src = Path(__file__).resolve().parent / "src" / "aec_api"
    files = sorted(src.rglob("*.py"))
    offenders = [f"{f.relative_to(src)}:{ln}" for f in files
                 for ln in scan(f.read_text(encoding="utf-8"))]
    check("no site in aec_api quantizes money to cents with float round()",
          not offenders,
          f"{offenders}" if offenders
          else f"scanned {len(files)} files, structurally, naming nothing")

    # **Assert the SCOPE, not only the verdict.** With the tree clean, narrowing this scan back to a
    # handful of files would pass silently — which is exactly how it spent two releases reporting a
    # tree it was not reading. So the population is pinned to the whole package: every module that
    # holds money must be inside it, and the four that historically did are named as a floor.
    scanned = {str(f.relative_to(src)) for f in files}
    must_reach = {"cost.py", "routers/cost.py", "payapp.py", "wip.py",
                  "evm.py", "project_budget.py"}
    check("the scan reaches every module, not a remembered handful",
          must_reach <= scanned and len(files) > 100,
          f"{len(files)} files; missing {sorted(must_reach - scanned)}" if must_reach - scanned
          else f"{len(files)} files, including the 3 the old scan listed and the 3 it did not")

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
