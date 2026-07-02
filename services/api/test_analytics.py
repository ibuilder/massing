"""Thematic colour-by-property + BIM data-QA over the property index.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_analytics.py"""
import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_analytics.db"
os.environ["STORAGE_DIR"] = "./test_storage_analytics"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_analytics.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient   # noqa: E402
from aec_api.main import app                # noqa: E402

PROPS = {
    "schema": "demo", "project": {"name": "Tower"},
    "elements": [
        {"guid": "g1", "ifc_class": "IfcWall", "storey": "L1", "name": "W1", "type_name": "Basic",
         "psets": {"Pset_WallCommon": {"IsExternal": True, "FireRating": "60"}}},
        {"guid": "g2", "ifc_class": "IfcWall", "storey": "L2", "name": "W2", "type_name": "Basic",
         "psets": {"Pset_WallCommon": {"IsExternal": False, "FireRating": "60"}}},
        {"guid": "g3", "ifc_class": "IfcColumn", "storey": "L1", "name": "C1",
         "psets": {"Pset_ColumnCommon": {"LoadBearing": True}}},
        {"guid": "g4", "ifc_class": "IfcColumn", "storey": "L1"},          # missing name + type + pset
    ],
}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Tower"}).json()["id"]
    # endpoints 404 before an index exists
    assert c.get(f"/projects/{pid}/elements/color-by?prop=ifc_class").status_code == 404
    assert c.get(f"/projects/{pid}/elements/qa").status_code == 404

    up = c.post(f"/projects/{pid}/properties/index",
                files={"file": ("props.json", json.dumps(PROPS).encode(), "application/json")})
    assert up.status_code == 200 and up.json()["loaded"] == 4, up.text[:160]

    # facets: attributes present + pset properties surfaced
    fac = c.get(f"/projects/{pid}/elements/facets-list").json()
    attr_props = {a["prop"] for a in fac["attributes"]}
    assert {"ifc_class", "storey", "name"} <= attr_props, attr_props
    pset_props = {p["prop"] for p in fac["properties"]}
    assert "Pset_WallCommon::FireRating" in pset_props, pset_props

    # colour-by categorical: two IfcWall + two IfcColumn
    cb = c.get(f"/projects/{pid}/elements/color-by?prop=ifc_class").json()
    assert cb["kind"] == "categorical" and cb["total"] == 4 and cb["colored"] == 4, cb
    counts = {b["label"]: b["count"] for b in cb["buckets"]}
    assert counts == {"IfcWall": 2, "IfcColumn": 2}, counts
    assert set(next(b for b in cb["buckets"] if b["label"] == "IfcWall")["guids"]) == {"g1", "g2"}

    # colour-by a pset property (only 2 walls have FireRating) -> 2 unset
    fr = c.get(f"/projects/{pid}/elements/color-by?prop=Pset_WallCommon::FireRating").json()
    assert fr["colored"] == 2 and fr["unset"] == 2, fr

    # data QA: g4 is missing name (required) -> 3/4 compliant = 75%; type/pset are recommended
    qa = c.get(f"/projects/{pid}/elements/qa").json()
    assert qa["total"] == 4 and qa["noncompliant"] == 1 and qa["compliant_pct"] == 75.0, qa
    assert "g4" in qa["noncompliant_guids"], qa["noncompliant_guids"]
    by_key = {r["key"]: r for r in qa["rules"]}
    assert by_key["name"]["missing"] == 1 and by_key["name"]["severity"] == "required", by_key["name"]
    assert by_key["type_name"]["severity"] == "recommended", by_key["type_name"]
    assert by_key["__pset"]["missing"] == 1, by_key["__pset"]      # g4 has no psets

print("ANALYTICS OK - facets list attrs+pset props; colour-by buckets categorical (2 walls/2 cols) + "
      "pset FireRating (2 coloured/2 unset); data-QA 75% (g4 missing required name), type/pset recommended; "
      "404 before an index exists")
