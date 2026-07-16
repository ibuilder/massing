"""MEP depth (P5): distribution runs (duct/pipe/cable-carrier/cable) with ports + IfcDistributionSystem,
and point equipment (panel, outlet, air terminal, waste terminal, fire alarm, sensor, comms).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_mep_families.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell                                    # noqa: E402
import ifcopenshell.api                                # noqa: E402
from aec_data import edit                              # noqa: E402
from aec_data.ifc_loader import open_model             # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_mepf.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_mepf_out.ifc")


def _build() -> str:
    m = ifcopenshell.api.run("project.create_file")
    proj = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    metre = m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    ifcopenshell.api.run("unit.assign_unit", m, units=[metre])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    ifcopenshell.api.run("context.add_context", m, context_type="Model", context_identifier="Body",
                         target_view="MODEL_VIEW", parent=m.by_type("IfcGeometricRepresentationContext")[0])
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="L1")
    st.Elevation = 0.0
    ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
    m.write(TMP)
    return TMP


path = _build()

# --- HVAC duct run: segment + a named IfcDistributionSystem ----------------------------------
edit.apply_recipe(path, "add_duct", {"start": [0, 0], "end": [6, 0], "size": 0.4}, OUT)
m = open_model(OUT)
assert len(m.by_type("IfcDuctSegment")) == 1, m.by_type("IfcDuctSegment")
assert "HVAC Supply" in {s.Name for s in m.by_type("IfcDistributionSystem")}
assert m.by_type("IfcCircleProfileDef"), "round duct section"

# --- pipe (own system) + cable tray (rect) + wire --------------------------------------------
edit.apply_recipe(OUT, "add_pipe", {"start": [0, 1], "end": [6, 1], "size": 0.05}, OUT)
edit.apply_recipe(OUT, "add_cable_tray", {"start": [0, 2], "end": [6, 2], "size": 0.3}, OUT)
edit.apply_recipe(OUT, "add_wire", {"start": [0, 3], "end": [6, 3], "size": 0.02}, OUT)
m = open_model(OUT)
assert m.by_type("IfcPipeSegment") and m.by_type("IfcCableCarrierSegment") and m.by_type("IfcCableSegment")
assert {"HVAC Supply", "Domestic Water", "Power"} <= {s.Name for s in m.by_type("IfcDistributionSystem")}
assert m.by_type("IfcRectangleProfileDef"), "cable tray rectangular section"

# --- point equipment: panel, outlet, air terminal, waste terminal, alarm, sensor, comms ------
terminals = [
    ("IfcElectricDistributionBoard", None), ("IfcOutlet", "POWEROUTLET"),
    ("IfcAirTerminal", "DIFFUSER"), ("IfcWasteTerminal", "FLOORTRAP"),
    ("IfcAlarm", "BELL"), ("IfcSensor", "SMOKESENSOR"), ("IfcCommunicationsAppliance", None),
]
for cls, pre in terminals:
    body = {"ifc_class": cls, "point": [1, 1], "width": 0.3, "depth": 0.3, "height": 0.3}
    if pre:
        body["predefined"] = pre
    edit.apply_recipe(OUT, "add_mep_terminal", body, OUT)
m = open_model(OUT)
for cls, _pre in terminals:
    assert m.by_type(cls), f"missing {cls}"
assert getattr(m.by_type("IfcOutlet")[0], "PredefinedType", None) == "POWEROUTLET"

# --- Fire Alarm (life-safety, distinct from fire protection) + Telecom as first-class devices -----
edit.apply_recipe(OUT, "add_fa_device", {"kind": "smoke_detector", "point": [2, 2], "storey": "L1"}, OUT)
edit.apply_recipe(OUT, "add_fa_device", {"kind": "pull_station", "point": [3, 2], "storey": "L1"}, OUT)
edit.apply_recipe(OUT, "add_fa_device", {"kind": "facp", "point": [4, 2], "storey": "L1"}, OUT)
edit.apply_recipe(OUT, "add_comms_device", {"kind": "idf", "point": [5, 2], "storey": "L1"}, OUT)
edit.apply_recipe(OUT, "add_comms_device", {"kind": "wap", "point": [6, 2], "storey": "L1"}, OUT)
m = open_model(OUT)
sysnames = {s.Name for s in m.by_type("IfcDistributionSystem")}
assert "Fire Alarm" in sysnames, sysnames                 # FA is its own system, apart from Fire Protection
assert "Telecommunications" in sysnames, sysnames
# smoke detector authored as a sensor with the right PredefinedType
assert any(getattr(s, "PredefinedType", None) == "SMOKESENSOR" for s in m.by_type("IfcSensor"))
# a comms appliance carries the IDF/WAP; discipline classification puts it in Telecommunications
from aec_api import classification as _cls                 # noqa: E402
assert _cls.discipline_of_ifc_class("IfcCommunicationsAppliance") == "T"
assert _cls.discipline_of_ifc_class("IfcAlarm") == "E"     # fire alarm folds to Electrical discipline (FA series)

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("MEP FAMILIES OK - duct/pipe/cable-carrier/cable runs authored as swept segments + named "
      "IfcDistributionSystems (HVAC Supply / Domestic Water / Power); round vs rect sections; point "
      "equipment for panel/outlet/air-terminal/waste-terminal/alarm/sensor/comms (PredefinedType kept).")
