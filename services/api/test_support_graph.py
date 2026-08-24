"""R21-4D-CLASH phase 2 — what the model states about support, and what it refuses to invent.

The whole value of this module is a refusal, so that is what these assertions are about:

1. **support is never inferred from geometry.** Two elements touching says nothing about load path —
   a ceiling touches a wall it does not rest on. Inferring support from proximity produces confident
   findings a structural engineer would reject, on the one question where being wrong is dearest;
2. **`connected` is not `supports`.** IFC's `RelatingElement`/`RelatedElement` is an authoring order,
   not a load direction, and reading it as one is the mistake this module exists to prevent;
3. **a model with no connection relations reports `stated: False`**, not an empty graph. No edges and
   no relations are indistinguishable in a bare adjacency list, and only one of them means
   "connectivity was never authored" — which is an absence of DATA, not an absence of conflicts.

Fixture is generated in-test; nothing is read from `samples/`.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_support_graph.py
"""
import os
import sys
import tempfile

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

import ifcopenshell  # noqa: E402

from aec_data import connections, edit, massing  # noqa: E402
from aec_data.support_graph import (  # noqa: E402
    EDGE_ASSEMBLY,
    EDGE_CONNECTED,
    EDGE_STRUCTURAL,
    connection_graph,
    directed_install_pairs,
    supports,
)

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


WORK = tempfile.mkdtemp(prefix="support_graph_")
SRC = os.path.join(WORK, "fixture.ifc")
massing.generate_blank_ifc(SRC, name="SupportFixture", storeys=1, storey_height=3.5)
m = ifcopenshell.open(SRC)
_st = [s.Name for s in m.by_type("IfcBuildingStorey")][0]

# A column and a beam that PHYSICALLY MEET at the origin but are not related in the model. This is the
# fixture the whole module turns on: geometry alone must not produce a support edge.
col = edit.RECIPES["add_column"](m, {"point": [0, 0], "height": 3.0, "storey": _st})
beam = edit.RECIPES["add_beam"](m, {"start": [0, 0], "end": [5, 0], "storey": _st})

# --- 1. TOUCHING IS NOT SUPPORT -------------------------------------------------------------------
g0 = connection_graph(m, include_assemblies=False)
check("a model with geometry but no stated connections reports stated=False",
      g0["stated"] is False, g0["by_grade"])
check("  it does NOT invent an edge between a column and the beam sitting on it",
      g0["edge_count"] == 0, g0["edges"][:3])
check("  and says the absence is of DATA, not of conflicts",
      "absence of data" in g0["note"].lower() or "ABSENCE of data" in g0["note"], g0["note"])
s0 = supports(g0, beam)
check("  asking what supports the beam returns known=False, not an empty 'nothing supports it'",
      s0["known"] is False, s0)
check("  with a reason distinguishing the two", "not the same as nothing" in s0["reason"], s0["reason"])

# --- 2. a STATED connection appears, and is graded honestly ----------------------------------------
connections.add_connection_assembly(m, col, beam, kind="bolted")
g1 = connection_graph(m, include_assemblies=False)
check("once the model STATES a connection, the graph reports it", g1["stated"] is True, g1["by_grade"])
edge = next((e for e in g1["edges"] if {e["a"], e["b"]} == {col, beam}), None)
check("  the column-beam edge is present", edge is not None, g1["edges"][:4])
if edge:
    check("  graded `connected`, not `supports`", edge["grade"] == EDGE_CONNECTED, edge)
    check("  WITH DIRECTION EXPLICITLY UNSTATED — Relating/Related is authoring order, not load path",
          edge["direction"] == "unstated", edge)

check("no structural-model edges exist, so nothing claims a direction",
      g1["supports_directionally_known"] == 0, g1["supports_directionally_known"])
check("  and the note says the rest say NOTHING about which holds which",
      "which holds up which" in g1["note"], g1["note"])

s1 = supports(g1, beam)
check("supports() lists the join but keeps it out of `directional`",
      col in s1["connected_unstated"] and s1["directional"] == [], s1)
