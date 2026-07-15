"""EST-1 productivity-rate library: man-hours/unit → labour hours + crew-days + cost, with loading factors;
plus a rough model-driven takeoff from element dimensions.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_productivity.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing, productivity  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# --- the catalog groups activities by trade + carries loading factors ------------------------------
cat = productivity.catalog()
assert "Concrete" in cat["groups"] and "MEP" in cat["groups"] and "Finishes" in cat["groups"], cat["groups"].keys()
assert cat["loading_factors"]["standard"] == 1.0 and cat["loading_factors"]["highrise"] > 1.0

# --- labor_estimate: hours = qty × mh × loading; cost = hours × rate -------------------------------
items = [{"activity": "block_masonry", "quantity": 100},   # 100 m² × 1.3 mh = 130 mh (standard)
         {"activity": "rc_casting", "quantity": 10}]        # 10 m³ × 10 mh = 100 mh
e = productivity.labor_estimate(items, hourly_rate=30.0, loading="standard")
assert e["loading_factor"] == 1.0 and e["line_count"] == 2, e
masonry = next(x for x in e["lines"] if x["activity"] == "block_masonry")
assert abs(masonry["man_hours"] - 130.0) < 0.1, masonry
assert abs(masonry["labor_cost"] - 130.0 * 30.0) < 0.1, masonry
assert masonry["crew_days"] > 0, masonry
assert abs(e["total_man_hours"] - 230.0) < 0.1 and abs(e["total_labor_cost"] - 230.0 * 30.0) < 0.1, e
# highrise loading inflates the hours
eh = productivity.labor_estimate(items, hourly_rate=30.0, loading="highrise")
assert eh["total_man_hours"] > e["total_man_hours"], (eh["total_man_hours"], e["total_man_hours"])
# unknown activity + zero qty are skipped
assert productivity.labor_estimate([{"activity": "teleport", "quantity": 5},
                                    {"activity": "painting", "quantity": 0}])["line_count"] == 0

# --- full_estimate: labour + material + equipment ---------------------------------------------------
fe = productivity.full_estimate(items, hourly_rate=30.0, loading="standard")
assert fe["has_material_equipment"] is True, fe
# labour total is unchanged from labor_estimate; material + equipment are added on top
assert abs(fe["total_labor_cost"] - e["total_labor_cost"]) < 0.1, (fe["total_labor_cost"], e["total_labor_cost"])
# rc_casting: 10 m³ × $130/m³ material = $1,300; × $15/m³ equipment = $150
cast = next(x for x in fe["lines"] if x["activity"] == "rc_casting")
assert abs(cast["material_cost"] - 1300.0) < 0.1, cast
assert abs(cast["equipment_cost"] - 150.0) < 0.1, cast
assert abs(cast["line_total"] - (cast["labor_cost"] + 1300.0 + 150.0)) < 0.1, cast
# block_masonry: 100 m² × $30/m² material = $3,000; no equipment key → $0
mas2 = next(x for x in fe["lines"] if x["activity"] == "block_masonry")
assert abs(mas2["material_cost"] - 3000.0) < 0.1 and mas2["equipment_cost"] == 0.0, mas2
assert abs(fe["total_material_cost"] - (1300.0 + 3000.0)) < 0.1, fe["total_material_cost"]
assert abs(fe["total_equipment_cost"] - 150.0) < 0.1, fe["total_equipment_cost"]
assert abs(fe["total_cost"] - (fe["total_labor_cost"] + fe["total_material_cost"] + fe["total_equipment_cost"])) < 0.1, fe
# the catalog now carries material/equipment $/unit
conc = next(a for a in cat["groups"]["Concrete"] if a["activity"] == "rc_casting")
assert conc["material_cost_per_unit"] == 130.0 and conc["equipment_cost_per_unit"] == 15.0, conc

# --- model-driven takeoff: walls → masonry area, slab → concrete -----------------------------------
TMP = os.path.join(os.path.dirname(__file__), "_prod_test.ifc")
massing.generate_blank_ifc(TMP, name="Prod Test", storeys=1, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [10, 0], 3.0, 0.2, st)            # 10 m × 3 m = 30 m² masonry
edit.add_wall(m, [10, 0], [10, 5], 3.0, 0.2, st)           # 5 m × 3 m = 15 m² masonry
edit.add_slab(m, [[0, 0], [10, 0], [10, 5], [0, 5]], thickness=0.2, storey=st)

fm = productivity.from_model(m, hourly_rate=25.0, loading="commercial")
assert fm["derived_from_model"] and fm["total_man_hours"] > 0, fm
mas = next((x for x in fm["lines"] if x["activity"] == "block_masonry"), None)
assert mas is not None and mas["quantity"] > 40, mas   # ~45 m² of wall face, × commercial loading
assert any(x["activity"] == "rc_casting" for x in fm["lines"]), "slab → concrete casting"
# full model estimate adds material + equipment on top of the same labour
fmf = productivity.from_model(m, hourly_rate=25.0, loading="commercial", full=True)
assert fmf["has_material_equipment"] and fmf["total_cost"] > fmf["total_labor_cost"], fmf
assert fmf["total_material_cost"] > 0 and abs(fmf["total_labor_cost"] - fm["total_labor_cost"]) < 0.1, fmf

if os.path.exists(TMP):
    os.remove(TMP)

print("PRODUCTIVITY OK - the rate catalog groups activities by trade w/ loading factors; labor_estimate "
      "computes man-hours (qty×mh×loading) + crew-days + cost (100 m² masonry → 130 mh → $3,900 at $30/hr), "
      "highrise loading inflates hours, unknown/zero lines skipped; from_model derives a rough takeoff "
      "(2 walls → ~45 m² masonry, slab → concrete casting) straight from element dimensions.")
