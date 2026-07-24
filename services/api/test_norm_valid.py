"""NORM-VALID — the normative openBIM conformance gauntlet (header + schema + IFC implementer-agreement
rules). Engine over a clean model (all pass/warn, none fail) + injected violations (bad GlobalId, a
second IfcProject) → fail, plus the /models/norm-valid route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_norm_valid.py"""
import os

TMP = os.path.join(os.path.dirname(__file__), "_normvalid.ifc")

from aec_data import massing, norm_valid  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a clean blank model should conform — nothing FAILS (warnings for header/context are acceptable)
massing.generate_blank_ifc(TMP, name="NormValid", storeys=2, storey_height=3.5, ground_size=20.0)
m = open_model(TMP)
res = norm_valid.validate(m)
assert res["schema"] == "IFC4", res["schema"]
assert res["passed"] is True, res["summary"]
by_id = {c["id"]: c for c in res["checks"]}
# the core normative rules pass on a well-formed model
for cid in ("header.schema", "project.single", "project.units", "guid.format", "guid.unique"):
    assert by_id[cid]["status"] == "pass", (cid, by_id[cid])
assert res["summary"]["fail"] == 0 and res["summary"]["pass"] >= 5, res["summary"]
# STEP-syntax + bSDD/classification lanes are present (warn on an unclassified blank model, never fail)
assert "header.file_name" in by_id and by_id["header.file_name"]["status"] in ("pass", "warn"), by_id.get("header.file_name")
assert "classification.coverage" in by_id, list(by_id)
assert by_id["classification.coverage"]["status"] in ("pass", "warn"), by_id["classification.coverage"]
assert "%" in by_id["classification.coverage"]["note"], by_id["classification.coverage"]["note"]

# --- inject violations: a bad GlobalId + a duplicate GlobalId + a second IfcProject → fails ---------
import ifcopenshell  # noqa: E402

bad = ifcopenshell.open(TMP)
walls = bad.by_type("IfcWall") or bad.by_type("IfcSlab")
walls[0].GlobalId = "not-a-valid-guid"                 # 13 chars, illegal alphabet → guid.format fail
# duplicate a GlobalId across two roots → guid.unique fail
roots = bad.by_type("IfcBuildingStorey")
if len(roots) >= 2:
    roots[1].GlobalId = roots[0].GlobalId
bad.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="Second")  # project.single fail
res2 = norm_valid.validate(bad)
b = {c["id"]: c for c in res2["checks"]}
assert res2["passed"] is False, res2["summary"]
assert b["guid.format"]["status"] == "fail" and b["guid.format"]["count"] >= 1, b["guid.format"]
assert b["guid.unique"]["status"] == "fail", b["guid.unique"]
assert b["project.single"]["status"] == "fail" and b["project.single"]["count"] == 2, b["project.single"]
assert res2["summary"]["fail"] >= 3, res2["summary"]

# ================= implementer-agreement depth ======================================================
# --- header: the MVD lane. The generator stamps a ViewDefinition, so a fresh model declares one.
# (These header checks read `model.header`; `wrapped_data.header` is a METHOD and silently yields
# nothing, which used to make every header check a permanent false "empty".)
assert by_id["header.view_definition"]["status"] == "pass", by_id["header.view_definition"]
assert any("DesignTransferView" in v for v in by_id["header.view_definition"]["sample"]), by_id["header.view_definition"]
assert by_id["header.description"]["status"] == "pass", by_id["header.description"]
assert by_id["header.file_name"]["status"] == "pass", by_id["header.file_name"]   # name + timestamp stamped

hdr = ifcopenshell.open(TMP)
hdr.header.file_description.description = ("ViewDefinition[MadeUpView]",)
hv = {c["id"]: c for c in norm_valid.validate(hdr)["checks"]}["header.view_definition"]
assert hv["status"] == "warn" and "MadeUpView" in hv["note"], hv       # unrecognised, named not swallowed
hdr.header.file_description.description = ("",)
hv2 = {c["id"]: c for c in norm_valid.validate(hdr)["checks"]}["header.view_definition"]
assert hv2["status"] == "warn" and hv2["count"] == 0, hv2

# --- units: complete + unambiguous ------------------------------------------------------------------
for cid in ("units.complete", "units.unambiguous"):
    assert by_id[cid]["status"] == "pass", (cid, by_id[cid])          # generator stamps PLANEANGLEUNIT

nou = ifcopenshell.open(TMP)
ctx = nou.by_type("IfcProject")[0].UnitsInContext
ctx.Units = [u for u in ctx.Units if str(getattr(u, "UnitType", "")).upper() != "AREAUNIT"]
u1 = {c["id"]: c for c in norm_valid.validate(nou)["checks"]}["units.complete"]
assert u1["status"] == "fail" and u1["sample"] == ["AREAUNIT"], u1     # names the missing one