check("  known is True — we do know they are joined", s1["known"] is True, s1)

# --- 3. assembly containment is a fact, and is not support -------------------------------------------
g2 = connection_graph(m, include_assemblies=True)
asm = [e for e in g2["edges"] if e["grade"] == EDGE_ASSEMBLY]
check("assembly edges are read when asked for", len(asm) > 0, g2["by_grade"])
check("  and graded `assembly`, never `structural`",
      all(e["grade"] != EDGE_STRUCTURAL for e in asm), asm[:2])
check("  the grade meaning says containment is not support",
      "not support" in g2["grade_meaning"][EDGE_ASSEMBLY], g2["grade_meaning"][EDGE_ASSEMBLY])
check("assemblies are OPT-OUT-able, so a caller can ask only about joins",
      g2["edge_count"] > g1["edge_count"], (g1["edge_count"], g2["edge_count"]))

# --- 4. every grade documents what it licenses -------------------------------------------------------
for grade in (EDGE_CONNECTED, EDGE_ASSEMBLY, EDGE_STRUCTURAL):
    check(f"grade `{grade}` documents what it licenses you to conclude",
          len(g2["grade_meaning"][grade]) > 40, g2["grade_meaning"].get(grade))
check("only the structural grade claims mechanical meaning",
      "mechanical" in g2["grade_meaning"][EDGE_STRUCTURAL]
      and "NOT a load direction" in g2["grade_meaning"][EDGE_CONNECTED], g2["grade_meaning"])

# --- 5. adjacency is symmetric, because a join is ------------------------------------------------------
check("adjacency records the join in both directions — a connection has no favoured end",
      beam in g1["adjacency"].get(col, []) and col in g1["adjacency"].get(beam, []),
      g1["adjacency"])
check("an element nobody connected is absent from adjacency rather than present-and-empty",
      "not-a-guid" not in g1["adjacency"])
check("supports() on an unknown guid returns known=False rather than raising",
      supports(g1, "not-a-real-guid")["known"] is False)
check("supports() on an empty graph refuses rather than erroring",
      supports({}, beam)["known"] is False and supports(None, beam)["known"] is False)

# directed_install_pairs uses only relations that license an order. The column-beam join above is
# `connected` / unstated, so it must NOT become a support pair — that would be reading Relating as
# load direction, which this module exists to refuse.
unstated_pairs = directed_install_pairs(g1)
check("an unstated IfcRelConnectsElements join is not a directed install pair",
      unstated_pairs == [], unstated_pairs)

asm_pairs = [p for p in directed_install_pairs(g2) if p["grade"] == "assembly"]
check("RelAggregates parent-before-part IS a directed pair (containment order, not load path)",
      len(asm_pairs) > 0, directed_install_pairs(g2))

# IfcRelConnectsStructuralMember's ends are RelatingStructuralMember / RelatedStructuralConnection,
# not RelatingElement. A reader that only knew the element pair produced an empty structural graph
# on every derived analysis model in this repo.
class _Fake:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeModel:
    def __init__(self, rels):
        self._rels = rels

    def by_type(self, t):
        return self._rels if t == "IfcRelConnectsStructuralMember" else []


rel = _Fake(RelatingStructuralMember=_Fake(GlobalId="MEM"),
            RelatedStructuralConnection=_Fake(GlobalId="NODE"),
            RelatingElement=None, RelatedElement=None)
gs = connection_graph(_FakeModel([rel]), include_assemblies=False)
check("structural rels are read from RelatingStructuralMember, not RelatingElement",
      gs["stated"] is True and gs["supports_directionally_known"] == 1, gs)
check("  and directed_install_pairs emits member-before-connection",
      directed_install_pairs(gs) == [{"support": "MEM", "supported": "NODE",
                                      "grade": "structural",
                                      "relation": "IfcRelConnectsStructuralMember"}],
      directed_install_pairs(gs))

print()
if FAILED:
    print(f"support_graph: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("support_graph: all checks passed")
