"""Natural-language authoring (keyword baseline): map plain-English instructions to a validated plan of
{recipe, params} without executing. Guards the no-API-key path that any user can type against.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_nlauthor.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import nlauthor as nl  # noqa: E402


def one(text, ctx=None):
    r = nl.interpret(text, ctx)
    assert r["needs_clarification"] is None, (text, r["needs_clarification"])
    assert len(r["plan"]) == 1, r
    return r["plan"][0]


# --- wall with coords + height ---------------------------------------------------------------------
c = one("add a 3 m tall wall from 0,0 to 5,0", {"active_storey": "Level 1"})
assert c["recipe"] == "add_wall" and c["ok"], c
assert c["params"]["start"] == [0.0, 0.0] and c["params"]["end"] == [5.0, 0.0], c
assert c["params"]["height"] == 3.0 and c["params"]["storey"] == "Level 1", c

# unit normalization: mm and ft → metres
assert one("draw a wall from 0,0 to 4,0 300mm thick")["params"]["thickness"] == 0.3
assert abs(one("wall from 0,0 to 3,0 10ft tall")["params"]["height"] - 3.048) < 1e-6

# --- column at a point -----------------------------------------------------------------------------
c = one("put a column at 3,2")
assert c["recipe"] == "add_column" and c["params"]["point"] == [3.0, 2.0], c

# --- steel column with a section -------------------------------------------------------------------
c = one("add a steel column W14x30 at 6,6")
assert c["recipe"] == "add_steel_column" and c["params"]["section"] == "W14x30", c

# --- curtain wall (two points) ---------------------------------------------------------------------
c = one("add a curtain wall from 0,0 to 8,0")
assert c["recipe"] == "add_curtain_wall" and c["params"]["cols"] == 3, c

# --- door/window need a selected host wall ---------------------------------------------------------
r = nl.interpret("add a window", {})                         # no selection → clarify
assert r["needs_clarification"] and not r["plan"], r
c = one("window in the selected wall", {"selected_guids": ["1abc$GUID000000000000"]})
assert c["recipe"] == "add_window" and c["params"]["host_guid"] == "1abc$GUID000000000000", c

# --- LOD / phase on the selection ------------------------------------------------------------------
c = one("set LOD 350 on selection", {"selected_guids": ["G1", "G2"]})
assert c["recipe"] == "set_lod" and c["params"]["stage"] == "350" and c["params"]["guids"] == ["G1", "G2"], c
c = one("mark the selection as demolish", {"selected_guids": ["G1"]})
assert c["recipe"] == "set_phase" and c["params"]["phase"] == "demolish", c

# --- destructive op is flagged ---------------------------------------------------------------------
c = one("delete the selected element", {"selected_guids": ["GX"]})
assert c["recipe"] == "delete_element" and c["destructive"] is True, c

# --- rooms count -----------------------------------------------------------------------------------
c = one("add 6 rooms")
assert c["recipe"] == "add_spaces" and c["params"]["rooms_per_storey"] == 6, c

# --- ambiguous / unknown → clarification, never a bad plan -----------------------------------------
assert nl.interpret("make it nice", {})["needs_clarification"], "gibberish should clarify"
assert nl.interpret("add a wall", {})["needs_clarification"], "wall with no points should clarify"

# --- validate_call rejects unknown recipe + missing required ---------------------------------------
assert not nl.validate_call("nope", {})["ok"]
assert "missing start" in nl.validate_call("add_wall", {"end": [1, 1]})["errors"]
ok = nl.validate_call("add_wall", {"start": [0, 0], "end": [5, 0]})
assert ok["ok"] and ok["params"]["height"] == 3.0, ok       # defaults filled

print("NLAUTHOR OK - keyword baseline maps plain English -> validated plan: wall/column/steel/curtain "
      "with coords + unit-normalized dims (mm/ft->m), door/window need a selected host, LOD/phase on the "
      "selection, delete flagged destructive, rooms count; ambiguous/unknown -> clarification (never a bad "
      "plan); validate_call rejects unknown recipe + missing required, fills defaults. No API key needed.")
