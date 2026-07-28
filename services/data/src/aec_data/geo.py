"""
Georeferencing — where the building actually is on the earth.

CLAUDE.md has named this a watch-out from the beginning ("preserve real coordinates for export,
render near scene origin") and until now nothing implemented it: the only georeferencing code in the
tree lived inside ifcopenshell's own package. A model with no georeferencing is fine on its own and
useless the moment it has to meet a survey, a site plan, a GIS layer or another discipline's model.

Shapes match the kernel's `project-schema/geo.ts` (`GeoReference`, `GeoAccuracy`, `LinearUnit`) so a
value read here is the value the viewer already understands. Adopting the contract is the point —
inventing a parallel one would be the same drift this codebase keeps writing tests to prevent.

**Read is best-effort and honest about its source.** IFC4 carries this properly in `IfcMapConversion`
+ `IfcProjectedCRS`. IFC2X3 has no such entity, so all that survives is `IfcSite`'s latitude/longitude
and the representation context's true-north vector. Those are different qualities of answer, and the
result says which one it is rather than presenting a rough site coordinate as a survey control point.
"""
from __future__ import annotations

import math
from typing import Any

import ifcopenshell

#: Metres per unit, matching the kernel's `LinearUnit`.
METRES_PER_UNIT: dict[str, float] = {
    "m": 1.0, "mm": 0.001, "cm": 0.01, "ft": 0.3048, "us-ft": 1200.0 / 3937.0,
}


def dms_to_degrees(compound) -> float | None:
    """IFC compound plane angle -> decimal degrees.

    IFC stores latitude and longitude as `(degrees, minutes, seconds[, millionths])` — a tuple, not a
    number. Reading element 0 and calling it a coordinate is a real and easy mistake: it silently
    puts the building up to a degree away, which is tens of kilometres, while looking like a plausible
    number. **The sign belongs to the whole angle**, so a southern latitude is (-33, -52, -4) and
    negating only the degrees would move the site to the wrong hemisphere-ish place; taking the
    magnitude of each part and applying one sign at the end is what makes that safe.
    """
    if compound is None:
        return None
    try:
        parts = list(compound)
    except TypeError:
        return float(compound)
    if not parts:
        return None
    sign = -1.0 if any(p < 0 for p in parts if p is not None) else 1.0
    deg = abs(parts[0] or 0)
    minutes = abs(parts[1]) if len(parts) > 1 and parts[1] is not None else 0
    seconds = abs(parts[2]) if len(parts) > 2 and parts[2] is not None else 0
    millionths = abs(parts[3]) if len(parts) > 3 and parts[3] is not None else 0
    return sign * (deg + minutes / 60.0 + (seconds + millionths / 1e6) / 3600.0)


def degrees_to_dms(value: float) -> tuple[int, int, int, int]:
    """Decimal degrees -> the IFC compound form, sign carried on every component.

    ifcopenshell writes what it is given; a tuple whose parts disagree in sign is not a coordinate
    anyone can read back. Round-trips with `dms_to_degrees` to within a micro-arcsecond — asserted,
    because a read/write pair that drifts is the defect this codebase has a memory about.
    """
    sign = -1 if value < 0 else 1
    v = abs(value)
    deg = int(v)
    rem = (v - deg) * 60.0
    minutes = int(rem)
    rem = (rem - minutes) * 60.0
    seconds = int(rem)
    millionths = int(round((rem - seconds) * 1e6))
    if millionths >= 1_000_000:          # carry, or a round trip lands on 60.000000"
        millionths -= 1_000_000
        seconds += 1
    if seconds >= 60:
        seconds -= 60
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        deg += 1
    return (sign * deg, sign * minutes, sign * seconds, sign * millionths)


def true_north_degrees(model: ifcopenshell.file) -> float | None:
    """Rotation from project north to true north, **degrees clockwise**, or None.

    IFC stores this as a 2D direction vector on the representation context, not an angle, and the
    vector points at true north in project coordinates. Project north is +Y, so the angle is measured
    from +Y and clockwise is the surveying convention — `atan2(x, y)`, not the usual `atan2(y, x)`.
    Getting that pair the wrong way round is a mirror error: it reads as plausible and puts east where
    west should be.
    """
    for ctx in model.by_type("IfcGeometricRepresentationContext"):
        tn = getattr(ctx, "TrueNorth", None)
        ratios = getattr(tn, "DirectionRatios", None) if tn else None
        if ratios and len(ratios) >= 2:
            x, y = float(ratios[0]), float(ratios[1])
            if x or y:
                return (math.degrees(math.atan2(x, y))) % 360.0
    return None


