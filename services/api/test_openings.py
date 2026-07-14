"""W11 B2 parametric door/window generators: author a wall, then add a parametric door + window whose
fill geometry comes from IfcOpenShell's built-in generators (real lining/frame/panels — a LOD 300→350
jump over the single box proxy). Verifies the void+fill relations and the box-proxy fallback.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_openings.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _fill_items(model, guid):
    el = model.by_guid(guid)
    reps = el.Representation.Representations if el.Representation else []
    return sum(len(r.Items) for r in reps)


TMP = os.path.join(os.path.dirname(__file__), "_openings_test.ifc")
massing.generate_blank_ifc(TMP, name="Openings Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
wall = edit.add_wall(m, [0, 0], [6, 0], 3.0, 0.2, st)

# --- parametric door: real lining + panel geometry (multi-item), voids the host, fills the opening ---
door = edit.add_opening(m, wall, width=0.9, height=2.1, kind="door", operation="SINGLE_SWING_LEFT")
d = m.by_guid(door)
assert d.is_a() == "IfcDoor", d
# parametric generator yields MANY geometry items (lining/panel/…), not the single box proxy
assert _fill_items(m, door) >= 3, f"door not parametric (items={_fill_items(m, door)})"
# host is voided (IfcRelVoidsElement) and the door fills the opening (IfcRelFillsElement)
assert m.by_type("IfcRelVoidsElement"), "no IfcRelVoidsElement — host not cut"
fills = m.by_type("IfcRelFillsElement")
assert any(f.RelatedBuildingElement == d for f in fills), "door does not fill an opening"

# --- parametric window: multi-panel lining/frame -----------------------------------------------------
win = edit.add_opening(m, wall, width=1.5, height=1.2, sill=0.9, kind="window", operation="SINGLE_PANEL")
w = m.by_guid(win)
assert w.is_a() == "IfcWindow", w
assert _fill_items(m, win) >= 2, f"window not parametric (items={_fill_items(m, win)})"
assert any(f.RelatedBuildingElement == w for f in m.by_type("IfcRelFillsElement")), "window does not fill an opening"

# --- fallback: parametric=False gives the simple 1-item box proxy (authoring never breaks) -----------
door2 = edit.add_opening(m, wall, width=0.8, height=2.0, kind="door", parametric=False)
assert _fill_items(m, door2) == 1, f"proxy should be a single item, got {_fill_items(m, door2)}"

# --- recipe path threads the operation type through /edit --------------------------------------------
OUT = os.path.join(os.path.dirname(__file__), "_openings_out.ifc")
res = edit.apply_recipe(TMP, "add_door",
                        {"host_guid": wall, "width": 1.8, "operation": "DOUBLE_DOOR_SINGLE_SWING"}, OUT)
mo = open_model(OUT)
assert res["changed"] and mo.by_guid(res["changed"]).is_a() == "IfcDoor"
assert _fill_items(mo, res["changed"]) >= 3, "recipe door not parametric"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("OPENINGS OK - parametric door (SINGLE_SWING_LEFT) + window (SINGLE_PANEL) get real "
      "lining/frame/panel geometry (multi-item reps) from IfcOpenShell generators; host voided "
      "(IfcRelVoidsElement) + fill related (IfcRelFillsElement); parametric=False falls back to the "
      "1-item box proxy; add_door recipe threads the operation type (DOUBLE_DOOR_SINGLE_SWING).")
