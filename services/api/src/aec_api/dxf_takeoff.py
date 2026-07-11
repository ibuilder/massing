"""DWG/DXF quantity takeoff — pull lengths, areas and counts out of a 2D CAD drawing, grouped by
layer, so estimating isn't IFC-only. Built on **ezdxf** (MIT, pure-Python) which reads DXF natively;
DWG must first be converted to DXF (ODA File Converter or similar — kept optional/external, no AGPL).

Estimators still work from 2D CAD constantly. This turns a floor plan into measured quantities per
layer — linear metres (walls, pipe, conduit runs), enclosed area (rooms, slabs), and block counts
(doors, fixtures, devices) — which map cleanly onto unit rates or the assembly catalog.

Pure over a file path; ezdxf is lazy-imported so importing this module never hard-fails."""
from __future__ import annotations

import math
from typing import Any

# DXF $INSUNITS header code -> metres-per-unit. 0 = unitless (assume the drawing is already in metres
# and flag it). Covers the common architectural/civil cases.
_INSUNITS_M = {0: 1.0, 1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 8: 2.54e-5, 9: 0.001, 10: 0.9144}
_INSUNITS_LABEL = {0: "unitless (assumed m)", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m",
                   8: "microinch", 9: "mil", 10: "yd"}


def _dist(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _poly_points(e) -> tuple[list[tuple[float, float]], bool]:
    """(x,y) vertices + closed flag for LWPOLYLINE / POLYLINE."""
    try:
        if e.dxftype() == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            return pts, bool(e.closed)
        # old-style POLYLINE
        pts = [(v.dxf.location[0], v.dxf.location[1]) for v in e.vertices]
        return pts, bool(e.is_closed)
    except Exception:       # noqa: BLE001 — malformed entity: skip, don't crash the whole takeoff
        return [], False


def _polyline_length(pts: list[tuple[float, float]], closed: bool) -> float:
    if len(pts) < 2:
        return 0.0
    total = sum(_dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if closed:
        total += _dist(pts[-1], pts[0])
    return total


def _shoelace_area(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 3:
        return 0.0
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def takeoff(path: str) -> dict[str, Any]:
    """Read a DXF and return quantities grouped by layer: linear length (LINE/ARC/polyline runs),
    enclosed area (closed polylines + circles), and block-insert counts, plus per-layer entity counts.
    Lengths/areas are converted to metres from the drawing's $INSUNITS. Raises RuntimeError if ezdxf
    is unavailable or the file can't be read as DXF."""
    try:
        import ezdxf  # lazy — keeps module import cheap and the dep swappable
    except ImportError as e:  # pragma: no cover - dep is declared, guard is belt-and-suspenders
        raise RuntimeError("DXF takeoff needs the 'ezdxf' package") from e
    try:
        doc = ezdxf.readfile(path)
    except Exception as e:  # noqa: BLE001 — surface a clean 4xx-able error for a bad upload
        raise RuntimeError(f"Not a readable DXF: {e}") from e

    code = int(doc.header.get("$INSUNITS", 0) or 0)
    m = _INSUNITS_M.get(code, 1.0)
    m2 = m * m

    layers: dict[str, dict[str, Any]] = {}
    blocks: dict[str, int] = {}

    def bucket(name: str) -> dict[str, Any]:
        return layers.setdefault(name or "0", {"layer": name or "0", "entities": 0,
                                               "length_m": 0.0, "area_m2": 0.0, "inserts": 0,
                                               "by_type": {}})

    for e in doc.modelspace():
        t = e.dxftype()
        b = bucket(getattr(e.dxf, "layer", "0"))
        b["entities"] += 1
        b["by_type"][t] = b["by_type"].get(t, 0) + 1
        if t == "LINE":
            b["length_m"] += _dist((e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])) * m
        elif t == "ARC":
            sweep = abs((e.dxf.end_angle - e.dxf.start_angle) % 360)
            b["length_m"] += e.dxf.radius * math.radians(sweep) * m
        elif t == "CIRCLE":
            b["area_m2"] += math.pi * e.dxf.radius ** 2 * m2
        elif t in ("LWPOLYLINE", "POLYLINE"):
            pts, closed = _poly_points(e)
            b["length_m"] += _polyline_length(pts, closed) * m
            if closed:
                b["area_m2"] += _shoelace_area(pts) * m2
        elif t == "INSERT":
            b["inserts"] += 1
            blocks[e.dxf.name] = blocks.get(e.dxf.name, 0) + 1

    out_layers = sorted(
        ({**v, "length_m": round(v["length_m"], 3), "area_m2": round(v["area_m2"], 3)}
         for v in layers.values()),
        key=lambda x: (x["length_m"] + x["area_m2"]), reverse=True)
    return {
        "units": _INSUNITS_LABEL.get(code, str(code)),
        "unitless": code == 0,
        "layer_count": len(out_layers),
        "entity_count": sum(v["entities"] for v in out_layers),
        "total_length_m": round(sum(v["length_m"] for v in out_layers), 3),
        "total_area_m2": round(sum(v["area_m2"] for v in out_layers), 3),
        "layers": out_layers,
        "blocks": sorted(({"block": k, "count": v} for k, v in blocks.items()),
                         key=lambda x: x["count"], reverse=True),
    }
