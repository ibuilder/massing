"""CityGML → GeoJSON — import city/site context models (the OGC standard behind 3D City Database /
Cesium city tiles) as building footprints the viewer's existing GIS layer can render.

Scope: extract building footprints (posList rings under each Building) → a GeoJSON FeatureCollection
of polygons, with a `height` property when a measuredHeight is present. This reuses the GeoJSON
reference-model path (no new client renderer). Namespace-agnostic (matches by local tag name) so it
works across CityGML 1.0/2.0/3.0 exports."""
from __future__ import annotations

import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all_local(elem, name: str):
    return [e for e in elem.iter() if _local(e.tag) == name]


def _parse_poslist(text: str, dim: int = 3) -> list[list[float]]:
    nums = [float(x) for x in text.replace(",", " ").split()]
    if dim not in (2, 3):
        dim = 3
    # try dim=3 first; if not divisible, fall back to 2
    if len(nums) % 3 != 0 and len(nums) % 2 == 0:
        dim = 2
    ring = []
    for i in range(0, len(nums) - dim + 1, dim):
        x, y = nums[i], nums[i + 1]
        ring.append([x, y])
    return ring


def _height(building) -> float | None:
    for e in building.iter():
        if _local(e.tag) == "measuredHeight" and (e.text or "").strip():
            try:
                return float(e.text.strip())
            except ValueError:
                return None
    return None


def to_geojson(xml_bytes: bytes) -> dict:
    """Parse CityGML → a GeoJSON FeatureCollection of building-footprint polygons."""
    root = ET.fromstring(xml_bytes)
    features = []
    buildings = _find_all_local(root, "Building")
    # some exports nest as BuildingPart; fall back to any element carrying posLists if no Building
    containers = buildings or [root]
    for b in containers:
        height = _height(b) if buildings else None
        rings: list[list[list[float]]] = []
        for pl in _find_all_local(b, "posList"):
            dim = 3
            sd = pl.get("srsDimension")
            if sd and sd.isdigit():
                dim = int(sd)
            ring = _parse_poslist(pl.text or "", dim)
            if len(ring) >= 3:
                if ring[0] != ring[-1]:
                    ring.append(ring[0])                # close the ring
                rings.append(ring)
        if not rings:
            continue
        # largest ring = footprint; keep the biggest by point count (robust without area calc)
        rings.sort(key=len, reverse=True)
        props: dict = {"kind": "building"}
        if height is not None:
            props["height"] = height
        features.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [rings[0]]},
        })
    return {"type": "FeatureCollection", "features": features,
            "meta": {"buildings": len(features), "source": "citygml"}}
