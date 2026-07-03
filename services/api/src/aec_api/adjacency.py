"""Concept space programming — the adjacency graph that sits upstream of the massing generator.

Before a building is massed, an architect programs it: what spaces, how big, and which should sit next
to which. This engine treats the space-program records as a graph — each program element is a node
(with its area and quantity), and its "should be adjacent to" preferences are the edges. It rolls the
program into a gross-area target and a mix by use (the numbers the zoning→massing generator and the
proforma consume), and reports which adjacency preferences are satisfiable from the program that
exists. Deterministic; the reusable-pattern idea competitors sell reduces here to a transparent graph
over the project's own program."""
from __future__ import annotations

from typing import Any

from . import modules as me

# Circulation/core/BOH/mechanical are the "grossing" space that pads net program up to gross area.
NET_TYPES = ("Residential Unit", "Office", "Retail", "Amenity")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def summary(db, pid: str) -> dict[str, Any]:
    """Program rollup + adjacency graph: total/gross/net area, mix by use, the node/edge graph, and
    which adjacency preferences can be satisfied by the program that exists."""
    spaces = me.list_records(db, "space_program", pid, limit=10000)
    by_type: dict[str, dict] = {}
    nodes = []
    total = 0.0
    types_present: set[str] = set()
    for s in spaces:
        d = _d(s)
        t = d.get("space_type") or "Other"
        qty = int(_f(d.get("quantity")) or 1)
        area = _f(d.get("target_area_sf")) * qty
        total += area
        types_present.add(t)
        b = by_type.setdefault(t, {"count": 0, "area": 0.0})
        b["count"] += qty
        b["area"] += area
        nodes.append({"id": s.get("ref"), "name": d.get("name") or s.get("ref"), "type": t,
                      "area": round(area, 0), "quantity": qty,
                      "adjacent_to": d.get("adjacent_to") or []})

    # edges: a space -> each requested adjacency type (flag whether that type exists in the program)
    edges = []
    for n in nodes:
        for target in n["adjacent_to"]:
            edges.append({"from": n["id"], "from_type": n["type"], "to_type": target,
                          "satisfiable": target in types_present})
    unmet = [e for e in edges if not e["satisfiable"]]

    net = sum(v["area"] for t, v in by_type.items() if t in NET_TYPES)
    efficiency = round(100 * net / total, 1) if total else None
    return {
        "spaces": len(spaces), "total_area_sf": round(total, 0),
        "net_area_sf": round(net, 0), "efficiency_pct": efficiency,
        "by_type": {t: {"count": v["count"], "area": round(v["area"], 0),
                        "pct": round(100 * v["area"] / total, 1) if total else 0}
                    for t, v in sorted(by_type.items(), key=lambda kv: -kv[1]["area"])},
        "graph": {"nodes": nodes, "edges": edges},
        "adjacency": {"total": len(edges), "satisfiable": len(edges) - len(unmet),
                      "unmet": [{"from_type": e["from_type"], "to_type": e["to_type"]} for e in unmet]},
        "massing_hints": {"gross_area_sf": round(total, 0), "net_area_sf": round(net, 0),
                          "mix_pct": {t: round(100 * v["area"] / total, 1) if total else 0
                                      for t, v in by_type.items() if t in NET_TYPES}},
        "note": "The program as a graph: nodes are spaces (area x quantity), edges are adjacency "
                "preferences. Net = leasable/occupiable use; the gross area and use mix feed the "
                "zoning->massing generator and the proforma.",
    }
