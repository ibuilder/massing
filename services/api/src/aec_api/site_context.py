"""SITE-1 — open-geodata site context: drop the georeferenced model onto its real surroundings.

Fetches OpenStreetMap features around the project's site — **building footprints** (with height /
storey tags), **roads**, and **land-use parcels** — via the Overpass API, normalized to a plain
GeoJSON FeatureCollection the viewer extrudes as a separate reference layer. Fetch-once semantics:
the router caches the result in object storage, so after the first (opt-in) fetch the viewer stays
fully offline. OSM data is ODbL — the attribution string ships in every payload and the UI shows it.

Follows the `bsdd.py` client pattern: one httpx entry point with an injectable transport so tests run
against a MockTransport, fully offline.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx

ATTRIBUTION = "© OpenStreetMap contributors (ODbL 1.0)"
DEFAULT_URL = "https://overpass-api.de/api/interpreter"
_TIMEOUT = 30.0
_STOREY_M = 3.0                                        # assumed storey height when only levels are tagged


def overpass_url() -> str:
    return os.environ.get("AEC_OVERPASS_URL", DEFAULT_URL)


# --- georef → decimal lat/lon -------------------------------------------------------------------
def dms_to_decimal(dms: Any) -> float | None:
    """IFC compound plane-angle (degrees, minutes, seconds[, millionth-seconds]) → decimal degrees."""
    if dms is None:
        return None
    if isinstance(dms, (int, float)):
        return float(dms)
    try:
        parts = list(dms)
    except TypeError:
        return None
    if not parts:
        return None
    deg = float(parts[0])
    sign = -1.0 if deg < 0 or str(parts[0]).startswith("-") else 1.0
    out = abs(deg)
    if len(parts) > 1:
        out += abs(float(parts[1])) / 60.0
    if len(parts) > 2:
        out += abs(float(parts[2])) / 3600.0
    if len(parts) > 3:
        out += abs(float(parts[3])) / 3_600_000_000.0
    return sign * out


def site_lat_lon(model) -> tuple[float, float] | None:
    """The model's site latitude/longitude in decimal degrees (IfcSite.RefLatitude/RefLongitude)."""
    for site in model.by_type("IfcSite"):
        lat = dms_to_decimal(getattr(site, "RefLatitude", None))
        lon = dms_to_decimal(getattr(site, "RefLongitude", None))
        if lat is not None and lon is not None and (lat or lon):
            return lat, lon
    return None


# --- Overpass → GeoJSON --------------------------------------------------------------------------
def _num_tag(tags: dict, *keys: str) -> float | None:
    for k in keys:
        v = tags.get(k)
        if v is None:
            continue
        try:
            return float(str(v).split()[0].replace(",", "."))   # "12", "12 m", "12,5"
        except (ValueError, IndexError):
            continue
    return None


def _way_coords(el: dict) -> list[list[float]]:
    return [[g["lon"], g["lat"]] for g in el.get("geometry", []) if "lon" in g and "lat" in g]


def to_geojson(overpass: dict) -> dict[str, Any]:
    """Normalize an Overpass `out geom` response to a GeoJSON FeatureCollection with per-feature
    `kind` (building | road | landuse), `height` (m), `levels`, and `name` properties."""
    feats: list[dict[str, Any]] = []
    counts = {"building": 0, "road": 0, "landuse": 0}
    for el in overpass.get("elements", []):
        tags = el.get("tags") or {}
        coords = _way_coords(el)
        if len(coords) < 2:
            continue
        closed = coords[0] == coords[-1] and len(coords) >= 4
        if "building" in tags and closed:
            kind = "building"
            levels = _num_tag(tags, "building:levels")
            height = _num_tag(tags, "height", "building:height")
            if height is None and levels is not None:
                height = levels * _STOREY_M
            props = {"kind": kind, "height": height, "levels": levels,
                     "name": tags.get("name"), "building": tags.get("building")}
            geom: dict[str, Any] = {"type": "Polygon", "coordinates": [coords]}
        elif "highway" in tags:
            kind = "road"
            props = {"kind": kind, "highway": tags.get("highway"), "name": tags.get("name")}
            geom = {"type": "LineString", "coordinates": coords}
        elif "landuse" in tags and closed:
            kind = "landuse"
            props = {"kind": kind, "landuse": tags.get("landuse"), "name": tags.get("name")}
            geom = {"type": "Polygon", "coordinates": [coords]}
        else:
            continue
        counts[kind] += 1
        feats.append({"type": "Feature", "properties": props, "geometry": geom})
    return {"type": "FeatureCollection", "features": feats, "counts": counts}


def overpass_query(lat: float, lon: float, radius: float) -> str:
    around = f"(around:{radius:.0f},{lat:.6f},{lon:.6f})"
    return (
        "[out:json][timeout:25];("
        f'way["building"]{around};'
        f'way["highway"]{around};'
        f'way["landuse"]{around};'
        ");out body geom;"
    )


def fetch(lat: float, lon: float, radius: float = 300.0, *,
          transport: httpx.BaseTransport | None = None) -> dict[str, Any]:
    """Query Overpass and return `{lat, lon, radius, attribution, counts, geojson}`.
    Raises RuntimeError with a friendly message on network/HTTP trouble."""
    # Overpass usage policy: identify the client (the default UA is rejected with 406)
    kwargs: dict[str, Any] = {"timeout": _TIMEOUT, "headers": {
        "User-Agent": "Massing-BIM/0.3 (+https://massing.build; site-context layer)",
        "Accept": "application/json"}}
    if transport is not None:
        kwargs["transport"] = transport
    try:
        with httpx.Client(**kwargs) as client:
            r = client.post(overpass_url(), data={"data": overpass_query(lat, lon, radius)})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Overpass fetch failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Overpass returned a non-JSON response (server busy?)") from exc
    gj = to_geojson(data)
    counts = gj.pop("counts")
    return {"lat": lat, "lon": lon, "radius": radius, "attribution": ATTRIBUTION,
            "counts": counts, "geojson": gj}
