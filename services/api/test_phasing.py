"""W10-8 element phasing: tag elements new/existing/demolish/temporary (Massing_Phasing.Status),
GUID-stable, and summarise the distribution. Also drives the set_phase recipe through apply_recipe.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_phasing.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_phasing_test.ifc")
massing.generate_blank_ifc(TMP, name="Phasing Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# author a few walls to phase
w1 = edit.add_wall(m, [0, 0], [5, 0], 3.0, 0.2, st)
w2 = edit.add_wall(m, [5, 0], [5, 5], 3.0, 0.2, st)
w3 = edit.add_wall(m, [5, 5], [0, 5], 3.0, 0.2, st)
guids = [w1, w2, w3]
assert all(guids), guids

# everything starts UNSET
s0 = edit.phase_summary(m)
assert s0["counts"]["UNSET"] == s0["total"] and s0["phased"] == 0, s0

# tag: w1 existing, w2 demolish, w3 stays new (default)
assert edit.set_phase(m, [w1], "existing") == 1
assert edit.set_phase(m, [w2], "demolish") == 1
assert edit.set_phase(m, [w3], "new") == 1

# the status Pset landed with the canonical code
assert ue.get_pset(m.by_guid(w1), "Massing_Phasing")["Status"] == "EXISTING"
assert ue.get_pset(m.by_guid(w2), "Massing_Phasing")["Status"] == "DEMOLISH"
assert ue.get_pset(m.by_guid(w3), "Massing_Phasing")["Status"] == "NEW"

s1 = edit.phase_summary(m)
assert s1["counts"]["EXISTING"] == 1 and s1["counts"]["DEMOLISH"] == 1 and s1["counts"]["NEW"] == 1, s1
assert s1["phased"] == 3, s1
assert s1["prop"] == "Massing_Phasing.Status"

# re-tagging changes the status in place (no duplicate pset) — GUID-stable
assert edit.set_phase(m, [w2], "temporary") == 1
assert ue.get_pset(m.by_guid(w2), "Massing_Phasing")["Status"] == "TEMPORARY"
assert sum(1 for r in (m.by_guid(w2).IsDefinedBy or [])
           if r.is_a("IfcRelDefinesByProperties")
           and r.RelatingPropertyDefinition.Name == "Massing_Phasing") == 1, "duplicate phasing pset"

# a stale GUID never aborts the batch
assert edit.set_phase(m, [w3, "NOTAGUID000000000000000"], "existing") == 1

# recipe path (the /edit route)
OUT = os.path.join(os.path.dirname(__file__), "_phasing_out.ifc")
r = edit.apply_recipe(TMP, "set_phase", {"guids": guids, "phase": "existing"}, OUT)
assert r["changed"] == 3, r
mo = open_model(OUT)
assert all(ue.get_pset(mo.by_guid(g), "Massing_Phasing")["Status"] == "EXISTING" for g in guids)

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("PHASING OK - set_phase stamps Massing_Phasing.Status (NEW/EXISTING/DEMOLISH/TEMPORARY) on "
      "elements GUID-stable; phase_summary counts by status (unset tracked); re-tagging updates in "
      "place (no duplicate pset); stale GUIDs skipped; set_phase recipe works via apply_recipe.")
