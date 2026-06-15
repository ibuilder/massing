"""Energy + MEP + IfcSpace authoring test (offline, uses samples/basichouse.ifc).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_analysis.py"""
import warnings

warnings.filterwarnings("ignore")

from aec_data import edit, energy, spaces  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

IFC = "../../samples/basichouse.ifc"

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
r = edit.apply_recipe(IFC, "add_spaces", {"rooms_per_storey": 4, "ceiling_height": 2.7},
                      "../../samples/_test_spaces.ifc")
assert r["changed"] == 8, r
m = open_model("../../samples/_test_spaces.ifc")
assert len(m.by_type("IfcSpace")) == 8
sch = spaces.space_schedule(m)
assert len(sch) == 8 and all(s["net_area"] and s["storey"] for s in sch), sch[:2]

import os  # noqa: E402
os.remove("../../samples/_test_spaces.ifc")

print("ANALYSIS OK")
print(f"  energy: EUI {e['eui_kwh_m2_yr']} kWh/m2.yr | heating {e['loads']['design_heating_kw']} kW | UA {e['ua_w_per_k']['total']} W/K")
print(f"  mep: {mep['total_distribution_elements']} distribution elements")
print(f"  spaces authored: {r['changed']} ({sch[0]['net_area']} m2/room on {sch[0]['storey']})")
