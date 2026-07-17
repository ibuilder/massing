"""TAKEOFF-2D: measure + price regions traced on a 2D drawing (PDF/scan) — the drawings-only takeoff that
feeds the same 5D estimate. Pure geometry (shoelace area, polyline length) + assembly rates.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_takeoff2d.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import takeoff2d as T  # noqa: E402

# --- geometry: shoelace area + polyline length -------------------------------------------------------
sq = [[0, 0], [100, 0], [100, 100], [0, 100]]        # a 100×100 px square
assert T.polygon_area_px2(sq) == 10000.0, T.polygon_area_px2(sq)
assert T.polygon_area_px2(list(reversed(sq))) == 10000.0, "winding-independent (absolute)"
assert T.polygon_area_px2([[0, 0], [1, 1]]) == 0.0, "a degenerate polygon has no area"
tri = [[0, 0], [10, 0], [0, 10]]
assert T.polygon_area_px2(tri) == 50.0, T.polygon_area_px2(tri)
assert T.polyline_length_px([[0, 0], [3, 4]]) == 5.0, "3-4-5"
assert T.polyline_length_px([[0, 0], [3, 4], [3, 4]]) == 5.0, "zero-length last segment"

# --- calibration: real units per pixel from two points + a known distance ----------------------------
# 100 px span = 5.0 m in the real world -> 0.05 m/px
scale = T.calibration_scale([0, 0], [100, 0], 5.0)
assert abs(scale - 0.05) < 1e-9, scale
assert T.calibration_scale([0, 0], [0, 0], 5.0) == 0.0, "coincident calibration points -> 0 (guarded)"

# --- quantify: a 100×100 px slab at 0.05 m/px = 5×5 m = 25 m² -----------------------------------------
regions = [
    {"category": "floor_slab", "points": sq, "label": "Level 1 slab"},
    {"category": "wall_linear", "points": [[0, 0], [100, 0], [100, 100]]},   # 200 px = 10 m of wall
]
r = T.quantify(regions, 0.05, unit="m")
assert r["region_count"] == 2, r["region_count"]
slab = next(x for x in r["regions"] if x["category"] == "floor_slab")
assert slab["quantity"] == 25.0 and slab["unit"] == "m²", slab          # 100² px² × 0.05² = 25 m²
assert slab["cost"] == round(25.0 * 130.0, 2), slab                     # floor_slab rate 130/m²
wall = next(x for x in r["regions"] if x["category"] == "wall_linear")
assert wall["measure"] == "length" and wall["quantity"] == 10.0, wall   # 200 px × 0.05 = 10 m
assert wall["cost"] == round(10.0 * 210.0, 2), wall                     # wall_linear 210/m
assert r["total_cost"] == round(25.0 * 130.0 + 10.0 * 210.0, 2), r["total_cost"]

# by-assembly rollup + sorted by cost desc
assert len(r["by_assembly"]) == 2 and r["by_assembly"][0]["cost"] >= r["by_assembly"][1]["cost"]

# --- rate override (project vintage) + unknown category falls back to generic_area -------------------
ro = T.quantify([{"category": "floor_slab", "points": sq}], 0.05, overrides={"floor_slab": 200.0})
assert ro["regions"][0]["cost"] == round(25.0 * 200.0, 2), "override rate applied"
unknown = T.quantify([{"category": "not_a_real_category", "points": sq}], 0.05)
assert unknown["regions"][0]["category"] == "not_a_real_category"
assert unknown["regions"][0]["assembly"] == T.TAKEOFF_ASSEMBLIES["generic_area"][2], "unknown → generic area"

# a different calibration scales the area by the square of the ratio (0.10 m/px → 4× the 0.05 area)
r2 = T.quantify([{"category": "floor_slab", "points": sq}], 0.10)
assert abs(r2["regions"][0]["quantity"] - 100.0) < 1e-6, r2["regions"][0]["quantity"]

# empty regions → a clean zero result
empty = T.quantify([], 0.05)
assert empty["region_count"] == 0 and empty["total_cost"] == 0.0, empty
assert empty["assemblies"], "the assembly catalog is always returned for the UI"

print("TAKEOFF-2D OK - shoelace area (winding-independent) + polyline length in pixels; a two-point "
      "calibration gives real units/px; quantify() converts each traced region to a real area (×scale²) or "
      "length (×scale), prices it at the assembly rate (overridable per project vintage), rolls up by "
      "assembly sorted by cost, and totals — a 100×100 px slab at 0.05 m/px = 25 m² @ $130 = $3,250; unknown "
      "categories fall back to a generic area; empty input is a clean zero.")
