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

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

assert math.isfinite(1.0)  # (import sanity)
print("GUARDS OK - precheck rejects zero-length lines, non-positive/non-finite dims, bad coords, "
      "out-of-range LOD/count, and missing host/target refs; warns on non-standard phase + huge dims; "
      "apply_recipe enforces the gate so a broken edit never writes a file, valid edits still apply.")
