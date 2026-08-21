"""R21-4D-CLASH phase 2 — what a model actually says about which element holds up which.

`sequence_clash` can already ask *what a task installs*: `element_guids` is a column on every module
record, so the task→element binding exists and reaches `analyze()`. The roadmap entry still says
otherwise ("`schedule_activity` carries no element GlobalId") — that text outlived `R25-TASK-BIND`
and is stale.

What is genuinely missing is the other half: **install-before-support needs to know that B supports
A**, and this module is the honest answer to where that comes from.

## The refusal this module exists to make

**Support is not derivable from geometry, and this will not invent it.** Two elements touching, or
one sitting above another in a bounding box, says nothing about load path: a ceiling touches a wall
it does not rest on, a beam passes over a column it is not connected to, and a raised floor sits above
a slab that carries none of it. Inferring support from proximity produces confident findings a
structural engineer would reject, on the one question where being confidently wrong is most expensive.

So the model reports exactly what the IFC states, and grades it:

* **`connected`** — `IfcRelConnectsElements` (and its realizing-element subtype) names two elements as
  joined. This is symmetric in meaning: IFC's `RelatingElement`/`RelatedElement` is an authoring
  order, **not a load direction**, and reading it as one is the mistake this module refuses.
* **`structural`** — `IfcRelConnectsStructuralMember` ties a member to a structural connection. This
  is the only relation here that comes from an analysis model, so it is the only one whose direction
  means anything mechanical, and it is reported separately for that reason.
* **`assembly`** — `IfcRelAggregates` parent/child. A part belongs to an assembly; the assembly is not
  thereby its support, but the containment is a real, stated fact and is worth knowing.

**`supports` is only ever emitted from a relation that encodes direction.** When the model says two
things are connected and nothing more, that is what comes back — `connected`, with `direction:
"unstated"` — because "we know they touch and not which holds which" is the true answer, and a
sequence check can use it as a *necessary* condition without treating it as a sufficient one.

A model with no connection relations at all returns `stated: False` rather than an empty graph: no
edges and no relations are indistinguishable in a bare adjacency list, and only one of them means
"this model was never authored with connectivity".
"""
from __future__ import annotations

import collections
from typing import Any

#: How an edge was learned, worst-to-best in terms of what it licenses you to conclude.
EDGE_CONNECTED = "connected"      # IfcRelConnectsElements — joined, direction unstated
EDGE_ASSEMBLY = "assembly"        # IfcRelAggregates — part of, not held up by
EDGE_STRUCTURAL = "structural"    # IfcRelConnectsStructuralMember — from an analysis model

EDGE_MEANING = {
    EDGE_CONNECTED: "the model states these two elements are joined. IFC's Relating/Related pair is "
                    "an authoring order, NOT a load direction, so no support direction is implied",
    EDGE_ASSEMBLY: "one is a part of the other's assembly. Containment is not support — a bolt "
                   "belongs to a connection assembly without holding it up",
    EDGE_STRUCTURAL: "from the structural analysis model, which is the only relation here whose "
                     "direction carries mechanical meaning",
}

#: Relations read, mapped to the grade they license.
_REL_SOURCES = (
    ("IfcRelConnectsWithRealizingElements", EDGE_CONNECTED),
    ("IfcRelConnectsElements", EDGE_CONNECTED),
    ("IfcRelConnectsStructuralMember", EDGE_STRUCTURAL),
)


def _guid(x) -> str | None:
    return getattr(x, "GlobalId", None)


