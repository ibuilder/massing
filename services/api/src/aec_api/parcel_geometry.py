"""PARCEL-IMPORT (R17 Sprint F) — cadastral **parcel geometry** ingest (GeoJSON / WKT, upload-driven — no
government scraping) → deterministic site math the zoning/feasibility work keys on.

Parses a parcel boundary (a GeoJSON Polygon/Feature or a WKT ``POLYGON``), computes **area / perimeter /
centroid / bbox** (shoelace over projected metres; lon/lat is converted equirectangularly at the centroid
latitude — good to ~0.1% at parcel scale), and — when a zoning envelope + a proposal are given — checks
**FAR / lot coverage / height** against the limits, reporting the slack or the violation on each axis.
"""
from __future__ import annotations

import json
import math
from typing import Any

_R_EARTH = 6_371_000.0


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def parse_boundary(geojson: Any = None, wkt: str | None = None) -> list[tuple[float, float]]:
    """The outer ring [(x, y)…] from a GeoJSON Polygon/Feature(/dict or JSON string) or a WKT POLYGON.
    Raises ValueError on anything unparseable."""
    if wkt:
        # Structural parse, NO regex — a lazy `\s*(.+?)\s*\)\)` pattern here was polynomial on crafted
        # whitespace (CodeQL py/polynomial-redos); find/rfind is linear and the input is size-capped.
        w = str(wkt).strip()
        if len(w) > 20_000:
            raise ValueError("WKT too large (a parcel boundary should be well under 20k chars)")
        if not w.upper().startswith("POLYGON"):
            raise ValueError("WKT must be a POLYGON ((x y, x y, ...))")
        i, j = w.find("(("), w.rfind("))")
        if i < 0 or j <= i + 2:
            raise ValueError("WKT must be a POLYGON ((x y, x y, ...))")
        pts = []
        for pair in w[i + 2:j].split(","):
            xy = pair.split()
            if len(xy) < 2:
                raise ValueError(f"bad WKT coordinate: {pair!r}")
            pts.append((float(xy[0]), float(xy[1])))
        return pts
    g = geojson
    if isinstance(g, str):
        g = json.loads(g)
    if not isinstance(g, dict):
        raise ValueError("boundary must be GeoJSON (Polygon/Feature) or WKT")
    if g.get("type") == "Feature":
        g = g.get("geometry") or {}
    if g.get("type") == "Polygon":
        rings = g.get("coordinates") or []
        if not rings or len(rings[0]) < 3:
            raise ValueError("GeoJSON Polygon needs an outer ring of ≥3 points")
        return [(float(p[0]), float(p[1])) for p in rings[0]]
    raise ValueError(f"unsupported GeoJSON type: {g.get('type')!r}")


def _is_lonlat(pts: list[tuple[float, float]]) -> bool:
    return all(abs(x) <= 180.0 and abs(y) <= 90.0 for x, y in pts)


def _to_metres(pts: list[tuple[float, float]]) -> tuple[list[tuple[float, float]], bool]:
    """Equirectangular projection at the centroid latitude when the ring looks like lon/lat."""
    if not _is_lonlat(pts):
        return pts, False
    lat0 = math.radians(sum(p[1] for p in pts) / len(pts))
    k = math.cos(lat0)
    return [(math.radians(x) * _R_EARTH * k, math.radians(y) * _R_EARTH) for x, y in pts], True


def analyze(geojson: Any = None, wkt: str | None = None, parcel_id: str | None = None,
            zoning: dict | None = None, proposal: dict | None = None) -> dict[str, Any]:
    """Parcel metrics (+ optional FAR / coverage / height compliance vs a zoning envelope)."""
    ring = parse_boundary(geojson, wkt)
    if ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        raise ValueError("a parcel boundary needs at least 3 distinct points")
    m, was_lonlat = _to_metres(ring)

    # shoelace area + perimeter over projected metres
    area2 = 0.0
    perim = 0.0
    for i in range(len(m)):
        x1, y1 = m[i]
        x2, y2 = m[(i + 1) % len(m)]
        area2 += x1 * y2 - x2 * y1
        perim += math.hypot(x2 - x1, y2 - y1)
    area = abs(area2) / 2.0
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)

    out: dict[str, Any] = {
        "parcel_id": parcel_id,
        "vertices": len(ring), "coordinates_were_lonlat": was_lonlat,
        "area_m2": round(area, 1), "area_acres": round(area / 4046.856, 3),
        "perimeter_m": round(perim, 1),
        "centroid": {"x": round(cx, 6), "y": round(cy, 6)},
        "bbox": {"minx": min(p[0] for p in ring), "miny": min(p[1] for p in ring),
                 "maxx": max(p[0] for p in ring), "maxy": max(p[1] for p in ring)},
        "note": "Parcel metrics from the uploaded boundary (GeoJSON/WKT — no government scraping). Lon/lat "
                "rings are projected equirectangularly at the centroid latitude (~0.1% at parcel scale).",
    }

    if zoning or proposal:
        z, p = zoning or {}, proposal or {}
        checks = []
        gfa, foot, height = _num(p.get("gfa_m2")), _num(p.get("footprint_m2")), _num(p.get("height_m"))
        max_far, max_cov, max_h = _num(z.get("max_far")), _num(z.get("max_coverage")), _num(z.get("max_height_m"))
        if area > 0 and gfa:
            far = round(gfa / area, 3)
            checks.append({"metric": "FAR", "value": far, "limit": max_far or None,
                           "ok": (far <= max_far) if max_far else None,
                           "slack": round(max_far - far, 3) if max_far else None,
                           "max_gfa_m2": round(max_far * area, 1) if max_far else None})
        if area > 0 and foot:
            cov = round(foot / area, 3)
            checks.append({"metric": "coverage", "value": cov, "limit": max_cov or None,
                           "ok": (cov <= max_cov) if max_cov else None,
                           "slack": round(max_cov - cov, 3) if max_cov else None})
        if height:
            checks.append({"metric": "height_m", "value": height, "limit": max_h or None,
                           "ok": (height <= max_h) if max_h else None,
                           "slack": round(max_h - height, 1) if max_h else None})
        judged = [c for c in checks if c["ok"] is not None]
        out["compliance"] = {
            "checks": checks,
            "ok": all(c["ok"] for c in judged) if judged else None,
            "violations": [c["metric"] for c in judged if not c["ok"]],
        }
    return out
