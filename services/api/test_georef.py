"""Shared-coordinates / georeferencing extraction — build a georeferenced IFC in memory and check the
map conversion (true-north bearing, scale), projected CRS and LoGeoRef level.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_georef.py"""
import math
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_georef.db"
os.environ["STORAGE_DIR"] = "./test_storage_georef"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_georef.db",):
    if os.path.exists(_f):
        os.remove(_f)

import ifcopenshell  # noqa: E402

from aec_api import georef  # noqa: E402

# --- a fully georeferenced model: projected CRS + map conversion rotated ~3 deg -------------------
f = ifcopenshell.file(schema="IFC4")
ctx = f.create_entity("IfcGeometricRepresentationContext")
crs = f.create_entity("IfcProjectedCRS", Name="EPSG:32633", GeodeticDatum="WGS84",
                      VerticalDatum="EGM2008 height", MapProjection="UTM", MapZone="33N")
f.create_entity("IfcMapConversion", SourceCRS=ctx, TargetCRS=crs, Eastings=500000.0,
                Northings=6600000.0, OrthogonalHeight=42.0,
                XAxisAbscissa=math.cos(math.radians(3)), XAxisOrdinate=math.sin(math.radians(3)), Scale=1.0)
f.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Site", RefElevation=42.0)

g = georef.georeferencing(f)
assert g["georeferenced"] is True, g
mc = g["map_conversion"]
assert mc["eastings"] == 500000.0 and mc["northings"] == 6600000.0, mc
assert abs(mc["true_north_bearing_deg"] - 3.0) < 0.01, mc["true_north_bearing_deg"]
assert mc["scale"] == 1.0, mc
assert g["crs"]["name"] == "EPSG:32633" and g["crs"]["map_zone"] == "33N", g["crs"]
assert g["level"] == 50 and "50" in g["level_label"], (g["level"], g["level_label"])
print(f"georef: {g['level_label']} · {g['crs']['name']} · N-bearing {mc['true_north_bearing_deg']}° · "
      f"E{mc['eastings']:.0f}/N{mc['northings']:.0f}")

# --- lat/long only (no map conversion) → LoGeoRef 20 ---------------------------------------------
f2 = ifcopenshell.file(schema="IFC4")
f2.create_entity("IfcSite", GlobalId=ifcopenshell.guid.new(), Name="Site",
                 RefLatitude=(59, 20, 0), RefLongitude=(18, 4, 0), RefElevation=10.0)
g2 = georef.georeferencing(f2)
assert g2["georeferenced"] is False and g2["map_conversion"] is None, g2
assert g2["level"] == 20 and g2["site"]["ref_latitude"] == [59, 20, 0], g2

# --- nothing → LoGeoRef 0 ------------------------------------------------------------------------
g0 = georef.georeferencing(ifcopenshell.file(schema="IFC4"))
assert g0["level"] == 0 and g0["georeferenced"] is False, g0

# --- endpoint: a project with no source IFC returns 409 ------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    r = c.get(f"/projects/{pid}/models/georeferencing")
    assert r.status_code == 409, (r.status_code, r.text[:160])

print("test_georef OK")
