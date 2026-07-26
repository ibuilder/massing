"""5D — the binding that ties the model to the money.

The takeoff already prices a model, but it maps IFC class → cost code and nothing else, so every wall
gets one rate regardless of type, storey, fire rating or phase. Real estimating does not work that
way: `IfcWall` with `FireRating=2HR` on the podium is a different line from a partition on level 12.

`query_dsl` is already THE element selector here — clash scopes, view filters, smart views and the
rule library all compose on it — so a cost rule is a **stored selector plus a rate**, not a new
engine. Everything below tests the three properties that make that trustworthy.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_fived.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_fived.db"
os.environ["STORAGE_DIR"] = "./test_storage_fived"
if os.path.exists("./test_fived.db"):
    os.remove("./test_fived.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import fived  # noqa: E402
from aec_api.query_dsl import QueryError  # noqa: E402
from aec_data import cost_ifc  # noqa: E402

# ---- the two tables encoding one vocabulary must not drift ---------------------------------------
# The API side names the bases it can price; the IFC side names the quantity entities it can write.
# Two tables for one concept WILL diverge silently unless something asserts they don't.
assert set(fived.BASES) == set(cost_ifc.QUANTITY_KINDS), \
    set(fived.BASES) ^ set(cost_ifc.QUANTITY_KINDS)

IDX = {
    "W1": {"ifc_class": "IfcWall", "name": "Podium ext",
           "psets": {"Pset_WallCommon": {"FireRating": "2HR"}}},
    "W2": {"ifc_class": "IfcWall", "name": "L12 partition"},
    "S1": {"ifc_class": "IfcSlab", "name": "L02 slab"},
    "D1": {"ifc_class": "IfcDoor", "name": "Door 12"},
}
QTY = {
    "W1": {"area": 120.0, "volume": 36.0},
    "W2": {"area": 40.0, "volume": 4.0},
    "S1": {"area": 800.0, "volume": 160.0},
    "D1": {},
}

# ---- validation refuses what it cannot price -----------------------------------------------------
def bad(rules, why):
    try:
        fived.validate_rules(rules)
    except QueryError:
        return
    raise AssertionError(f"expected refusal: {why}")


bad([{"code": "03", "basis": "area", "unit_cost": 1}], "no selector")
bad([{"selector": "IfcWall", "basis": "area", "unit_cost": 1}], "no cost code")
bad([{"selector": "IfcWall", "code": "03", "unit_cost": 1}], "no basis")
bad([{"selector": "IfcWall", "code": "03", "basis": "sqft", "unit_cost": 1}], "unknown basis")
bad([{"selector": "IfcWall", "code": "03", "basis": "area"}], "no unit_cost")
bad([{"selector": "IfcWall", "code": "03", "basis": "area", "unit_cost": "free"}], "non-numeric rate")
bad([{"selector": "IfcWall", "code": "03", "basis": "area", "unit_cost": -5}], "negative rate")
bad([{"selector": "", "code": "03", "basis": "area", "unit_cost": 1}], "empty selector")

# The DSL grammar is deliberately permissive — nearly any token parses as an existence test — so
# "does it parse" is a weak guarantee. The real hazard is a selector that parses fine and matches
# NOTHING, which would otherwise be a silent pass. It is caught downstream instead, where it belongs:
# the elements it failed to price show up as UNPRICED rather than vanishing.
never = fived.bind({"W1": {"ifc_class": "IfcWall"}},
                   [{"selector": "Pset_Nope.Nothing=xyz", "code": "99", "basis": "area",
                     "unit_cost": 1.0}])
assert never["priced_count"] == 0 and never["unpriced"] == ["W1"], never
assert never["coverage_pct"] == 0.0, "a rule that matches nothing prices nothing, and says so"

assert fived.validate_rules([{"selector": "IfcWall", "code": "03 30 00",
                              "basis": "area", "unit_cost": 185}])[0]["description"] == "03 30 00"

# ---- PROPERTY 1: later rules win, and every element records which rule priced it ------------------
RULES = [
    {"selector": "IfcWall", "code": "03 30 00", "description": "Concrete wall",
     "basis": "area", "unit_cost": 185.0},
    # the layering case: the podium fire-rated wall is a different line from a plain partition
    {"selector": "Pset_WallCommon.FireRating=2HR", "code": "03 30 10",
     "description": "Fire-rated wall", "basis": "area", "unit_cost": 240.0},
    {"selector": "IfcSlab", "code": "03 30 20", "description": "Slab", "basis": "volume",
     "unit_cost": 410.0},
]
b = fived.bind(IDX, RULES)
assert b["assigned"]["W1"]["code"] == "03 30 10", b["assigned"]["W1"]   # override won
assert b["assigned"]["W1"]["rule"] == 1, "the element records WHICH rule priced it"
assert b["assigned"]["W1"]["selector"] == "Pset_WallCommon.FireRating=2HR"
assert b["assigned"]["W2"]["code"] == "03 30 00", "the un-overridden wall keeps the base rate"
assert b["assigned"]["S1"]["code"] == "03 30 20"

# ---- PROPERTY 2: an element matched by no rule is UNPRICED, never silently zero -------------------
# This is the most expensive defect an estimate can have, because the total still looks like a total.
assert b["unpriced"] == ["D1"], b["unpriced"]
assert b["unpriced_count"] == 1
assert b["priced_count"] == 3 and b["element_count"] == 4
assert b["coverage_pct"] == 75.0

# ---- PROPERTY 3: a rate with nothing to multiply is an UNKNOWN cost, not a cost of nothing --------
withdoor = RULES + [{"selector": "IfcDoor", "code": "08 11 00", "description": "Doors",
                     "basis": "area", "unit_cost": 95.0}]
e = fived.estimate(IDX, withdoor, QTY)
assert [m["guid"] for m in e["missing_quantity"]] == ["D1"], e["missing_quantity"]
assert e["missing_quantity_count"] == 1
assert all(ln["code"] != "08 11 00" for ln in e["lines"]), "no line is billed at zero quantity"

# ---- the estimate itself --------------------------------------------------------------------------
e = fived.estimate(IDX, RULES, QTY)
by_code = {ln["code"]: ln for ln in e["lines"]}
assert abs(by_code["03 30 10"]["quantity"] - 120.0) < 1e-6
assert abs(by_code["03 30 10"]["amount"] - 120.0 * 240.0) < 1e-6
assert abs(by_code["03 30 00"]["quantity"] - 40.0) < 1e-6, "W1 is NOT double-counted into the base line"
assert abs(by_code["03 30 20"]["quantity"] - 160.0) < 1e-6, "the slab bills on VOLUME, per its rule"
assert abs(e["total"] - (120 * 240 + 40 * 185 + 160 * 410)) < 1e-6, e["total"]
# lines carry their elements, which is what makes the IFC write-back possible
assert by_code["03 30 10"]["guids"] == ["W1"]
# biggest money first — an estimator reads the top of the list
assert e["lines"][0]["amount"] >= e["lines"][-1]["amount"]

# ---- `complete` is the only honest headline over a partly-priced model ---------------------------
assert e["complete"] is False, "D1 is unpriced, so this total is a floor rather than an estimate"
full = fived.estimate({k: v for k, v in IDX.items() if k != "D1"}, RULES, QTY)
assert full["complete"] is True and full["unpriced_count"] == 0
assert fived.estimate({}, RULES, QTY)["complete"] is False, "an empty model has priced nothing"
assert fived.estimate(None, RULES, QTY)["total"] == 0.0

# ---- END TO END: model → selector → quantity → cost line → INTO the IFC ---------------------------
# This is the whole point of 5D. The estimate produced above is written into the model itself through
# IFC's own relationships, and read back out — so the money travels with the geometry.
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "_fived.ifc")
massing.generate_blank_ifc(PATH, name="5D end to end", storeys=1, storey_height=3.5, ground_size=20.0)
model = open_model(PATH)
st = model.by_type("IfcBuildingStorey")[0].Name
gw = edit.add_wall(model, [-8, 0], [8, 0], 3.2, 0.3, st)

live_idx = {gw: {"ifc_class": "IfcWall", "name": "Wall"}}
live_qty = {gw: {"area": 51.2}}
est = fived.estimate(live_idx, [{"selector": "IfcWall", "code": "03 30 00",
                                 "description": "Concrete wall", "basis": "area",
                                 "unit_cost": 185.0}], live_qty)
assert est["complete"] is True, est
res = cost_ifc.write_cost_schedule(model, est["lines"], name="Model-derived estimate")
assert res["written"] == 1 and res["missing_guids"] == [], res

back = cost_ifc.read_cost_schedule(model)[0]
assert back["code"] == "03 30 00" and back["basis"] == "area"
assert abs(back["quantity"] - 51.2) < 1e-6 and abs(back["unit_cost"] - 185.0) < 1e-6
assert back["guids"] == [gw], "the cost is bound to the element it priced, by GlobalId, in the model"
os.remove(PATH)

# ---- REVIEW FIX: summing `by_element` must reproduce `total` --------------------------------------
# A per-element amount is an intermediate fact, not money as presented. Rounding each one to a cent
# before summing drifts one-directionally away from the line that rounds its sum once -- -$150 across
# 50,000 elements at a fractional rate. Since `by_element` is part of the response, anything totalling
# it disagreed with `total` and nothing said which was authoritative.
_N = 5000
_pe_est = fived.estimate(
    {f"g{i:06d}": {"ifc_class": "IfcWall"} for i in range(_N)},
    [{"selector": "IfcWall", "code": "A", "description": "w", "basis": "area", "unit_cost": 3.333}],
    quantities={f"g{i:06d}": {"area": 1.0} for i in range(_N)})
_summed = round(sum(v["amount"] for v in _pe_est["by_element"].values()), 2)
assert _summed == _pe_est["total"], (_summed, _pe_est["total"], "by_element must sum to total")

print("5D-BIND OK - the model now ties to the money through the selector spine rather than a "
      "class-to-code lookup: a cost rule is a stored query_dsl selector plus a rate, which is the "
      "same spine clash scopes, view filters and the rule library already compose on, so no new "
      "engine was invented. Layering works the way estimators actually build - price all concrete, "
      "then override the podium - because LATER RULES WIN, and every element records WHICH rule "
      "priced it so a line can be traced back to the selector that produced it rather than taken on "
      "faith. An element matched by no rule is reported UNPRICED and never silently zeroed, which is "
      "the most expensive defect an estimate can carry because the total still looks like a total - "
      "the same failure as a clash matrix reporting an untested pair as clean - and a rate with no "
      "quantity to multiply is reported as an unknown cost rather than billed as a cost of nothing. "
      "The end-to-end path is asserted: model -> selector -> quantity -> cost line -> written INTO "
      "the IFC via IfcCostItem and read back with its GlobalId binding intact, so the money travels "
      "with the geometry instead of beside it.")
