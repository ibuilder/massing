"""FEM-EXPORT (R15) — export the W10-7 analytical model to an **OpenSees** (BSD, opensees.berkeley.edu)
`.tcl` input file, so a structural engineer can independently verify the gravity/lateral solver in a
third-party FE solver.

Reads the `IfcStructuralCurveMember` frame (reusing `struct_solve._member_endpoints` for the node
topology), dedupes shared endpoints into OpenSees nodes, fixes the base-level nodes, and writes one
`elasticBeamColumn` per member with a geometric transform chosen per orientation (a column's local axis
is vertical, so it needs a different reference vector than a beam). Units: **kip · inch · ksi**. Section
properties are nominal defaults — the model is a runnable skeleton the analyst re-sections and loads;
this exchanges the *geometry + connectivity + supports*, not a specific design.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.unit as _uu

_IN_PER_M = 1000.0 / 25.4                                # 39.3701
# nominal steel section in a consistent kip-inch-ksi system (analyst replaces per design)
_E_KSI, _G_KSI = 29000.0, 11200.0
_A_IN2, _JX, _IY, _IZ = 20.0, 10.0, 100.0, 300.0
_Z_TOL_IN = 12.0                                         # nodes within 12" of the lowest are "base"


def to_opensees(model: ifcopenshell.file) -> dict[str, Any]:
    """Build the OpenSees `.tcl` for the model's analytical frame. Returns
    `{available, tcl, node_count, element_count, fixed_count}` (available=False when there's no
    analytical model)."""
    from .struct_solve import _member_endpoints

    members = model.by_type("IfcStructuralCurveMember")
    if not members:
        return {"available": False, "tcl": "",
                "message": "No analytical model — run the derive_analytical recipe first.",
                "node_count": 0, "element_count": 0, "fixed_count": 0}

    scale = _uu.calculate_unit_scale(model)              # metres per file unit
    to_in = lambda c: round(float(c) * scale * _IN_PER_M, 2)  # noqa: E731

    nodes: dict[tuple, int] = {}
    order: list[tuple] = []

    def _nid(pt) -> int:
        key = (to_in(pt[0]), to_in(pt[1]), to_in(pt[2]))
        nid = nodes.get(key)
        if nid is None:
            nid = nodes[key] = len(nodes) + 1
            order.append(key)
        return nid

    elems: list[tuple[int, int, bool]] = []              # (n1, n2, is_vertical)
    for cm in members:
        ends = _member_endpoints(cm)
        if not ends:
            continue
        n1, n2 = _nid(ends[0]), _nid(ends[1])
        if n1 == n2:
            continue
        a, b = order[n1 - 1], order[n2 - 1]
        length = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2 + (b[2] - a[2]) ** 2) ** 0.5 or 1.0
        vertical = abs(b[2] - a[2]) / length >= 0.9
        elems.append((n1, n2, vertical))

    if not order or not elems:
        return {"available": False, "tcl": "", "message": "analytical model carries no usable geometry",
                "node_count": 0, "element_count": 0, "fixed_count": 0}

    min_z = min(k[2] for k in order)
    base = [i + 1 for i, k in enumerate(order) if k[2] - min_z <= _Z_TOL_IN]

    lines = [
        "# OpenSees model exported by Massing — analytical frame for third-party verification.",
        "# Units: kip, inch, ksi. Sections are NOMINAL defaults — re-section + apply your load case.",
        "wipe", "model BasicBuilder -ndm 3 -ndf 6", "", "# --- nodes (id x y z) ---"]
    for i, (x, y, z) in enumerate(order, 1):
        lines.append(f"node {i} {x} {y} {z}")
    lines += ["", "# --- restraints: base nodes fully fixed ---"]
    for nid in base:
        lines.append(f"fix {nid} 1 1 1 1 1 1")
    lines += ["", "# --- geometric transforms (1 = beams, 2 = columns/vertical) ---",
              "geomTransf Linear 1 0 0 1", "geomTransf Linear 2 1 0 0",
              "", "# --- elements: elasticBeamColumn eid n1 n2 A E G Jx Iy Iz transfTag ---"]
    for eid, (n1, n2, vert) in enumerate(elems, 1):
        transf = 2 if vert else 1
        lines.append(f"element elasticBeamColumn {eid} {n1} {n2} "
                     f"{_A_IN2} {_E_KSI} {_G_KSI} {_JX} {_IY} {_IZ} {transf}")
    lines += ["", "# Define your load pattern + analysis below (this file is the geometry/supports "
              "skeleton).", ""]
    return {"available": True, "tcl": "\n".join(lines),
            "node_count": len(order), "element_count": len(elems), "fixed_count": len(base)}
