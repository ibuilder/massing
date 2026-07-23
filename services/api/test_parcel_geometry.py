"""PARCEL-IMPORT — cadastral parcel geometry (GeoJSON/WKT) → area/perimeter/centroid + FAR/coverage/height
compliance vs a zoning envelope.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_parcel_geometry.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_parcel_geometry.db"
os.environ["STORAGE_DIR"] = "./test_storage_parcelgeo"
os.environ.pop("AEC_RBAC", None)

from aec_api import parcel_geometry as pg  # noqa: E402

# --- a 100×50 m rectangle in projected metres: exact shoelace area -------------------------------
rect = {"type": "Polygon", "coordinates": [[[1000, 2000], [1100, 2000], [1100, 2050], [1000, 2050], [1000, 2000]]]}
r = pg.analyze(geojson=rect, parcel_id="LOT-42")
assert r["area_m2"] == 5000.0 and r["perimeter_m"] == 300.0, r
assert r["area_acres"] == 1.236 and r["vertices"] == 4 and r["coordinates_were_lonlat"] is False, r
assert r["parcel_id"] == "LOT-42" and r["bbox"]["maxx"] == 1100, r

# --- same via WKT + a Feature wrapper --------------------------------------------------------------
w = pg.analyze(wkt="POLYGON ((1000 2000, 1100 2000, 1100 2050, 1000 2050, 1000 2000))")
assert w["area_m2"] == 5000.0, w
f = pg.analyze(geojson={"type": "Feature", "geometry": rect, "properties": {}})
assert f["area_m2"] == 5000.0, f

# --- a lon/lat ring converts equirectangularly (~111.19 m per 0.001° lat at the equator) -----------
ll = {"type": "Polygon", "coordinates": [[[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001], [0, 0]]]}
g = pg.analyze(geojson=ll)
assert g["coordinates_were_lonlat"] is True, g
assert abs(g["area_m2"] - 111.19**2) / 111.19**2 < 0.01, g["area_m2"]        # ~12,363 m² within 1%

# --- zoning compliance: FAR over, coverage under, height at limit ---------------------------------
z = pg.analyze(geojson=rect, zoning={"max_far": 2.0, "max_coverage": 0.6, "max_height_m": 30},
               proposal={"gfa_m2": 12_000, "footprint_m2": 2_000, "height_m": 30})
comp = z["compliance"]
by = {c["metric"]: c for c in comp["checks"]}
assert by["FAR"]["value"] == 2.4 and by["FAR"]["ok"] is False and by["FAR"]["max_gfa_m2"] == 10_000.0, by["FAR"]
assert by["coverage"]["value"] == 0.4 and by["coverage"]["ok"] is True and by["coverage"]["slack"] == 0.2, by["coverage"]
assert by["height_m"]["ok"] is True, by["height_m"]                           # at the limit = compliant
assert comp["ok"] is False and comp["violations"] == ["FAR"], comp

# no zoning limits given → checks report values with ok=None, overall None
n = pg.analyze(geojson=rect, proposal={"gfa_m2": 12_000})
assert n["compliance"]["checks"][0]["ok"] is None and n["compliance"]["ok"] is None, n["compliance"]

# --- bad input raises ------------------------------------------------------------------------------
for bad in ({"type": "Point", "coordinates": [0, 0]}, "not json {", None):
    try:
        pg.analyze(geojson=bad)
        raise AssertionError(f"expected ValueError for {bad!r}")
    except (ValueError, TypeError, KeyError):
        pass

# --- route: 422 on a bad boundary; 200 otherwise ---------------------------------------------------
if os.path.exists("./test_parcel_geometry.db"):
    os.remove("./test_parcel_geometry.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/parcels/analyze", json={"geojson": {"type": "Point", "coordinates": [0, 0]}}).status_code == 422
    rr = c.post("/parcels/analyze", json={"geojson": rect, "zoning": {"max_far": 2.0},
                                          "proposal": {"gfa_m2": 12_000}})
    assert rr.status_code == 200, rr.text
    assert rr.json()["compliance"]["violations"] == ["FAR"], rr.json()

print("PARCEL-IMPORT OK - a 100×50 m parcel parses from GeoJSON/Feature/WKT to exactly 5,000 m² (1.236 ac, "
      "300 m perimeter); a lon/lat ring projects equirectangularly to within 1% of the analytic area; against "
      "a max-FAR 2.0 / coverage 0.6 / height 30 m envelope a 12,000 m² GFA proposal is FAR 2.4 (violation, "
      "max buildable 10,000 m²) while coverage 0.4 and height-at-limit pass; missing limits report ok=None; "
      "the /parcels/analyze route 422s on a Point and returns the compliance read otherwise.")
