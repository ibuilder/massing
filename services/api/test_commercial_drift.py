"""R41-COMMERCIAL-DRIFT — the drift is real, and an agreed number is not drift.

The entry asks for a diff across bid → contract → PO → invoice. Premise-checked first: three of the
four hops already exist AND are already referentially wired, and `margin.py`/`cost_spine.py` already
diff the chain **per cost code** — which structurally cannot see this, because a roll-up adds before
it compares and two documents can net to the right code total while one award drifted.

So the engine walks documents. These checks are about the two ways such a walk lies:

1. **calling an agreed number a problem.** `subcontract.change_orders` sums signed change orders. Put
   it in the bid-to-contract hop and every project with a CO reports scope added in the dark. And an
   **unaccepted** alternate was never bought — comparing the bid's `amount` blindly treats rejected
   alternates as awarded, comparing `base_bid` alone treats accepted ones as scope from nowhere;
2. **calling a missing number a zero.** A bid with no figure against a real contract is not a 100%
   overrun. Incomparable is its own status and is counted separately.

The field names below were read off the registers (`base_bid`, `alternates[].accepted`, `value`,
`change_orders`, `awarded_from`, `subcontract`, `amount`), not assumed — inventing key names is the
seam that has cost this session repeatedly.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_commercial_drift.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import commercial_drift as cd  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def hop(row, name):
    return next(h for h in row["hops"] if h["hop"] == name)


# --- 1. THE AWARD FIGURE: accepted alternates count, rejected ones do not -------------------------
BID = {"id": "b1", "data": {"bidder": "Ace", "base_bid": 100_000,
                            "alternates": [{"no": "1", "amount": 10_000, "accepted": True},
                                           {"no": "2", "amount": 25_000, "accepted": False}]}}
f = cd.bid_award_figure(BID)
check("the award figure is base bid + ACCEPTED alternates only",
      f["value"] == 110_000, f)
check("  on a basis the row states, so a reader can disagree with it",
      f["basis"] == cd.BASIS_BASE_PLUS_ACCEPTED, f["basis"])
check("  the rejected alternate is excluded — it was never bought",
      f["accepted_alternates"] == 1 and f["accepted_alternates_value"] == 10_000, f)
check("a bid with only `amount` falls back to it, and says so",
      cd.bid_award_figure({"id": "x", "data": {"amount": 77_000}})["basis"] == cd.BASIS_AMOUNT)
check("a bid with no figure at all is UNAVAILABLE, not zero",
      cd.bid_award_figure({"id": "y", "data": {}})["value"] is None)

# --- 2. THE WALK ----------------------------------------------------------------------------------
SUBS = [
    # awarded at 118k against a 110k comparable bid -> 8k of scope added between bid and contract,
    # PLUS 20k of signed change orders that must NOT be counted as drift.
    {"id": "s1", "data": {"vendor": "Ace", "trade": "Concrete", "value": 118_000,
                          "change_orders": 20_000, "awarded_from": "b1"}},
    # awarded exactly at bid; over-invoiced against the agreed sum.
    {"id": "s2", "data": {"vendor": "Bolt", "trade": "Steel", "value": 50_000,
                          "change_orders": 0, "awarded_from": "b2"}},
    # no linked bid at all -> the first hop cannot be compared.
    {"id": "s3", "data": {"vendor": "Cole", "trade": "Glazing", "value": 30_000}},
]
BIDS = [BID, {"id": "b2", "data": {"bidder": "Bolt", "amount": 50_000}}]
INVS = [
    {"id": "i1", "data": {"subcontract": "s1", "amount": 60_000}},
    {"id": "i2", "data": {"subcontract": "s1", "amount": 40_000}},
    {"id": "i3", "data": {"subcontract": "s2", "amount": 62_000}},   # over the 50k agreed sum
]
R = cd.walk(BIDS, SUBS, INVS)
row = {r["subcontract_id"]: r for r in R["rows"]}

check("every subcontract produces a row", R["subcontract_count"] == 3, R["subcontract_count"])

s1 = hop(row["s1"], "bid_to_contract")
check("BID → CONTRACT drift is measured against the comparable bid, not the base bid",
      s1["from"] == 110_000 and s1["to"] == 118_000, (s1["from"], s1["to"]))
check("  the delta is the scope added between bid and executed contract",
      s1["delta"] == 8_000, s1["delta"])
check("  THE CHANGE ORDERS ARE NOT IN IT — a CO is money somebody signed for",
      s1["delta"] == 8_000 and row["s1"]["change_orders"] == 20_000,
      (s1["delta"], row["s1"]["change_orders"]))
check("  and drift_pct is off the bid, not off the contract",
      s1["drift_pct"] == round(8_000 / 110_000 * 100, 2), s1["drift_pct"])

s1b = hop(row["s1"], "contract_to_invoiced")
check("CONTRACT → INVOICED compares against the sum INCLUDING change orders",
      s1b["from"] == 138_000, s1b["from"])
check("  billing 100k of an agreed 138k is under, not drift-positive",
      s1b["delta"] == -38_000, s1b["delta"])
check("  and the contract sum to date is stated on the row",
      row["s1"]["contract_sum_to_date"] == 138_000, row["s1"]["contract_sum_to_date"])

s2 = hop(row["s2"], "contract_to_invoiced")
check("OVER-INVOICING against the agreed sum shows as positive drift",
      s2["delta"] == 12_000, s2["delta"])
check("  a contract awarded exactly at bid shows zero drift on the first hop",
      hop(row["s2"], "bid_to_contract")["delta"] == 0,
      hop(row["s2"], "bid_to_contract")["delta"])

# --- 3. A MISSING FIGURE IS NOT A ZERO ------------------------------------------------------------
s3 = hop(row["s3"], "bid_to_contract")
check("a subcontract with no linked bid is INCOMPARABLE on that hop",
      s3["status"] == cd.STATUS_INCOMPARABLE, s3["status"])
check("  with no delta invented for it",
      s3["delta"] is None and s3["drift_pct"] is None, s3)
check("  and the note says it is not a zero-dollar difference",
      "NOT a zero-dollar difference" in s3["note"], s3["note"])
check("  while its OTHER hop still works — absence is per-hop",
      hop(row["s3"], "contract_to_invoiced")["status"] == cd.STATUS_INCOMPARABLE
      or hop(row["s3"], "contract_to_invoiced")["from"] == 30_000)
check("incomparable hops are COUNTED, not dropped",
      R["hops_incomparable"] >= 1, R["hops_incomparable"])
# DERIVED from the rows, not a literal. This read `== 6` (3 subcontracts x 2 hops) and adding the
# PO hop in v0.3.970 made it 9 — a hardcoded total that had no way to notice a hop was added, which
# is the same drift the roadmap's own item-count line was rewritten to avoid. Every hop must land in
# exactly one bucket; that is the claim, and it survives a fourth hop.
_total_hops = sum(len(r["hops"]) for r in R["rows"])
check("  separately from the ones that were compared, and every hop lands in exactly one bucket",
      R["hops_compared"] + R["hops_incomparable"] == _total_hops,
      (R["hops_compared"], R["hops_incomparable"], _total_hops))

# --- 4. the roll-up cannot see what this sees ------------------------------------------------------
# Two subcontracts that net to zero on a shared cost code, one over and one under. A per-code total
# reports nothing; the per-document walk reports both.
NET = cd.walk(
    [{"id": "n1", "data": {"amount": 100_000}}, {"id": "n2", "data": {"amount": 100_000}}],
    [{"id": "m1", "data": {"vendor": "A", "value": 115_000, "awarded_from": "n1"}},
     {"id": "m2", "data": {"vendor": "B", "value": 85_000, "awarded_from": "n2"}}], [])
deltas = sorted(hop(r, "bid_to_contract")["delta"] for r in NET["rows"])
check("TWO AWARDS THAT NET TO ZERO ARE BOTH REPORTED — the per-code roll-up cannot see this",
      deltas == [-15_000, 15_000], deltas)
check("  and both count as drifted", NET["drifted_count"] == 2, NET["drifted_count"])

# ---------------------------------------------------------------------------------------------
# The PO hop (v0.3.970). The roadmap recorded this as blocked on a `purchase_order` register that
# "still does not exist". `commitment` IS that register — titled "Commitments (POs)", carrying
# po_date/amount/vendor, and ALREADY referencing `subcontract`. The blocker was the name, which is
# the third time in this ring that a capability was filed as missing because it was called something
# else. So the assertion is that the hop walks on the register as it stands, unchanged.
PO = cd.walk(
    [{"id": "pb", "data": {"base_bid": 100_000}}],
    [{"id": "ps", "data": {"vendor": "Ace", "value": 105_000, "change_orders": 8_000,
                           "awarded_from": "pb"}}],
    [],
    # TWO POs against one subcontract. A subcontract is routinely bought out in more than one, and
    # comparing the contract to the LARGEST would report the rest as money that vanished.
    [{"id": "p1", "data": {"subcontract": "ps", "amount": 70_000}},
     {"id": "p2", "data": {"subcontract": "ps", "amount": 32_000}}])
po_row = PO["rows"][0]
check("the PO hop walks on `commitment` as it stands — no schema change",
      hop(po_row, "contract_to_po")["status"] == "compared",
      hop(po_row, "contract_to_po"))
check("  every PO against the subcontract is summed, not just the largest",
      po_row["committed"] == 102_000 and po_row["po_count"] == 2,
      f'{po_row["committed"]} from {po_row["po_count"]} POs')
check("  a contract signed at one number and PO'd at another is reported",
      hop(po_row, "contract_to_po")["delta"] == -3_000,
      hop(po_row, "contract_to_po")["delta"])

# Change orders are EXCLUDED from this hop, unlike contract_to_invoiced. A CO raises the contract sum
# and is usually followed by its own PO; comparing the CO-inclusive sum against POs raised before it
# would report every mid-job change as an under-commitment until the paperwork caught up — a timing
# artefact, not drift. Asserted by the numbers rather than by reading the comment.
check("  change orders are EXCLUDED from contract_to_po but INCLUDED in contract_to_invoiced",
      hop(po_row, "contract_to_po")["from"] == 105_000
      and hop(po_row, "contract_to_invoiced")["from"] == 113_000,
      f'{hop(po_row, "contract_to_po")["from"]} vs {hop(po_row, "contract_to_invoiced")["from"]}')

NO_PO = cd.walk([{"id": "pb", "data": {"base_bid": 100_000}}],
                [{"id": "ps", "data": {"value": 105_000, "awarded_from": "pb"}}], [])
check("a project with NO commitments gets `incomparable`, never a zero-dollar drift",
      hop(NO_PO["rows"][0], "contract_to_po")["status"] == "incomparable"
      and hop(NO_PO["rows"][0], "contract_to_po")["delta"] is None,
      "a subcontract nobody has raised a PO against has not drifted by $0 — it is unmeasured")
# The parity twin, asserted by COMPARING THE TWO CALLS rather than by predicting either. My first
# version guessed `contract_to_invoiced` would be "compared" and it is not — that fixture has no
# invoices. Comparing the results cannot be wrong about the fixture.
_three_arg = cd.walk([{"id": "pb", "data": {"base_bid": 100_000}}],
                     [{"id": "ps", "data": {"value": 105_000, "awarded_from": "pb"}}], [])
_four_arg = cd.walk([{"id": "pb", "data": {"base_bid": 100_000}}],
                    [{"id": "ps", "data": {"value": 105_000, "awarded_from": "pb"}}], [], [])
check("  and the pre-existing hops are IDENTICAL with and without the new argument — the parity twin",
      [hop(_three_arg["rows"][0], h) for h in ("bid_to_contract", "contract_to_invoiced")]
      == [hop(_four_arg["rows"][0], h) for h in ("bid_to_contract", "contract_to_invoiced")],
      "every existing caller passes three arguments and must keep the walk it had")

check("rows are ordered by the largest movement, so the worst reads first",
      R["rows"][0]["subcontract_id"] == "s1", [r["subcontract_id"] for r in R["rows"]])
check("nothing at all is an empty walk, not a crash", cd.walk(None, None, None)["rows"] == [])
check("the note names the refusal a reader would otherwise assume away",
      "counting it as drift" in R["note"])

print()
if FAILED:
    print(f"commercial_drift: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("commercial_drift: all checks passed")
