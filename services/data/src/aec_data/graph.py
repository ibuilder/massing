"""Semantic model graph (Wave 9 · W9-4, v1).

The property index answers attribute lookups ("what's this door's width"); it can't answer *relational*
questions ("which space does this wall bound", "what's contained in Level 2", "what opening is in this
wall"). This builds a typed graph from the IFC's own relationships (IfcRel*) so those multi-hop questions
get **cited** answers — every node is an IFC GlobalId, every edge names the relationship. Nodes = IFC
entities; edges are directional with a relationship label.

Edge types (from the standard IfcRel* relationships):
  contained_in   element  → spatial container   (IfcRelContainedInSpatialStructure)
  aggregates     parent   → child               (IfcRelAggregates — project▸site▸building▸storey)
  bounds         element  → space               (IfcRelSpaceBoundary)
  has_opening    element  → opening             (IfcRelVoidsElement)
  fills          opening  → element             (IfcRelFillsElement — door/window in the opening)
  serves         system   → element             (IfcRelServicesBuildings / distribution systems)

Spec/code-document ingestion and NL→graph query are a deliberate follow-up (this is the model half).
"""
from __future__ import annotations

from typing import Any

import ifcopenshell


def _node(el) -> dict[str, Any]:
    return {"guid": el.GlobalId, "class": el.is_a(), "name": getattr(el, "Name", None)}


def _guid(el) -> str | None:
    return getattr(el, "GlobalId", None)


def build(model: ifcopenshell.file) -> dict[str, Any]:
    """Nodes (by GUID) + typed directional edges + per-type counts."""
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def add(el):
        g = _guid(el)
        if g and g not in nodes:
            nodes[g] = _node(el)
        return g

    def link(a, b, rel):
        ga, gb = _guid(a), _guid(b)
        if ga and gb:
            add(a)
            add(b)
            edges.append({"from": ga, "to": gb, "rel": rel})

    for r in model.by_type("IfcRelContainedInSpatialStructure"):
        for el in r.RelatedElements or []:
            link(el, r.RelatingStructure, "contained_in")
    for r in model.by_type("IfcRelAggregates"):
        for el in r.RelatedObjects or []:
            link(r.RelatingObject, el, "aggregates")
    for r in model.by_type("IfcRelSpaceBoundary"):
        if getattr(r, "RelatedBuildingElement", None) and getattr(r, "RelatingSpace", None):
            link(r.RelatedBuildingElement, r.RelatingSpace, "bounds")
    for r in model.by_type("IfcRelVoidsElement"):
        if getattr(r, "RelatingBuildingElement", None) and getattr(r, "RelatedOpeningElement", None):
            link(r.RelatingBuildingElement, r.RelatedOpeningElement, "has_opening")
    for r in model.by_type("IfcRelFillsElement"):
        if getattr(r, "RelatingOpeningElement", None) and getattr(r, "RelatedBuildingElement", None):
            link(r.RelatingOpeningElement, r.RelatedBuildingElement, "fills")
    for r in model.by_type("IfcRelServicesBuildings"):
        for el in getattr(r, "RelatedBuildings", None) or []:
            link(r.RelatingSystem, el, "serves")

    by_rel: dict[str, int] = {}
    for e in edges:
        by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1
    return {"nodes": len(nodes), "edges": len(edges), "by_rel": by_rel}


def neighbors(model: ifcopenshell.file, guid: str, depth: int = 1) -> dict[str, Any]:
    """The connected subgraph around `guid` out to `depth` hops (both edge directions), with the paths
    that reach each node — every step cited by GUID + relationship. Answers 'what is this related to'."""
    depth = max(1, min(depth, 4))
    # adjacency in both directions
    adj: dict[str, list[tuple[str, str, str]]] = {}   # node -> [(neighbor, rel, direction)]
    node_map: dict[str, dict] = {}

    def add(el):
        g = _guid(el)
        if g and g not in node_map:
            node_map[g] = _node(el)
        return g

    def link(a, b, rel):
        ga, gb = _guid(a), _guid(b)
        if not (ga and gb):
            return
        add(a)
        add(b)
        adj.setdefault(ga, []).append((gb, rel, "out"))
        adj.setdefault(gb, []).append((ga, rel, "in"))

    for r in model.by_type("IfcRelContainedInSpatialStructure"):
        for el in r.RelatedElements or []:
            link(el, r.RelatingStructure, "contained_in")
    for r in model.by_type("IfcRelAggregates"):
        for el in r.RelatedObjects or []:
            link(r.RelatingObject, el, "aggregates")
    for r in model.by_type("IfcRelSpaceBoundary"):
        if getattr(r, "RelatedBuildingElement", None) and getattr(r, "RelatingSpace", None):
            link(r.RelatedBuildingElement, r.RelatingSpace, "bounds")
    for r in model.by_type("IfcRelVoidsElement"):
        if getattr(r, "RelatingBuildingElement", None) and getattr(r, "RelatedOpeningElement", None):
            link(r.RelatingBuildingElement, r.RelatedOpeningElement, "has_opening")
    for r in model.by_type("IfcRelFillsElement"):
        if getattr(r, "RelatingOpeningElement", None) and getattr(r, "RelatedBuildingElement", None):
            link(r.RelatingOpeningElement, r.RelatedBuildingElement, "fills")

    if guid not in node_map:
        # the element may exist but be isolated (no relationships) — still return it as the root
        el = model.by_guid(guid) if any(e.GlobalId == guid for e in model.by_type("IfcRoot")) else None
        if el is None:
            return {"root": guid, "found": False, "nodes": [], "edges": [], "paths": []}
        node_map[guid] = _node(el)

    # BFS out to `depth`, recording the first path that reaches each node
    seen = {guid: []}
    frontier = [guid]
    out_edges: list[dict] = []
    for _ in range(depth):
        nxt: list[str] = []
        for g in frontier:
            for (nb, rel, direction) in adj.get(g, []):
                out_edges.append({"from": g if direction == "out" else nb,
                                  "to": nb if direction == "out" else g, "rel": rel})
                if nb not in seen:
                    seen[nb] = [*seen[g], {"rel": rel, "dir": direction, "to": nb}]
                    nxt.append(nb)
        frontier = nxt
    # dedupe edges
    uniq = {(e["from"], e["to"], e["rel"]): e for e in out_edges}
    reached = [g for g in seen if g != guid]
    return {
        "root": guid, "found": True, "depth": depth,
        "nodes": [node_map[g] for g in seen if g in node_map],
        "edges": list(uniq.values()),
        "neighbor_count": len(reached),
        "paths": [{"guid": g, **node_map.get(g, {}), "path": seen[g]} for g in reached],
    }
