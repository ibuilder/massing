"""MEP-FITTINGS (R16 Tier-2) — **implied fitting insertion** over the port-connectivity graph.

At every junction and transition of a connected MEP run, a fitting is *implied* by the topology and the
segment sizes — a duct/pipe network can't branch or change diameter or turn a corner without one. This
reads the ``mep_graph`` adjacency and infers, deterministically (no CV — IFC already gives us the
connectivity that others reconstruct from scanned drawings):

- **tee / cross** at each branch **node** (element with degree ≥ 3): a 3-way node → one tee, a 4-way →
  one cross, an *n*-way manifold → (n − 2) tees.
- **reducer** at a segment-to-segment **joint** whose two segments carry a different nominal size.
- **elbow** at a segment-to-segment joint where the two segments **change direction** (the angle between
  their sweep axes, read from the placement, exceeds ``_ELBOW_DEG``). A joint that both turns *and*
  reduces is counted once, as the elbow (a reducing elbow is a single fitting).

Reducer/elbow inference is confined to **segment↔segment** joints where neither element is itself a
branch (degree ≤ 2), so a real authored fitting or a tee's own legs are never double-counted. The counts
roll straight into a QTO ``qto_lines`` block (EA), so buyout + estimate see the fittings the model implies
rather than only the segments drawn. Pure over an opened model — unit-testable on an authored + connected
system.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

_ELBOW_DEG = 30.0   # a segment-to-segment turn beyond this implies an elbow
# nominal-size property keys, widest-first: our authored pset, then standard type/quantity keys
_SIZE_KEYS = ("NominalSize_mm", "NominalDiameter", "OuterDiameter", "OverallDiameter", "Diameter",
              "InnerDiameter", "NominalWidth", "OverallWidth", "Width", "NominalHeight",
              "OverallHeight", "Height")


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _is_segment(el: Any) -> bool:
    try:
        if el.is_a("IfcFlowSegment"):
            return True
    except Exception:                                    # noqa: BLE001 — is_a on an odd entity
        pass
    return "Segment" in el.is_a()


def _nominal_size(el: Any, ue) -> float | None:
    """The element's nominal size in mm — round diameter, else the larger rectangular dimension. Read from
    our sizing pset or the standard type/quantity keys; None when the model carries no size (so a reducer
    isn't guessed at)."""
    if ue is None:
        return None
    try:
        psets = ue.get_psets(el) or {}
    except Exception:                                    # noqa: BLE001 — opaque psets
        return None
    best = 0.0
    for pset in psets.values():
        if not isinstance(pset, dict):
            continue
        for k in _SIZE_KEYS:
            v = _num(pset.get(k))
            if v > best:
                best = v
    return best or None


def _direction(el: Any) -> tuple[float, float, float] | None:
    """The element's sweep/flow axis (unit vector) — the local +Z column of the world placement, which is
    the extrusion direction for our authored segments. Deterministic geometry, no meshing."""
    try:
        import ifcopenshell.util.placement as pl
        m = pl.get_local_placement(el.ObjectPlacement)
        v = (float(m[0][2]), float(m[1][2]), float(m[2][2]))
        n = math.sqrt(sum(x * x for x in v))
        return (v[0] / n, v[1] / n, v[2] / n) if n > 1e-9 else None
    except Exception:                                    # noqa: BLE001 — no/opaque placement
        return None


def _bend_deg(d1, d2) -> float | None:
    """Deviation-from-straight angle between two sweep axes, in [0, 90] — 0 is collinear (parallel *or*
    antiparallel, i.e. a straight run), 90 is a right-angle turn. None if either axis is missing."""
    if d1 is None or d2 is None:
        return None
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(d1, d2))))
    ang = math.degrees(math.acos(dot))
    return min(ang, 180.0 - ang)                         # fold: antiparallel segments are still "straight"