dup = ifcopenshell.open(TMP)
dctx = dup.by_type("IfcProject")[0].UnitsInContext
dctx.Units = list(dctx.Units) + [dup.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Prefix="MILLI", Name="METRE")]
u2 = {c["id"]: c for c in norm_valid.validate(dup)["checks"]}["units.unambiguous"]
assert u2["status"] == "fail" and u2["sample"] == ["LENGTHUNIT"], u2   # two length units = ambiguous

# --- relationship cardinality + single-parent rules -------------------------------------------------
for cid in ("rel.cardinality", "rel.single_container", "rel.single_aggregate", "rel.single_void",
            "rel.double_placed", "spatial.hierarchy"):
    assert by_id[cid]["status"] == "pass", (cid, by_id[cid])

# a relationship with an EMPTY related set parses and validates against EXPRESS but means nothing
dang = ifcopenshell.open(TMP)
storey = dang.by_type("IfcBuildingStorey")[0]
dang.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                   RelatingStructure=storey, RelatedElements=[])
d1 = {c["id"]: c for c in norm_valid.validate(dang)["checks"]}["rel.cardinality"]
assert d1["status"] == "fail" and d1["sample"][0]["missing"] == "RelatedElements", d1

# the same element contained by TWO storeys — a consumer picks one arbitrarily
two = ifcopenshell.open(TMP)
storeys = two.by_type("IfcBuildingStorey")
slab = two.by_type("IfcSlab")[0]
two.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                  RelatingStructure=storeys[-1], RelatedElements=[slab])
t1 = {c["id"]: c for c in norm_valid.validate(two)["checks"]}
assert t1["rel.single_container"]["status"] == "fail", t1["rel.single_container"]
assert t1["rel.single_container"]["sample"][0]["parents"] == 2, t1["rel.single_container"]["sample"]

# a slab both aggregated into an assembly AND still hanging off the storey is taken off twice
dbl = ifcopenshell.open(TMP)
asm = dbl.create_entity("IfcElementAssembly", GlobalId=ifcopenshell.guid.new(), Name="Asm")
dbl.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(),
                  RelatingObject=asm, RelatedObjects=[dbl.by_type("IfcSlab")[0]])
db1 = {c["id"]: c for c in norm_valid.validate(dbl)["checks"]}["rel.double_placed"]
assert db1["status"] == "warn" and db1["count"] == 1, db1

# an orphaned storey breaks the site→building→storey aggregation chain
orph = ifcopenshell.open(TMP)
orph.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="Floating")
o1 = {c["id"]: c for c in norm_valid.validate(orph)["checks"]}["spatial.hierarchy"]
assert o1["status"] == "fail" and o1["sample"][0]["name"] == "Floating", o1

# --- route -----------------------------------------------------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_norm_valid.db"
os.environ["STORAGE_DIR"] = "./test_storage_normvalid"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_norm_valid.db"):
    os.remove("./test_norm_valid.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "NV"}).json()["id"]
    assert c.get(f"/projects/{pid}/models/norm-valid").status_code == 409   # no source IFC
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = TMP
        db.commit()
    r = c.get(f"/projects/{pid}/models/norm-valid")
    assert r.status_code == 200, r.status_code
    j = r.json()
    assert j["passed"] is True and j["schema"] == "IFC4" and j["summary"]["fail"] == 0, j["summary"]
    assert any(ck["id"] == "guid.format" for ck in j["checks"])

if os.path.exists(TMP):
    os.remove(TMP)

print("NORM-VALID OK - a clean IFC4 model passes the gauntlet (recognised schema, single IfcProject with "
      "units + context, valid+unique 22-char GlobalIds, no fails); injecting an illegal GlobalId + a "
      "duplicate GlobalId + a second IfcProject flips passed=False with guid.format/guid.unique/"
      "project.single all failing; the /models/norm-valid route 409s without a source IFC and returns the "
      "structured pass/warn/fail report otherwise. DEPTH: the header lane now actually reads the "
      "header (it went through `wrapped_data.header`, a METHOD, so every header check silently read "
      "as empty) and parses the ViewDefinition[...] MVD — an unrecognised view is named, a missing "
      "one warns; units are checked for COMPLETENESS (dropping AREAUNIT fails and names it) and "
      "UNAMBIGUITY (a second LENGTHUNIT fails); and the relationship-cardinality lane catches a "
      "dangling relationship with an empty related set, an element contained by two storeys, a part "
      "both aggregated and directly contained, and a storey outside the aggregation chain. Fixing "
      "the generator to stamp PLANEANGLEUNIT + a real FILE_NAME/FILE_DESCRIPTION was a consequence "
      "of the check, not a workaround for it.")
