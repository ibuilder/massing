"""R27-SOV-LOOP — the schedule of values built from the estimate, not re-keyed from it.

The research that produced this item confirmed the gap rather than assuming it: the `estimate` and
`sov` modules both exist, `cost.g703` reads SOV records into a continuation sheet and
`report.payapp_pdf` renders the application — and **nothing built an SOV from an estimate**. The chain
was bridged by typing the numbers in again, which is exactly where the trace from a pay-app line back
to a model element was being lost.

What is tested here is mostly *what the regrouping refuses to lose*.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_sov_build.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_sov_build.db"
os.environ["STORAGE_DIR"] = "./test_storage_sov_build"
if os.path.exists("./test_sov_build.db"):
    os.remove("./test_sov_build.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import sov_build as sb  # noqa: E402


def line(code, desc, amount, *, basis="area", guids=(), qsrc="declared", rsrc="quoted",
         unit_cost=1.0):
    return {"code": code, "description": desc, "amount": amount, "basis": basis,
            "unit_cost": unit_cost, "quantity": amount / unit_cost, "guids": list(guids),
            "quantity_source": qsrc, "rate_source": rsrc}


def est(lines, **extra):
    total = round(sum(x["amount"] for x in lines), 2)
    by_el = {}
    for ln in lines:
        for g in ln["guids"]:
            by_el[g] = {"amount": round(ln["amount"] / max(1, len(ln["guids"])), 6)}
    return {"lines": lines, "total": total, "by_element": by_el, **extra}


# ---- the ordinary case: two priced lines under one code become one billable item -------------------
# An estimate splits 03 30 00 into concrete-by-volume and formwork-by-area because they price
# differently. A contract bills the code. That regrouping is the whole feature.
r = sb.from_estimate(est([
    line("03 30 00", "Concrete", 1000.0, basis="volume", guids=["A", "B"]),
    line("03 30 00", "Formwork", 500.0, basis="area", guids=["C"]),
    line("09 91 00", "Painting", 250.0, guids=["D"]),
]))
assert r["item_count"] == 2, r["item_count"]
conc = next(i for i in r["items"] if i["cost_code"] == "03 30 00")
assert conc["scheduled_value"] == 1500.0, conc
assert conc["merged_lines"] == 2 and conc["element_count"] == 3, conc
assert conc["guids"] == ["A", "B", "C"], conc["guids"]
assert conc["basis"] == "mixed", "two bases collapse to mixed rather than picking one"
assert "(+1 more)" in conc["description"], conc["description"]
assert r["reconciles"] and r["reconciles_by_element"], r
assert r["sov_total"] == 1750.0 == r["estimate_total"], r

# ---- trade order, NOT amount order ------------------------------------------------------------------
# An estimate sorts by amount because the reader hunts for what dominates cost. An SOV is read down the
# trades by someone checking nothing is ABSENT, and re-sorting by size hides an omission.
assert [i["cost_code"] for i in r["items"]] == ["03 30 00", "09 91 00"], r["items"]
assert [i["item_no"] for i in r["items"]] == ["0001", "0002"], r["items"]

# ---- unpriced scope is EXCLUDED and SAID, never dropped ---------------------------------------------
# An SOV built only from lines that happened to price is smaller than the job, and looks complete
# because every line in it is right.
e = sb.from_estimate(est([line("03 30 00", "Concrete", 1000.0, guids=["A"])],
                         unpriced=[{"guid": "Z1"}, {"guid": "Z2"}],
                         no_rate=[{"guid": "Z3"}],
                         missing_quantity=[{"guid": "Z4"}]))
assert not e["covers_whole_model"], e
reasons = {x["reason"]: x for x in e["excluded"]}
assert set(reasons) == {"unpriced", "no rate", "missing quantity"}, reasons
assert reasons["unpriced"]["count"] == 2 and reasons["unpriced"]["guids"] == ["Z1", "Z2"], reasons
# ...and a fully priced estimate says so positively
assert sb.from_estimate(est([line("03 30 00", "C", 1.0, guids=["A"])]))["covers_whole_model"]

# ---- the rounding residual is PLACED and REPORTED, not discarded -------------------------------------
# Rounding each item to cents and summing does not equal rounding the total once. The difference is the
# penny that gets a G703 rejected.
d = sb.from_estimate(est([line("01 00 00", "A", 1.11, guids=["A"]),
                          line("02 00 00", "B", 2.22, guids=["B"]),
                          line("03 00 00", "C", 3.33, guids=["C"])]), markup_pct=50.0)
assert d["residual_applied"] == -0.01, d["residual_applied"]
assert d["sov_total"] == round(6.66 * 1.5, 2) == 9.99, d
assert round(sum(i["scheduled_value"] for i in d["items"]), 2) == d["sov_total"], "the column foots"
assert d["reconciles"], d
big = max(d["items"], key=lambda i: i["scheduled_value"])
assert big["cost_code"] == "03 00 00", "the residual lands on the largest item"
# and markup_amount stays consistent with the adjusted value
for i in d["items"]:
    assert i["markup_amount"] == round(i["scheduled_value"] - i["estimate_amount"], 2), i

# ---- an SOV at cost SAYS SO --------------------------------------------------------------------------
# Scheduled values are CONTRACT values; an estimate is COST. Billing lump-sum off unmarked-up cost
# under-bills by the entire fee, silently, every month.
z = sb.from_estimate(est([line("03 30 00", "C", 100.0, guids=["A"])]))
assert z["at_cost"] is True and z["markup_pct"] == 0.0, z
assert z["items"][0]["markup_amount"] == 0.0, z["items"]
m = sb.from_estimate(est([line("03 30 00", "C", 100.0, guids=["A"])]), markup_pct=15.0)
assert m["at_cost"] is False, m
assert m["items"][0]["scheduled_value"] == 115.0 and m["items"][0]["markup_amount"] == 15.0, m
assert m["items"][0]["estimate_amount"] == 100.0, "the cost is still visible under the fee"

# ---- provenance survives the regrouping ---------------------------------------------------------------
# The entire point: a pay-app line traces to the elements it bills for, and to whether those
# quantities were measured or declared.
p = sb.from_estimate(est([
    line("03 30 00", "C", 10.0, guids=["A"], qsrc="declared", rsrc="quoted"),
    line("03 30 00", "F", 10.0, guids=["B"], qsrc="measured", rsrc="quoted"),
]))
it = p["items"][0]
assert it["quantity_source"] == "mixed", "one measured element among many is NOT 'declared'"
assert it["rate_source"] == "quoted", "agreeing lines keep the value"
assert it["guids"] == ["A", "B"], it["guids"]
same = sb.from_estimate(est([line("03 30 00", "C", 10.0, guids=["A"], qsrc="declared"),
                             line("03 30 00", "F", 10.0, guids=["B"], qsrc="declared")]))
assert same["items"][0]["quantity_source"] == "declared", same["items"]

# ---- groupings ------------------------------------------------------------------------------------------
g = est([line("03 30 00", "Concrete", 100.0, basis="volume", guids=["A"]),
         line("03 40 00", "Precast", 100.0, guids=["B"]),
         line("09 91 00", "Paint", 100.0, guids=["C"])])
assert sb.from_estimate(g, grouping="code")["item_count"] == 3
div = sb.from_estimate(g, grouping="division")
assert div["item_count"] == 2, div["item_count"]          # 03 rolls up, 09 stands alone
assert div["reconciles"] and div["sov_total"] == 300.0, div
assert sb.from_estimate(g, grouping="line")["item_count"] == 3

# ---- a GlobalId may not reach two items ------------------------------------------------------------------
# fived assigns each element to exactly one line, so this should be impossible — which is why it is
# checked. An assumption that quietly stops holding bills an owner twice for the same wall.
dup = sb.from_estimate(est([line("03 30 00", "C", 10.0, guids=["A"]),
                            line("09 91 00", "P", 10.0, guids=["A"])]))
assert dup["duplicate_guids"] == ["A"], dup["duplicate_guids"]
assert sb.from_estimate(est([line("03 30 00", "C", 10.0, guids=["A"])]))["duplicate_guids"] == []

# ---- malformed input is REFUSED ----------------------------------------------------------------------------
for bad_kwargs in ({"grouping": "nope"}, {"markup_pct": -1.0}, {"markup_pct": 5000.0},
                   {"markup_pct": "lots"}):
    try:
        sb.from_estimate(est([line("03 30 00", "C", 1.0, guids=["A"])]), **bad_kwargs)
        raise AssertionError(f"accepted {bad_kwargs!r}")
    except ValueError:
        pass

# ---- degenerate inputs are answers ---------------------------------------------------------------------------
empty = sb.from_estimate({"lines": [], "total": 0.0, "by_element": {}})
assert empty["item_count"] == 0 and empty["sov_total"] == 0.0 and empty["reconciles"], empty
assert empty["covers_whole_model"], "nothing priced and nothing excluded is not a coverage failure"

# reconciliation is CONSERVATION, not correctness, and the module says so rather than implying it
assert "NOT that the estimate was right" in empty["note"]
assert sb.GROUPINGS == ("code", "division", "line")

print("R27-SOV-LOOP OK - the schedule of values is now BUILT from the estimate instead of re-keyed "
      "from it, closing the one missing link in a chain whose every other piece already existed: "
      "fived.estimate measures and prices the model, cost.g703 reads sov records into a continuation "
      "sheet, report.payapp_pdf renders the application - and nothing joined the first to the second. "
      "The transformation is a REGROUPING (an estimate is keyed by code+basis+rate because those "
      "price differently; a contract bills the code), and the whole risk of a regrouping is money "
      "going missing inside it. So: UNPRICED SCOPE IS EXCLUDED AND SAID, never dropped, because an "
      "SOV built only from the lines that happened to price is smaller than the job and looks "
      "complete since every line in it is right. THE ROUNDING RESIDUAL IS PLACED ON THE LARGEST ITEM "
      "AND REPORTED, because rounding each item then summing does not equal rounding the total once, "
      "and that penny is what gets a G703 rejected. AN SOV AT COST SAYS SO, since scheduled values "
      "are contract values while an estimate is cost, and billing lump-sum off unmarked-up cost "
      "under-bills by the entire fee every month. PROVENANCE SURVIVES: each item keeps its GlobalIds "
      "and its quantity/rate sources, collapsing to 'mixed' rather than rounding one measured element "
      "among fifty up to 'declared' - which is the point, because a pay-app line can now be traced to "
      "the model elements it bills for. And `reconciles` is checked against TWO independent "
      "accumulations in the source, while being named honestly: it proves the regrouping lost no "
      "money, NOT that the estimate was right.")
