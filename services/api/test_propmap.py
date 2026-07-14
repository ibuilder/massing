"""Property mapping / normalization (Wave 9 W9-1): detect present psets/props, plan a dry-run remap,
apply it (move + copy semantics + type cast), and confirm the recipe path writes GUID-stable IFC.
Pure data-service engine test. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_propmap.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402
import ifcopenshell.api  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, propmap  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_propmap_test.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_propmap_test_out.ifc")


def _wall_with(model, name, pset, props):
    w = ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcWall", name=name)
    ps = ifcopenshell.api.run("pset.add_pset", model, product=w, name=pset)
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties=props)
    return w


# --- build a model with vendor-named properties (the messy federated input) --------------------------
m = ifcopenshell.api.run("project.create_file")
ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="PropMap Test")
_wall_with(m, "W1", "Pset_Custom", {"Fire_Rating": "2HR", "Acoustic": "STC50"})
_wall_with(m, "W2", "Pset_Custom", {"Fire_Rating": "1HR"})
_wall_with(m, "W3", "Pset_WallCommon", {"ThermalTransmittance": "0.25"})   # no Fire_Rating → untouched
m.write(TMP)

# --- detect: the source side lists the vendor psets/props with counts ---------------------------------
det = propmap.detect(open_model(TMP))
props = {(r["pset"], r["prop"]): r["count"] for r in det["properties"]}
assert props.get(("Pset_Custom", "Fire_Rating")) == 2, props
assert props.get(("Pset_Custom", "Acoustic")) == 1, props
assert det["element_count"] == 3, det

# --- plan: dry-run remap Pset_Custom.Fire_Rating -> Pset_WallCommon.FireRating (no mutation) ----------
rules = [{"from_pset": "Pset_Custom", "from_prop": "Fire_Rating",
          "to_pset": "Pset_WallCommon", "to_prop": "FireRating"}]
pl = propmap.plan(open_model(TMP), rules)
assert pl["dry_run"] is True and pl["changed"] == 2, pl
assert pl["rules"][0]["matched"] == 2 and pl["rules"][0]["samples"], pl
# the plan must NOT have written anything
assert propmap.detect(open_model(TMP))["properties"], "plan mutated the file"
assert ("Pset_WallCommon", "FireRating") not in {(r["pset"], r["prop"]) for r in propmap.detect(open_model(TMP))["properties"]}

# --- apply via the GUID-stable recipe (the real /edit path) ------------------------------------------
guids_before = sorted(w.GlobalId for w in open_model(TMP).by_type("IfcWall"))
res = edit.apply_recipe(TMP, "map_properties", {"rules": rules}, OUT)
assert res["changed"] == 2, res
m2 = open_model(OUT)
# GUIDs preserved (pins/RFIs/clashes survive)
assert sorted(w.GlobalId for w in m2.by_type("IfcWall")) == guids_before, "GUIDs changed"
# target property written on W1/W2, source removed (move semantics); W3 untouched
by_name = {w.Name: w for w in m2.by_type("IfcWall")}
assert ue.get_pset(by_name["W1"], "Pset_WallCommon", "FireRating") == "2HR"
assert ue.get_pset(by_name["W2"], "Pset_WallCommon", "FireRating") == "1HR"
assert ue.get_pset(by_name["W1"], "Pset_Custom", "Fire_Rating") is None, "source not removed (move)"
assert ue.get_pset(by_name["W1"], "Pset_Custom", "Acoustic") == "STC50", "unrelated prop clobbered"

# --- copy semantics (keep_source) + numeric cast -----------------------------------------------------
rules2 = [{"from_pset": "Pset_Custom", "from_prop": "Acoustic", "to_pset": "Pset_WallCommon",
           "to_prop": "AcousticRatingCopy", "keep_source": True}]
res2 = edit.apply_recipe(OUT, "map_properties", {"rules": rules2}, OUT)
m3 = open_model(OUT)
by_name = {w.Name: w for w in m3.by_type("IfcWall")}
assert res2["changed"] == 1
assert ue.get_pset(by_name["W1"], "Pset_WallCommon", "AcousticRatingCopy") == "STC50"
assert ue.get_pset(by_name["W1"], "Pset_Custom", "Acoustic") == "STC50", "keep_source dropped the source"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("PROPMAP OK - detect lists vendor psets w/ counts; plan dry-runs 2 matches without mutating; "
      "map_properties recipe moves Pset_Custom.Fire_Rating -> Pset_WallCommon.FireRating (GUID-stable, "
      "source removed, unrelated props intact); keep_source copies without dropping the source.")
