"""W11 selector query DSL: run IfcOpenShell selector queries over a model (class, multi-class, pset
filters) and return matched elements. Foundational power-selection primitive.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_selector.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_selector_test.ifc")
massing.generate_blank_ifc(TMP, name="Selector Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
w1 = edit.add_wall(m, [0, 0], [5, 0], 3.0, 0.2, st)
edit.add_wall(m, [5, 0], [5, 5], 3.0, 0.2, st)
c1 = edit.add_column(m, [2, 2], 3.0, 0.4, 0.4, st)

# single class
r = edit.query_elements(m, "IfcWall")
assert r["count"] == 2 and {e["ifc_class"] for e in r["elements"]} == {"IfcWall"}, r

# multi-class union
r2 = edit.query_elements(m, "IfcWall, IfcColumn")
assert r2["count"] == 3, r2
assert w1 in {e["guid"] for e in r2["elements"]} and c1 in {e["guid"] for e in r2["elements"]}

# rows carry storey + name
assert all(e["storey"] == st for e in r2["elements"]), r2["elements"]

# pset value filter: tag one wall then query by it (selector filters by pset property value)
edit.set_element_pset(m, w1, "Pset_WallCommon", "FireRating", "2HR", "str")
rp = edit.query_elements(m, "IfcWall, Pset_WallCommon.FireRating=2HR")
assert rp["count"] == 1 and rp["elements"][0]["guid"] == w1, rp

# limit + truncation flag
rl = edit.query_elements(m, "IfcWall", limit=1)
assert len(rl["elements"]) == 1 and rl["count"] == 2 and rl["truncated"] is True, rl

# invalid syntax raises ValueError (surfaced as 400)
try:
    edit.query_elements(m, "!!not a query!!")
    raised = False
except ValueError:
    raised = True
assert raised, "invalid selector query should raise ValueError"

# empty query rejected
try:
    edit.query_elements(m, "   ")
    raised2 = False
except ValueError:
    raised2 = True
assert raised2

if os.path.exists(TMP):
    os.remove(TMP)

print("SELECTOR OK - query_elements runs the IfcOpenShell selector DSL: single class (2 walls), "
      "multi-class union (2 walls + 1 column), pset value filter (FireRating=2HR -> 1), rows carry "
      "name/class/storey, limit truncation flag, and invalid/empty queries raise ValueError (400).")
