"""S3 LLM-backed authoring: the network-free plan assembly (`_steps_to_plan`) validates + fills context
from synthetic model output, destructive recipes are withheld from the model, and with no API key the
dispatcher falls back to the deterministic keyword baseline.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_nl_ai.py"""
import os
import sys

os.environ.pop("ANTHROPIC_API_KEY", None)   # ensure the offline path
_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import nl_ai  # noqa: E402

# --- destructive recipes are NOT offered to the model ---------------------------------------------
recipes = nl_ai._llm_recipes()
assert "add_wall" in recipes and "delete_element" not in recipes, "delete must be withheld from the LLM"

# --- multi-step plan: a 5x4 room = 4 walls; storey filled from context ----------------------------
ctx = {"active_storey": "Level 1", "selected_guids": []}
steps = [
    {"recipe": "add_wall", "params": {"start": [0, 0], "end": [5, 0]}},
    {"recipe": "add_wall", "params": {"start": [5, 0], "end": [5, 4]}},
    {"recipe": "add_wall", "params": {"start": [5, 4], "end": [0, 4]}},
    {"recipe": "add_wall", "params": {"start": [0, 4], "end": [0, 0]}},
]
res = nl_ai._steps_to_plan(steps, ctx)
assert res["source"] == "claude" and len(res["plan"]) == 4, res
assert res["needs_clarification"] is None, res
assert all(c["params"]["storey"] == "Level 1" for c in res["plan"]), "storey injected server-side"
assert all(c.get("summary") for c in res["plan"]), "each step carries a human summary"

# --- selection-targeted recipe: host GUID filled from selection, never fabricated -----------------
sel = "1a2b3c4d5e6f7g8h9i0jZZ"
r2 = nl_ai._steps_to_plan([{"recipe": "add_window", "params": {"width": 1.5}}],
                          {"selected_guids": [sel]})
assert r2["plan"] and r2["plan"][0]["params"]["host_guid"] == sel, r2
assert r2["plan"][0]["params"]["width"] == 1.5, "model-supplied param kept"

# --- window with no selection → no host → clarification, not a broken apply ------------------------
r3 = nl_ai._steps_to_plan([{"recipe": "add_window", "params": {}}], {"selected_guids": []})
assert not r3["plan"] and r3["needs_clarification"], r3

# --- unknown/withheld recipe is dropped with a reason, never applied -------------------------------
r4 = nl_ai._steps_to_plan([{"recipe": "delete_element", "params": {"guid": "x"}},
                           {"recipe": "nope", "params": {}}], {})
assert not r4["plan"] and "recipe" in r4["needs_clarification"], r4

# --- partial success surfaces skipped steps but returns the usable ones ----------------------------
r5 = nl_ai._steps_to_plan([{"recipe": "add_column", "params": {"point": [3, 2]}},
                           {"recipe": "add_wall", "params": {"start": [0, 0]}}],  # missing 'end'
                          {})
assert len(r5["plan"]) == 1 and r5["plan"][0]["recipe"] == "add_column", r5
assert r5["needs_clarification"] and "skipped" in r5["needs_clarification"], r5

# --- no API key → deterministic keyword baseline (source 'keyword') --------------------------------
kw = nl_ai.plan("add a wall from 0,0 to 6,0", {"active_storey": "Level 1"})
assert kw["source"] == "keyword" and kw["plan"] and kw["plan"][0]["recipe"] == "add_wall", kw

# --- the system prompt catalogues real recipes and hides GUID/storey params -----------------------
brief = nl_ai._spec_brief()
assert "add_wall" in brief and "host_guid" not in brief and "delete_element" not in brief, brief

print("NL_AI OK - _steps_to_plan validates + fills storey/selection, withholds destructive recipes, "
      "handles missing host/unknown/partial steps, and falls back to the keyword baseline with no key.")
