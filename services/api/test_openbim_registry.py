"""openBIM standards + version registry: the capability matrix is derived from the live engines
(so it can't drift), reports read+write versions per standard, and the /openbim/capabilities endpoint
serves it. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_openbim_registry.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_openbim_registry.db"
os.environ["STORAGE_DIR"] = "./test_storage_openbim_registry"
os.environ.pop("AEC_RBAC", None)
os.environ["AEC_TRUST_XUSER"] = "1"
for _f in ("./test_openbim_registry.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import bcf_io, openbim  # noqa: E402
from aec_api import model_capabilities as mc  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- the matrix is DERIVED from real code (no drift) -------------------------
caps = openbim.capabilities()
idx = caps["index"]
# BCF read+write versions are exactly what the BCF engine supports
assert set(idx["bcf"]["read"]) == set(bcf_io.SUPPORTED_VERSIONS), idx["bcf"]
assert set(idx["bcf"]["write"]) == set(bcf_io.SUPPORTED_VERSIONS), idx["bcf"]
assert "2.1" in idx["bcf"]["read"] and "3.0" in idx["bcf"]["read"], idx["bcf"]
# IFC read schemas come from model_capabilities (+ the IFC5 JSON read path)
assert set(mc.SUPPORTED_SCHEMAS).issubset(set(idx["ifc"]["read"])), idx["ifc"]
assert "IFC4X3" in idx["ifc"]["read"] and "IFC5" in idx["ifc"]["read"], idx["ifc"]   # ISO 16739 + IFCX
# IDS 1.0 and bSDD v1 present
assert idx["ids"]["read"] == ["1.0"], idx["ids"]
assert idx["bsdd"]["read"] == ["v1"] or idx["bsdd"]["write"] == ["v1"], idx["bsdd"]  # api versions

# --- supports() helper -------------------------------------------------------
assert openbim.supports("bcf", "3.0", "write") is True
assert openbim.supports("bcf", "3.0", "read") is True
assert openbim.supports("bcf", "9.9") is False
assert openbim.supports("ids", "1.0") is True
assert openbim.supports("nope", "1.0") is False

# --- every standard entry is well-formed ------------------------------------
keys = {s["key"] for s in caps["standards"]}
assert {"ifc", "bcf", "ids", "bsdd", "cobie", "cde"} <= keys, keys
for s in caps["standards"]:
    assert s.get("name") and s.get("current"), s
    assert s.get("read") or s.get("write") or s.get("api"), s   # every standard declares some capability

# --- endpoint ----------------------------------------------------------------
with TestClient(app) as c:
    r = c.get("/openbim/capabilities", headers={"X-User": "admin"})
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["summary"]["standards"] == len(caps["standards"])
    assert "3.0" in body["index"]["bcf"]["write"], body["index"]["bcf"]

print("OPENBIM REGISTRY OK - capability matrix derives BCF versions from bcf_io + IFC schemas from "
      "model_capabilities (no drift); reports read/write per standard (IFC/BCF/IDS/bSDD/COBie/CDE); "
      "supports() answers 'do you read/write X vN'; /openbim/capabilities serves it.")
