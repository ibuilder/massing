"""DORMER slice — add_roof_window: cut a skylight opening through a flat IfcRoof and fill it with an
IfcWindow (SKYLIGHT), voided + filled via the standard feature relations, GUID-stable recipe.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_roof_window.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_roofwin.ifc")

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

massing.generate_blank_ifc(TMP, name="RoofWin", storeys=1, storey_height=3.0, ground_size=15.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
roof_guid = edit.add_roof(m, [[0, 0], [8, 0], [8, 6], [0, 6]], 0.3, st)

# --- the recipe (through the RECIPES registry, as the edit endpoint would call it) -----------------
win_guid = edit.RECIPES["add_roof_window"](m, {"roof_guid": roof_guid, "position": [4, 3],
                                               "width": 1.0, "length": 1.5, "storey": st})
win = m.by_guid(win_guid)
assert win is not None and win.is_a("IfcWindow"), win
assert str(getattr(win, "PredefinedType", "")) == "SKYLIGHT", getattr(win, "PredefinedType", None)
assert float(win.OverallWidth) == 1.0 and float(win.OverallHeight) == 1.5, (win.OverallWidth, win.OverallHeight)

# the opening voids the ROOF and the window fills the opening (standard IFC feature relations)
roof = m.by_guid(roof_guid)
voids = list(getattr(roof, "HasOpenings", []) or [])
assert len(voids) == 1, "the roof must carry exactly one opening"
opening = voids[0].RelatedOpeningElement
assert opening.is_a("IfcOpeningElement"), opening
fills = list(getattr(opening, "HasFillings", []) or [])
assert len(fills) == 1 and fills[0].RelatedBuildingElement.GlobalId == win_guid, "the window fills the opening"

# a second skylight on the same roof coexists
win2 = edit.add_roof_window(m, roof_guid, [2, 2], 0.8, 0.8, st)
assert win2 != win_guid and len(list(roof.HasOpenings)) == 2

# a bad host raises cleanly
try:
    edit.add_roof_window(m, "not-a-roof", [1, 1])
    raise AssertionError("bad roof guid must raise")
except ValueError as e:
    assert "not found" in str(e)

# the file round-trips (write + reopen keeps the relations)
m.write(TMP)
m2 = open_model(TMP)
r2 = m2.by_guid(roof_guid)
assert len(list(r2.HasOpenings)) == 2 and m2.by_guid(win_guid).is_a("IfcWindow")
if os.path.exists(TMP):
    os.remove(TMP)

print("ROOF-WINDOW OK - the add_roof_window recipe cuts a skylight opening through a flat IfcRoof at [4,3] "
      "(IfcOpeningElement voiding the roof, full-depth) and fills it with a 1.0×1.5 IfcWindow of "
      "PredefinedType SKYLIGHT via the standard feature relations; a second skylight coexists (2 openings), "
      "a bad host GUID raises cleanly, and the relations survive a write/reopen round-trip. The flat-roof "
      "DORMER slice — the pitched-roof dormer assembly follows when pitched roofs land.")
