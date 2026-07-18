"""SITE-1 — open-geodata site context: Overpass → GeoJSON normalization, DMS→decimal georef,
fetch-once caching (offline afterwards), and the no-coordinates 409.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_site_context.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_site_context.db"
os.environ["STORAGE_DIR"] = "./test_storage_site"
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_site_context.db",):
    if os.path.exists(_f):
        os.remove(_f)

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import site_context as sc  # noqa: E402
from aec_api.main import app  # noqa: E402

HDR = {"X-User": "architect"}

# --- DMS → decimal ------------------------------------------------------------------------------
assert sc.dms_to_decimal(None) is None
assert sc.dms_to_decimal(40.5) == 40.5
assert abs(sc.dms_to_decimal((40, 42, 46)) - 40.712777) < 1e-4          # NYC lat
assert abs(sc.dms_to_decimal((-74, 0, 21)) - (-74.005833)) < 1e-4       # NYC lon (negative)
assert abs(sc.dms_to_decimal((40, 42, 46, 500000)) - 40.712777) < 1e-3  # millionth-seconds tail

# --- Overpass → GeoJSON -------------------------------------------------------------------------
OVERPASS = {"elements": [
    {"type": "way", "id": 1, "tags": {"building": "yes", "height": "21 m", "name": "Depot"},
     "geometry": [{"lat": 40.0, "lon": -74.0}, {"lat": 40.0004, "lon": -74.0},
                  {"lat": 40.0004, "lon": -73.9996}, {"lat": 40.0, "lon": -74.0}]},
    {"type": "way", "id": 2, "tags": {"building": "residential", "building:levels": "4"},
     "geometry": [{"lat": 40.001, "lon": -74.0}, {"lat": 40.0014, "lon": -74.0},
                  {"lat": 40.0014, "lon": -73.9996}, {"lat": 40.001, "lon": -74.0}]},
    {"type": "way", "id": 3, "tags": {"highway": "residential", "name": "Main St"},
     "geometry": [{"lat": 40.0, "lon": -74.0}, {"lat": 40.002, "lon": -74.0}]},
    {"type": "way", "id": 4, "tags": {"landuse": "industrial"},
     "geometry": [{"lat": 40.0, "lon": -74.001}, {"lat": 40.0008, "lon": -74.001},
                  {"lat": 40.0008, "lon": -74.0002}, {"lat": 40.0, "lon": -74.001}]},
    {"type": "way", "id": 5, "tags": {"building": "yes"},                 # open ring → skipped
     "geometry": [{"lat": 40.0, "lon": -74.0}, {"lat": 40.001, "lon": -74.0}]},
]}
gj = sc.to_geojson(OVERPASS)
assert gj["counts"] == {"building": 2, "road": 1, "landuse": 1}, gj["counts"]
b1 = gj["features"][0]
assert b1["geometry"]["type"] == "Polygon" and b1["properties"]["height"] == 21.0, b1
b2 = gj["features"][1]
assert b2["properties"]["levels"] == 4.0 and b2["properties"]["height"] == 12.0, b2  # 4 × 3 m
road = next(f for f in gj["features"] if f["properties"]["kind"] == "road")
assert road["geometry"]["type"] == "LineString" and road["properties"]["name"] == "Main St"

# --- fetch via MockTransport (fully offline) ----------------------------------------------------
calls = {"n": 0}


def _handler(request: httpx.Request) -> httpx.Response:
    calls["n"] += 1
    from urllib.parse import unquote_plus
    body = unquote_plus(request.read().decode())                         # form-encoded → plain text
    assert "around:300" in body and "40.712" in body, body[:200]         # query carries lat/radius
    return httpx.Response(200, json=OVERPASS)


out = sc.fetch(40.7128, -74.0060, 300.0, transport=httpx.MockTransport(_handler))
assert out["counts"]["building"] == 2 and out["attribution"].startswith("©"), out["counts"]
assert calls["n"] == 1

# --- endpoint: 409 with no coordinates; cache serves offline after a seeded fetch ---------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Site Context"}, headers=HDR).json()["id"]
    r = c.get(f"/projects/{pid}/site-context", headers=HDR)
    assert r.status_code == 409 and "coordinates" in r.text, r.text[:200]

    # seed the cache exactly as the router writes it, then GET must serve it with NO network
    from aec_api import storage
    cached = {**out, "fetched_at": "2026-07-18T00:00:00+00:00", "cached": True}
    storage.put(f"{pid}/site/context.json", json.dumps(cached).encode())
    r2 = c.get(f"/projects/{pid}/site-context", headers=HDR)
    assert r2.status_code == 200, r2.text[:200]
    b = r2.json()
    assert b["counts"]["building"] == 2 and b["attribution"].startswith("©"), b["counts"]
    assert b["geojson"]["features"], "cached GeoJSON round-trips"

    # DELETE clears the cache → back to 409 (no coords, no network attempted for lat/lon-less call)
    assert c.delete(f"/projects/{pid}/site-context", headers=HDR).json()["deleted"] is True
    assert c.get(f"/projects/{pid}/site-context", headers=HDR).status_code == 409

print("SITE-CONTEXT OK - DMS→decimal georef; Overpass→GeoJSON (2 buildings w/ height 21m + 4-storey "
      "→12m, road LineString, landuse parcel, open ring skipped); MockTransport fetch carries "
      "lat/radius; endpoint 409s without coordinates, serves the cache fully offline, DELETE clears.")
