"""IFCPATCH-LIB — maintenance purges (orphaned property sets, empty groups): the scan dry-run + the
recipes via edit.apply_recipe (GUID-stable, attached data survives) + the /model/maintenance route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifcpatch.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ifcpatch.db"
os.environ["STORAGE_DIR"] = "./test_storage_ifcpatch"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_ifcpatch.db"):
    os.remove("./test_ifcpatch.db")

import ifcopenshell  # noqa: E402
import ifcopenshell.guid  # noqa: E402

from aec_data import edit, ifcpatch_lib  # noqa: E402


def _model_with_cruft():
    """A tiny IFC4 model: a wall with an ATTACHED pset + a type with a pset, plus an ORPHANED pset,
    an ORPHANED pset owned by nothing, an EMPTY group, and a NON-empty group."""
    f = ifcopenshell.file(schema="IFC4")
    f.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="P")
    wall = f.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new(), Name="W1")
    # attached pset (must survive)
    pv = f.create_entity("IfcPropertySingleValue", Name="FireRating", NominalValue=f.create_entity("IfcLabel", "2HR"))
    ps_att = f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_WallCommon", HasProperties=[pv])
    f.create_entity("IfcRelDefinesByProperties", GlobalId=ifcopenshell.guid.new(),
                    RelatedObjects=[wall], RelatingPropertyDefinition=ps_att)
    # type-attached pset (must survive)
    wtype = f.create_entity("IfcWallType", GlobalId=ifcopenshell.guid.new(), Name="WT", PredefinedType="STANDARD")
    ps_type = f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name="Pset_Type", HasProperties=[
        f.create_entity("IfcPropertySingleValue", Name="X", NominalValue=f.create_entity("IfcLabel", "y"))])
    wtype.HasPropertySets = [ps_type]
    # two ORPHANED psets (must be purged)
    for nm in ("Pset_Dead1", "Pset_Dead2"):
        f.create_entity("IfcPropertySet", GlobalId=ifcopenshell.guid.new(), Name=nm, HasProperties=[
            f.create_entity("IfcPropertySingleValue", Name="Z", NominalValue=f.create_entity("IfcLabel", "z"))])
    # an EMPTY group (purged) + a NON-empty group (kept)
    f.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name="EmptyGrp")
    keep = f.create_entity("IfcGroup", GlobalId=ifcopenshell.guid.new(), Name="RealGrp")
    f.create_entity("IfcRelAssignsToGroup", GlobalId=ifcopenshell.guid.new(),
                    RelatedObjects=[wall], RelatingGroup=keep)
    return f, wall.GlobalId


# --- engine: scan is a dry run (no mutation) ------------------------------------------------------
m, wall_guid = _model_with_cruft()
before_ps = len(m.by_type("IfcPropertySet"))
sc = ifcpatch_lib.scan(m)
assert before_ps == len(m.by_type("IfcPropertySet")), "scan must not mutate"
ps_recipe = next(r for r in sc["recipes"] if r["recipe"] == "purge_orphan_psets")
grp_recipe = next(r for r in sc["recipes"] if r["recipe"] == "purge_empty_groups")
assert ps_recipe["removable"] == 2 and set(ps_recipe["sample"]) == {"Pset_Dead1", "Pset_Dead2"}, ps_recipe
assert grp_recipe["removable"] == 1 and grp_recipe["sample"] == ["EmptyGrp"], grp_recipe
assert sc["cleanable"] == 3, sc

# --- engine: purge removes orphans, keeps attached + non-empty ------------------------------------
n = ifcpatch_lib.purge_orphan_psets(m)
assert n == 2, n
kept = {p.Name for p in m.by_type("IfcPropertySet")}
assert kept == {"Pset_WallCommon", "Pset_Type"}, kept                # attached + type psets survive
assert m.by_type("IfcWall")[0].GlobalId == wall_guid, "element GUIDs are untouched"
ng = ifcpatch_lib.purge_empty_groups(m)
assert ng == 1 and {g.Name for g in m.by_type("IfcGroup")} == {"RealGrp"}, [g.Name for g in m.by_type("IfcGroup")]
# a second run is a clean no-op (idempotent)
assert ifcpatch_lib.purge_orphan_psets(m) == 0 and ifcpatch_lib.purge_empty_groups(m) == 0

# --- via the edit pipeline: apply_recipe (file → file), GUID-stable -------------------------------
m2, _ = _model_with_cruft()
src = os.path.join(os.path.dirname(__file__), "_ifcpatch_src.ifc")
out = os.path.join(os.path.dirname(__file__), "_ifcpatch_out.ifc")
m2.write(src)
res = edit.apply_recipe(src, "purge_orphan_psets", {}, out)
assert res["changed"] == 2, res
reopened = ifcopenshell.open(out)
assert len(reopened.by_type("IfcPropertySet")) == 2, "orphans gone after republish"
for f in (src, out):
    if os.path.exists(f):
        os.remove(f)

# both recipes are registered + categorized (the authoring-matrix completeness guard)
assert "purge_orphan_psets" in edit.RECIPES and "purge_empty_groups" in edit.RECIPES

# --- route: the dry-run scan is registered ---------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert "/projects/{pid}/model/maintenance" in app.openapi()["paths"]

print("IFCPATCH-LIB OK - scan is a dry run reporting 2 orphaned psets (Dead1/Dead2) + 1 empty group "
      "without mutating; purge_orphan_psets removes both orphans while the wall's Pset_WallCommon + the "
      "type's Pset_Type survive and element GUIDs are untouched; purge_empty_groups drops EmptyGrp, keeps "
      "RealGrp; both idempotent; apply_recipe runs the purge through the GUID-stable republish path; "
      "recipes registered + categorized; /model/maintenance route present.")