def fittings(model) -> dict[str, Any]:
    """Infer the implied tee / cross / reducer / elbow fittings over the connected MEP runs → counts +
    QTO lines. Deterministic over the model's own port graph + element sizes/placements."""
    from . import mep
    from . import mep_graph as mg

    try:
        import ifcopenshell.util.element as ue
    except Exception:                                    # noqa: BLE001
        ue = None

    els = mg._elements(model)
    id_el = {e.id(): e for e in els}
    port_owner: dict[int, int] = {}
    for e in els:
        for p in mep._ports(e):
            port_owner[p.id()] = e.id()

    adj: dict[int, set] = defaultdict(set)
    for e in els:
        for p in mep._ports(e):
            for cp in mg._connected_ports(p):
                oid = port_owner.get(cp.id())
                if oid is not None and oid != e.id():
                    adj[e.id()].add(oid)
                    adj[oid].add(e.id())

    counts = {"tee": 0, "cross": 0, "reducer": 0, "elbow": 0}
    details: list[dict] = []
    unknown_size_joints = 0

    # --- branch nodes → tees / crosses -------------------------------------------------------------
    for e in els:
        deg = len(adj[e.id()])
        if deg >= 3:
            kind = "cross" if deg == 4 else "tee"
            n = 1 if deg <= 4 else deg - 2               # n-way manifold ≈ (n−2) tees
            counts[kind] += n
            if len(details) < 200:
                details.append({"guid": e.GlobalId, "ifc_class": e.is_a(), "fitting": kind,
                                "count": n, "reason": f"{deg}-way branch node"})

    # --- segment↔segment joints (neither a branch) → elbows / reducers -----------------------------
    seen_edges: set[tuple[int, int]] = set()
    for e in els:
        eid = e.id()
        for nid in adj[eid]:
            key = (eid, nid) if eid < nid else (nid, eid)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            a, b = id_el[key[0]], id_el[key[1]]
            if len(adj[a.id()]) > 2 or len(adj[b.id()]) > 2:
                continue                                 # a branch leg — the tee/cross already covers it
            if not (_is_segment(a) and _is_segment(b)):
                continue                                 # only segment-to-segment joints imply elbow/reducer
            bend = _bend_deg(_direction(a), _direction(b))
            if bend is not None and bend > _ELBOW_DEG:
                counts["elbow"] += 1
                if len(details) < 200:
                    details.append({"guid": a.GlobalId, "ifc_class": a.is_a(), "fitting": "elbow",
                                    "count": 1, "reason": f"run turns {round(bend)}°"})
                continue                                 # a reducing elbow is one fitting — don't also add a reducer
            sa, sb = _nominal_size(a, ue), _nominal_size(b, ue)
            if sa is None or sb is None:
                unknown_size_joints += 1
            elif abs(sa - sb) > 1.0:                     # > 1 mm size step → a reducer/transition
                counts["reducer"] += 1
                if len(details) < 200:
                    details.append({"guid": a.GlobalId, "ifc_class": a.is_a(), "fitting": "reducer",
                                    "count": 1, "reason": f"size {round(sa)}→{round(sb)} mm"})

    total = sum(counts.values())
    labels = {"tee": "MEP tee fitting", "cross": "MEP cross fitting",
              "reducer": "MEP reducer / transition", "elbow": "MEP elbow"}
    order = ("elbow", "tee", "cross", "reducer")
    qto_lines = [{"item": labels[k], "fitting": k, "unit": "EA", "qty": counts[k]} for k in order if counts[k]]
    by_type = [{"type": k, "count": counts[k]} for k in order if counts[k]]

    return {
        "element_count": len(els),
        "fittings": counts,
        "total_fittings": total,
        "by_type": by_type,
        "qto_lines": qto_lines,
        "unknown_size_joints": unknown_size_joints,
        "details": details,
        "note": "Fittings IMPLIED by the port graph + segment sizes/axes (tee/cross at branches, reducer at "
                "a size step, elbow at a direction change) — deterministic, no CV. Counts roll into QTO as "
                "EA lines. " + (
                    f"{unknown_size_joints} joint(s) had no readable size, so a reducer there couldn't be "
                    "inferred." if unknown_size_joints else ""),
    }


def fittings_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return fittings(open_model(ifc_path))
