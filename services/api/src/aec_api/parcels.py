"""Land / parcel screening — map-based multi-parcel deal discovery over parcels you already hold.

Acres owns the pre-acquisition land-intelligence layer, but the national parcel dataset is a data-
licensing play (a flagged connector — see `parcels_bridge`). The *pure-software* win, which plays to our
existing GIS + feasibility + proforma engines, is **screening**: given a set of parcels (imported GeoJSON,
a connector feed, or hand-entered), filter and rank them by size / zoning / flood / utilities and chain
each straight to a **max-buildable envelope** and a **conceptual cost** — the screen → envelope → proforma
chain Acres cannot do. Deterministic; no external data required for the screen itself."""
from __future__ import annotations

from . import conceptual_estimate as ce

_SQFT_PER_ACRE = 43_560.0


def _num(v) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _acres(p: dict) -> float:
    if p.get("acres") not in (None, ""):
        return _num(p.get("acres"))
    sf = _num(p.get("area_sf") or p.get("sqft"))
    return round(sf / _SQFT_PER_ACRE, 3) if sf else 0.0


def _passes(p: dict, c: dict) -> tuple[bool, list[str]]:
    """(pass, reasons-it-failed)."""
    fails = []
    ac = _acres(p)
    if c.get("min_acres") and ac < _num(c["min_acres"]):
        fails.append(f"{ac:.2f} ac < min {c['min_acres']}")
    if c.get("max_acres") and ac > _num(c["max_acres"]):
        fails.append(f"{ac:.2f} ac > max {c['max_acres']}")
    zin = c.get("zoning_in")
    if zin and str(p.get("zoning", "")).upper() not in {str(z).upper() for z in zin}:
        fails.append(f"zoning {p.get('zoning') or '?'} not in {zin}")
    if c.get("exclude_flood") and str(p.get("flood_zone", "")).upper() in {"A", "AE", "V", "VE", "AO", "AH"}:
        fails.append(f"in flood zone {p.get('flood_zone')}")
    if c.get("require_sewer") and not p.get("sewer"):
        fails.append("no sewer access")
    if c.get("require_water") and not p.get("water"):
        fails.append("no water access")
    if c.get("max_price") and _num(p.get("price")) and _num(p.get("price")) > _num(c["max_price"]):
        fails.append(f"price ${_num(p.get('price')):,.0f} > max")
    return (not fails), fails


def _buildable(p: dict, c: dict) -> dict:
    """Quick max envelope + conceptual cost from area × FAR (the screen → envelope → proforma chain)."""
    ac = _acres(p)
    site_sf = ac * _SQFT_PER_ACRE
    far = _num(p.get("far") or c.get("assume_far"))
    max_gfa = round(site_sf * far, 0) if far else 0
    out = {"acres": ac, "site_sf": round(site_sf, 0), "far": far or None, "max_gfa_sf": max_gfa or None}
    btype = c.get("building_type")
    if max_gfa and btype:
        est = ce.estimate({"building_type": btype, "gfa_sf": max_gfa, "region": c.get("region", "us_average")})
        if "total_cost" in est:
            out["conceptual_cost"] = est["total_cost"]
            out["cost_per_sf"] = est["metrics"]["total_per_sf"]
            price = _num(p.get("price"))
            if price and max_gfa:
                out["land_cost_per_buildable_sf"] = round(price / max_gfa, 2)
    return out


def screen(parcels: list[dict], criteria: dict | None = None) -> dict:
    """Filter + rank parcels by criteria, each with a max-buildable envelope + conceptual cost.

    parcels: [{id, acres|area_sf, zoning, flood_zone, sewer, water, price, far?}].
    criteria: {min_acres, max_acres, zoning_in[], exclude_flood, require_sewer/water, max_price,
               assume_far, building_type, region}."""
    c = criteria or {}
    matches, rejected = [], []
    for p in parcels:
        ok, fails = _passes(p, c)
        row = {"id": p.get("id") or p.get("apn") or p.get("parcel"), "acres": _acres(p),
               "zoning": p.get("zoning"), "flood_zone": p.get("flood_zone"),
               "price": _num(p.get("price")) or None, "buildable": _buildable(p, c)}
        if ok:
            matches.append(row)
        else:
            rejected.append({**row, "failed": fails})
    # rank matches by buildable GFA (opportunity size), then by lowest land cost per buildable sf
    matches.sort(key=lambda r: (-(r["buildable"].get("max_gfa_sf") or 0),
                                r["buildable"].get("land_cost_per_buildable_sf") or 9e9))
    return {"matches": matches, "rejected": rejected,
            "match_count": len(matches), "screened": len(parcels),
            "message": (None if matches else "No parcels passed the screen — loosen the criteria.")}
