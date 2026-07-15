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

if os.path.exists(TMP):
    os.remove(TMP)

print("PRODUCTIVITY OK - the rate catalog groups activities by trade w/ loading factors; labor_estimate "
      "computes man-hours (qty×mh×loading) + crew-days + cost (100 m² masonry → 130 mh → $3,900 at $30/hr), "
      "highrise loading inflates hours, unknown/zero lines skipped; from_model derives a rough takeoff "
      "(2 walls → ~45 m² masonry, slab → concrete casting) straight from element dimensions.")
