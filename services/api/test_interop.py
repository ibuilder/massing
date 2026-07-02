"""Speckle interoperability bridge — feature-flag + status gating (no server required).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_interop.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_interop.db"
os.environ["STORAGE_DIR"] = "./test_storage_interop"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("SPECKLE_SERVER", None)
os.environ.pop("SPECKLE_TOKEN", None)
for _f in ("./test_interop.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api import speckle_bridge            # noqa: E402
from aec_api.main import app                  # noqa: E402

# off by default
assert speckle_bridge.is_enabled() is False
st = speckle_bridge.status()
assert st["enabled"] is False and st["connected"] is False, st
assert "SPECKLE_SERVER" in st["message"], st

# send raises a clear config error when off
try:
    speckle_bridge.send_model("p", "Proj", None)
    raise AssertionError("expected RuntimeError when unconfigured")
except RuntimeError as e:
    assert "not configured" in str(e), e

# enabled (config present) but unreachable server -> connected False, no crash
os.environ["SPECKLE_SERVER"] = "https://speckle.invalid.example"
os.environ["SPECKLE_TOKEN"] = "tok"
assert speckle_bridge.is_enabled() is True
st2 = speckle_bridge.status()
assert st2["enabled"] is True and st2["connected"] is False, st2
# send now passes the config gate and raises NotImplemented (real upload runs in a deployment)
try:
    speckle_bridge.send_model("p", "Proj", None)
    raise AssertionError("expected NotImplementedError")
except NotImplementedError:
    pass
os.environ.pop("SPECKLE_SERVER", None)
os.environ.pop("SPECKLE_TOKEN", None)

# endpoint reflects the off state
with TestClient(app) as c:
    r = c.get("/interop/speckle/status")
    assert r.status_code == 200 and r.json()["enabled"] is False, r.text[:160]
    pid = c.post("/projects", json={"name": "P"}).json()["id"]
    r = c.post(f"/projects/{pid}/interop/speckle/send")
    assert r.status_code == 501, r.text[:160]      # bridge off -> 501 with guidance

    # CityGML -> GeoJSON footprints
    gml = (b'<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0" '
           b'xmlns:bldg="http://www.opengis.net/citygml/building/2.0" xmlns:gml="http://www.opengis.net/gml">'
           b'<core:cityObjectMember><bldg:Building><bldg:measuredHeight>9</bldg:measuredHeight>'
           b'<bldg:lod0FootPrint><gml:Polygon><gml:exterior><gml:LinearRing>'
           b'<gml:posList srsDimension="3">0 0 0 5 0 0 5 5 0 0 5 0 0 0 0</gml:posList>'
           b'</gml:LinearRing></gml:exterior></gml:Polygon></bldg:lod0FootPrint></bldg:Building></core:cityObjectMember>'
           b'</core:CityModel>')
    r = c.post("/convert/citygml", files={"file": ("site.gml", gml, "application/xml")})
    assert r.status_code == 200, r.text[:160]
    fc = r.json()
    assert fc["type"] == "FeatureCollection" and fc["meta"]["buildings"] == 1, fc["meta"]
    assert fc["features"][0]["properties"]["height"] == 9.0, fc["features"][0]
    # empty/garbage CityGML -> 422 (no footprints), never a fake layer
    assert c.post("/convert/citygml", files={"file": ("x.gml", b"<a/>", "application/xml")}).status_code == 422

print("INTEROP OK - Speckle bridge off by default (status enabled=False, guidance message); send() "
      "raises 'not configured' when off; configured-but-unreachable -> connected=False (no crash) + "
      "send raises NotImplemented; /interop/speckle/status 200, send 501 when off")