def read(model: ifcopenshell.file) -> dict[str, Any]:
    """The model's georeference, shaped like the kernel's `GeoReference`.

    `method` says how the answer was obtained, because the qualities differ by orders of magnitude:

    - `"map-conversion"` — IFC4 `IfcMapConversion` + `IfcProjectedCRS`. A real survey transform.
    - `"site-coordinates"` — only `IfcSite` lat/long survived (IFC2X3, or an exporter that skipped
      the conversion). Fine for putting a pin on a map, not for setting out.
    - `None` — nothing. Reported as `georeferenced: False` rather than defaulted to (0, 0), because a
      building at null island is a wrong answer wearing the shape of a right one.
    """
    out: dict[str, Any] = {"georeferenced": False, "method": None, "units": "m"}

    for u in model.by_type("IfcSIUnit"):
        if getattr(u, "UnitType", None) == "LENGTHUNIT":
            prefix, name = getattr(u, "Prefix", None), getattr(u, "Name", None)
            if name == "METRE":
                out["units"] = {"MILLI": "mm", "CENTI": "cm"}.get(prefix, "m")
            break

    mc = model.by_type("IfcMapConversion") if model.schema != "IFC2X3" else []
    if mc:
        c = mc[0]
        crs = getattr(c, "TargetCRS", None)
        scale = getattr(c, "Scale", None)
        out.update({
            "georeferenced": True,
            "method": "map-conversion",
            "sourceCrs": getattr(crs, "Name", None) if crs else None,
            "verticalDatum": getattr(crs, "VerticalDatum", None) if crs else None,
            # The map conversion's eastings/northings ARE the offset between the local engineering
            # frame and the projected grid — exactly what the kernel calls `originOffset`, and what a
            # renderer must subtract to keep float32 geometry from jittering at 500000-metre values.
            "originOffset": [float(getattr(c, "Eastings", 0.0) or 0.0),
                             float(getattr(c, "Northings", 0.0) or 0.0),
                             float(getattr(c, "OrthogonalHeight", 0.0) or 0.0)],
            "scale": float(scale) if scale else 1.0,
        })
        ax, ay = getattr(c, "XAxisAbscissa", None), getattr(c, "XAxisOrdinate", None)
        if ax is not None and ay is not None and (ax or ay):
            out["trueNorthAngle"] = (math.degrees(math.atan2(float(ay), float(ax)))) % 360.0
        return out

    sites = model.by_type("IfcSite")
    if sites:
        s = sites[0]
        lat = dms_to_degrees(getattr(s, "RefLatitude", None))
        lon = dms_to_degrees(getattr(s, "RefLongitude", None))
        if lat is not None and lon is not None:
            out.update({
                "georeferenced": True,
                "method": "site-coordinates",
                "sourceCrs": "EPSG:4326",       # WGS 84 — what IfcSite lat/long means
                "latitude": lat,
                "longitude": lon,
                "elevation": float(getattr(s, "RefElevation", 0.0) or 0.0),
            })

    tn = true_north_degrees(model)
    if tn is not None:
        out["trueNorthAngle"] = tn
        out["georeferenced"] = out["georeferenced"] or False   # north alone is not a location
    return out


def write_site_coordinates(model: ifcopenshell.file, latitude: float, longitude: float,
                           elevation: float = 0.0) -> str | None:
    """Set `IfcSite` latitude/longitude/elevation. Returns the site's GlobalId, or None if there is
    no site to place — creating one silently would invent spatial structure the author did not."""
    sites = model.by_type("IfcSite")
    if not sites:
        return None
    s = sites[0]
    s.RefLatitude = degrees_to_dms(latitude)
    s.RefLongitude = degrees_to_dms(longitude)
    s.RefElevation = float(elevation)
    return getattr(s, "GlobalId", None)
