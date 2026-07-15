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
