"""Regression: authoring recipes must produce correct real-world sizes on a NON-METRE (millimetre) model
(the common case for imported IFCs). Profile dims must be authored in file units (metres / unit_scale),
else a wall/column/beam is 1000x too thin. Also guards the egress door-width fix (reads OverallWidth).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_unit_scale.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.util.unit as uu  # noqa: E402

from aec_api import codecheck as cc  # noqa: E402
from aec_data import edit, massing, rebar  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _first_solid(el):
    for r in (el.Representation.Representations if el.Representation else []):
        for it in (r.Items or []):
            if it.is_a("IfcExtrudedAreaSolid"):
                return it
    return None


TMP = os.path.join(os.path.dirname(__file__), "_unit_test.ifc")
massing.generate_blank_ifc(TMP, name="MM", storeys=1, storey_height=3.0, ground_size=10.0)
m = open_model(TMP)
# force MILLIMETRE length unit — as an imported mm IFC would be — so new authoring uses scale=0.001
for u in m.by_type("IfcSIUnit"):
    if u.UnitType == "LENGTHUNIT":
        u.Prefix = "MILLI"
scale = uu.calculate_unit_scale(m)
assert abs(scale - 0.001) < 1e-9, scale
st = m.by_type("IfcBuildingStorey")[0].Name


def real(v):                       # file units -> metres
    return float(v) * scale


# --- rectangular column 0.4 x 0.4 m: profile must read 0.4 m REAL, not 0.4 mm ---------------------
col = edit.add_column(m, [3, 3], 3.0, 0.4, 0.4, st)
sol = _first_solid(m.by_guid(col))
assert abs(real(sol.SweptArea.XDim) - 0.4) < 1e-4, f"column {real(sol.SweptArea.XDim)} m (want 0.4)"
assert abs(real(sol.Depth) - 3.0) < 1e-3, real(sol.Depth)

# --- wall (via _rect_profile) --------------------------------------------------------------------
wall = edit.add_wall(m, [0, 0], [5, 0], 3.0, 0.25, st)
ws = _first_solid(m.by_guid(wall))
assert abs(real(ws.SweptArea.YDim) - 0.25) < 1e-4, f"wall thickness {real(ws.SweptArea.YDim)} (want 0.25)"

# --- steel column (native W-shape i_profile) -----------------------------------------------------
from aec_data import steel  # noqa: E402

scol = edit.add_steel_column(m, [6, 6], 3.0, "W12x26", st)
iso = _first_solid(m.by_guid(scol))
bf = steel.section_dims_m("W12x26")["bf"]
assert abs(real(iso.SweptArea.OverallWidth) - bf) < 1e-4, f"W-shape bf {real(iso.SweptArea.OverallWidth)} want {bf}"

# --- MEP round duct (inline circle profile) ------------------------------------------------------
duct = edit.add_mep_run(m, "IfcDuctSegment", [0, 5], [4, 5], "round", 0.3, st)
ds = _first_solid(m.by_guid(duct))
assert abs(real(ds.SweptArea.Radius) - 0.15) < 1e-4, f"duct radius {real(ds.SweptArea.Radius)} want 0.15"

# --- slab (polyline profile coords) --------------------------------------------------------------
slab = edit.add_slab(m, [[0, 0], [4, 0], [4, 3], [0, 3]], 0.2, st)
ss = _first_solid(m.by_guid(slab))
xs = [real(p.Coordinates[0]) for p in ss.SweptArea.OuterCurve.Points]
assert abs(max(xs) - 4.0) < 1e-3, f"slab span {max(xs)} m (want 4.0)"

# --- rebar cage must NOT crash on a mm model (bug #2 was a hard fail here) ------------------------
cage = rebar.add_rebar_cage(m, col, bar_size="#8", tie_size="#3", cover=0.04, tie_spacing=0.3)
assert cage["bars"] == 4, cage
bar0 = next(b for b in m.by_type("IfcReinforcingBar") if b.Name == "Rebar")
solid = bar0.Representation.Representations[0].Items[0]
assert abs(real(solid.Radius) * 2 - steel.rebar_diameter("#8")) < 1e-4, "rebar diameter wrong on mm model"

# --- egress door-width fix: OverallWidth is read (was Pset_DoorCommon.Width → always 0) ------------
m2path = os.path.join(os.path.dirname(__file__), "_unit_test2.ifc")
massing.generate_blank_ifc(m2path, name="Egress", storeys=1, storey_height=3.0, ground_size=20.0)
m2 = open_model(m2path)
st2 = m2.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(m2, rooms_per_storey=2, ceiling_height=3.0)
w2 = edit.add_wall(m2, [0, 0], [6, 0], 3.0, 0.2, st2)
edit.add_opening(m2, w2, width=0.9, height=2.1, kind="door")
eg = cc.egress_from_model(m2)
assert eg["doors"]["checked"] >= 1, f"door not counted: {eg['doors']}"
assert eg["egress"]["provided_width_in"] > 0, f"provided width still 0: {eg['egress']}"

for f in (TMP, m2path):
    if os.path.exists(f):
        os.remove(f)

print("UNIT-SCALE OK - on a MILLIMETRE model, authored column/wall/steel/duct/slab/rebar all carry correct "
      "REAL sizes (profile dims in file units, not raw metres); rebar cage no longer crashes on mm; egress "
      "now reads the door OverallWidth attribute so provided egress width > 0.")
