"""Module-relations graph — the config-driven modules form a data model, and this reads that model
back as a graph: one node per module, one edge per cross-module link. Edges come from **reference**
fields (a record points at another module's record) and **rollup** fields (a module aggregates a
numeric field from records that point at it). Pure over the module registry (a dict of module defs),
so it's testable without a database and drives a node-canvas relations view in the UI."""
from __future__ import annotations

from typing import Any


def _ref_fields(mod: dict) -> list[dict]:
    return [f for f in mod.get("fields", []) if f.get("type") == "reference" and f.get("module")]


def _rollup_fields(mod: dict) -> list[dict]:
    return [f for f in mod.get("fields", []) if f.get("type") == "rollup" and f.get("source_module")]


def build(registry: dict[str, dict], workspace: str | None = None) -> dict[str, Any]:
    """Build the module-relations graph from `registry` (key → module def). Optionally restrict to a
    `workspace` (keeps that workspace's modules + any module they reference, so cross-workspace links
    still show their target). Returns nodes (with in/out degree), edges (reference + rollup, deduped),
    and summary metrics (most-referenced modules, orphans with no links)."""
    keys = set(registry)
    # candidate node set: all modules, or a workspace slice + the targets it references
    if workspace:
        selected = {k for k, m in registry.items() if m.get("workspace") == workspace}
        for k in list(selected):
            for f in _ref_fields(registry[k]):
                if f["module"] in keys:
                    selected.add(f["module"])
            for f in _rollup_fields(registry[k]):
                if f["source_module"] in keys:
                    selected.add(f["source_module"])
    else:
        selected = set(keys)

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for k in selected:
        mod = registry.get(k, {})
        for f in _ref_fields(mod):                     # this module → the module it points at
            tgt = f["module"]
            if tgt not in keys:
                continue
            sig = (k, tgt, f.get("name", ""))
            if sig in seen:
                continue
            seen.add(sig)
            edges.append({"source": k, "target": tgt, "field": f.get("name"),
                          "label": f.get("label") or f.get("name"), "kind": "reference"})
        for f in _rollup_fields(mod):                  # records in source_module roll up INTO this module
            src = f["source_module"]
            if src not in keys:
                continue
            sig = (src, k, f.get("name", "") + ":rollup")
            if sig in seen:
                continue
            seen.add(sig)
            edges.append({"source": src, "target": k, "field": f.get("name"),
                          "label": f"{f.get('op', 'sum')}({f.get('source_field', '')})", "kind": "rollup"})

    # only keep edges whose endpoints are both in the (possibly workspace-filtered) node set
    node_keys = set(selected)
    if workspace:
        for e in edges:
            node_keys.add(e["source"]); node_keys.add(e["target"])
    edges = [e for e in edges if e["source"] in node_keys and e["target"] in node_keys]

    indeg: dict[str, int] = dict.fromkeys(node_keys, 0)
    outdeg: dict[str, int] = dict.fromkeys(node_keys, 0)
    for e in edges:
        outdeg[e["source"]] = outdeg.get(e["source"], 0) + 1
        indeg[e["target"]] = indeg.get(e["target"], 0) + 1

    nodes = []
    for k in sorted(node_keys):
        m = registry.get(k, {})
        nodes.append({"key": k, "label": m.get("name", k), "section": m.get("section", ""),
                      "workspace": m.get("workspace", ""), "icon": m.get("icon", ""),
                      "in_degree": indeg.get(k, 0), "out_degree": outdeg.get(k, 0)})

    top = sorted(({"key": n["key"], "label": n["label"], "in_degree": n["in_degree"]}
                  for n in nodes if n["in_degree"] > 0), key=lambda x: -x["in_degree"])[:8]
    orphans = [n["key"] for n in nodes if n["in_degree"] == 0 and n["out_degree"] == 0]
    return {
        "workspace": workspace, "node_count": len(nodes), "edge_count": len(edges),
        "nodes": nodes, "edges": edges,
        "most_referenced": top, "orphan_count": len(orphans),
    }
