"""Municipal building-permit open data — an interchangeable, multi-city feed.

Most large US cities publish building/construction permits on a Socrata (SODA) portal with the same
query model, so one client + a per-city registry (domain, dataset, field map) covers them all. Each
city's quirky columns are normalized to one record shape so the rest of the app — the GC permit module
and the GIS overlay — never sees a city-specific schema.

No API key required (Socrata allows anonymous reads, rate-limited); a free Socrata app token can be set
via SOCRATA_APP_TOKEN to lift the limit. Network failures degrade gracefully (raise OpendataError, which
the router turns into a clean 502) — nothing here is on a hot path and results are cached briefly.

Add a city by appending to CITIES — no other code changes. Today's set is Socrata; the `_fetch`
indirection leaves room for a non-Socrata provider later.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from typing import Any

from . import settings_store


class OpendataError(RuntimeError):
    """A city feed could not be reached or returned an error (router -> 502)."""


# --- per-city registry -------------------------------------------------------
# map: normalized_key -> source column. person fields: {business?, first?, last?, name?}.
# geo: a `point` column (Socrata location/point, enables within_circle) and/or numeric lat/lon columns.
CITIES: dict[str, dict[str, Any]] = {
    "nyc": {
        "label": "New York City — DOB NOW", "region": "NY",
        "domain": "data.cityofnewyork.us", "dataset": "w9ak-ipjd",
        "authority": "NYC Dept. of Buildings",
        "map": {"permit_number": "job_filing_number", "permit_type": "job_type",
                "status": "filing_status", "units": "proposed_dwelling_units",
                "floor_area": "total_construction_floor_area", "est_cost": "initial_cost",
                "filed_date": "filing_date", "issued_date": "approved_date",
                "description": "job_description"},
        "address_parts": ["house_no", "street_name", "borough"],
        "owner": {"business": "owner_s_business_name", "first": "owner_first_name", "last": "owner_last_name"},
        "applicant": {"business": "applicant_business_name", "first": "applicant_first_name", "last": "applicant_last_name"},
        "contractor": None,
        "lat": "latitude", "lon": "longitude", "point": None,
    },
    "sf": {
        "label": "San Francisco — DBI", "region": "CA",
        "domain": "data.sfgov.org", "dataset": "i98e-djp9",
        "authority": "SF Dept. of Building Inspection",
        "map": {"permit_number": "permit_number", "permit_type": "permit_type_definition",
                "status": "status", "units": "proposed_units", "floor_area": None,
                "est_cost": "estimated_cost", "filed_date": "filed_date", "issued_date": "issued_date",
                "description": "description"},
        "address_parts": ["street_number", "street_name", "street_suffix"],
        "owner": None, "applicant": None, "contractor": None,
        "lat": None, "lon": None, "point": "location",
    },
    "chicago": {
        "label": "Chicago — Buildings", "region": "IL",
        "domain": "data.cityofchicago.org", "dataset": "ydr8-5enu",
        "authority": "Chicago Dept. of Buildings",
        "map": {"permit_number": "permit_", "permit_type": "permit_type", "status": None,
                "units": None, "floor_area": None, "est_cost": "reported_cost",
                "filed_date": "application_start_date", "issued_date": "issue_date",
                "fee": "total_fee", "description": "work_description"},
        "address_parts": ["street_number", "street_direction", "street_name"],
        "owner": {"name": "contact_2_name"}, "applicant": None,
        "contractor": {"name": "contact_1_name"},
        "lat": "latitude", "lon": "longitude", "point": "location",
    },
    "la": {
        "label": "Los Angeles — LADBS", "region": "CA",
        "domain": "data.lacity.org", "dataset": "pi9x-tg5x",
        "authority": "LA Dept. of Building & Safety",
        "map": {"permit_number": "permit_nbr", "permit_type": "permit_type", "status": "status_desc",
                "units": None, "floor_area": None, "est_cost": "valuation",
                "filed_date": None, "issued_date": "issue_date", "description": "work_desc"},
        "address_parts": ["primary_address"],
        "owner": None, "applicant": None, "contractor": None,
        "lat": "lat", "lon": "lon", "point": "geolocation",
    },
    "austin": {
        "label": "Austin — DSD", "region": "TX",
        "domain": "data.austintexas.gov", "dataset": "3syk-w9eu",
        "authority": "Austin Development Services Dept.",
        "map": {"permit_number": "permit_number", "permit_type": "permit_type_desc",
                "status": "status_current", "units": None, "floor_area": None, "est_cost": None,
                "filed_date": "applieddate", "issued_date": "issue_date", "expires_date": "expiresdate",
                "description": "description"},
        "address_parts": ["original_address1", "original_city"],
        "owner": None, "applicant": None, "contractor": None,
        "lat": None, "lon": None, "point": None,      # no coords in this dataset -> text search only
    },
}


def list_cities() -> list[dict[str, Any]]:
    """The selectable cities (id, label, region, authority, whether geo-radius search works)."""
    return [{"id": k, "label": c["label"], "region": c["region"], "authority": c["authority"],
             "geo": bool(c.get("point") or (c.get("lat") and c.get("lon")))}
            for k, c in CITIES.items()]


def _f(v: Any) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def _join(row: dict, cols: list[str]) -> str:
    return " ".join(str(row[c]).strip() for c in cols if row.get(c)).strip()


def _person(row: dict, cfg: dict | None) -> str | None:
    if not cfg:
        return None
    if cfg.get("name") and row.get(cfg["name"]):
        return str(row[cfg["name"]]).strip()
    if cfg.get("business") and row.get(cfg["business"]):
        return str(row[cfg["business"]]).strip()
    name = " ".join(str(row[k]).strip() for k in (cfg.get("first"), cfg.get("last")) if k and row.get(k)).strip()
    return name or None


def _coords(row: dict, c: dict) -> tuple[float | None, float | None]:
    if c.get("lat") and c.get("lon"):
        return _f(row.get(c["lat"])), _f(row.get(c["lon"]))
    pt = c.get("point") and row.get(c["point"])
    if isinstance(pt, dict) and pt.get("coordinates") and len(pt["coordinates"]) == 2:
        return _f(pt["coordinates"][1]), _f(pt["coordinates"][0])   # GeoJSON is [lon, lat]
    return None, None


def _normalize(city: str, c: dict, row: dict) -> dict[str, Any]:
    m = c["map"]
    def g(key):
        col = m.get(key)
        return row.get(col) if col else None
    lat, lon = _coords(row, c)
    return {
        "source": "opendata", "city": city, "authority": c["authority"],
        "permit_number": (g("permit_number") or "").strip() or None,
        "permit_type": (g("permit_type") or "").strip() or None,
        "status": (g("status") or "").strip() or None,
        "address": _join(row, c["address_parts"]) or None,
        "lat": lat, "lon": lon,
        "owner": _person(row, c.get("owner")),
        "applicant": _person(row, c.get("applicant")),
        "contractor": _person(row, c.get("contractor")),
        "units": int(_f(g("units"))) if _f(g("units")) is not None else None,
        "floor_area": _f(g("floor_area")),
        "est_cost": _f(g("est_cost")),
        "fee": _f(g("fee")),
        "filed_date": (str(g("filed_date"))[:10] if g("filed_date") else None),
        "issued_date": (str(g("issued_date"))[:10] if g("issued_date") else None),
        "expires_date": (str(g("expires_date"))[:10] if g("expires_date") else None),
        "description": (g("description") or "").strip() or None,
        "url": f"https://{c['domain']}/resource/{c['dataset']}.json?{urllib.parse.urlencode({m['permit_number']: g('permit_number')})}"
               if g("permit_number") else None,
    }


_CACHE: dict[str, tuple[float, list]] = {}
_TTL = 300.0


def _fetch(domain: str, dataset: str, where: str | None, q: str | None, order: str | None,
           limit: int) -> list[dict]:
    params: dict[str, Any] = {"$limit": max(1, min(limit, 1000))}
    if where:
        params["$where"] = where
    if q:
        params["$q"] = q
    if order:
        params["$order"] = order
    url = f"https://{domain}/resource/{dataset}.json?{urllib.parse.urlencode(params)}"
    ck = url
    hit = _CACHE.get(ck)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    headers = {"Accept": "application/json", "User-Agent": "ModelMaker/opendata"}
    token = settings_store.get("SOCRATA_APP_TOKEN")
    if token:
        headers["X-App-Token"] = token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as r:   # noqa: S310 — Socrata host from the registry
            rows = json.loads(r.read().decode("utf-8"))
    except Exception as e:    # noqa: BLE001 — any network/parse failure is a clean upstream error
        raise OpendataError(f"{domain} feed unavailable: {e}") from e
    if not isinstance(rows, list):
        raise OpendataError(f"{domain} returned an unexpected payload")
    _CACHE[ck] = (time.time(), rows)
    return rows


def fetch_permits(city: str, *, lat: float | None = None, lon: float | None = None,
                  radius_m: float = 1500, address: str | None = None, q: str | None = None,
                  limit: int = 100) -> list[dict[str, Any]]:
    """Normalized permit records for a city, optionally near a point (radius_m), or matching a
    free-text query / address. Newest issued first where the dataset supports it."""
    if city not in CITIES:
        raise OpendataError(f"unknown city {city!r}")
    c = CITIES[city]
    where_parts: list[str] = []
    if lat is not None and lon is not None:
        if c.get("point"):
            where_parts.append(f"within_circle({c['point']}, {lat}, {lon}, {int(radius_m)})")
        elif c.get("lat") and c.get("lon"):
            dlat = radius_m / 111_320.0
            dlon = radius_m / (111_320.0 * max(0.1, math.cos(math.radians(lat))))
            where_parts.append(
                f"{c['lat']} between {lat - dlat} and {lat + dlat} "
                f"and {c['lon']} between {lon - dlon} and {lon + dlon}")
    text = q or address
    order = (c["map"].get("issued_date") + " DESC") if c["map"].get("issued_date") else None
    rows = _fetch(c["domain"], c["dataset"], " and ".join(where_parts) or None,
                  text, order, limit)
    return [_normalize(city, c, r) for r in rows]
