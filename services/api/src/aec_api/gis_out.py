"""GIS-OUT (R14) — lean BIM → GIS export: the building **footprint + site point as WGS84 GeoJSON**, so
the model drops onto a real web map / GIS without a heavy CityGML round-trip.

Anchors on the model's ``IfcSite`` reference latitude/longitude (read via ``georef``) and transforms the
elements' plan bounding box from local metres to lat/long with an **equirectangular local-tangent-plane**
approximation, rotated by the model's true-north bearing. Dependency-free (no pyproj) and building-scale
accurate — good for placing a footprint on a map, not a survey-grade reprojection. Returns
``available=False`` when the model carries no site lat/long.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell


def _dms_to_deg(dms: Any) -> float | None:
    """IFC compound plane-angle [deg, min, sec, millionths] → decimal degrees."""
    if not dms:
        return None
    d = list(dms) + [0, 0, 0, 0]
    deg, minute, sec, milli = d[0] or 0, d[1] or 0, d[2] or 0, d[3] or 0
    sign = -1.0 if deg < 0 else 1.0
    return round(sign * (abs(deg) + minute / 60.0 + sec / 3600.0 + milli / 3.6e9), 8)


def to_geojson(model: ifcopenshell.file) -> dict[str, Any]:
    """Export the footprint bbox + site point as a WGS84 GeoJSON FeatureCollection."""
    import ifcopenshell.util.placement as uplace
    import ifcopenshell.util.unit as uunit

    from . import georef

    gr = georef.georeferencing(model)
    site = gr.get("site") or {}
    lat0 = _dms_to_deg(site.get("ref_latitude"))
    lon0 = _dms_to_deg(site.get("ref_longitude"))
    if lat0 is None or lon0 is None:
        return {"available": False,
                "message": "model has no IfcSite reference lat/long — set georeferencing first",
                "geojson": None}

    bearing = ((gr.get("map_conversion") or {}).get("true_north_bearing_deg")) or 0.0
    scale = uunit.calculate_unit_scale(model)          # file units → metres
    xs: list[float] = []
    ys: list[float] = []
    for e in model.by_type("IfcElement"):
        pl = getattr(e, "ObjectPlacement", None)
        if pl is None:
            continue
        try:
            m = uplace.get_local_placement(pl)
            xs.append(float(m[0][3]) * scale)
            ys.append(float(m[1][3]) * scale)
        except Exception:                              # noqa: BLE001 — skip un-placeable elements
            continue
    if not xs:
        return {"available": False, "message": "no placed elements to bound", "geojson": None}

    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    br = math.radians(bearing)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0)) or 1.0
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)]
    ring = []
    for x, y in corners:
        # rotate the local (east-ish, north-ish) offset by the true-north bearing, then equirectangular
        ex = x * math.cos(br) - y * math.sin(br)
        ny = x * math.sin(br) + y * math.cos(br)
        ring.append([round(lon0 + ex / m_per_deg_lon, 8), round(lat0 + ny / m_per_deg_lat, 8)])

    proj = model.by_type("IfcProject")
    name = (proj[0].Name if proj and proj[0].Name else None) or "Building"
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"kind": "site", "name": name},
         "geometry": {"type": "Point", "coordinates": [lon0, lat0]}},
        {"type": "Feature",
         "properties": {"kind": "footprint", "name": name,
                        "width_m": round(maxx - minx, 2), "depth_m": round(maxy - miny, 2)},
         "geometry": {"type": "Polygon", "coordinates": [ring]}},
    ]}
    return {
        "available": True, "crs": "EPSG:4326", "geojson": fc,
        "anchor": {"lat": lat0, "lon": lon0, "true_north_bearing_deg": bearing},
        "note": "Footprint bounding box + site point in WGS84, anchored on the IfcSite reference "
                "lat/long via an equirectangular local-tangent transform (building-scale accurate; not a "
                "survey-grade reprojection).",
    }
