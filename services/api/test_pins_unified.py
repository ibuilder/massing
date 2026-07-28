"""
One meaning of "pin", whichever half of the product created it.

There were two ways to attach an issue to the model. A Topic carried an anchor and showed in the
viewer. A register record — the RFI with the workflow that reaches `closed` — carried element GUIDs
and showed nowhere: binding one to a wall returned `count: 1` and produced no pin. So a user could
track an issue to completion or see it on the model, never both.

The fix makes "pin" a view over both, with position DERIVED from the element rather than stored, so a
pin follows its element instead of pointing where the element used to be.
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_api import pins as pin_engine  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- what counts as spatial ------------------------------------------------------------------
check("an RFI is a place in the building", "rfi" in pin_engine.SPATIAL_MODULES)
check("so is a punch item", "punchlist" in pin_engine.SPATIAL_MODULES)
check("a change order is NOT — it is about the project, not a point",
      "change_order" not in pin_engine.SPATIAL_MODULES)
check("nor is a submittal", "submittal" not in pin_engine.SPATIAL_MODULES)

# --- located() is what stops a sheet under-reporting -------------------------------------------
rows = [
    {"label": "placed", "x": 1.0, "y": 2.0, "z": 0.5},
    {"label": "no position", "x": None, "y": None, "z": None},
    {"label": "half a position", "x": 3.0, "y": None, "z": 0.0},
]
loc = pin_engine.located(rows)
check("only fully-positioned pins are drawable", len(loc) == 1 and loc[0]["label"] == "placed")
check("the caller can still count what it could not place", len(rows) - len(loc) == 2,
      "a list that silently returns fewer pins than exist is the bug")

# --- the world-coordinate trap, asserted directly -----------------------------------------------
# `ifcopenshell.geom.settings()` defaults use-world-coords to FALSE, so verts come back in the
# element's local frame and every centroid lands near the origin — pins rendering confidently in the
# wrong place. Volume and area never noticed because they are placement-invariant. Position is not.
import ifcopenshell.geom as _g  # noqa: E402

_default = _g.settings()
check("the library default really is local coordinates", _default.get("use-world-coords") is False,
      "if this ever flips, the explicit set below becomes redundant, not wrong")

import inspect  # noqa: E402

from aec_data import qto  # noqa: E402

src = inspect.getsource(qto.element_centroids)
check("element_centroids sets world coords explicitly", 'set("use-world-coords", True)' in src,
      "without it a 12 m wall centres at the origin instead of at 6 m")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_pins_unified OK")
