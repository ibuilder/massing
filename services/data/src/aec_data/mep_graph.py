"""MEP-GRAPH (R14) — a first-class **port connectivity graph** over ``IfcDistributionPort``.

The MEP browser already flags unconnected ports; this extracts the actual network: nodes are MEP
elements, edges are the port-to-port ``IfcRelConnectsPorts`` connections, and connected components are
**runs**. For each run it reports the endpoints (degree-1 terminals), branch points (degree ≥3), and
the **longest linear path** — the index-run backbone a balancing engineer follows and the foundation a
real pressure-loss path calculation needs (vs. today's per-segment sum). Isolated elements (no
connected port) are the wiring gap.

Pure over the model — no geometry, no I/O — so it unit-tests against an authored + connected system.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

import ifcopenshell

_MEP_FALLBACK = ("IfcFlowSegment", "IfcFlowFitting", "IfcFlowTerminal", "IfcFlowController",
                 "IfcFlowMovingDevice", "IfcFlowStorageDevice", "IfcEnergyConversionDevice",
                 "IfcDistributionFlowElement")


def _connected_ports(port: Any) -> list:
    """The ports this port connects to, across both directions of IfcRelConnectsPorts."""
    out = []
    for rel in (getattr(port, "ConnectedTo", None) or []):
        rp = getattr(rel, "RelatedPort", None)
        if rp is not None:
            out.append(rp)
    for rel in (getattr(port, "ConnectedFrom", None) or []):
        rp = getattr(rel, "RelatingPort", None)
        if rp is not None:
            out.append(rp)
    return out


def _elements(model: ifcopenshell.file) -> list:
    els = list(model.by_type("IfcDistributionElement"))
    if not els:
        seen: dict[int, Any] = {}
        for cls in _MEP_FALLBACK:
            for e in model.by_type(cls):
                seen[e.id()] = e
        els = list(seen.values())
    return list({e.id(): e for e in els}.values())


def _longest_path(comp: list[int], adj: dict[int, set]) -> list[int]:
    """Longest simple path in the component — exact tree diameter via double-BFS (MEP runs are tree-like;
    a graph with cycles degrades to a long-but-not-guaranteed-maximal path)."""
    def _bfs(src: int) -> tuple[int, dict[int, int]]:
        prev = {src: src}
        q = deque([src])
        far = src
        while q:
            n = q.popleft()
            far = n
            for m in adj[n]:
                if m not in prev:
                    prev[m] = n
                    q.append(m)
        return far, prev

    if len(comp) < 2:
        return list(comp)
    u, _ = _bfs(comp[0])
    v, prev = _bfs(u)
    path = [v]
    while path[-1] != u:
        path.append(prev[path[-1]])
    return path


def graph(model: ifcopenshell.file) -> dict[str, Any]:
    """Build the port graph → connected runs (with endpoints / branches / longest path) + isolated count."""
    els = _elements(model)
    id_el = {e.id(): e for e in els}
    port_owner: dict[int, int] = {}
    for e in els:
        for p in _ports(e):
            port_owner[p.id()] = e.id()

    adj: dict[int, set] = defaultdict(set)
    for e in els:
        for p in _ports(e):
            for cp in _connected_ports(p):
                oid = port_owner.get(cp.id())
                if oid is not None and oid != e.id():
                    adj[e.id()].add(oid)
                    adj[oid].add(e.id())

    def _brief(eid: int) -> dict:
        el = id_el[eid]
        return {"guid": el.GlobalId, "ifc_class": el.is_a(), "name": getattr(el, "Name", None)}

    seen: set[int] = set()
    runs = []
    for e in els:
        if e.id() in seen:
            continue
        comp: list[int] = []
        q = deque([e.id()])
        seen.add(e.id())
        while q:
            n = q.popleft()
            comp.append(n)
            for m in adj[n]:
                if m not in seen:
                    seen.add(m)
                    q.append(m)
        if len(comp) < 2:
            continue                              # a lone element isn't a run (counted as isolated below)
        endpoints = [n for n in comp if len(adj[n]) == 1]
        branches = [n for n in comp if len(adj[n]) >= 3]
        classes: dict[str, int] = {}
        for n in comp:
            c = id_el[n].is_a()
            classes[c] = classes.get(c, 0) + 1
        path = _longest_path(comp, adj)
        runs.append({
            "element_count": len(comp), "endpoints": len(endpoints), "branch_points": len(branches),
            "classes": sorted(({"ifc_class": c, "count": n} for c, n in classes.items()),
                              key=lambda x: -x["count"]),
            "longest_path_length": len(path),
            "longest_path": [_brief(n) for n in path[:50]],
            "sample_guids": [id_el[n].GlobalId for n in comp[:20]],
        })

    isolated = sum(1 for e in els if not adj[e.id()])
    return {
        "element_count": len(els), "connected_runs": len(runs), "isolated_elements": isolated,
        "runs": sorted(runs, key=lambda r: -r["element_count"]),
        "note": "Port connectivity graph over IfcDistributionPort (IfcRelConnectsPorts edges): connected "
                "runs with endpoints / branch points + the longest linear path (the index-run backbone). "
                "Isolated elements have no connected port — the wiring gap to close with connect_mep.",
    }


def _ports(el: Any) -> list:
    from . import mep
    return mep._ports(el)


def graph_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return graph(open_model(ifc_path))
