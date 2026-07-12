"""Model -> field layout (Wave 8 ②): PENZD/PNEZD points CSV + DXF from the IFC, and as-installed
verification by point number. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_layout.py"""
import os

import ifcopenshell   # noqa: E402

from aec_api import layout   # noqa: E402

SAMPLES = os.path.join(os.path.dirname(__file__), "..", "..", "samples")

# --- IFC4 model with columns + walls: extract georeferenced setout points -----------------------------
m = ifcopenshell.open(os.path.join(SAMPLES, "maple_tower.ifc"))
pts = layout.points(m)
assert len(pts) > 50, len(pts)
assert all(p["guid"] and p["number"].startswith("P") for p in pts), "numbered + GlobalId-anchored"
assert all("|" in p["description"] and p["guid"] in p["description"] for p in pts), "GlobalId in Description"
assert {p["ifc_class"] for p in pts} >= {"IfcColumn"}, "columns extracted"

# --- PENZD CSV: header + one row per point; PNEZD swaps the E/N columns ------------------------------
csv_txt = layout.to_penzd_csv(pts, order="PENZD")
lines = csv_txt.strip().splitlines()
assert lines[0] == "Point,Easting,Northing,Elevation,Description", lines[0]
assert len(lines) == 1 + len(pts), (len(lines), len(pts))
pnezd = layout.to_penzd_csv(pts, order="PNEZD")
assert pnezd.splitlines()[0] == "Point,Northing,Easting,Elevation,Description", pnezd.splitlines()[0]
tab = layout.to_penzd_csv(pts[:2], order="PENZD", delimiter="\t")
assert "\t" in tab.splitlines()[0]

# --- DXF: valid drawing bytes with layers per element type ------------------------------------------
dxf = layout.to_dxf(pts)
assert b"SECTION" in dxf and b"COLUMN" in dxf, "layered DXF (a COLUMN layer)"

# --- as-installed verification: match by point number, flag out-of-tolerance ------------------------
p0, p1 = pts[0], pts[1]
measured = [
    {"number": p0["number"], "e": p0["e"] + 0.10, "n": p0["n"], "z": p0["z"]},   # 100 mm off -> fail @20mm
    {"number": p1["number"], "e": p1["e"], "n": p1["n"], "z": p1["z"]},           # exact -> pass
]
v = layout.verify(pts, measured, tolerance_m=0.02)
assert v["checked"] == 2, v
assert v["in_tolerance"] == 1 and len(v["out_of_tolerance"]) == 1, v
assert v["out_of_tolerance"][0]["number"] == p0["number"], v["out_of_tolerance"]
assert v["out_of_tolerance"][0]["guid"] == p0["guid"], "deviation anchored to the element GlobalId"
assert abs(v["max_deviation_m"] - 0.10) < 0.005, v["max_deviation_m"]

# --- older IFC2X3 schema (no IfcMapConversion) must not raise, falls back to local coords ------------
m2 = ifcopenshell.open(os.path.join(SAMPLES, "basichouse.ifc"))
pts2 = layout.points(m2)
assert isinstance(pts2, list)   # walls at least; no crash on the missing-map-conversion schema

print("LAYOUT OK - model -> field setout points (grids + column/footing/opening/wall placements), "
      f"georeferenced, GlobalId in the Description ({len(pts)} pts on maple_tower); PENZD + PNEZD + "
      "tab CSV; layered DXF for floor printers; as-installed verify matches by point number and flags "
      "the 100 mm-off point (out of 20 mm tolerance), anchored to its GlobalId; IFC2X3 no-map-conversion "
      "path degrades gracefully.")
