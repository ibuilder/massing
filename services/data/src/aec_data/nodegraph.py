"""AUTH-VS · visual node-based authoring — the execution engine.

The edit-recipe log already *is* a graph: each recipe is a node, and one recipe's output (a created GUID)
feeds the next (a base plate needs the column it sits on). This runs a **recipe graph** — a set of recipe
nodes wired by data dependencies — as a single authoring pass: topologically order the nodes, apply each
recipe on one open model, and thread upstream outputs into downstream params.

A graph is `{"nodes": [{"id", "recipe", "params"}], "edges": [{"from", "to"}]}`. A param value may
reference an upstream node's output with `{"$from": "<node id>", "key"?: "<field>"}` — resolved to that
node's returned GUID (a bare string result, or `result[key]`, defaulting to a `guid`/first-value field).
Order comes from the edges (a Kahn topological sort); with no edges, node array order is used. This is the
no-code sibling of the AI command bar + the sandboxed `execute_ifc_code`, over the same GUID-stable
`RECIPES` registry.
"""
from __future__ import annotations

from typing import Any


def _resolve_output(output: Any, key: str | None) -> Any:
    """Pick the value a downstream param wants from an upstream node's result. Explicit `key` wins; else
    a bare string is used as-is, and a dict yields its `guid` (or first value) — the common 'the thing I
    just made' reference."""
    if key is not None:
        if isinstance(output, dict):
            return output.get(key)
        return output
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        if "guid" in output:
            return output["guid"]
        vals = list(output.values())
        return vals[0] if vals else None
    return output


def _resolve_params(params: Any, outputs: dict[str, Any]) -> Any:
    """Deep-resolve `{"$from": id, key?}` references in a param structure against already-run outputs."""
    if isinstance(params, dict):
        if "$from" in params:
            ref = params["$from"]
            if ref not in outputs:
                raise ValueError(f"node param references '{ref}', which has no output (bad order or id)")
            return _resolve_output(outputs[ref], params.get("key"))
        return {k: _resolve_params(v, outputs) for k, v in params.items()}
    if isinstance(params, list):
        return [_resolve_params(v, outputs) for v in params]
    return params


def _topo_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn topological sort of node ids by dependency edges (`from` must run before `to`). Falls back to
    array order when there are no edges; raises on an unknown id or a cycle."""
    ids = [n["id"] for n in nodes]
    idset = set(ids)
    if len(idset) != len(ids):
        raise ValueError("duplicate node id in the graph")
    if not edges:
        return ids
    indeg = dict.fromkeys(ids, 0)
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        a, b = e.get("from"), e.get("to")
        if a not in idset or b not in idset:
            raise ValueError(f"edge references an unknown node id: {a!r} -> {b!r}")
        adj[a].append(b)
        indeg[b] += 1
    # preserve array order among ready nodes for a stable, predictable run
    ready = [i for i in ids if indeg[i] == 0]
    order: list[str] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
        ready.sort(key=ids.index)
    if len(order) != len(ids):
        raise ValueError("the recipe graph has a cycle")
    return order


def run(model, graph: dict) -> dict[str, Any]:
    """Execute a recipe graph on an open model (in place). Returns {order, outputs:{id:result},
    node_count}. Raises ValueError on a bad graph (unknown recipe/id, cycle, dangling ref)."""
    from .edit import RECIPES

    raw = graph.get("nodes") or []
    if not raw:
        return {"order": [], "outputs": {}, "node_count": 0}
    if len({n["id"] for n in raw}) != len(raw):
        raise ValueError("duplicate node id in the graph")
    nodes = {n["id"]: n for n in raw}
    order = _topo_order(list(nodes.values()), graph.get("edges") or [])
    outputs: dict[str, Any] = {}
    for nid in order:
        node = nodes[nid]
        recipe = node.get("recipe")
        if recipe not in RECIPES:
            raise ValueError(f"node {nid!r}: unknown recipe {recipe!r}")
        params = _resolve_params(node.get("params") or {}, outputs)
        outputs[nid] = RECIPES[recipe](model, params)
    return {"order": order, "outputs": outputs, "node_count": len(order)}


def execute_graph(ifc_path: str, graph: dict, out_path: str) -> dict[str, Any]:
    """Open the model, run the recipe graph, and write the result — the single-call authoring pass a
    visual node canvas commits. Returns {order, outputs, node_count, out}."""
    from .ifc_loader import open_model

    model = open_model(ifc_path)
    result = run(model, graph)
    model.write(out_path)
    result["out"] = out_path
    return result
