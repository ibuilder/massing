"""GIS-OUT — the building footprint + site point as a WGS84 GeoJSON FeatureCollection, anchored on the
IfcSite reference lat/long. Engine (DMS decode, bbox transform, not-available without georef) + the
/models/footprint.geojson route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_gis_out.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_gisout.ifc")

from aec_api import gis_out  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# DMS decode
assert gis_out._dms_to_deg((40, 0, 0)) == 40.0
assert gis_out._dms_to_deg((-74, 30, 0)) == -74.5
assert gis_out._dms_to_deg(None) is None

# a model with NO site lat/long → not available
massing.generate_blank_ifc(TMP, name="No Geo", storeys=1, storey_height=4.0, ground_size=20.0)
m0 = open_model(TMP)
edit.add_column(m0, [0, 0], 4.0, 0.4, 0.4, m0.by_type("IfcBuildingStorey")[0].Name)
r0 = gis_out.to_geojson(m0)
assert r0["available"] is False and "lat/long" in r0["message"], r0

# georeference it: set IfcSite reference lat/long (40 N, 74 W) + a footprint from two columns
massing.generate_blank_ifc(TMP, name="Downtown Tower", storeys=1, storey_height=4.0, ground_size=30.0)
m = open_model(TMP)
site = m.by_type("IfcSite")[0]
site.RefLatitude = (40, 0, 0)
site.RefLongitude = (-74, 0, 0)
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_column(m, [0, 0], 4.0, 0.4, 0.4, st)
edit.add_column(m, [10, 20], 4.0, 0.4, 0.4, st)     # bbox 10 wide × 20 deep

r = gis_out.to_geojson(m)
assert r["available"] is True and r["crs"] == "EPSG:4326", r
assert r["anchor"]["lat"] == 40.0 and r["anchor"]["lon"] == -74.0, r["anchor"]
fc = r["geojson"]
assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 2, fc
site_f = next(f for f in fc["features"] if f["properties"]["kind"] == "site")
foot_f = next(f for f in fc["features"] if f["properties"]["kind"] == "footprint")
assert site_f["geometry"]["coordinates"] == [-74.0, 40.0], site_f            # [lon, lat]
assert site_f["properties"]["name"] == "Downtown Tower", site_f
# the footprint bbox spans ~10 m × 20 m and anchors at the site corner
assert abs(foot_f["properties"]["width_m"] - 10.0) < 0.5, foot_f
assert abs(foot_f["properties"]["depth_m"] - 20.0) < 0.5, foot_f
ring = foot_f["geometry"]["coordinates"][0]
assert len(ring) == 5 and ring[0] == ring[-1], ring                          # closed polygon
assert ring[0] == [-74.0, 40.0], ring[0]                                     # first corner at the anchor
# the far corner is east + north of the anchor (positive lon/lat deltas), building-scale small
assert ring[2][0] > -74.0 and ring[2][1] > 40.0, ring[2]
assert ring[2][0] - (-74.0) < 0.001 and ring[2][1] - 40.0 < 0.001, ring[2]   # <~100 m in degrees

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_gis_out.db"
os.environ["STORAGE_DIR"] = "./test_storage_gisout"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_gis_out.db"):
    os.remove("./test_gis_out.db")
m.write(TMP)
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "GIS"}).json()["id"]
    assert c.get(f"/projects/{pid}/models/footprint.geojson").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    jr = c.get(f"/projects/{pid}/models/footprint.geojson")
    assert jr.status_code == 200 and jr.json()["available"] is True, jr.status_code
    assert jr.json()["geojson"]["features"][0]["geometry"]["type"] in ("Point", "Polygon")

if os.path.exists(TMP):
    os.remove(TMP)

print("GIS-OUT OK - a model georeferenced to 40N/74W exports a WGS84 GeoJSON FeatureCollection: a site "
      "Point at [-74, 40] and a footprint Polygon (~10 m × 20 m bbox) whose corners sit building-scale-close "
      "to the anchor; DMS decodes correctly; a model with no site lat/long is not-available; the "
      "/models/footprint.geojson route 409s without a model and streams the FeatureCollection otherwise.")
