"""W11 B6 MEP fittings + system browser: author duct runs + fittings (elbow/junction) assigned to a
named IfcDistributionSystem, then read the system back with per-class counts + connectivity signal.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mep_systems.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing, mep  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_mep_test.ifc")
massing.generate_blank_ifc(TMP, name="MEP Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# two duct segments meeting at a corner + an elbow fitting joining them, all on "HVAC Supply"
seg1 = edit.add_mep_run(m, "IfcDuctSegment", [0, 0], [5, 0], "round", 0.3, st, system="HVAC Supply")
edit.add_mep_run(m, "IfcDuctSegment", [5, 0], [5, 4], "round", 0.3, st, system="HVAC Supply")
elbow = edit.add_mep_fitting(m, "IfcDuctFitting", [5, 0], 0.3, "BEND", st, system="HVAC Supply")
tee = edit.add_mep_fitting(m, "IfcDuctFitting", [5, 2], 0.3, "JUNCTION", st, system="HVAC Supply")

# the fittings are real IfcDuctFitting with the right PredefinedType + ports
e = m.by_guid(elbow)
assert e.is_a() == "IfcDuctFitting" and e.PredefinedType == "BEND", e
t = m.by_guid(tee)
assert t.PredefinedType == "JUNCTION", t.PredefinedType
assert e.Representation is not None, "fitting has no geometry"
assert mep._ports(e) and len(mep._ports(e)) == 2, "elbow should have 2 ports"
assert len(mep._ports(t)) == 3, "junction should have 3 ports"

# --- system browser -------------------------------------------------------------------------------
s = mep.mep_summary(m)
assert s["total_systems"] >= 1, s
hvac = next((x for x in s["systems"] if x["name"] == "HVAC Supply"), None)
assert hvac is not None, s["systems"]
assert hvac["segments"] == 2 and hvac["fittings"] == 2, hvac
assert hvac["members"] == 4, hvac
# ports were added but not connected → all 4 members show open ports
assert hvac["elements_with_open_ports"] == 4, hvac
# nothing unassigned (all on the system)
assert s["unassigned"]["segments"] == 0 and s["unassigned"]["fittings"] == 0, s["unassigned"]

# --- W10-4: port-to-port connectivity + validation report -----------------------------------------
c0 = mep.connectivity(m)
assert c0["ports_total"] > 0 and c0["ports_connected"] == 0, c0     # nothing wired yet
assert c0["connections"] == 0 and c0["dangling_count"] == c0["elements"], c0  # every element floats

# connect the elbow to the first segment (port-to-port) → 1 connection, 2 fewer open ports
edit.connect_mep(m, elbow, seg1)
c1 = mep.connectivity(m)
assert c1["connections"] == 1, c1
assert c1["ports_connected"] == 2 and c1["ports_open"] == c0["ports_open"] - 2, (c0, c1)
assert c1["dangling_count"] == c0["dangling_count"] - 2, "elbow + seg1 are no longer floating"
assert 0 < c1["connected_pct"] < 100, c1["connected_pct"]

# connecting an element with no free port raises (both elbow ports now used up after 2 connects)
edit.connect_mep(m, elbow, tee)                                     # elbow's 2nd port → tee
raised = False
try:
    edit.connect_mep(m, elbow, seg1)                               # elbow has no free port left
except ValueError as ex:
    raised = True
    assert "free connection port" in str(ex), str(ex)
assert raised, "connecting via a fully-used element should raise"
# connect_mep is a registered recipe
assert "connect_mep" in edit.RECIPES

# a fitting on a DIFFERENT system is counted separately + an unassigned one shows in unassigned
edit.add_mep_fitting(m, "IfcPipeFitting", [10, 10], 0.05, "TRANSITION", st, system="Domestic Water")
s2 = mep.mep_summary(m)
assert any(x["name"] == "Domestic Water" and x["fittings"] == 1 for x in s2["systems"]), s2["systems"]

# invalid predefined falls back to BEND (2 ports), never crashes
weird = edit.add_mep_fitting(m, "IfcDuctFitting", [0, 8], 0.3, "NOTATYPE", st, system="HVAC Supply")
assert len(mep._ports(m.by_guid(weird))) == 2

# --- recipe path (the /edit route) ----------------------------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_mep_out.ifc")
r = edit.apply_recipe(TMP, "add_mep_fitting",
                      {"ifc_class": "IfcDuctFitting", "point": [2, 2], "predefined": "JUNCTION",
                       "system": "HVAC Return"}, OUT)
assert r["changed"], r
mo = open_model(OUT)
assert any(x["name"] == "HVAC Return" for x in mep.mep_summary(mo)["systems"])

# --- MEP-FP: fire protection as a first-class distribution system ---------------------------------
# a sprinkler branch pipe (discipline='fire') + two sprinkler heads on a "Fire Protection" system
edit.add_mep_run(m, "IfcPipeSegment", [0, 12], [6, 12], "round", 0.05, st,
                 system="Fire Protection", discipline="fire")
edit.add_mep_terminal(m, "IfcFireSuppressionTerminal", [2, 12], 0.15, 0.15, 0.1, "SPRINKLER", st,
                      system="Fire Protection", discipline="fire")
edit.add_mep_terminal(m, "IfcFireSuppressionTerminal", [4, 12], 0.15, 0.15, 0.1, "SPRINKLER", st,
                      system="Fire Protection", discipline="fire")
sfp = mep.mep_summary(m)
fp = next((x for x in sfp["systems"] if x["name"] == "Fire Protection"), None)
assert fp is not None, sfp["systems"]
assert fp["discipline"] == "fire" and fp["predefined_type"] == "FIREPROTECTION", fp
assert fp["segments"] == 1 and fp["terminals"] == 2 and fp["members"] == 3, fp
# fire protection is now a recognised discipline in the rollup
assert sfp["has_fire_protection"] is True, sfp
assert sfp["by_discipline"]["fire"]["systems"] == 1 and sfp["by_discipline"]["fire"]["members"] == 3, sfp["by_discipline"]
# the HVAC system is classified by its duct members (no explicit PredefinedType from the direct calls)
assert next(x for x in sfp["systems"] if x["name"] == "HVAC Supply")["discipline"] == "hvac", sfp["systems"]
# a fire-suppression terminal is connectable (it got a port because a system was given)
fire_heads = list(m.by_type("IfcFireSuppressionTerminal"))
assert fire_heads and mep._ports(fire_heads[0]), "sprinkler head should have a connection port"

# MEP-FP equipment: hose reel + fire-department connection (IfcFireSuppressionTerminal subtypes) + fire pump
hr = edit.add_fire_equipment(m, "hose_reel", [1, 13], st)
fdc = edit.add_fire_equipment(m, "fdc", [0, 13], st)
pump = edit.add_fire_equipment(m, "fire_pump", [5, 13], st)
assert m.by_guid(hr).is_a() == "IfcFireSuppressionTerminal" and m.by_guid(hr).PredefinedType == "HOSEREEL", m.by_guid(hr)
assert m.by_guid(fdc).PredefinedType == "BREECHINGINLET", m.by_guid(fdc).PredefinedType
assert m.by_guid(pump).is_a() == "IfcPump", m.by_guid(pump).is_a()
# all landed on the Fire Protection system (still discipline=fire)
sfe = mep.mep_summary(m)
fp2 = next(x for x in sfe["systems"] if x["name"] == "Fire Protection")
assert fp2["discipline"] == "fire" and fp2["members"] >= 6, fp2   # pipe + 2 sprinklers + hose reel + fdc + pump
assert "add_fire_equipment" in edit.RECIPES

# sprinkler coverage: 2 SPRINKLER heads over authored spaces; required = ceil(area / max-coverage)
import math  # noqa: E402
edit.add_spaces(m, rooms_per_storey=2, ceiling_height=3.0)       # gives measurable NetFloorArea
cov = mep.sprinkler_coverage(m, "light")
assert cov["sprinkler_heads"] == 2, cov                          # hose reel/fdc/pump are NOT counted
assert cov["protected_area_m2"] > 0 and cov["max_coverage_m2_per_head"] == 18.58, cov
assert cov["required_heads"] == math.ceil(cov["protected_area_m2"] / 18.58), cov
assert cov["adequate"] == (cov["sprinkler_heads"] >= cov["required_heads"]), cov
# ordinary hazard requires MORE heads than light (smaller coverage per head)
cov_o = mep.sprinkler_coverage(m, "ordinary")
assert cov_o["required_heads"] >= cov["required_heads"], (cov_o["required_heads"], cov["required_heads"])
# no spaces → area unknown → adequate None (a fresh empty model)
import ifcopenshell as _ios  # noqa: E402
covn = mep.sprinkler_coverage(_ios.file(schema="IFC4"), "light")
assert covn["protected_area_m2"] == 0 and covn["sprinkler_heads"] == 0 and covn["adequate"] is None, covn

# set_system_predefined retags an existing plain system's discipline
edit.set_system_predefined(m, "Domestic Water", "plumbing")
dw = next(x for x in mep.mep_summary(m)["systems"] if x["name"] == "Domestic Water")
assert dw["predefined_type"] == "DOMESTICCOLDWATER" and dw["discipline"] == "plumbing", dw
# set_system_predefined + add_sprinkler are registered recipes
assert "set_system_predefined" in edit.RECIPES and "add_sprinkler" in edit.RECIPES
try:
    edit.set_system_predefined(m, "No Such System", "fire")
    raise AssertionError("should raise for an unknown system")
except ValueError:
    pass

# --- IFC2x3 models must not crash the browser (IfcDistributionSystem is IFC4+) --------------------
import ifcopenshell  # noqa: E402

legacy = mep.mep_summary(ifcopenshell.file(schema="IFC2X3"))
assert legacy["total_systems"] == 0 and legacy["systems"] == [], legacy

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("MEP OK - add_mep_fitting authors IfcDuctFitting/IfcPipeFitting (BEND=2 ports / JUNCTION=3 ports, "
      "PredefinedType set, bad type -> BEND fallback) assigned to a named IfcDistributionSystem; "
      "mep_summary browses systems (segments/fittings/terminals counts + open-port connectivity signal + "
      "unassigned tally); add_mep_fitting recipe works via apply_recipe. W10-4: connect_mep wires elements "
      "port-to-port (IfcRelConnectsPorts, first free port, raises when none), and mep.connectivity reports "
      "ports connected/open, connection count, dangling (floating) elements + connected %.")
