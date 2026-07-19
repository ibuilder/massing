"""E8 authoring guardrails: precheck rejects broken edits (zero-length lines, non-positive dims, bad
coords/enums, missing references) BEFORE they touch the model, and apply_recipe enforces it.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_guards.py"""
import math
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, guards, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def err(recipe, params):
    r = guards.precheck(recipe, params)
    return (not r["ok"], r["errors"])


# --- valid edits pass ------------------------------------------------------------------------------
assert guards.precheck("add_wall", {"start": [0, 0], "end": [5, 0], "height": 3, "thickness": 0.2})["ok"]
assert guards.precheck("add_column", {"point": [3, 2], "height": 3, "width": 0.4, "depth": 0.4})["ok"]
assert guards.precheck("set_lod", {"guids": ["abc"], "stage": "350"})["ok"]
assert guards.precheck("add_window", {"host_guid": "w1", "width": 1.2, "height": 1.2, "sill": 0.0})["ok"]

# --- zero-length line rejected ---------------------------------------------------------------------
bad, es = err("add_wall", {"start": [2, 2], "end": [2, 2], "height": 3})
assert bad and any("zero length" in e for e in es), es

# --- non-positive / non-finite dimensions rejected -------------------------------------------------
assert err("add_wall", {"start": [0, 0], "end": [5, 0], "height": 0})[0]
assert err("add_column", {"point": [0, 0], "height": -3})[0]
assert err("add_wall", {"start": [0, 0], "end": [5, 0], "height": float("inf")})[0]
assert err("add_wall", {"start": [0, 0], "end": [5, 0], "thickness": float("nan")})[0]

# --- bad coordinates rejected ----------------------------------------------------------------------
assert err("add_wall", {"start": [0], "end": [5, 0], "height": 3})[0]              # not a pair
assert err("add_column", {"point": [float("nan"), 0], "height": 3})[0]            # non-finite coord

# --- enum + count guards ---------------------------------------------------------------------------
assert err("set_lod", {"guids": ["a"], "stage": "275"})[0]                        # not a LOD stage
assert err("add_curtain_wall", {"start": [0, 0], "end": [5, 0], "cols": 0})[0]    # count < 1
# a non-standard phase is a WARNING, not an error
w = guards.precheck("set_phase", {"guids": ["a"], "phase": "future"})
assert w["ok"] and w["warnings"], w

# --- missing required references -------------------------------------------------------------------
assert err("add_door", {"width": 0.9})[0]                                         # no host_guid
assert err("set_lod", {"stage": "300"})[0]                                        # no guids
assert err("delete_element", {})[0]                                               # no guid

# --- huge dimension warns (unit slip) but doesn't block --------------------------------------------
huge = guards.precheck("add_wall", {"start": [0, 0], "end": [5, 0], "height": 9000})
assert huge["ok"] and huge["warnings"], huge

# --- E8 deepen: nested type dims, points arrays, slope heights, new refs, mesh ----------------------
# nested `dims` map (type create/edit) — non-positive/non-finite rejected, huge warns
assert guards.precheck("create_type", {"dims": {"width": 0.9, "height": 2.1}})["ok"]
assert err("create_type", {"dims": {"width": 0, "height": 2.1}})[0]                # dims.width <= 0
assert err("edit_type", {"dims": {"height": float("nan")}})[0]                     # dims non-finite
assert guards.precheck("create_type", {"dims": {"width": 9000}})["warnings"]       # huge dims → warn
# a footprint `points` array — malformed points rejected, valid pass
assert guards.precheck("add_slab", {"points": [[0, 0], [5, 0], [5, 5], [0, 5]], "thickness": 0.2})["ok"]
assert err("add_slab", {"points": [[0, 0], [float("nan"), 0], [5, 5]]})[0]         # a NaN vertex
assert err("add_slab", {"points": [[0, 0]]})[0]                                    # < 2 vertices
# sloped-wall heights: finite, >= 0
assert guards.precheck("set_wall_slope", {"guid": "w", "start_height": 2, "end_height": 4})["ok"]
assert err("set_wall_slope", {"guid": "w", "start_height": -1, "end_height": 4})[0]
assert err("set_wall_slope", {"guid": "w", "start_height": 2, "end_height": float("inf")})[0]
# new reference requirements: connect_mep needs both guids, set_system_predefined needs a system
assert err("connect_mep", {"guid_a": "a"})[0]                                      # missing guid_b
assert guards.precheck("connect_mep", {"guid_a": "a", "guid_b": "b"})["ok"]
assert err("set_system_predefined", {"discipline": "fire"})[0]                     # missing system
# procedural mesh needs non-empty verts + faces
assert err("add_mesh_representation", {"verts": [], "faces": [[0, 1, 2]]})[0]
assert guards.precheck("add_mesh_representation", {"verts": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "faces": [[0, 1, 2]]})["ok"]

