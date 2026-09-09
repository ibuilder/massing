"""TM-RATES — the T&M ticket is priced from the rate registers, and the price STICKS.

## The defect, in one sentence

`POST /projects/{pid}/cost/tm` computed the ticket's totals from the rate tables, wrote them onto
the record, returned **200 with the right numbers in its body**, and the record kept the old ones.

## Why nothing caught it

Four independent silences, and it needed all four:

1. **The write-back was undone in the same call.** The route wrote `labor_total` directly.
   `apply_table_totals` (MOD-TOTALS, `modules.py`) recomputes every `totals_into` target from its
   table inside `update_record` — so the priced total was replaced by the sum of the `amount` cells
   the pricing had never touched. MOD-TOTALS is six weeks YOUNGER than the route: a feature landed
   on top of another and neutered it, and neither side was wrong on its own terms.
2. **It wrote into a field the module does not declare.** `tm_lines` is on no `eticket` form, in no
   list column, and read by no engine — `tm.summarize` reads `labor_total`. The pricing was stored
   where nobody could see it.
3. **The existing test could not express the collision.** `test_cost.py` asserted
   `et2["data"]["labor_total"] == 1000.0` and PASSED — because its fixture ticket has no
   `labor_lines` at all, and `apply_table_totals` skips a table whose rows key is absent. The one
   case where the write-back survives is the case where the total has no evidence behind it.
   *An assertion cannot be stronger than the world its fixture can describe.*
4. **No client ever called the route, and no gate could say so.** `test_route_reachability.py`
   matches the last static path segment against the web source and skips any segment shorter than
   `MIN_SEGMENT` (5). This route's leaf is `tm` — two characters. It is one of the 113 routes that
   gate documents itself as never assessing, and its docstring's claim that "exactly two" of those
   are genuinely uncalled was written on 2026-08-20 and was already wrong.

Found by deriving the mirror of DEAD-FIELD: not "which response field does nothing read", but
**which request parameter does nothing send**. `eticket_id` was required by a route and named
nowhere in the web tree. `test_body_param_reach.py` is that derivation as a gate.

## What is asserted here

The pricing rules, because each is a decision about somebody's money:

- a blank rate is filled from the register, and `amount` follows;
- a rate a human typed is **kept** and reported as a variance — a T&M rate that disagrees with the
  contract rate table is the thing a GC must see before signing, not something to correct silently;
- a line no register knows is left exactly as it is, and named;
- overtime and idle hours are reported UNPRICED. Neither `labor_rate` nor `equipment_rate` holds an
  OT or idle rate, and a 1.5x nobody agreed to is a contract term, not a default;
- the totals the route reports are READ BACK off the stored record, so the number in the response
  is by construction the number the ticket holds. That is the fix for the whole defect above.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_tm_rates.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_tm_rates.db"
os.environ["STORAGE_DIR"] = "./test_storage_tm_rates"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_tm_rates.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}
FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


with TestClient(app) as c:
    pid = c.post("/projects", headers=H, json={"name": "T&M rates"}).json()["id"]
    for mod, data in (
        ("labor_rate", {"trade": "Electrician", "rate": 95}),
        ("labor_rate", {"trade": "Labourer", "rate": 48.5}),
        ("material_rate", {"material": "EMT 3/4", "rate": 4.25}),
        ("equipment_rate", {"equipment": "Scissor lift", "rate": 30}),
    ):
        c.post(f"/projects/{pid}/modules/{mod}", headers=H, json={"data": data})

    def ticket(**data):
        base = {"subject": "Extra conduit", "work_date": "2026-09-01"}
        return c.post(f"/projects/{pid}/modules/eticket", headers=H,
                      json={"data": {**base, **data}}).json()["id"]

    def price(tid):
        r = c.post(f"/projects/{pid}/cost/tm", headers=H, json={"eticket_id": tid})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return r.json()

    def stored(tid):
        return c.get(f"/projects/{pid}/modules/eticket/{tid}", headers=H).json()["data"]

    def rows(tid, field="labor_lines"):
        """The stored rows, or one empty row.

        So a mutation that stops writing the lines reports FAIL rather than a KeyError traceback: a
        crash IS a failing test, but it stops the run at the first assertion and hides every other
        one the same mutation would have broken. The point of a mutation check is the FULL list of
        what stops holding."""
        r = stored(tid).get(field)
        return r if isinstance(r, list) and r else [{}]

    # ---- 1. THE REGRESSION: a ticket WITH lines. This is the fixture the old test lacked ---------
    tid = ticket(labor_lines=[{"worker": "A", "trade": "Electrician", "hours": 8}])
    rep = price(tid)
    d = stored(tid)
    check("a blank rate is filled from the register",
          rows(tid, "labor_lines")[0].get("rate") == 95, rows(tid, "labor_lines")[0])
    check("the row's amount follows the rate", rows(tid, "labor_lines")[0].get("amount") == 760.0,
          rows(tid, "labor_lines")[0])
    # The whole defect: this used to be 0.0 while the response said 760.0.
    check("the STORED total carries the price, not the pre-pricing sum",
          d.get("labor_total") == 760.0, d.get("labor_total"))
    check("the reported total is the stored total",
          rep["totals"]["labor_total"] == d.get("labor_total") == rep["totals"]["grand_total"],
          (rep["totals"], d.get("labor_total")))
    check("the run says how many rows it moved", rep["priced"] == 1, rep["priced"])

    # ---- 2. a typed rate is EVIDENCE, not a blank to fill ----------------------------------------
    tid = ticket(labor_lines=[{"worker": "B", "trade": "Electrician", "hours": 4, "rate": 110}])
    rep = price(tid)
    d = stored(tid)
    check("a rate somebody typed is left as typed", rows(tid, "labor_lines")[0].get("rate") == 110,
          rows(tid, "labor_lines")[0])
    check("...and the disagreement with the register is reported with BOTH numbers",
          [(v["typed"], v["register"]) for v in rep["variance"]] == [(110.0, 95.0)], rep["variance"])
    check("the amount is still recomputed from the rate that is there",
          rows(tid, "labor_lines")[0].get("amount") == 440.0 and d.get("labor_total") == 440.0, rows(tid, "labor_lines")[0])

    # ---- 3. a line no register knows is untouched and NAMED --------------------------------------
    tid = ticket(labor_lines=[{"worker": "C", "trade": "Glazier", "hours": 3}])
    rep = price(tid)
    d = stored(tid)
    check("an unknown trade is left exactly as it was — never zeroed",
          "rate" not in rows(tid, "labor_lines")[0] and "amount" not in rows(tid, "labor_lines")[0],
          rows(tid, "labor_lines")[0])
    check("...and it is named, with the register that would fix it",
          [(u["name"], u["register"]) for u in rep["unmatched"]] == [("Glazier", "labor_rate")],
          rep["unmatched"])
    check("an unpriceable line leaves the total at zero rather than guessing",
          d.get("labor_total") == 0, d.get("labor_total"))

    # ---- 4. hours the register CANNOT price are reported, never assumed --------------------------
    tid = ticket(
        labor_lines=[{"worker": "A", "trade": "Electrician", "hours": 8, "ot_hours": 2}],
        equipment_lines=[{"equipment": "Scissor lift", "hours": 6, "idle_hours": 2}])
    rep = price(tid)
    d = stored(tid)
    cols = sorted((u["column"], u["quantity"]) for u in rep["unpriced"])
    check("overtime and idle hours come back as unpriced quantities",
          cols == [("idle_hours", 2.0), ("ot_hours", 2.0)], rep["unpriced"])
    # 8h x 95 = 760, NOT 8h + 2h OT at some invented multiplier.
    check("no overtime multiplier is invented", d.get("labor_total") == 760.0, d.get("labor_total"))
    check("no idle rate is invented", d.get("equipment_total") == 180.0, d.get("equipment_total"))

    # ---- 4b. the extended amount rounds HALF-UP, like money and unlike float round() -------------
    # Raised in review. `round(rate * qty, 2)` multiplies binary floats and rounds HALF-EVEN, so a
    # rate of 2.675 at quantity 1 extends to 2.67 — a cent short on the line a contractor is paid
    # on. `money.mul` does the multiply in Decimal and quantizes half-up. This is the same defect
    # MONEY-SCOPE swept, in the one shape `test_money_spine.py` structurally cannot see: its scan
    # requires the expression to divide by 100, which a percentage does and a product does not.
    c.post(f"/projects/{pid}/modules/material_rate", headers=H,
           json={"data": {"material": "Half-cent widget", "rate": 2.675}})
    tid = ticket(material_lines=[{"description": "Half-cent widget", "qty": 1}])
    price(tid)
    check("an extended amount rounds half-UP at the half-cent, not half-even",
          rows(tid, "material_lines")[0].get("amount") == 2.68,
          f"{rows(tid, 'material_lines')[0].get('amount')} — float round() gives "
          f"{round(2.675 * 1, 2)}, which is a cent short")
    check("...and the derived total carries the same cent", stored(tid).get("material_total") == 2.68,
          stored(tid).get("material_total"))

    # ---- 4c. FIVE REVIEW FINDINGS, each a fixture the first version could not express ------------
    # Every one of these passed the original suite. They are grouped because they share a cause: the
    # fixtures described a world simpler than the schema, so the assertions could not reach the bug.

    # (i) THE MATERIAL NAME COLUMN. `material_lines` has columns description/qty/unit/unit_price/
    # amount — there is NO `material` column. The first TM_TABLES used one field for both the
    # REGISTER's name column and the LINE's, which is right for labour and equipment by coincidence
    # and wrong for material, so every material line a user could create priced as unmatched. The
    # original test passed only because its fixture put a `material` key on the row.
    # Its own fixture, deliberately: the first draft of THIS check read a `tid` left over from the
    # section above and asserted 4.25 against a different ticket. Same error one layer up — an
    # assertion whose subject is not the thing it names.
    tid = ticket(material_lines=[{"description": "EMT 3/4", "qty": 10}])
    price(tid)
    check("a material line names its item in `description`, the column the schema actually has",
          rows(tid, "material_lines")[0].get("unit_price") == 4.25,
          rows(tid, "material_lines")[0])
    check("...and it extends", rows(tid, "material_lines")[0].get("amount") == 42.5,
          rows(tid, "material_lines")[0])
    tid = ticket(material_lines=[{"description": "EMT 3/4", "qty": 10, "material": "nonsense"}])
    price(tid)
    check("...while a stray non-schema key on the row changes nothing",
          rows(tid, "material_lines")[0].get("amount") == 42.5,
          rows(tid, "material_lines")[0])

    # (ii) A TYPED AMOUNT IS EVIDENCE, exactly as a typed rate is. 8h + 2h OT written up at $1,045
    # must not become $760 because straight time is all this engine can derive.
    tid = ticket(labor_lines=[{"worker": "A", "trade": "Electrician", "hours": 8, "ot_hours": 2,
                               "rate": 95, "amount": 1045}])
    rep = price(tid)
    check("a typed amount is NOT overwritten by rate x quantity",
          rows(tid, "labor_lines")[0].get("amount") == 1045, rows(tid, "labor_lines")[0])
    check("...and the difference from straight time is reported instead",
          [(v["field"], v["typed"], v["register"]) for v in rep["variance"]]
          == [("amount", 1045.0, 760.0)], rep["variance"])
    # A lump-sum line with no hours must not be zeroed either.
    tid = ticket(labor_lines=[{"worker": "B", "trade": "Electrician", "amount": 500}])
    price(tid)
    check("a lump-sum line with no quantity keeps its amount",
          rows(tid, "labor_lines")[0].get("amount") == 500, rows(tid, "labor_lines")[0])

    # (iii) A REGISTER ROW WITH NO RATE IS NOT AN ENTRY. `rate` is optional, so a half-filled row
    # gave 0.0 — not None — and the line took a rate of zero, was reported as priced, and kept a
    # stale amount because the recompute is guarded on a truthy rate.
    c.post(f"/projects/{pid}/modules/labor_rate", headers=H, json={"data": {"trade": "Rigger"}})
    tid = ticket(labor_lines=[{"worker": "C", "trade": "Rigger", "hours": 6}])
    rep = price(tid)
    check("a register row with no rate reads as NO entry, not as $0",
          [u["name"] for u in rep["unmatched"]] == ["Rigger"] and not rep["filled"], rep)
    check("...so the line is left alone rather than priced at zero",
          "rate" not in rows(tid, "labor_lines")[0], rows(tid, "labor_lines")[0])

    # (iv) THE REGISTER'S UNIT. equipment_rate offers Hour|Day|Week|Month and the line's quantity is
    # hours, so a $1,200/Week lift extended against an 8-hour day reads as $9,600 — reported as an
    # ordinary success. Converting needs a working day nobody stated, so it is named, not guessed.
    c.post(f"/projects/{pid}/modules/equipment_rate", headers=H,
           json={"data": {"equipment": "Tower crane", "rate": 1200, "unit": "Week"}})
    tid = ticket(equipment_lines=[{"equipment": "Tower crane", "hours": 8}])
    rep = price(tid)
    check("a per-week rate is NOT extended against hours",
          "rate" not in rows(tid, "equipment_lines")[0], rows(tid, "equipment_lines")[0])
    check("...and the reason names the register's unit",
          any("per week" in (u.get("reason") or "") for u in rep["unpriced"]), rep["unpriced"])
    # `column` must name the QUANTITY, not the rate: the panel renders it as
    # "{quantity} {column} are NOT in the figures above", so `rate_col` here read as "8 rate".
    # Asserting only the reason text missed it — raised in review, and the THIRD time in this item
    # that a fixture checked less than the thing it was about.
    check("...and `column` names the quantity the panel prints beside it",
          [(u["column"], u["quantity"]) for u in rep["unpriced"]] == [("hours", 8.0)],
          rep["unpriced"])
    check("...and the entry says the quantity is NOT in the totals, because it is not",
          [u["in_totals"] for u in rep["unpriced"]] == [False], rep["unpriced"])

    # (iv-c) THE SAME LINE, WITH A RATE THE USER TYPED. The fixture above gives the line no rate of
    # its own, so the engine had nothing to extend and the report's "these hours are NOT in the
    # figures above" was true by accident. Add one and the two halves contradict each other: the
    # register cannot price the line, but `equipment_lines.rate` is declared `"unit": "$/hr"` in
    # module.json, so `rate x hours` is the LINE's own arithmetic and is computed — and the panel
    # printed "8 hours are NOT in the figures above" directly beneath the $800 it had just added.
    #
    # The fix is to the CLAIM, not the sum. Refusing to extend a rate the user typed would drop a
    # line they priced out of the ticket total, which is worse than the wrong sentence. Raised in
    # review on #483 and missed before that PR merged.
    #
    # FOURTH time in this item that a fixture was narrower than the rule it covered, and the same
    # shape every time: the case that distinguishes two behaviours was the case nobody wrote.
    typed_tid = ticket(equipment_lines=[{"equipment": "Tower crane", "hours": 8, "rate": 100}])
    typed_rep = price(typed_tid)
    typed_row = rows(typed_tid, "equipment_lines")[0]
    check("a rate the USER typed still extends against hours — the register's unit is a fact about "
          "the register, not the line",
          typed_row.get("amount") == 800.0, typed_row)
    check("...and the report says the hours ARE in the totals, instead of denying the amount above",
          [u["in_totals"] for u in typed_rep["unpriced"]] == [True], typed_rep["unpriced"])
    check("...with a reason about what the REGISTER could not do",
          all("could not check the rate you entered" in (u.get("reason") or "")
              for u in typed_rep["unpriced"]), typed_rep["unpriced"])
    check("...and no rate variance, because $100/hr and $1,200/week are not comparable numbers",
          not typed_rep["variance"], typed_rep["variance"])
    # Sequenced plainly rather than crammed into one expression: the walrus-and-tuple version put
    # `price()` inside a short-circuit `and`, so a None from `stored()` would have SKIPPED the
    # pricing rather than failing the check, and it carried no detail. Raised in review.
    hourly_tid = ticket(equipment_lines=[{"equipment": "Scissor lift", "hours": 6}])
    hourly_before = stored(hourly_tid)
    price(hourly_tid)
    hourly_row = rows(hourly_tid, "equipment_lines")[0]
    check("...while an explicitly hourly rate still prices",
          hourly_before is not None and hourly_row.get("amount") == 180.0,
          {"before": hourly_before, "row": hourly_row})

    # (iv-b) THE RATE COMPARISON ROUNDS LIKE MONEY. `round()` is HALF-EVEN and `money.q2` HALF-UP,
    # so a line typed at 2.675 against a register at 2.68 AGREES to the cent under q2 and DISAGREES
    # under round() — a variance reported over nothing, on the screen whose whole job is to flag a
    # real disagreement. Raised in review; added here because reverting to round() left every other
    # assertion green, which makes a consistency claim untestable rather than true.
    c.post(f"/projects/{pid}/modules/material_rate", headers=H,
           json={"data": {"material": "Half-cent stock", "rate": 2.68}})
    tid = ticket(material_lines=[{"description": "Half-cent stock", "qty": 4, "unit_price": 2.675}])
    rep = price(tid)
    check("a typed rate that agrees with the register TO THE CENT reports no variance",
          [v for v in rep["variance"] if v["field"] == "unit_price"] == [],
          f"round() would call 2.675 vs 2.68 a disagreement; money.q2 makes both 2.68 — {rep['variance']}")

    # (v) A CLOSED RATE IS RETIRED. Both registers carry open/closed and list_records is oldest
    # first, so a superseded rate won the lookup and was SNAPSHOTTED onto the line permanently.
    lr = c.get(f"/projects/{pid}/modules/labor_rate", headers=H, params={"limit": 100}).json()
    lr = lr["records"] if isinstance(lr, dict) else lr
    old = next(r for r in lr if r["data"]["trade"] == "Electrician")
    c.post(f"/projects/{pid}/modules/labor_rate/{old['id']}/transition", headers=H,
           json={"action": "close"})
    c.post(f"/projects/{pid}/modules/labor_rate", headers=H,
           json={"data": {"trade": "Electrician", "rate": 130}})
    tid = ticket(labor_lines=[{"worker": "D", "trade": "Electrician", "hours": 2}])
    price(tid)
    check("a CLOSED register row does not win the lookup over its live replacement",
          rows(tid, "labor_lines")[0].get("rate") == 130, rows(tid, "labor_lines")[0])

    # ---- 5. material prices off `unit_price`, not `rate` -----------------------------------------
    # The three tables do not share a rate column, which is why the mapping is a table and not a
    # naming convention: a loop assuming `rate` would silently price no material at all.
    tid = ticket(material_lines=[{"description": "EMT 3/4", "qty": 100}])
    price(tid)
    d = stored(tid)
    check("material takes the register's rate into unit_price",
          rows(tid, "material_lines")[0].get("unit_price") == 4.25, rows(tid, "material_lines")[0])
    check("material amount = unit_price x qty",
          rows(tid, "material_lines")[0].get("amount") == 425.0 and d.get("material_total") == 425.0,
          rows(tid, "material_lines")[0])

    # ---- 6. pricing twice changes nothing the second time ---------------------------------------
    rep2 = price(tid)
    check("a second run reports zero rows moved", rep2["priced"] == 0, rep2["priced"])
    check("...and the totals are unchanged", stored(tid).get("material_total") == 425.0)

    # ---- 7. the shapes that must not raise -------------------------------------------------------
    tid = ticket()                                    # no line tables at all
    rep = price(tid)
    check("a ticket with no lines prices to nothing rather than 500ing",
          rep["priced"] == 0 and rep["totals"]["grand_total"] == 0, rep)
    tid = ticket(labor_lines="4 hrs @ 85")            # legacy free text on a converted field
    rep = price(tid)
    check("legacy free text on a line field is skipped, not summed or crashed on",
          rep["priced"] == 0, rep)
    check("a missing ticket is a 404, not a 500",
          c.post(f"/projects/{pid}/cost/tm", headers=H,
                 json={"eticket_id": "no-such-id"}).status_code == 404)

    # ---- 8. the rate is a SNAPSHOT — this is the rule test_eticket_tm.py pins, from the other end -
    # Re-pricing after the register moves must not restate what a priced line was worked at... but
    # it MUST report the disagreement, which is what makes the snapshot safe rather than merely
    # stale. Both halves, because either alone is a different (wrong) product.
    tid = ticket(labor_lines=[{"worker": "A", "trade": "Labourer", "hours": 10}])
    price(tid)
    check("priced at the register's rate on the day", stored(tid).get("labor_total") == 485.0,
          stored(tid).get("labor_total"))
    lr = c.get(f"/projects/{pid}/modules/labor_rate", headers=H, params={"limit": 100}).json()
    lr = lr["records"] if isinstance(lr, dict) else lr
    row = next(r for r in lr if r["data"]["trade"] == "Labourer")
    c.patch(f"/projects/{pid}/modules/labor_rate/{row['id']}", headers=H, json={"rate": 60})
    rep = price(tid)
    check("a later register change does NOT retroactively re-rate work already done",
          stored(tid).get("labor_total") == 485.0, stored(tid).get("labor_total"))
    check("...and the ticket says the register has moved since",
          [(v["typed"], v["register"]) for v in rep["variance"]] == [(48.5, 60.0)], rep["variance"])

print()
if FAILED:
    print(f"TM-RATES FAILED ({len(FAILED)}): " + "; ".join(FAILED))
    raise SystemExit(1)
print("TM-RATES OK")
