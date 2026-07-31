"""A cost map is matched by IFC class INCLUDING inherited classes — a map keyed `IfcWall` must price
`IfcWallStandardCase` walls.

The defect this pins was found on a real model, not by reading. `qto.takeoff` did
`cost_map.get(el.is_a())` — an exact string match on the CONCRETE class — so an ordinary cost map keyed
`IfcWall` matched **none** of `samples/basichouse.ifc`'s 13 `IfcWallStandardCase` walls.

What makes it expensive is the shape of the wrong answer. It was not an error and not a zero-cost line:
those walls came back **uncoded**, which reads as *"no cost data was configured for this project"*
rather than *"your cost map does not match this model's classes"*. A takeoff that silently omits every
wall while looking exactly like a clean unconfigured-project result.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_qto_class_match.py
"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_qto_class_match.db")
for _f in ("./test_qto_class_match.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell  # noqa: E402

from aec_data import qto  # noqa: E402

# Built here rather than read from `samples/` — those are gitignored, and a test that reads one turns
# `main` red on a fresh clone. This is the same construction the defect was found in: walls declared as
# IfcWallStandardCase, which is what most authoring tools actually emit.
f = ifcopenshell.file(schema="IFC4")
proj = f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="ClassMatch")
walls = [f.create_entity("IfcWallStandardCase", GlobalId=ifcopenshell.guid.new(), Name=f"W{i}")
         for i in range(3)]
slab = f.create_entity("IfcSlab", GlobalId=ifcopenshell.guid.new(), Name="S1")
path = str(Path(tempfile.gettempdir()) / "qto_class_match.ifc")
f.write(path)
model = ifcopenshell.open(path)

# The concrete classes really are the derived ones — if this changes, the test below stops testing
# anything and would pass vacuously.
assert {w.is_a() for w in model.by_type("IfcWallStandardCase")} == {"IfcWallStandardCase"}, "fixture"

# --- the chain is read from the SCHEMA, not a hand-written table -----------------------------------
chain = qto._class_chain(model, "IfcWallStandardCase")
assert chain[0] == "IfcWallStandardCase", chain
assert "IfcWall" in chain, chain
assert chain.index("IfcWallStandardCase") < chain.index("IfcWall"), "most specific first"
# An unknown class must not raise — it degrades to an exact-match-only lookup.
assert qto._class_chain(model, "IfcNotARealClass") == ["IfcNotARealClass"]

# --- a map keyed by the ANCESTOR now prices the derived walls --------------------------------------
w = model.by_type("IfcWallStandardCase")[0]
row = qto.CostCodeRow(match_class="IfcWall", cost_code="03 30 00", description="Concrete wall",
                      unit="area", unit_cost=100.0)

hit, key = qto.cost_code_for(model, w, {"IfcWall": row})
assert hit is row, "a map keyed IfcWall must price an IfcWallStandardCase — this is the whole defect"
assert key == "IfcWall", key            # ...and it must SAY the match came from the ancestor

# --- most specific still wins ----------------------------------------------------------------------
exact = qto.CostCodeRow(match_class="IfcWallStandardCase", cost_code="03 30 10",
                        description="Std-case wall", unit="area", unit_cost=120.0)
hit2, key2 = qto.cost_code_for(model, w, {"IfcWall": row, "IfcWallStandardCase": exact})
assert hit2 is exact and key2 == "IfcWallStandardCase", (hit2, key2)

# --- an unrelated class still misses; inheritance must not become a wildcard ------------------------
hit3, key3 = qto.cost_code_for(model, w, {"IfcSlab": row})
assert hit3 is None and key3 is None, (hit3, key3)
# and the slab is not priced by the wall rule either
s = model.by_type("IfcSlab")[0]
assert qto.cost_code_for(model, s, {"IfcWall": row})[0] is None, "IfcSlab is not an IfcWall"

# --- the row REPORTS which key priced it, which is what made the old failure invisible --------------
rows = qto.takeoff(model, {"IfcWall": row}, geometry_fallback=False)
wall_rows = [r for r in rows if r["ifc_class"] == "IfcWallStandardCase"]
assert wall_rows, [r["ifc_class"] for r in rows]
for r in wall_rows:
    assert r["cost_code"] == "03 30 00", r          # priced at all — it used to be None
    assert r["matched_class"] == "IfcWall", r       # ...and honest that it matched by ancestor
    assert r["ifc_class"] != r["matched_class"], r  # the two differ exactly when inheritance was used
slab_rows = [r for r in rows if r["ifc_class"] == "IfcSlab"]
assert slab_rows and slab_rows[0]["matched_class"] is None, slab_rows

print("QTO CLASS MATCH OK - a cost map keyed `IfcWall` now prices IfcWallStandardCase walls, which it "
      "silently did not: the exact-string match returned None and the walls came back UNCODED, so a "
      "takeoff missing every wall was indistinguishable from a project with no cost data configured "
      "(found on samples/basichouse.ifc, 13 walls). The class chain is read from the ifcopenshell "
      "schema rather than a hand-written table, most-specific still wins over an ancestor, inheritance "
      "is not a wildcard (IfcSlab is not priced by an IfcWall rule), and every row reports "
      "`matched_class` — the field whose absence is what made the original failure invisible.")
