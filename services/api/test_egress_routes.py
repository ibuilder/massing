"""D2 — routed egress. The old check measured the wrong thing, and said so.

`geometric_rules.check_escape_distance` reports straight-line distance to an exit. IBC 1017 limits
travel distance measured *along the path of egress travel*. A straight line ignores every wall in the
way, so it is always shorter than the real route — which means the error runs in the unsafe
direction: it passes plans that do not comply. Reading the output carefully does not help, because
the number itself is the wrong measurement.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_egress_routes.py
"""
import math
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_egress_routes.db"
os.environ["STORAGE_DIR"] = "./test_storage_egress_routes"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_egress_routes.db"):
    os.remove("./test_egress_routes.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import numpy as np  # noqa: E402

from aec_api import egress_route as er  # noqa: E402

# ---- the routing core, on grids whose answers can be worked out by hand -------------------------
free = np.zeros((21, 21), dtype=bool)
dist, prev = er.distance_field(free, [(0, 0)], 0.5)
# 8-connected with a √2 diagonal: the corner-to-corner run is a pure diagonal
assert abs(float(dist[20, 20]) - 20 * 0.5 * math.sqrt(2)) < 1e-9, float(dist[20, 20])
assert abs(float(dist[20, 0]) - 20 * 0.5) < 1e-9, "a straight run is exactly its length"
# a 4-connected grid would have said 20 — overstating an open-floor diagonal by ~41%
assert float(dist[20, 20]) < 20 * 0.5 * 2

# THE POINT: a wall in the way makes the route longer than the straight line
blocked = np.zeros((40, 20), dtype=bool)
blocked[20, 0:15] = True                       # a stub wall leaving a gap at the top
d2, prev2 = er.distance_field(blocked, [(0, 0)], 0.5)
routed = float(d2[39, 0])
straight = 39 * 0.5
assert routed > straight, (routed, straight)
assert routed / straight > 1.3, "the detour must be materially longer, not marginally"

# a sealed region is UNREACHABLE, which is a different finding from "far away"
sealed = np.zeros((10, 10), dtype=bool)
sealed[5, :] = True
d3, _ = er.distance_field(sealed, [(0, 0)], 0.5)
assert math.isfinite(float(d3[4, 9])) and not math.isfinite(float(d3[9, 9]))

# the path traces back to the source and starts at the queried cell
path = er._path_from((39, 0), prev2, (0.0, 0.0), 0.5)
assert len(path) > 2 and path[0] == (round(39 * 0.5 + 0.25, 3), round(0.25, 3)), path[:2]
assert path[-1] == (0.25, 0.25), path[-1]        # ends at the exit cell
# no cycles — a predecessor chain that looped would hang or repeat
assert len(set(path)) == len(path), "the traced path must not revisit a cell"

# ---- a real model, end to end -------------------------------------------------------------------
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

PATH = os.path.join(os.path.dirname(__file__), "_egress_routes.ifc")
massing.generate_blank_ifc(PATH, name="Egress", storeys=1, storey_height=3.5, ground_size=40.0)
model = open_model(PATH)
storey = model.by_type("IfcBuildingStorey")[0].Name

# no exterior door yet: the engine must refuse rather than route to an arbitrary door
bare = er.analyze(model, elevation=0.0)
assert bare["routed"] is False and bare.get("exits", 0) == 0, bare
assert "IsExternal" in bare["note"], bare["note"]

# a spine wall with a single door at one end: anything on the far side must walk around to reach it
spine = edit.add_wall(model, [-15, 0], [10, 0], 3.0, 0.25, storey)
door = edit.add_opening(model, spine, width=1.0, height=2.1, kind="door", position=[9, 0])
edit.set_element_pset(model, door, "Pset_DoorCommon", "IsExternal", True, "bool")
edit.add_spaces(model, rooms_per_storey=4)

res = er.analyze(model, elevation=0.0, max_travel_m=61.0, cell=0.5)
assert res["routed"] is True, res.get("note")
assert res["exits"] == 1, res["exits"]
assert res["cell_m"] == 0.5 and res["max_travel_m"] == 61.0
assert "along the route" in res["note"].lower() and "0.5 m grid" in res["note"]
assert res["spaces"] == len(res["results"]) >= 1, res["spaces"]

# every space reports BOTH measurements, so the understatement is visible per space
for r in res["results"]:
    assert "straight_line_m" in r and "travel_m" in r and "unreachable" in r
    if not r["unreachable"]:
        # a route around obstacles can never be shorter than the straight line between the same
        # points (allowing one cell of rasterisation slack at each end)
        assert r["travel_m"] >= r["straight_line_m"] - 2 * res["cell_m"], r
        assert r["detour_ratio"] is None or r["detour_ratio"] >= 0.9, r
        assert r["path"] and len(r["path"]) >= 2, r
assert res["compliant"] + res["over_limit"] + res["unreachable"] == res["spaces"]

# at least one space sits behind the spine wall and must therefore detour
detours = [r["detour_ratio"] for r in res["results"]
           if not r["unreachable"] and r.get("detour_ratio")]
assert detours and max(detours) > 1.05, f"expected a real detour behind the wall, got {detours}"
assert res["max_detour_ratio"] == max(detours), res["max_detour_ratio"]

# a tighter limit turns compliant spaces into findings — the limit is genuinely a lever
tight = er.analyze(model, elevation=0.0, max_travel_m=1.0, cell=0.5)
assert tight["over_limit"] > res["over_limit"], (tight["over_limit"], res["over_limit"])
assert tight["compliant"] < res["compliant"] or res["compliant"] == 0

# ---- guard rails ---------------------------------------------------------------------------------
# an absurdly fine grid is refused with the cell count, not silently attempted
try:
    er.build_grid(model, 0.0, 1.2, cell=0.001)
    raise AssertionError("expected a refusal for a 1 mm grid")
except ValueError as e:
    assert "cells at" in str(e) and "larger `cell`" in str(e), str(e)

# the plan renders and states its approximation rather than implying precision
svg = er.plan_svg(model, elevation=0.0, max_travel_m=61.0, cell=0.5)
assert svg.lstrip().startswith(("<?xml", "<svg")) and svg.rstrip().endswith("</svg>")
if res["routed"]:
    assert "EGRESS / LIFE-SAFETY PLAN" in svg
    assert "measured along the route" in svg and "0.5 m grid" in svg
    for colour in (er._OK, er._OVER, er._NONE):
        assert colour.startswith("#")
else:
    assert "IsExternal" in svg or "no egress" in svg.lower()

os.remove(PATH)
print("EGRESS-ROUTES OK - travel distance is now measured along the route a person would walk, which "
      "is what IBC 1017 limits. The existing check measured a straight line and said so, and that is "
      "precisely the problem: a straight line ignores every wall between a space and its exit, so it "
      "is always shorter than the real walk and the error runs in the UNSAFE direction — it passes "
      "plans that do not comply, and reading it carefully cannot recover that, because the number is "
      "the wrong measurement. Routing is a multi-source Dijkstra outward from every exit over a "
      "rasterised floor plate: deterministic, offline, and 8-connected with a sqrt2 diagonal so an "
      "open-floor run is not overstated by ~41% the way a 4-connected grid would be. Every space "
      "reports BOTH numbers plus their ratio, so the understatement is visible per space rather than "
      "asserted in general. A space with no route at all is reported as unreachable rather than "
      "merely distant — a different and worse finding. The grid resolution is stated on the drawing "
      "instead of implied away, and a grid too fine to compute is refused with its cell count rather "
      "than attempted. With no exterior door marked the engine refuses outright rather than routing "
      "to an arbitrary door, which would produce confident and meaningless distances.")
