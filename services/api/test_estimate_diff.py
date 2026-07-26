"""R25-ESTIMATE-DIFF — two estimates, diffed by GlobalId, with every dollar attributed to a cause.

"The estimate went up $340k" is not information. *Which elements* moved it, and *why*, is — and
because both estimates key on GlobalId, the diff can say. That is the whole reason this platform
refuses to identify elements any other way.

**The first version of this module was wrong in a way its own checks could not see**, and the cases
below are mostly the ones that catch that class of error:

* It reconstructed per-element quantities by dividing a line's total evenly across its GlobalIds. Add
  one wall to an existing line and every *other* wall in it reported as a design change, while the
  new wall took the average instead of its own quantity. `reconciles` stayed **true** the whole time,
  because invented numbers still sum correctly — a self-consistency check is not a correctness check.
* It compared a *quantity* against the *money* epsilon, and `repriced` was the fall-through branch,
  so a pure design change with identical rates on both sides came back labelled a commercial one.
* It skipped on a small money delta *before* deciding the cause, so a compensating change — quantity
  doubled, rate halved — was reported as unchanged.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_estimate_diff.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_estimate_diff.db"
os.environ["STORAGE_DIR"] = "./test_storage_estimate_diff"
if os.path.exists("./test_estimate_diff.db"):
    os.remove("./test_estimate_diff.db")

from aec_api import estimate_diff as ed  # noqa: E402
from aec_api import fived  # noqa: E402


def E(elements):
    """An estimate carrying exact per-element facts, the way `fived.estimate` emits them."""
    by, lines = {}, {}
    for g, (code, qty, rate) in elements.items():
        by[g] = {"code": code, "basis": "area", "quantity": qty, "unit_cost": rate,
                 "amount": round(qty * rate, 2), "rate_source": "quoted",
                 "quantity_source": "declared"}
        ln = lines.setdefault((code, rate), {"code": code, "basis": "area", "unit_cost": rate,
                                             "quantity": 0.0, "guids": []})
        ln["quantity"] += qty
        ln["guids"].append(g)
    out = [{**v, "amount": round(v["quantity"] * v["unit_cost"], 2)} for v in lines.values()]
    return {"lines": out, "by_element": by,
            "total": round(sum(x["amount"] for x in out), 2)}


# ---- THE REGRESSION: adding an element must not restate its neighbours -----------------------------
# Two 50 m² walls become three, and the third is 20 m². Under even apportionment w1 and w2 each
# reported a -$1,000 "design change" with rate_from == rate_to, and w3 was credited $4,000 instead of
# $2,000. All of it reconciled. This is the most ordinary edit an estimate ever sees.
grow = ed.diff(E({"w1": ("A", 50.0, 100.0), "w2": ("A", 50.0, 100.0)}),
               E({"w1": ("A", 50.0, 100.0), "w2": ("A", 50.0, 100.0), "w3": ("A", 20.0, 100.0)}))
g = {c["cause"]: c for c in grow["causes"]}
assert grow["granularity"] == "element", grow["granularity"]
assert g["requantified"]["count"] == 0, g["requantified"]["items"]
assert g["repriced"]["count"] == 0 and g["both"]["count"] == 0, grow["causes"]
assert g["added"]["count"] == 1 and g["added"]["items"][0]["guid"] == "w3", g["added"]
assert g["added"]["items"][0]["delta"] == 2000.0, g["added"]["items"][0]   # its own quantity, not the mean
assert grow["total_delta"] == 2000.0 and grow["reconciles"], grow

# ---- a quantity is not money, and `repriced` is not a fall-through ---------------------------------
# Comparing a quantity against the money epsilon reported a pure design change as a commercial one —
# with rate_from == rate_to right there in the payload it emitted.
tiny = ed.diff(E({"a": ("A", 100.0, 1500.0)}), E({"a": ("A", 100.01, 1500.0)}))
t = {c["cause"]: c for c in tiny["causes"]}
assert t["requantified"]["count"] == 1, tiny["causes"]
assert t["repriced"]["count"] == 0, t["repriced"]["items"]
assert t["requantified"]["items"][0]["rate_from"] == t["requantified"]["items"][0]["rate_to"]

# ---- a compensating change is a change ------------------------------------------------------------
# Quantity doubled, rate halved: the money is identical and the building is not. Skipping on the
# money delta before classifying asserted this away entirely.
comp = ed.diff(E({"x": ("A", 10.0, 100.0)}), E({"x": ("A", 20.0, 50.0)}))
c = {k["cause"]: k for k in comp["causes"]}
assert c["both"]["count"] == 1, comp["causes"]
assert comp["total_delta"] == 0.0, comp["total_delta"]
assert comp["changed"] == 1 and comp["unchanged"] == 0, comp
item = c["both"]["items"][0]
assert item["quantity_from"] == 10.0 and item["quantity_to"] == 20.0, item
assert item["rate_from"] == 100.0 and item["rate_to"] == 50.0, item

# ---- the four causes are kept apart ---------------------------------------------------------------
before = E({"w1": ("A", 50.0, 90.0), "s1": ("B", 4.0, 220.0), "b1": ("C", 2.0, 500.0)})
after = E({"w1": ("A", 70.0, 90.0), "s1": ("B", 4.0, 260.0), "t1": ("D", 3.0, 300.0)})
d = ed.diff(before, after)
by = {x["cause"]: x for x in d["causes"]}
assert by["added"]["count"] == 1 and by["added"]["items"][0]["guid"] == "t1"
assert by["removed"]["count"] == 1 and by["removed"]["items"][0]["guid"] == "b1"
assert by["requantified"]["count"] == 1 and by["requantified"]["items"][0]["guid"] == "w1"
assert by["repriced"]["count"] == 1 and by["repriced"]["items"][0]["guid"] == "s1"
assert by["both"]["count"] == 0
assert d["reconciles"] and abs(d["attributed"] - d["total_delta"]) <= 0.05, d

# ---- without `by_element` it diffs LINES rather than inventing element shares ----------------------
# A coarser true answer beats a finer invented one.
coarse_a = {"lines": [{"code": "A", "basis": "area", "quantity": 100.0, "unit_cost": 100.0,
                       "amount": 10000.0, "guids": ["w1", "w2"]}], "total": 10000.0}
coarse_b = {"lines": [{"code": "A", "basis": "area", "quantity": 120.0, "unit_cost": 100.0,
                       "amount": 12000.0, "guids": ["w1", "w2", "w3"]}], "total": 12000.0}
co = ed.diff(coarse_a, coarse_b)
cb = {x["cause"]: x for x in co["causes"]}
assert co["granularity"] == "line", co["granularity"]
assert cb["requantified"]["count"] == 1, co["causes"]
assert "guid" not in cb["requantified"]["items"][0], cb["requantified"]["items"][0]
assert cb["requantified"]["items"][0]["delta"] == 2000.0
assert co["reconciles"], co
# one side alone is not enough — attribution needs both
assert ed.diff(coarse_a, E({"w1": ("A", 120.0, 100.0)}))["granularity"] == "line"

# ---- merged line keys ACCUMULATE rather than overwrite --------------------------------------------
# Two lines with the same code and basis are two costs against that code; keeping the last drops
# money silently, which is the exact failure this module exists to catch.
dup = {"lines": [{"code": "A", "basis": "area", "quantity": 5.0, "unit_cost": 10.0, "amount": 50.0},
                 {"code": "A", "basis": "area", "quantity": 7.0, "unit_cost": 10.0, "amount": 70.0}],
       "total": 120.0}
same = ed.diff(dup, dup)
assert same["changed"] == 0 and same["reconciles"], same
grown = ed.diff(dup, {"lines": [{"code": "A", "basis": "area", "quantity": 12.0, "unit_cost": 10.0,
                                 "amount": 120.0}], "total": 120.0})
assert grown["changed"] == 0, grown          # 5+7 == 12 at the same rate: nothing moved

# ---- a code priced at SEVERAL rates is one line group, and a repricing of it is still a repricing --
# `fived.estimate` keys its lines on (code, basis, unit_cost) so layering can price one code at more
# than one rate; those lines merge here. Two wrong answers were available. Reporting `unit_cost=None`
# for the merged group looks conservative but hides the change entirely — no rate movement, no
# quantity movement, real money unattributed and `reconciles` false. Putting the rate in the KEY makes
# the money reconcile but reclassifies a repricing as a removal plus an addition: scope change, the
# one distinction this module exists to draw.
two_rates = {"lines": [
    {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 10.0, "amount": 100.0},
    {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 20.0, "amount": 200.0}],
    "total": 300.0}
repriced_group = {"lines": [
    {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 10.0, "amount": 100.0},
    {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 23.0, "amount": 230.0}],
    "total": 330.0}
mr = ed.diff(two_rates, repriced_group)
mrb = {x["cause"]: x for x in mr["causes"]}
assert mr["granularity"] == "line", mr["granularity"]
assert mrb["repriced"]["count"] == 1, mr["causes"]
assert mrb["added"]["count"] == 0 and mrb["removed"]["count"] == 0, mr["causes"]
assert mr["total_delta"] == 30.0 and mr["attributed"] == 30.0, mr
assert mr["reconciles"], mr

# ...and a shift in the MIX at unchanged rates is a design change, not a commercial one. A blended
# rate moves when the mix moves, so comparing blends alone would call this `repriced` — or `both`.
mix = {"lines": [
    {"code": "A", "basis": "area", "quantity": 30.0, "unit_cost": 10.0, "amount": 300.0},
    {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 20.0, "amount": 200.0}],
    "total": 500.0}
mx = ed.diff(two_rates, mix)
mxb = {x["cause"]: x for x in mx["causes"]}
assert mxb["requantified"]["count"] == 1, mx["causes"]
assert mxb["repriced"]["count"] == 0 and mxb["both"]["count"] == 0, mx["causes"]
assert mx["reconciles"], mx

# an ABSENT rate is not a rate of zero — an unpriced line and one priced at zero are different claims
none_rate = {"lines": [{"code": "A", "basis": "area", "quantity": 1.0, "amount": 0.0}], "total": 0.0}
zero_rate = {"lines": [{"code": "A", "basis": "area", "quantity": 1.0, "unit_cost": 0.0,
                        "amount": 0.0}], "total": 0.0}
nz = ed.diff(none_rate, zero_rate)
assert {x["cause"]: x["count"] for x in nz["causes"]}["repriced"] == 1, nz["causes"]

# a caller cannot steer its own attribution by smuggling this module's internals through the body
smuggled = {"lines": [], "total": 0.0,
            "by_element": {"x": {"code": "A", "quantity": 1.0, "unit_cost": 1.0, "amount": 1.0,
                                 "_rate_set": frozenset([999.0])}}}
sm = ed.diff(smuggled, smuggled)
assert sm["changed"] == 0, sm

# ---- a truncated item list SAYS so ----------------------------------------------------------------
# A capped list whose `count` covers the whole set makes any UI that totals the items disagree with
# the reported delta, with no way to tell why.
many_a = E({f"g{i}": ("A", 1.0, 10.0) for i in range(ed.MAX_ITEMS + 40)})
many_b = E({f"g{i}": ("A", 2.0, 10.0) for i in range(ed.MAX_ITEMS + 40)})
big = ed.diff(many_a, many_b)
bq = next(x for x in big["causes"] if x["cause"] == "requantified")
assert bq["count"] == ed.MAX_ITEMS + 40, bq["count"]
assert len(bq["items"]) == ed.MAX_ITEMS, len(bq["items"])
assert bq["truncated"] == 40, bq["truncated"]
assert bq["delta"] == round(sum(x["delta"] for x in bq["items"]) * (bq["count"] / len(bq["items"])), 2)
assert big["reconciles"], big

# ---- rounding noise is not a change; degenerate inputs are answers ---------------------------------
noise = ed.diff(E({"x": ("A", 10.0, 100.0)}), E({"x": ("A", 10.0, 100.0)}))
assert noise["changed"] == 0 and noise["unchanged"] == 1, noise
empty = ed.diff(None, None)
assert empty["total_delta"] == 0.0 and empty["changed"] == 0 and empty["reconciles"]
first = ed.diff({}, E({"x": ("A", 10.0, 100.0)}))
assert {x["cause"]: x["count"] for x in first["causes"]}["added"] == 1 and first["reconciles"]
last = ed.diff(E({"x": ("A", 10.0, 100.0)}), {})
assert {x["cause"]: x["count"] for x in last["causes"]}["removed"] == 1 and last["reconciles"]
# every cause is listed with its meaning even at zero — nobody should have to wonder whether
# "removed" is absent because nothing was removed or because the key was dropped
assert [x["cause"] for x in empty["causes"]] == list(ed.CAUSES)
for x in empty["causes"]:
    assert len(x["means"]) > 20 and x["truncated"] == 0, x

# ---- and it consumes what `fived.estimate` actually emits -------------------------------------------
# The whole fix rests on the estimate carrying exact per-element facts, so that is asserted against
# the real producer rather than against this file's fixture.
IDX = {"e1": {"ifc_class": "IfcWall"}, "e2": {"ifc_class": "IfcWall"}}
RULES = [{"selector": "class=IfcWall", "code": "09 21 16", "basis": "area", "unit_cost": 100.0}]
real_a = fived.estimate(IDX, RULES, {"e1": {"area": 10.0}, "e2": {"area": 30.0}})
real_b = fived.estimate(IDX, RULES, {"e1": {"area": 10.0}, "e2": {"area": 40.0}})
assert real_a.get("by_element"), "fived.estimate must emit by_element for the diff to be exact"
assert real_a["by_element"]["e1"]["quantity"] == 10.0, real_a["by_element"]
rd = ed.diff(real_a, real_b)
rq = {x["cause"]: x for x in rd["causes"]}
assert rd["granularity"] == "element", rd["granularity"]
assert rq["requantified"]["count"] == 1, rd["causes"]
assert rq["requantified"]["items"][0]["guid"] == "e2", rq["requantified"]["items"][0]
assert rd["total_delta"] == 1000.0 and rd["reconciles"], rd

# ---- REVIEW FIX: a by_element entry with no `amount` is bad input, not a 500 -----------------------
# The route catches (TypeError, ValueError, AttributeError). A bare fact["amount"] raised KeyError,
# which is NOT in that tuple, so it escaped to the global handler as a 500 and wrote an error-log row
# per attempt. The module docstring explicitly anticipates this input ("a payload assembled by hand,
# or an older stored estimate"), so it must degrade rather than fault.
_lean = {"by_element": {"g1": {"code": "A", "quantity": 1.0, "unit_cost": 1.0, "amount": 1.0}},
         "total": 1.0}
_noamt = {"by_element": {"g1": {"code": "A", "quantity": 1.0, "unit_cost": 1.0, "amount": 1.0},
                         "g2": {"code": "A", "quantity": 1.0, "unit_cost": 1.0}}, "total": 2.0}
for _b, _a in ((_lean, _noamt), (_noamt, _lean)):     # the `added` side AND the `removed` side
    ed.diff(_b, _a)                                   # must not raise

# ---- REVIEW FIX: a merged multi-rate group reports its BLENDED rate -------------------------------
# fived.estimate keys lines on (code, basis, unit_cost) so layering can price one code at several
# rates, and those lines merge here. Collapsing them to unit_cost=None meant `_classify` saw neither a
# rate movement nor a quantity movement, and a pure repricing was attributed to NOTHING: $30 of real
# change, zero changes reported, `reconciles` false. Putting the rate in the KEY instead does make the
# money reconcile, but relabels a repricing as removed+added -- scope change, which is the single
# distinction this module exists to draw.
_MIX = {"lines": [{"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 5.0, "amount": 50.0},
                  {"code": "A", "basis": "area", "quantity": 10.0, "unit_cost": 7.0, "amount": 70.0}],
        "total": 120.0}


def _causes(before, after):
    d = ed.diff(before, after)
    assert d["granularity"] == "line", d["granularity"]
    assert d["reconciles"], d
    assert abs(d["attributed"] - d["total_delta"]) <= 0.02, d
    return {c["cause"]: c["delta"] for c in d["causes"] if c["count"]}


def _L(*rows):
    lines = [{"code": "A", "basis": "area", "quantity": q, "unit_cost": r, "amount": round(q * r, 2)}
             for q, r in rows]
    return {"lines": lines, "total": round(sum(x["amount"] for x in lines), 2)}


# rates move, total quantity does not -> a commercial decision
assert _causes(_MIX, _L((10.0, 6.0), (10.0, 9.0))) == {"repriced": 30.0}
# quantity moves and the RATES do not -> a design event, even though the BLEND shifts 6.0 -> 5.8.
# This is exactly why the rate SET decides `r_moved` rather than the blended rate: a shift in the mix
# is not a repricing, and labelling it one puts a commercial cause on a design change.
assert _causes(_MIX, _L((15.0, 5.0), (10.0, 7.0))) == {"requantified": 25.0}
# both moved -> ONE honest change, not two half-truths
assert _causes(_MIX, _L((15.0, 6.0), (10.0, 9.0))) == {"both": 60.0}
assert _causes(_MIX, _MIX) == {}, "identical estimates changed nothing"

# ---- REVIEW FIX: internals are not steerable from the request body --------------------------------
# `_rate_set` is this module's own, and `by_element` arrives from the body, so underscore keys are
# stripped rather than trusted -- otherwise a caller could choose its own cause attribution. A
# frozenset must also never reach the response, which is JSON.
_inj = ed.diff({"by_element": {"g1": {"code": "A", "quantity": 1.0, "unit_cost": 1.0, "amount": 1.0,
                                      "_rate_set": ["whatever"]}}, "total": 1.0},
               {"by_element": {"g1": {"code": "A", "quantity": 1.0, "unit_cost": 9.0, "amount": 9.0}},
                "total": 9.0})
assert {c["cause"]: c["delta"] for c in _inj["causes"] if c["count"]} == {"repriced": 8.0}, _inj
assert not any(isinstance(v, (set, frozenset))
               for c in _inj["causes"] for i in c["items"] for v in i.values()), _inj

print("R25-ESTIMATE-DIFF OK - two estimates diff by GlobalId with every dollar attributed to ONE of "
      "four causes: added/removed are scope, requantified is a design event, repriced is a commercial "
      "decision, and `both` is the honest answer when quantity and rate move together rather than a "
      "leftover bucket. The first version of this module was wrong in a way its own checks could not "
      "see: it reconstructed per-element quantities by dividing a line evenly across its GlobalIds, "
      "so adding ONE wall to a line reported every other wall in it as a design change while the new "
      "wall took the average instead of its own quantity - and `reconciles` stayed TRUE throughout, "
      "because invented numbers still sum correctly. A self-consistency check is not a correctness "
      "check. fived.estimate now emits exact per-element facts and this consumes them; where an input "
      "lacks them it diffs LINES rather than inventing each element's share, because a coarser true "
      "answer beats a finer invented one. Two more of the same family are fixed and pinned: a "
      "quantity was being compared against the MONEY epsilon with `repriced` as the fall-through, so "
      "a pure design change with identical rates on both sides came back labelled commercial; and the "
      "small-delta skip ran BEFORE classification, so a compensating change - quantity doubled, rate "
      "halved - was asserted to be no change at all.")
