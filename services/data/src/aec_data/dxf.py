"""Minimal, dependency-free DXF writer (AutoCAD R12 ASCII) for 2D drawing linework.

Emits plan / section / elevation polylines as R12 `POLYLINE`/`VERTEX` entities — the most universally
readable DXF flavour, so any CAD tool (AutoCAD, DraftSight, LibreCAD, BricsCAD, QCAD…) opens the output.
Written by hand rather than pulling a library, so there is **no new dependency and no license exposure**
(the drawing stack is otherwise permissive-only). Coordinates are the view's drawing-plane units (metres).
"""
from __future__ import annotations

import numpy as np


def polylines_to_dxf(polylines, layer: str = "DRAWING", closed_hint: bool = False) -> str:
    """Serialise a list of (n,2) polylines to an R12 DXF document. A polyline is emitted closed when
    `closed_hint` is set or its first and last points coincide."""
    out: list[str] = ["0\nSECTION\n2\nENTITIES\n"]
    for poly in polylines:
        pts = np.asarray(poly, dtype=float)
        if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] < 2:
            continue
        closed = closed_hint or (pts.shape[0] > 2 and bool(np.allclose(pts[0], pts[-1])))
        out.append(f"0\nPOLYLINE\n8\n{layer}\n66\n1\n70\n{1 if closed else 0}\n")
        for p in pts:
            out.append(f"0\nVERTEX\n8\n{layer}\n10\n{float(p[0]):.4f}\n20\n{float(p[1]):.4f}\n30\n0.0\n")
        out.append("0\nSEQEND\n")
    out.append("0\nENDSEC\n0\nEOF\n")
    return "".join(out)
