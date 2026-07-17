"""AUTH-VS visual node authoring: execute a recipe graph (nodes wired by data dependencies) as one
GUID-stable authoring pass — topological order, upstream-output references, and graph validation.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_nodegraph.py"""
import os
import sys
import tempfile

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import massing, nodegraph  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _blank():
    tmp = os.path.join(tempfile.gettempdir(), "_nodegraph_test.ifc")
    massing.generate_blank_ifc(tmp, name="NodeGraph Test", storeys=1, storey_height=4.0, ground_size=20.0)
    m = open_model(tmp)
    return m, m.by_type("IfcBuildingStorey")[0].Name, tmp


# --- data-threaded run: a column feeds the base plate that sits on it -------------------------------
m, st, TMP = _blank()
graph = {
    "nodes": [
        {"id": "c1", "recipe": "add_column", "params": {"point": [3, 3], "height": 4.0, "storey": st}},
        {"id": "bp", "recipe": "add_base_plate", "params": {"column_guid": {"$from": "c1"}, "width": 0.5}},
    ],
    "edges": [{"from": "c1", "to": "bp"}],
}
r = nodegraph.run(m, graph)
assert r["order"] == ["c1", "bp"] and r["node_count"] == 2, r
assert isinstance(r["outputs"]["c1"], str), "add_column returns a GUID string"
assert m.by_type("IfcColumn") and m.by_type("IfcPlate") and m.by_type("IfcElementAssembly"), "graph authored both"
# the base plate assembled onto the column the reference resolved to
assert r["outputs"]["bp"]["column"] == r["outputs"]["c1"], r["outputs"]

# --- topological order: edges reorder nodes given out of dependency order --------------------------
m, st, _ = _blank()
g2 = {
    "nodes": [
        {"id": "b", "recipe": "add_base_plate", "params": {"column_guid": {"$from": "a"}}},
        {"id": "a", "recipe": "add_column", "params": {"point": [1, 1], "height": 3.0, "storey": st}},
    ],
    "edges": [{"from": "a", "to": "b"}],
}
assert nodegraph.run(m, g2)["order"] == ["a", "b"], "toposort must run the column before its base plate"

# --- no edges: falls back to array order ----------------------------------------------------------
m, st, _ = _blank()
g3 = {"nodes": [
    {"id": "w1", "recipe": "add_wall", "params": {"start": [0, 0], "end": [4, 0], "storey": st}},
    {"id": "w2", "recipe": "add_wall", "params": {"start": [4, 0], "end": [4, 4], "storey": st}},
]}
assert nodegraph.run(m, g3)["order"] == ["w1", "w2"] and len(m.by_type("IfcWall")) >= 2, "array order"

# --- key-based reference: pick a field out of a dict result ---------------------------------------
m, st, _ = _blank()
g4 = {"nodes": [
    {"id": "cw", "recipe": "add_curtain_wall", "params": {"start": [0, 0], "end": [6, 0], "storey": st}},
    {"id": "lod", "recipe": "set_lod", "params": {"guids": [{"$from": "cw", "key": "curtain_wall"}],
                                                  "stage": "300"}},
]}
r4 = nodegraph.run(m, g4)
assert r4["outputs"]["cw"]["curtain_wall"], "curtain wall returns a dict with the assembly GUID"

# --- validation: cycles, unknown recipe/id, dangling refs all raise ValueError --------------------
def _raises(graph, needle=""):
    m2, _st, _ = _blank()
    try:
        nodegraph.run(m2, graph)
        return False
    except ValueError as e:
        return needle in str(e) if needle else True


assert _raises({"nodes": [{"id": "x", "recipe": "add_wall", "params": {}},
                          {"id": "y", "recipe": "add_wall", "params": {}}],
                "edges": [{"from": "x", "to": "y"}, {"from": "y", "to": "x"}]}, "cycle"), "cycle must raise"
assert _raises({"nodes": [{"id": "n", "recipe": "no_such_recipe", "params": {}}]}, "unknown recipe")
assert _raises({"nodes": [{"id": "n", "recipe": "add_wall", "params": {}}],
                "edges": [{"from": "n", "to": "ghost"}]}, "unknown node id")
assert _raises({"nodes": [{"id": "n", "recipe": "add_base_plate",
                           "params": {"column_guid": {"$from": "missing"}}}]}, "no output")
assert _raises({"nodes": [{"id": "d", "recipe": "add_wall", "params": {}},
                          {"id": "d", "recipe": "add_wall", "params": {}}]}, "duplicate node id")

# an empty graph is a valid no-op
assert nodegraph.run(_blank()[0], {"nodes": []}) == {"order": [], "outputs": {}, "node_count": 0}

# --- execute_graph writes a versioned model -------------------------------------------------------
OUT = os.path.join(tempfile.gettempdir(), "_nodegraph_out.ifc")
res = nodegraph.execute_graph(TMP, {"nodes": [
    {"id": "col", "recipe": "add_column", "params": {"point": [2, 2], "height": 3.0}}]}, OUT)
assert res["node_count"] == 1 and res["out"] == OUT, res
assert open_model(OUT).by_type("IfcColumn"), "executed graph persisted to the out model"

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("NODEGRAPH OK - a recipe graph runs as one authoring pass: nodes wired by edges topologically "
      "order (column before its base plate), a downstream param references an upstream node's output "
      "({$from} -> GUID, with {key} to pick a field of a dict result), no-edge graphs use array order; "
      "cycles / unknown recipes / unknown edge ids / dangling refs / duplicate ids all raise ValueError; "
      "an empty graph is a no-op; execute_graph writes a versioned model. The no-code sibling of the AI "
      "command bar over the same GUID-stable RECIPES registry.")
