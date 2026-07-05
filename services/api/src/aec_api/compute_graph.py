"""Computational graph (M4) — a Dynamo/Hypar-style node graph over the platform's pure functions.

Inspired by Dynamo "zero-touch" (https://primer2.dynamobim.org): a function becomes a node, its
parameters become input ports (with defaults), and a dict return becomes named output ports. Wire a
node's output port into another's input port and the executor runs the graph in dependency order —
so a designer can chain zoning → structure → schedule → cost → yield without code.

`node_catalog()` lists the nodes (for a palette); `run_graph(graph)` executes {nodes, edges}.
Node functions here are thin, scalar-parametered wrappers around massing/structure/takt/test_fit so
the ports are clean (the "By"-factory convention from the zero-touch primer)."""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

_NODES: dict[str, dict[str, Any]] = {}


def _node(key: str, label: str, category: str, outputs: list[str]) -> Callable:
    """Register a pure function as a graph node; params→inputs (with defaults), `outputs`→ports."""
    def deco(fn: Callable) -> Callable:
        sig = inspect.signature(fn)
        inputs = [{"name": n, "default": (None if p.default is inspect.Parameter.empty else p.default)}
                  for n, p in sig.parameters.items()]
        _NODES[key] = {"key": key, "label": label, "category": category, "fn": fn,
                       "inputs": inputs, "outputs": outputs, "doc": (fn.__doc__ or "").strip().split("\n")[0]}
        return fn
    return deco


# --- nodes (scalar ports → clean zero-touch wrappers over the pure engines) ---
@_node("zoning_massing", "Zoning → Program", "Generative",
       ["floors", "buildable_gfa_sf", "buildable_gfa_m2", "units", "footprint_m2", "building_height_m"])
def zoning_massing(lot_width: float = 40, lot_depth: float = 30, far: float = 3.0,
                   height_limit: float = 0, floor_to_floor: float = 3.2, avg_unit_m2: float = 75) -> dict:
    from aec_data import massing  # type: ignore — the data-service engine
    p = {"lot_width": lot_width, "lot_depth": lot_depth, "far": far, "floor_to_floor": floor_to_floor,
         "avg_unit_m2": avg_unit_m2}
    if height_limit:
        p["height_limit"] = height_limit
    m = massing.compute_massing(p)
    return {k: m[k] for k in ("floors", "buildable_gfa_sf", "buildable_gfa_m2", "units", "footprint_m2", "building_height_m")}


@_node("structure_advisor", "Structural System", "Design",
       ["system", "column_mm", "beam_depth_mm", "slab_mm", "slenderness"])
def structure_advisor(building_height_m: float = 30, floors: int = 8, span_m: float = 7.5) -> dict:
    from . import structure
    r = structure.recommend(building_height_m, int(floors), span_m)
    mm = r["members_mm"]
    return {"system": r["system"], "column_mm": mm["column"], "beam_depth_mm": mm["beam_depth"],
            "slab_mm": mm["slab"], "slenderness": r["slenderness"]}


@_node("takt_schedule", "Takt Schedule", "Construction",
       ["duration_days", "duration_weeks", "floors_per_week", "crew_peak"])
def takt_schedule(floors: int = 8, structure_takt_days: int = 5) -> dict:
    from . import takt
    p = takt.plan(int(floors), [{"name": "Structure", "takt_days": int(structure_takt_days)},
                                {"name": "Envelope", "takt_days": 5}, {"name": "MEP", "takt_days": 6},
                                {"name": "Interiors", "takt_days": 8}, {"name": "Finishes", "takt_days": 6}])
    return {k: p[k] for k in ("duration_days", "duration_weeks", "floors_per_week", "crew_peak")}


@_node("cost_from_gfa", "Cost from GFA", "Finance", ["hard_cost", "soft_cost", "total_cost"])
def cost_from_gfa(buildable_gfa_sf: float = 0, hard_psf: float = 225, soft_pct: float = 0.2,
                  land: float = 0) -> dict:
    hard = buildable_gfa_sf * hard_psf
    soft = hard * soft_pct
    return {"hard_cost": round(hard), "soft_cost": round(soft), "total_cost": round(hard + soft + land)}


@_node("yield_on_cost", "Yield on Cost", "Finance", ["noi", "yield_on_cost", "stabilized_value"])
def yield_on_cost(units: float = 0, rent_per_unit_month: float = 2800, opex_ratio: float = 0.35,
                  total_cost: float = 1, exit_cap: float = 0.05) -> dict:
    pgi = units * rent_per_unit_month * 12
    noi = pgi * (1 - opex_ratio)
    return {"noi": round(noi), "yield_on_cost": round(noi / total_cost, 4) if total_cost else 0.0,
            "stabilized_value": round(noi / exit_cap) if exit_cap else 0}


def node_catalog() -> dict[str, Any]:
    """The node palette (no functions) for a visual editor."""
    return {"nodes": [{k: v for k, v in n.items() if k != "fn"} for n in _NODES.values()]}


def run_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Execute {nodes:[{id,type,params}], edges:[{from,from_port,to,to_port}]} in dependency order.
    Returns each node's output dict + the execution order. Raises on unknown node or a cycle."""
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    for n in nodes.values():
        if n["type"] not in _NODES:
            raise ValueError(f"unknown node type {n['type']!r}")
    deps: dict[str, set] = {nid: set() for nid in nodes}
    for e in edges:
        if e["to"] in deps and e["from"] in nodes:
            deps[e["to"]].add(e["from"])
    order: list[str] = []
    seen: set = set()

    def visit(nid: str, stack: frozenset) -> None:
        if nid in seen:
            return
        if nid in stack:
            raise ValueError(f"cycle through {nid}")
        for d in deps.get(nid, ()):  # noqa
            visit(d, stack | {nid})
        seen.add(nid); order.append(nid)
    for nid in nodes:
        visit(nid, frozenset())

    results: dict[str, dict] = {}
    for nid in order:
        n = nodes[nid]
        spec = _NODES[n["type"]]
        kwargs = dict(n.get("params", {}))
        for e in edges:                       # wired inputs override params
            if e["to"] == nid and e["from"] in results:
                up = results[e["from"]]
                kwargs[e["to_port"]] = up.get(e["from_port"]) if isinstance(up, dict) else up
        valid = {i["name"] for i in spec["inputs"]}
        out = spec["fn"](**{k: v for k, v in kwargs.items() if k in valid})
        results[nid] = out if isinstance(out, dict) else {"result": out}
    return {"order": order, "results": results, "node_count": len(nodes)}
