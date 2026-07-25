"""5D — cost carried IN the IFC, via the schema's own relationships.

The takeoff has always produced good rows and left them OUTSIDE the model, and that is precisely what
stopped it being 5D: a cost in a sidecar cannot travel with the file, cannot be read by another tool,
and drifts the moment the model is re-exported. IFC is our stated source of truth, and a cost sitting
beside the IFC is not in it.

IFC already has the relationships, so nothing bespoke is needed — `IfcCostItem` for the priced line,
`IfcRelAssignsToControl` to bind the elements it prices (the actual 5D link, by GlobalId, inside the
model), `IfcCostSchedule` to group an estimate. The 4D equivalent, `IfcRelAssignsToProcess`, is
already read by `schedule.from_ifc`, so both dimensions become the same kind of fact.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_cost_ifc.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_cost_ifc.db"
os.environ["STORAGE_DIR"] = "./test_storage_cost_ifc"
if os.path.exists("./test_cost_ifc.db"):
    os.remove("./test_cost_ifc.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import cost_ifc, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "_cost_ifc.ifc")
massing.generate_blank_ifc(PATH, name="5D", storeys=2, storey_height=3.5, ground_size=24.0)
model = open_model(PATH)
st = model.by_type("IfcBuildingStorey")[0].Name
# add_wall returns the new element's GlobalId (the GUID-stable recipe contract)
g1 = edit.add_wall(model, [-9, 0], [9, 0], 3.2, 0.3, st)
g2 = edit.add_wall(model, [0, -9], [0, 9], 3.2, 0.3, st)
assert isinstance(g1, str) and isinstance(g2, str) and g1 != g2, (g1, g2)

# ---- write an estimate into the model -----------------------------------------------------------
res = cost_ifc.write_cost_schedule(model, [
    {"code": "03 30 00", "description": "Cast-in-place concrete wall", "unit_cost": 185.0,
     "basis": "area", "quantity": 57.6, "guids": [g1, g2]},
    {"code": "09 91 00", "description": "Painting", "unit_cost": 12.5,
     "basis": "area", "quantity": 115.2, "guids": [g1]},
], name="GMP Estimate")
assert res["written"] == 2, res
assert res["missing_guids"] == [], res
assert res["schedule"].Name == "GMP Estimate"

# the schedule and the link relationships are real IFC entities, not our own invention
assert len(model.by_type("IfcCostSchedule")) == 1
assert len(model.by_type("IfcCostItem")) == 2
assert model.by_type("IfcRelAssignsToControl"), "the element→cost link must exist in the model"

# ---- THE ROUND TRIP: written into IFC, read back out of IFC --------------------------------------
# A cost written into the model that cannot be read back is a sidecar with extra steps.
PATH2 = os.path.join(os.path.dirname(__file__), "_cost_ifc_rt.ifc")
model.write(PATH2)
reread = open_model(PATH2)                       # a genuinely separate parse, not the in-memory file
lines = cost_ifc.read_cost_schedule(reread)
assert len(lines) == 2, lines
by_code = {ln["code"]: ln for ln in lines}

conc = by_code["03 30 00"]
assert conc["description"] == "Cast-in-place concrete wall"
assert abs(conc["unit_cost"] - 185.0) < 1e-6
assert abs(conc["quantity"] - 57.6) < 1e-6
assert conc["guids"] == sorted([g1, g2]), conc["guids"]

paint = by_code["09 91 00"]
assert paint["guids"] == [g1], "a line prices only the elements it was bound to"

# ---- the basis survives the round trip, because a bare number is not a measurement ---------------
# "120 m2" is not a measurement; "120 m2, net area, openings deducted" is. Two estimators measuring
# gross and net disagree by the openings, and a number with no stated basis gives nobody a way to
# find out which happened.
assert conc["basis"] == "area", conc
assert conc["basis_meaning"] and "openings" in conc["basis_meaning"].lower(), conc["basis_meaning"]
assert set(cost_ifc.QUANTITY_KINDS) == {"length", "area", "volume", "weight", "count"}
for basis, kind in cost_ifc.QUANTITY_KINDS.items():
    assert kind["entity"].startswith("IfcQuantity") and kind["unit"] and kind["meaning"], basis

# ---- a bad basis is refused rather than silently defaulted ---------------------------------------
# NOTE: open_model CACHES by path, so re-opening PATH returns the same in-memory model that already
# carries the writes above. Each case below therefore gets its own file.
def fresh(tag):
    p = os.path.join(os.path.dirname(__file__), f"_cost_ifc_{tag}.ifc")
    massing.generate_blank_ifc(p, name=tag, storeys=1, storey_height=3.0, ground_size=12.0)
    m = open_model(p)
    gid = edit.add_wall(m, [-4, 0], [4, 0], 3.0, 0.2, m.by_type("IfcBuildingStorey")[0].Name)
    return p, m, gid


# case is normalised — refusing "AREA" would reject a clearly-intended valid basis, which blocks
# correct work for no safety gain. The refusal exists for a basis we cannot MEASURE, not for shouting.
_p, _m, _g = fresh("case")
assert cost_ifc.write_cost_schedule(_m, [{"code": "c", "basis": "AREA", "quantity": 1}])["written"] == 1
assert cost_ifc.read_cost_schedule(_m)[0]["basis"] == "area"
os.remove(_p)
for bad in ("sqft", "square metres", "", "ea"):
    try:
        cost_ifc.write_cost_schedule(model, [{"code": "x", "basis": bad, "quantity": 1}])
        raise AssertionError(f"expected refusal for basis={bad!r}")
    except ValueError as e:
        assert "basis must be one of" in str(e), e

# ---- an unmatched GlobalId is REPORTED, never silently dropped -----------------------------------
# Dropping the line would make the estimate quietly cheaper than the project — the worst possible
# direction for an error in a bid.
p2, m2, gw = fresh("missing")
r2 = cost_ifc.write_cost_schedule(m2, [
    {"code": "26 00 00", "description": "Electrical", "unit_cost": 40.0, "basis": "count",
     "quantity": 12, "guids": ["NOTAREALGUID0000000000", gw]},
])
assert r2["written"] == 1, "the cost line is still written — the money is real"
assert r2["missing_guids"] == ["NOTAREALGUID0000000000"], r2["missing_guids"]
back = cost_ifc.read_cost_schedule(m2)
assert len(back) == 1 and back[0]["quantity"] == 12 and back[0]["basis"] == "count", back
assert back[0]["guids"] == [gw], "only the elements that exist are bound"
os.remove(p2)

# a line with no elements at all is still a cost — general conditions price nothing in particular
p3, m3, _ = fresh("lump")
r3 = cost_ifc.write_cost_schedule(m3, [
    {"code": "01 00 00", "description": "General conditions", "unit_cost": 250000.0,
     "basis": "count", "quantity": 1, "guids": []}])
assert r3["written"] == 1 and r3["missing_guids"] == []
assert cost_ifc.read_cost_schedule(m3)[0]["guids"] == []
os.remove(p3)

# an empty estimate writes a schedule and no items rather than failing
p4, m4, _ = fresh("empty")
assert cost_ifc.write_cost_schedule(m4, [])["written"] == 0
assert cost_ifc.read_cost_schedule(m4) == []
assert len(m4.by_type("IfcCostSchedule")) == 1, "an empty estimate is still an estimate"
os.remove(p4)

for p in (PATH, PATH2):
    if os.path.exists(p):
        os.remove(p)

print("5D-COST-IFC OK - cost now lives IN the model, through IFC's own relationships rather than "
      "anything bespoke: IfcCostItem for the priced line, IfcRelAssignsToControl binding the "
      "elements it prices (the actual 5D link, by GlobalId, inside the file), and IfcCostSchedule "
      "grouping the estimate so one model can carry a bid and a GMP without them merging. This is "
      "what the takeoff was missing - it produced good rows and left them OUTSIDE the model, and a "
      "cost in a sidecar cannot travel with the file, cannot be read by another tool, and drifts the "
      "moment the model is re-exported, which is exactly what our IFC-is-source-of-truth rule "
      "forbids. The round trip is asserted through a real re-parse from disk rather than the "
      "in-memory file, because a cost that cannot be read back is a sidecar with extra steps. Every "
      "quantity carries its BASIS into the model as the quantity's own description, since '120 m2' "
      "is not a measurement while '120 m2, net area, openings deducted' is - two estimators measuring "
      "gross and net disagree by the openings and an unstated basis gives nobody a way to find out "
      "which happened. A bad basis is refused rather than defaulted, and a GlobalId that is not in "
      "the model is REPORTED while the cost line is still written, because dropping it would make "
      "the estimate quietly cheaper than the project - the worst possible direction for an error in "
      "a bid.")
