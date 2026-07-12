"""Shared coordinates / georeferencing — extract a model's real-world placement so federated models
and **BIM-to-field setout** share one survey basis (the "Construction Execution → BIM-to-field layout"
layer of the BIM control stack). Reads the full IfcMapConversion (eastings/northings/height, the X-axis
rotation → **true-north bearing**, and scale) and the IfcProjectedCRS (EPSG name, datums, map
projection) — not just the eastings/northings the alignment report uses. Reports a BSI **LoGeoRef**
level (0/10/20/40/50) so a coordinator can see at a glance how well-georeferenced a model is.

Pure over an already-opened ifcopenshell model (no file I/O here)."""
from __future__ import annotations

import math
from typing import Any

_LEVEL_LABEL = {
    0: "Not georeferenced", 10: "LoGeoRef 10 (elevation)", 20: "LoGeoRef 20 (lat/long)",
    40: "LoGeoRef 40 (map conversion)", 50: "LoGeoRef 50 (projected CRS)",
}


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def georeferencing(model) -> dict[str, Any]:
    """Full georeferencing picture for one model: map conversion (with true-north bearing + scale),
    projected CRS, site lat/long fallback, and the implied LoGeoRef level."""
    out: dict[str, Any] = {"georeferenced": False, "map_conversion": None, "crs": None, "site": None}

    mc = next(iter(model.by_type("IfcMapConversion")), None)
    if mc is not None:
        ab = _num(getattr(mc, "XAxisAbscissa", None))
        ordn = _num(getattr(mc, "XAxisOrdinate", None))
        bearing = None
        if ab is not None and ordn is not None and (ab or ordn):
            # the map/grid X-axis (easting) direction relative to the model X-axis → true-north bearing
            bearing = round(math.degrees(math.atan2(ordn, ab)) % 360, 4)
        out["map_conversion"] = {
            "eastings": _num(getattr(mc, "Eastings", None)),
            "northings": _num(getattr(mc, "Northings", None)),
            "orthogonal_height": _num(getattr(mc, "OrthogonalHeight", None)),
            "x_axis_abscissa": ab, "x_axis_ordinate": ordn,
            "true_north_bearing_deg": bearing,
            "scale": _num(getattr(mc, "Scale", None)) or 1.0,
        }
        out["georeferenced"] = True
        tc = getattr(mc, "TargetCRS", None)
        if tc is not None and tc.is_a("IfcProjectedCRS"):
            out["crs"] = {
                "name": getattr(tc, "Name", None), "description": getattr(tc, "Description", None),
                "geodetic_datum": getattr(tc, "GeodeticDatum", None),
                "vertical_datum": getattr(tc, "VerticalDatum", None),
                "map_projection": getattr(tc, "MapProjection", None),
                "map_zone": getattr(tc, "MapZone", None),
            }

    for site in model.by_type("IfcSite"):
        lat, lon = getattr(site, "RefLatitude", None), getattr(site, "RefLongitude", None)
        elev = _num(getattr(site, "RefElevation", None))
        if lat or lon or elev is not None:
            out["site"] = {"ref_latitude": list(lat) if lat else None,
                           "ref_longitude": list(lon) if lon else None, "ref_elevation": elev}
            break

    lvl = 0
    if out["site"] and out["site"].get("ref_elevation") is not None:
        lvl = 10
    if out["site"] and (out["site"].get("ref_latitude") or out["site"].get("ref_longitude")):
        lvl = 20
    if out["map_conversion"]:
        lvl = 40
    if out["crs"] and out["crs"].get("name"):
        lvl = 50
    out["level"] = lvl
    out["level_label"] = _LEVEL_LABEL[lvl]
    out["note"] = ("Shared-coordinates basis for federation + BIM-to-field setout. LoGeoRef per BSI: "
                   "50 = projected CRS + map conversion; 40 = map conversion; 20 = site lat/long; "
                   "10 = elevation only; 0 = none.")
    return out
