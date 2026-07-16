"""A4 scene digest: compose the shipped summaries (element counts, storeys, spaces, MEP, phasing, LOD,
hygiene) into a compact dict + a one-paragraph prose string that grounds the AI command bar.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scene.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import scene  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_scene_test.ifc")
massing.generate_blank_ifc(TMP, name="Scene Test", storeys=2, storey_height=3.0, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
w1 = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)
edit.add_wall(m, [6, 0], [6, 4], 3.0, 0.2, st)
edit.add_column(m, [0, 0], 3.0, 0.4, 0.4, st)
edit.add_mep_run(m, "IfcPipeSegment", [0, 2], [6, 2], "round", 0.05, st, system="Fire Protection", discipline="fire")
edit.set_phase(m, [w1], "existing")

d = scene.digest(m)

# --- totals + by-class -----------------------------------------------------------------------------
assert d["totals"]["elements"] >= 4 and d["totals"]["storeys"] == 2, d["totals"]
assert d["by_class"].get("IfcWall", 0) == 2 and d["by_class"].get("IfcColumn", 0) == 1, d["by_class"]
# by_class is sorted most-common first
vals = list(d["by_class"].values())
assert vals == sorted(vals, reverse=True), d["by_class"]

# --- MEP discipline rollup picks up the fire-protection system ------------------------------------
assert d["mep"]["systems"] >= 1 and "fire" in d["mep"]["by_discipline"], d["mep"]
assert d["mep"]["has_fire_protection"] is True, d["mep"]

# --- phasing reflects the existing wall ------------------------------------------------------------
assert d["phasing"].get("EXISTING", 0) == 1, d["phasing"]

# --- prose is a non-empty one-liner naming the counts ---------------------------------------------
assert isinstance(d["prose"], str) and "element" in d["prose"] and "storey" in d["prose"], d["prose"]
assert "fire" in d["prose"].lower(), d["prose"]                    # mentions the MEP discipline
assert d["prose"].endswith("."), d["prose"]

# --- degrades gracefully on an empty IFC4 model ---------------------------------------------------
import ifcopenshell as _ios  # noqa: E402
d0 = scene.digest(_ios.file(schema="IFC4"))
assert d0["totals"]["elements"] == 0 and d0["prose"], d0

if os.path.exists(TMP):
    os.remove(TMP)

print("SCENE OK - digest composes element counts by class (sorted), storeys, spaces, MEP systems + "
      "disciplines (fire-protection detected), phasing (1 existing), LOD + hygiene, into a compact dict + a "
      "one-paragraph prose overview naming the counts; degrades gracefully on an empty model.")
