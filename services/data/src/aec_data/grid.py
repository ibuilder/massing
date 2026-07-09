"""Grid + levels reader for the Draft workspace (P1).

A modeler drafts against a **grid** (axes A/B/C × 1/2/3, bubbles at the ends) and **levels**
(storey work-planes). This reads both from the project IFC so the web Draft panel can render them and
snap placement to grid intersections + the active level's elevation:

- Real ``IfcGrid`` axes (``UAxes`` / ``VAxes`` — each an ``IfcGridAxis`` with an ``AxisTag`` and an
  ``AxisCurve`` polyline) when the model has one.
- Otherwise a grid **derived** from ``IfcColumn`` centres (many IFC exports carry no IfcGrid), reusing
  the same column-clustering the 2D drawings use — numbered 1,2,3… on X, lettered A,B,C… on Y.

Levels come from ``IfcBuildingStorey.Elevation`` (metres). Coordinates are returned in metres in the
plan frame ``[E, N]`` = ``[x, y]`` (the Draft panel's convention), near the model origin.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.placement as _place
import ifcopenshell.util.unit as _uunit

from .drawings import _cluster, storey_elevations


def _xy(matrix) -> tuple[float, float]:
    """Translation (x, y) from a 4x4 placement matrix."""
    return float(matrix[0][3]), float(matrix[1][3])


def _polyline_points(curve) -> list[tuple[float, float]]:
    """2D points of an IfcGridAxis AxisCurve (IfcPolyline / IfcLine), else []."""
    try:
        if curve.is_a("IfcPolyline"):
            return [(float(p.Coordinates[0]), float(p.Coordinates[1])) for p in curve.Points]
        if curve.is_a("IfcLine"):
            o = curve.Pnt.Coordinates
            d = curve.Dir.Orientation.DirectionRatios
            mag = curve.Dir.Magnitude
            return [(float(o[0]), float(o[1])),
                    (float(o[0] + d[0] * mag), float(o[1] + d[1] * mag))]
    except Exception:                                 # noqa: BLE001 — a malformed curve is skipped
        return []
    return []


def _from_ifcgrid(model: ifcopenshell.file, grid) -> dict[str, Any]:
    scale = _uunit.calculate_unit_scale(model)        # file units -> metres
    try:
        ox, oy = _xy(_place.get_local_placement(grid.ObjectPlacement))
    except Exception:                                 # noqa: BLE001
        ox, oy = 0.0, 0.0
    axes: list[dict[str, Any]] = []
    for direction, group in (("u", grid.UAxes or []), ("v", grid.VAxes or [])):
        for ax in group:
            pts = _polyline_points(getattr(ax, "AxisCurve", None))
            if len(pts) < 2:
                continue
            (x1, y1), (x2, y2) = pts[0], pts[-1]
            axes.append({"tag": ax.AxisTag or "?", "dir": direction,
                         "start": [(x1 + ox) * scale, (y1 + oy) * scale],
                         "end": [(x2 + ox) * scale, (y2 + oy) * scale]})
    return _finish(axes, "ifcgrid")


def _derived_grid(model: ifcopenshell.file) -> dict[str, Any]:
    """Cluster IfcColumn XY centres into an orthogonal grid (metres) — the common no-IfcGrid case."""
    scale = _uunit.calculate_unit_scale(model)
    cxs: list[float] = []
    cys: list[float] = []
    for col in model.by_type("IfcColumn"):
        try:
            x, y = _xy(_place.get_local_placement(col.ObjectPlacement))
            cxs.append(x * scale)
            cys.append(y * scale)
        except Exception:                             # noqa: BLE001 — skip a column with no placement
            continue
    if len(cxs) < 2:
        return {"source": "none", "axes": [], "intersections": [], "bounds": None,
                "note": "No IfcGrid and too few columns to derive a grid."}
    xlines = _cluster(cxs, 0.4)                        # constant-X → numbered axes 1,2,3…
    ylines = _cluster(cys, 0.4)                        # constant-Y → lettered axes A,B,C…
    ymin, ymax = min(cys), max(cys)
    xmin, xmax = min(cxs), max(cxs)
    pad = 2.0
    axes: list[dict[str, Any]] = []
    for i, x in enumerate(xlines):
        axes.append({"tag": str(i + 1), "dir": "v",
                     "start": [x, ymin - pad], "end": [x, ymax + pad]})
    for j, y in enumerate(ylines):
        axes.append({"tag": chr(ord("A") + j), "dir": "u",
                     "start": [xmin - pad, y], "end": [xmax + pad, y]})
    return _finish(axes, "derived")


def _finish(axes: list[dict[str, Any]], source: str) -> dict[str, Any]:
    """Attach the U×V intersections (snap points) + bounds to an axis list."""
    us = [a for a in axes if a["dir"] == "u"]
    vs = [a for a in axes if a["dir"] == "v"]
    inter: list[dict[str, Any]] = []
    for u in us:
        for v in vs:
            pt = _line_intersect(u["start"], u["end"], v["start"], v["end"])
            if pt is not None:
                inter.append({"x": pt[0], "y": pt[1], "label": f"{u['tag']}-{v['tag']}"})
    xs = [c for a in axes for c in (a["start"][0], a["end"][0])]
    ys = [c for a in axes for c in (a["start"][1], a["end"][1])]
    bounds = {"min": [min(xs), min(ys)], "max": [max(xs), max(ys)]} if xs else None
    return {"source": source, "axes": axes, "intersections": inter, "bounds": bounds}


def _line_intersect(a1, a2, b1, b2):
    """2D intersection of segment a with segment b (infinite lines), or None if parallel."""
    x1, y1 = a1
    x2, y2 = a2
    x3, y3 = b1
    x4, y4 = b2
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return [x1 + t * (x2 - x1), y1 + t * (y2 - y1)]


def read_grid(model: ifcopenshell.file) -> dict[str, Any]:
    """The drafting grid: real IfcGrid axes if present, else derived from IfcColumn centres."""
    try:
        grids = model.by_type("IfcGrid")
        if grids:
            g = _from_ifcgrid(model, grids[0])
            if g["axes"]:
                return g
    except Exception:                                 # noqa: BLE001 — fall back to the derived grid
        pass
    return _derived_grid(model)


def grid_and_levels(model: ifcopenshell.file) -> dict[str, Any]:
    """Everything the Draft panel needs: the grid (axes + snap intersections) + storey levels."""
    return {"grid": read_grid(model), "levels": storey_elevations(model)}
