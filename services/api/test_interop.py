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
from aec_api import speckle_bridge, settings_store  # noqa: E402
from aec_api.main import app                  # noqa: E402

# Settings catalog exposes Speckle + APS so a non-technical admin can add keys in the UI (no env edit),
# and secrets are write-only (the public catalog never returns a secret value).
_cat = settings_store.public_catalog()
_groups = [g["group"] for g in _cat]
assert any(g.startswith("Speckle") for g in _groups) and any("APS" in g for g in _groups), _groups
_tok = next(k for g in _cat for k in g["keys"] if k["key"] == "SPECKLE_TOKEN")
assert _tok["secret"] and "value" not in _tok, _tok        # write-only secret

# "Test connection" dispatcher — ✓/✗ per integration (off = ✗ with guidance, unknown = guarded)
from aec_api import conntest                                # noqa: E402
assert conntest.test_group("Speckle (interoperability)")["ok"] is False
assert conntest.test_group("SSO — Google")["ok"] is False
assert conntest.test_group("Nope")["ok"] is False
assert conntest.test_group("Massing licence")["ok"] is True    # open mode — licence optional

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

    # HARDENING: a billion-laughs / XXE bomb is rejected (defusedxml), not expanded -> 422, no OOM
    bomb = (b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
            b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>'
            b'<core:CityModel xmlns:core="http://www.opengis.net/citygml/2.0"><a>&lol3;</a></core:CityModel>')
    assert c.post("/convert/citygml", files={"file": ("bomb.gml", bomb, "application/xml")}).status_code == 422

    # model alignment report needs >=2 models -> 409 when a project has none
    assert c.get(f"/projects/{pid}/models/alignment").status_code == 409

print("INTEROP OK - Speckle bridge off by default (status enabled=False, guidance message); send() "
      "raises 'not configured' when off; configured-but-unreachable -> connected=False (no crash) + "
      "send raises NotImplemented; /interop/speckle/status 200, send 501 when off")
