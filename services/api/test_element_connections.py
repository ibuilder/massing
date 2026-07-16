"""B5 element connections: connect_elements records an IfcRelConnectsElements between two building
elements (idempotent per ordered pair, rejects self/missing), and element_connections reads the graph back.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_element_connections.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import edit, guards, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_elconn_test.ifc")
massing.generate_blank_ifc(TMP, name="Conn Test", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name
a = edit.add_column(m, [0, 0], 3.0, 0.4, 0.4, st)                # a column
b = edit.add_wall(m, [0, 0], [5, 0], 3.0, 0.2, st)              # walls framing into it
c = edit.add_wall(m, [0, 0], [0, 5], 3.0, 0.2, st)

# --- connect two elements → one IfcRelConnectsElements -------------------------------------------
r = edit.connect_elements(m, a, b, description="wall-to-column")
assert r["created"] is True and r["connected"] == [a, b], r
assert len(m.by_type("IfcRelConnectsElements")) == 1, m.by_type("IfcRelConnectsElements")
rel = m.by_type("IfcRelConnectsElements")[0]
assert rel.RelatingElement.GlobalId == a and rel.RelatedElement.GlobalId == b and rel.Description == "wall-to-column", rel

# --- idempotent per ordered pair (no duplicate) --------------------------------------------------
r2 = edit.connect_elements(m, a, b)
assert r2["created"] is False and len(m.by_type("IfcRelConnectsElements")) == 1, r2

# --- a second distinct connection ----------------------------------------------------------------
edit.connect_elements(m, a, c)
assert len(m.by_type("IfcRelConnectsElements")) == 2

# --- self-connection + missing element rejected --------------------------------------------------
for bad in (lambda: edit.connect_elements(m, a, a), lambda: edit.connect_elements(m, a, "no-such-guid")):
    raised = False
    try:
        bad()
    except ValueError:
        raised = True
    assert raised, "self / missing connection should raise"

# --- element_connections reads the graph back ----------------------------------------------------
g = edit.element_connections(m)
assert g["count"] == 2 and g["elements_connected"] == 3, g          # a-b + a-c → a has degree 2
assert g["max_degree"] == 2, g                                      # the column a is connected twice
assert all({"a", "a_class", "b", "b_class"} <= set(p) for p in g["connections"]), g["connections"]

# --- guarded (needs both guids) + registered recipe ----------------------------------------------
assert guards.precheck("connect_elements", {"guid_a": a})["errors"], "missing guid_b blocked"
assert guards.precheck("connect_elements", {"guid_a": a, "guid_b": b})["ok"]
assert "connect_elements" in edit.RECIPES

# --- via the recipe path (apply_recipe reads from disk) → connect a fresh pair (b-c) --------------
m.write(TMP)                                                        # persist the 3 elements + 2 rels
OUT = os.path.join(os.path.dirname(__file__), "_elconn_out.ifc")
res = edit.apply_recipe(TMP, "connect_elements", {"guid_a": b, "guid_b": c}, OUT)   # b-c not yet linked
assert res["changed"] and os.path.exists(OUT), res
assert len(open_model(OUT).by_type("IfcRelConnectsElements")) == 3                  # a-b, a-c + new b-c

for f in (TMP, OUT):
    if os.path.exists(f):
        os.remove(f)

print("ELEMENT-CONNECTIONS OK - connect_elements records an IfcRelConnectsElements (RelatingElement/"
      "RelatedElement + description), idempotent per ordered pair, rejects self/missing; element_connections "
      "reports the connected pairs + per-element degree (column connected twice -> max_degree 2); guarded "
      "(needs both guids) + reachable through apply_recipe.")