# --- apply_recipe enforces the gate (a broken edit never writes a file) ----------------------------
TMP = os.path.join(os.path.dirname(__file__), "_guards_test.ifc")
OUT = os.path.join(os.path.dirname(__file__), "_guards_out.ifc")
massing.generate_blank_ifc(TMP, name="Guards", storeys=1, storey_height=3.0, ground_size=20.0)
raised = False
try:
    edit.apply_recipe(TMP, "add_wall", {"start": [1, 1], "end": [1, 1], "height": 3, "thickness": 0.2}, OUT)
except ValueError as e:
    raised = True
    assert "zero length" in str(e), str(e)
assert raised, "apply_recipe should reject a zero-length wall"
assert not os.path.exists(OUT), "no output file should be written for a rejected edit"

# a valid edit still applies through the gate
res = edit.apply_recipe(TMP, "add_wall", {"start": [0, 0], "end": [6, 0], "height": 3, "thickness": 0.2}, OUT)
assert os.path.exists(OUT) and res["recipe"] == "add_wall", res
m = open_model(OUT)
assert len(m.by_type("IfcWall")) == 1, "the valid wall was authored"

# --- E8 model-aware layer: references validated against the OPEN model -----------------------------
wall_guid = m.by_type("IfcWall")[0].GlobalId
slab_guid = m.by_type("IfcSlab")[0].GlobalId
st_name = m.by_type("IfcBuildingStorey")[0].Name

# a typo'd storey name is rejected with the available names listed
mp = guards.model_precheck(m, "add_wall", {"start": [0, 4], "end": [4, 4], "storey": "Level 99"})
assert not mp["ok"] and "not found" in mp["errors"][0] and st_name in mp["errors"][0], mp
assert guards.model_precheck(m, "add_wall", {"start": [0, 4], "end": [4, 4], "storey": st_name})["ok"]

# a door hosted on a SLAB is rejected; on the wall it passes; a hallucinated host is rejected
mp2 = guards.model_precheck(m, "add_door", {"host_guid": slab_guid, "width": 0.9, "height": 2.1})
assert not mp2["ok"] and "needs a wall" in mp2["errors"][0], mp2
assert guards.model_precheck(m, "add_door", {"host_guid": wall_guid, "width": 0.9, "height": 2.1})["ok"]
mp3 = guards.model_precheck(m, "add_door", {"host_guid": "0" * 22, "width": 0.9, "height": 2.1})
assert not mp3["ok"] and "not found" in mp3["errors"][0], mp3

# single-element edits: a missing GUID is rejected; connect_mep needs ports on both ends
assert not guards.model_precheck(m, "move_element", {"guid": "0" * 22, "dx": 1})["ok"]
mp4 = guards.model_precheck(m, "connect_mep", {"guid_a": wall_guid, "guid_b": slab_guid})
assert not mp4["ok"] and "no connection ports" in mp4["errors"][0], mp4

# guids batches: all-missing fails; partly-missing warns and proceeds
mp5 = guards.model_precheck(m, "set_lod", {"guids": ["0" * 22, "1" * 22], "stage": "300"})
assert not mp5["ok"] and "different model" in mp5["errors"][0], mp5
mp6 = guards.model_precheck(m, "set_lod", {"guids": [wall_guid, "0" * 22], "stage": "300"})
assert mp6["ok"] and mp6["warnings"], mp6

# and apply_recipe ENFORCES it: the slab-hosted door never writes a file
OUT2 = os.path.join(os.path.dirname(__file__), "_guards_out2.ifc")
raised2 = False
try:
    edit.apply_recipe(OUT, "add_door", {"host_guid": slab_guid, "width": 0.9, "height": 2.1}, OUT2)
except ValueError as e:
    raised2 = True
    assert "needs a wall" in str(e), str(e)
assert raised2 and not os.path.exists(OUT2), "the model-aware gate must block before writing"
# a wall-hosted door passes through the same gate
r2 = edit.apply_recipe(OUT, "add_door", {"host_guid": wall_guid, "width": 0.9, "height": 2.1}, OUT2)
assert os.path.exists(OUT2) and r2["recipe"] == "add_door", r2

for f in (TMP, OUT, OUT2):
    if os.path.exists(f):
        os.remove(f)

assert math.isfinite(1.0)  # (import sanity)
print("GUARDS OK - precheck rejects zero-length lines, non-positive/non-finite dims, bad coords, "
      "out-of-range LOD/count, and missing host/target refs; warns on non-standard phase + huge dims; "
      "apply_recipe enforces the gate so a broken edit never writes a file, valid edits still apply. "
      "E8 model-aware: a typo'd storey (names listed), a slab-hosted door, a hallucinated host/guid, "
      "port-less connect_mep ends, and an all-stale guids batch are rejected against the OPEN model "
      "(partly-stale warns); apply_recipe enforces it (slab-door blocked before write, wall-door ok).")