def connection_graph(model, include_assemblies: bool = True) -> dict[str, Any]:
    """Every connection the model STATES, graded by what it licenses you to conclude.

    Returns edges, an adjacency index, and — importantly — whether the model states anything at all."""
    edges: list[dict] = []
    seen: set[tuple] = set()

    for rel_type, grade in _REL_SOURCES:
        try:
            rels = model.by_type(rel_type)
        except Exception:                              # noqa: BLE001 — class absent from this schema
            continue
        for rel in rels:
            # IfcRelConnectsElements uses RelatingElement/RelatedElement. IfcRelConnectsStructuralMember
            # does not: its ends are RelatingStructuralMember / RelatedStructuralConnection. Reading the
            # element pair on a structural rel silently produced ZERO structural edges on every model
            # this repo can derive — the only relation that licenses a direction was never collected.
            if grade == EDGE_STRUCTURAL:
                a = _guid(getattr(rel, "RelatingStructuralMember", None)
                          or getattr(rel, "RelatingElement", None))
                b = _guid(getattr(rel, "RelatedStructuralConnection", None)
                          or getattr(rel, "RelatedElement", None))
            else:
                a = _guid(getattr(rel, "RelatingElement", None))
                b = _guid(getattr(rel, "RelatedElement", None))
            if not a or not b or a == b:
                continue
            key = (a, b, grade)
            if key in seen:
                continue
            seen.add(key)
            edges.append({
                "a": a, "b": b, "grade": grade, "relation": rel_type,
                # The one field that keeps this honest. Only a structural relation is allowed to
                # claim a direction; everything else says so plainly rather than leaving a reader to
                # assume Relating means "supports".
                "direction": "relating_to_related" if grade == EDGE_STRUCTURAL else "unstated",
            })

    if include_assemblies:
        try:
            for rel in model.by_type("IfcRelAggregates"):
                parent = _guid(getattr(rel, "RelatingObject", None))
                if not parent:
                    continue
                for child in (getattr(rel, "RelatedObjects", None) or []):
                    c = _guid(child)
                    if not c or c == parent:
                        continue
                    key = (parent, c, EDGE_ASSEMBLY)
                    if key in seen:
                        continue
                    seen.add(key)
                    edges.append({"a": parent, "b": c, "grade": EDGE_ASSEMBLY,
                                  "relation": "IfcRelAggregates", "direction": "parent_to_part"})
        except Exception:                              # noqa: BLE001
            pass

    adjacency: dict[str, set] = collections.defaultdict(set)
    for e in edges:
        adjacency[e["a"]].add(e["b"])
        adjacency[e["b"]].add(e["a"])

    by_grade = collections.Counter(e["grade"] for e in edges)
    structural = by_grade.get(EDGE_STRUCTURAL, 0)

    return {
        # Not an empty graph — the DISTINCTION. No edges and no relations look identical in a bare
        # adjacency list, and only one of them means "connectivity was never authored".
        "stated": bool(edges),
        "edges": edges,
        "edge_count": len(edges),
        "by_grade": dict(by_grade),
        "grade_meaning": EDGE_MEANING,
        "adjacency": {k: sorted(v) for k, v in adjacency.items()},
        "elements_with_connections": len(adjacency),
        # The headline caveat, in the payload rather than only in this docstring.
        "supports_directionally_known": structural,
        "note": (
            "no connection relations are authored in this model, so nothing here can support an "
            "install-before-support check. That is an ABSENCE of data, not an absence of conflicts."
            if not edges else
            f"{len(edges)} stated connections. {structural} come from the structural model and carry "
            "a meaningful direction; the rest state that two elements are joined and say NOTHING "
            "about which holds up which. Support is not inferred from geometry here — proximity "
            "would produce confident findings a structural engineer would reject."),
    }


def supports(graph: dict, guid: str) -> dict[str, Any]:
    """What the model states about `guid`'s connections — never a guess.

    `directional` are the elements a structural relation actually points from; `connected_unstated`
    are joins with no stated direction. A caller doing install-before-support may use the second as a
    *necessary* condition (unconnected elements cannot support each other) and must not use it as a
    sufficient one."""
    if not graph or not graph.get("stated"):
        return {"known": False, "directional": [], "connected_unstated": [],
                "reason": "the model states no connections, so nothing is known about what supports "
                          "this element — which is not the same as nothing supporting it"}
    directional = [e["a"] for e in graph["edges"]
                   if e["b"] == guid and e["grade"] == EDGE_STRUCTURAL]
    unstated = sorted({(e["a"] if e["b"] == guid else e["b"]) for e in graph["edges"]
                       if guid in (e["a"], e["b"]) and e["grade"] != EDGE_STRUCTURAL})
    return {
        "known": bool(directional or unstated),
        "directional": sorted(set(directional)),
        "connected_unstated": unstated,
        "reason": ("elements joined to this one are listed; only `directional` entries come from a "
                   "relation that states which way the load goes"),
    }


def _product_map(model) -> dict[str, str]:
    """Analytical GlobalId → physical product GlobalId via IfcRelAssignsToProduct.

    `derive_analytical` assigns each curve member to its IfcColumn/IfcBeam. Schedule bindings are on
    those products, so an install-before-support check that compared analytical GUIDs to activity
    `element_guids` would find nothing even when the graph was fully stated."""
    out: dict[str, str] = {}
    try:
        rels = model.by_type("IfcRelAssignsToProduct")
    except Exception:  # noqa: BLE001 — class absent from this schema
        return out
    for rel in rels:
        prod = _guid(getattr(rel, "RelatingProduct", None))
        if not prod:
            continue
        for obj in getattr(rel, "RelatedObjects", None) or []:
            g = _guid(obj)
            if g:
                out[g] = prod
    return out


def directed_install_pairs(graph: dict, model=None) -> list[dict[str, str]]:
    """(support, supported) pairs a sequence check may treat as ordered, and nothing else.

    * `structural` — RelatingStructuralMember before RelatedStructuralConnection (analysis-model
      direction). Ends are remapped to physical products when `model` is given.
    * `assembly` — RelatingObject (whole) before RelatedObjects (parts). The roadmap's example is a
      beam aggregated into a frame that has not been installed; containment is not load path, but it
      *is* a stated order.

    `connected` joins with `direction: unstated` are omitted on purpose: using Relating/Related as a
    load direction is the inference this module exists to refuse.
    """
    phys = _product_map(model) if model is not None else {}
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for e in graph.get("edges") or []:
        grade = e.get("grade")
        if grade == EDGE_STRUCTURAL and e.get("direction") == "relating_to_related":
            kind = "structural"
        elif grade == EDGE_ASSEMBLY and e.get("direction") == "parent_to_part":
            kind = "assembly"
        else:
            continue
        a = phys.get(e["a"], e["a"])
        b = phys.get(e["b"], e["b"])
        if not a or not b or a == b:
            continue
        key = (a, b, kind)
        if key in seen:
            continue
        seen.add(key)
        out.append({"support": a, "supported": b, "grade": kind,
                    "relation": str(e.get("relation") or "")})
    return out
