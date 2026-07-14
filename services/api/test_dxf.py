"""W11 C6 DXF export: plan/section/elevation linework serialises to valid R12 DXF (POLYLINE entities),
in world coordinates so off-origin geometry lands correctly.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_dxf.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, dxf, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _x_coords(dxf_text: str) -> list[str]:
    """Every vertex X value (the token after a `10` group code) in the DXF."""
    lines = dxf_text.split("\n")
    return [lines[i + 1] for i in range(len(lines) - 1) if lines[i] == "10"]

# --- the raw serialiser: well-formed R12, closed-loop detection ------------------------------------
square = [[0, 0], [4, 0], [4, 3], [0, 3], [0, 0]]          # first == last → closed
open_line = [[0, 0], [5, 5]]
d = dxf.polylines_to_dxf([square, open_line], layer="TEST")
assert d.startswith("0\nSECTION\n2\nENTITIES\n") and d.rstrip().endswith("EOF"), "DXF envelope"
assert d.count("\nPOLYLINE\n") == 2 and d.count("\nSEQEND\n") == 2, "two polylines"
assert d.count("\nVERTEX\n") == 7, "5 + 2 vertices"
# closed flag (70=1) present for the square, open (70=0) for the line
assert "70\n1\n" in d and "70\n0\n" in d, "closed + open flags"
# degenerate polylines are skipped, never emitted
assert dxf.polylines_to_dxf([[[1, 1]], []]).count("POLYLINE") == 0, "single-point / empty skipped"

# --- from a model, off the origin (world-coord correctness) ----------------------------------------
TMP = os.path.join(os.path.dirname(__file__), "_dxf_test.ifc")
massing.generate_blank_ifc(TMP, name="DXF Test", storeys=1, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [10, 5], [18, 5], 3.0, 0.2, st)          # placed away from the origin

plan = drawings.plan_dxf(m, 0.0, 1.2)
assert "\nPOLYLINE\n" in plan and plan.rstrip().endswith("EOF"), "plan DXF has geometry"
assert "8\nPLAN\n" in plan, "plan layer"
# world placement: some vertex X sits out near the wall (x≈10–18), not collapsed at the origin
xs = [float(v) for v in _x_coords(plan)]
assert any(x > 8.0 for x in xs), f"plan linework should be world-placed, got max X {max(xs, default=0)}"

sec = drawings.section_dxf(m, "x")                         # auto-centred
assert "8\nSECTION\n" in sec and sec.rstrip().endswith("EOF"), "section DXF"

elev = drawings.elevation_dxf(m, "north")
assert "8\nELEVATION\n" in elev and "70\n1\n" in elev, "elevation DXF (closed silhouettes)"

if os.path.exists(TMP):
    os.remove(TMP)

print("DXF OK - polylines_to_dxf emits well-formed R12 (POLYLINE/VERTEX/SEQEND, closed-loop flag, skips "
      "degenerate), and plan/section/elevation export world-placed linework on named layers.")
