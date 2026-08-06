"""R22-PROVENANCE — the estimate leg, gathered for real, and the rename that would have faked it.

`provenance_report` reported the estimate leg `not_captured` and said exactly why: the `estimate`
register stored line items as code/description/qty/unit/unit_cost/amount and captured no `source`,
`quote_ref` or `basis_date` — the three fields a basis-of-estimate ledger checks. Those columns now
exist, so the leg is gathered from stored records instead of only from a request body.

**The check that matters is the seam, not the columns.** `boe_ledger` reads `cost_code` and `total`;
the register's columns are `code` and `amount`. Handing the rows over unmapped does not crash — and
that is the danger. `_key()` falls through to `description`, so every line still gets a key,
`cost_code` comes back None on every row, and `total` silently drops to None for any line priced as a
lump sum rather than qty x unit_cost. The output is a full, plausible, quietly-wrong ledger.

So these checks are written against `boe_ledger`'s REAL output — the module is imported and run, not
imitated by a fixture built to agree with my mapping. A fixture that supplies both sides of a seam
agrees with itself no matter which side is wrong.

The other refusal: the ANSWERS leg must stay `not_captured`. Closing one leg is not closing the ring,
and a verdict that quietly promoted itself to `admissible` would be the exact failure this module was
written to prevent.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_provenance_estimate_leg.py
"""
import json
import sys

sys.path.insert(0, "src")

from aec_api import boe_ledger  # noqa: E402
from aec_api import provenance_report as pr

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- the register really carries the three columns now --------------------------------------------
mod = json.load(open("modules/estimate/module.json", encoding="utf-8"))
cols = {c["name"] for f in mod["fields"] if f["name"] == "line_items" for c in f["columns"]}
for c in ("source", "quote_ref", "basis_date"):
    check(f"the estimate register captures {c!r}", c in cols, sorted(cols))
check("  without dropping the columns it already had",
      {"code", "description", "qty", "unit", "unit_cost", "amount"} <= cols, sorted(cols))

# --- THE SEAM — asserted against boe_ledger's real behaviour ---------------------------------------
REC = [{"data": {"line_items": [
    # a lump-sum line: NO qty/unit_cost, so `total` can only come from `amount`
    {"code": "03 30 00", "description": "Concrete", "amount": 250_000,
     "source": "quote", "quote_ref": "Q-118", "basis_date": "2026-06-01"},
    # a measured line, fully documented
    {"code": "04 20 00", "description": "Masonry", "qty": 1200, "unit": "sf", "unit_cost": 32,
     "amount": 38_400, "source": "historical", "basis_date": "2026-05-14"},
    # undocumented: no source, no basis date
    {"code": "09 90 00", "description": "Painting", "qty": 5000, "unit": "sf", "unit_cost": 3,
     "amount": 15_000},
]}}]

mapped = pr.estimate_lines(REC)
check("every line item is gathered", len(mapped) == 3, len(mapped))

led = boe_ledger.ledger(mapped)
rows = {r["description"]: r for r in led["lines"]}

check("THE COST CODE SURVIVES THE SEAM — boe_ledger sees cost_code, the register wrote code",
      rows["Concrete"]["cost_code"] == "03 30 00", rows["Concrete"])
check("  so the ledger keys on the code, not on the description text",
      led["lines"][0]["key"] == "03 30 00", led["lines"][0]["key"])
check("THE LUMP-SUM AMOUNT SURVIVES — a line with no qty x unit_cost still has a total",
      rows["Concrete"]["total"] == 250_000, rows["Concrete"]["total"])
check("  while a measured line is still computed from qty x unit_cost",
      rows["Masonry"]["total"] == 38_400, rows["Masonry"]["total"])
check("the documentation fields arrive",
      rows["Concrete"]["source"] == "quote" and rows["Concrete"]["quote_ref"] == "Q-118"
      and rows["Concrete"]["basis_date"] == "2026-06-01", rows["Concrete"])

check("the undocumented line is CAUGHT, not counted as fine",
      [u["description"] for u in led["undocumented"]] == ["Painting"], led["undocumented"])
check("  naming which fields it lacks", sorted(led["undocumented"][0]["missing"]) ==
      ["basis_date", "source"], led["undocumented"][0]["missing"])
check("two of three lines are documented", led["documented"] == 2, led["documented"])

# a quote line with no quote_ref is its own failure, and the register can now express it
q = boe_ledger.ledger(pr.estimate_lines(
    [{"data": {"line_items": [{"code": "1", "description": "X", "amount": 1, "source": "quote",
                               "basis_date": "2026-01-01"}]}}]))
check("a line claiming a QUOTE with no quote ref is undocumented",
      q["undocumented"] and "quote_ref" in q["undocumented"][0]["missing"], q["undocumented"])

# --- pass-through: a row already named the ledger's way is not clobbered ---------------------------
pt = pr.estimate_lines([{"data": {"line_items": [
    {"cost_code": "already", "description": "D", "total": 99}]}}])
check("a row already using the ledger's names is left alone",
      pt[0]["cost_code"] == "already" and pt[0]["total"] == 99, pt[0])
check("the mapping is stated in one place, not scattered",
      pr.ESTIMATE_TO_BOE == {"code": "cost_code", "amount": "total"}, pr.ESTIMATE_TO_BOE)
check("no records is no lines, not a crash", pr.estimate_lines(None) == [])

# --- THE REFUSAL — closing one leg is not closing the ring -----------------------------------------
check("the ANSWERS leg is still declared not-captured",
      "answers" in pr.NOT_CAPTURED_REASON, sorted(pr.NOT_CAPTURED_REASON))
check("  and the estimate leg is NO LONGER excused as not-captured",
      "estimate" not in pr.NOT_CAPTURED_REASON, sorted(pr.NOT_CAPTURED_REASON))
check("  with the answers reason naming the schema change it needs",
      "not persisted" in pr.NOT_CAPTURED_REASON["answers"])

rep = pr.report(None, led, None)
check("a report with a real estimate ledger is NOT admissible on that alone",
      rep["verdict"] != pr.VERDICT_ADMISSIBLE, rep["verdict"])

print()
if FAILED:
    print(f"provenance_estimate_leg: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("provenance_estimate_leg: all checks passed")
