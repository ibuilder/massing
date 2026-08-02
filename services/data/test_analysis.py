"""Energy + MEP + IfcSpace authoring test (offline, on a GENERATED fixture).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_analysis.py

Until 2026-08-02 this read samples/basichouse.ifc — a 52 MB file that was never tracked, so the
test could only pass on the one machine that had it. It was also DARK (nothing ran it) until the
DATA_TESTS dimension lit it, at which point CI honestly reported what had always been true. The
fixture is now authored here through the same recipes the product uses: every quantity the
assertions depend on (walls, windows, exactly 7 MEP distribution segments, 2 storeys) is stated in
this file, so the test carries its own premise instead of trusting a file to keep it."""
import os
import tempfile
import warnings

warnings.filterwarnings("ignore")

from aec_data import edit, energy, massing, spaces  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_DIR = tempfile.mkdtemp(prefix="test_analysis_")
IFC = os.path.join(_DIR, "fixture.ifc")
massing.generate_blank_ifc(IFC, name="AnalysisFixture", storeys=2, storey_height=3.0)
_m = open_model(IFC)
_storeys = [s.Name for s in _m.by_type("IfcBuildingStorey")]
# envelope: a 10 x 8 m perimeter on the ground storey, a floor slab, two windows
_wall_guids = [edit.RECIPES["add_wall"](_m, {"start": list(a), "end": list(b), "height": 3.0,
                                             "thickness": 0.2, "storey": _storeys[0]})
               for a, b in [((0, 0), (10, 0)), ((10, 0), (10, 8)),
                            ((10, 8), (0, 8)), ((0, 8), (0, 0))]]
edit.RECIPES["add_slab"](_m, {"points": [[0, 0], [10, 0], [10, 8], [0, 8]], "thickness": 0.2,
                              "storey": _storeys[0]})
for _host in _wall_guids[:2]:
    edit.RECIPES["add_window"](_m, {"host_guid": _host, "width": 1.2, "height": 1.4})
# exactly SEVEN distribution segments — the number the MEP inventory assertion states below
for _i in range(4):
    edit.RECIPES["add_duct"](_m, {"start": [1 + _i, 1], "end": [1 + _i, 6], "storey": _storeys[0]})
for _i in range(3):
    edit.RECIPES["add_pipe"](_m, {"start": [6 + _i, 1], "end": [6 + _i, 6], "storey": _storeys[0]})
_m.write(IFC)

# --- energy (envelope, real geometry) ---------------------------------------
e = energy.analyze_file(IFC)
assert e["areas_m2"]["exterior_wall_net"] > 0 and e["areas_m2"]["window"] > 0, e["areas_m2"]
assert e["ua_w_per_k"]["total"] > 0 and e["loads"]["design_heating_kw"] > 0
assert 20 < e["eui_kwh_m2_yr"] < 400, e["eui_kwh_m2_yr"]  # plausible building EUI

# override a U-value and confirm the model responds (better wall → lower load)
e2 = energy.analyze_file(IFC, {"u_wall": 0.1})
assert e2["ua_w_per_k"]["wall"] < e["ua_w_per_k"]["wall"]

# --- MEP inventory (deduplicated) -------------------------------------------
mep = energy.mep_inventory(open_model(IFC))
assert mep["total_distribution_elements"] == 7, mep

# --- IfcSpace authoring -> room schedule ------------------------------------
_SPACES_OUT = os.path.join(_DIR, "_test_spaces.ifc")
r = edit.apply_recipe(IFC, "add_spaces", {"rooms_per_storey": 4, "ceiling_height": 2.7},
                      _SPACES_OUT)
assert r["changed"] == 8, r
m = open_model(_SPACES_OUT)
assert len(m.by_type("IfcSpace")) == 8
sch = spaces.space_schedule(m)
assert len(sch) == 8 and all(s["net_area"] and s["storey"] for s in sch), sch[:2]
# regression (2026-08-02): add_spaces authored a Position-LESS rectangle profile — the one recipe
# that did. ifcopenshell tolerates it, but web-ifc silently skips such elements, so every authored
# room was invisible in the viewer. Assert the profile carries a placement like every other recipe.
for _sp in m.by_type("IfcSpace"):
    for _rep in _sp.Representation.Representations:
        for _it in (_rep.Items or []):
            if _it.is_a("IfcExtrudedAreaSolid") and _it.SweptArea.is_a("IfcRectangleProfileDef"):
                assert _it.SweptArea.Position is not None, "space profile lost its Position (web-ifc skips it)"


os.remove(_SPACES_OUT)

# --- Primavera P6 .xer schedule import (TASK table → dated activities) -------
from aec_data import schedule  # noqa: E402

_xer = "\n".join([
    "\t".join(["%T", "TASK"]),
    "\t".join(["%F", "task_id", "task_code", "task_name", "target_start_date", "target_end_date"]),
    "\t".join(["%R", "1", "A1010", "Foundations", "2026-03-01 08:00", "2026-03-20 17:00"]),
    "\t".join(["%R", "2", "A1020", "Superstructure", "2026-03-21 08:00", "2026-05-15 17:00"]),
    "\t".join(["%T", "PROJWBS"]), "\t".join(["%F", "wbs_id", "wbs_name"]), "\t".join(["%R", "9", "skip"]),
])
xrows = schedule.parse_xer(_xer)
assert len(xrows) == 2, xrows                                   # only the TASK table, PROJWBS ignored
assert xrows[0] == {"activity_id": "A1010", "name": "Foundations", "start": "2026-03-01", "finish": "2026-03-20"}, xrows[0]
assert xrows[1]["name"] == "Superstructure" and xrows[1]["finish"] == "2026-05-15"

print("ANALYSIS OK")
print(f"  energy: EUI {e['eui_kwh_m2_yr']} kWh/m2.yr | heating {e['loads']['design_heating_kw']} kW | UA {e['ua_w_per_k']['total']} W/K")
print(f"  mep: {mep['total_distribution_elements']} distribution elements")
print(f"  spaces authored: {r['changed']} ({sch[0]['net_area']} m2/room on {sch[0]['storey']})")
print(f"  P6 .xer import: {len(xrows)} activities ({xrows[0]['activity_id']} {xrows[0]['start']} - {xrows[0]['finish']})")
