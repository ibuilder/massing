"""FAMILY-DEPTH ② — instance-level parameter overrides: the effective (instance-over-type)
property view, the reset-to-type recipe, and the /model/element/{guid}/effective-props route.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_instance_props.py"""
import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_instance_props.db"
os.environ["STORAGE_DIR"] = "./test_storage_instprops"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_instance_props.db"):
    os.remove("./test_instance_props.db")

import ifcopenshell.api  # noqa: E402

from aec_data import edit, instance_props, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_ifc = Path(tempfile.gettempdir()) / "instance_props.ifc"
massing.generate_blank_ifc(str(_ifc), name="Inst", storeys=1, storey_height=3.0, ground_size=20.0)
m = open_model(str(_ifc))
# two desks of the same cataloged type — then override ONE desk's finish at the instance level
g1 = edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1600 × 800", "storey": "Level 1"})
g2 = edit.RECIPES["add_family"](m, {"family": "desk", "type_name": "1600 × 800", "storey": "Level 1"})
guid1 = g1 if isinstance(g1, str) else (g1.get("guid") or g1.get("changed"))
guid2 = g2 if isinstance(g2, str) else (g2.get("guid") or g2.get("changed"))
el1, el2 = m.by_guid(guid1), m.by_guid(guid2)
typ = next(t for t in m.by_type("IfcFurnitureType") if "1.6" in (t.Name or ""))
# a type-level pset both desks inherit
tps = ifcopenshell.api.run("pset.add_pset", m, product=typ, name="Pset_Custom")
ifcopenshell.api.run("pset.edit_pset", m, pset=tps, properties={"Finish": "Oak", "Grade": "A"})
# instance override on desk 1 only
ips = ifcopenshell.api.run("pset.add_pset", m, product=el1, name="Pset_Custom")
ifcopenshell.api.run("pset.edit_pset", m, pset=ips, properties={"Finish": "Walnut"})

# --- the effective view: instance shadows type, sibling untouched ----------------------------------
eff1 = instance_props.effective_properties(m, guid1)
row = eff1["psets"]["Pset_Custom"]
assert row["Finish"] == {"value": "Walnut", "source": "instance", "overridden": True,
                         "type_value": "Oak"}, row["Finish"]
assert row["Grade"]["source"] == "type" and row["Grade"]["value"] == "A"
assert eff1["override_count"] == 1 and eff1["type_name"] and "1.6" in eff1["type_name"]
eff2 = instance_props.effective_properties(m, guid2)
assert eff2["psets"]["Pset_Custom"]["Finish"]["source"] == "type"      # sibling still pure type
assert eff2["override_count"] == 0

# --- reset to type: the override disappears, the type value shows through --------------------------
out = instance_props.reset_property_to_type(m, guid1, "Pset_Custom", "Finish")
assert out["now"] == "Oak", out
eff1b = instance_props.effective_properties(m, guid1)
assert eff1b["psets"]["Pset_Custom"]["Finish"]["source"] == "type"
assert eff1b["override_count"] == 0
# the empty occurrence pset is gone entirely (no dangling shells)
assert not [ps for rel in (el1.IsDefinedBy or []) if rel.is_a("IfcRelDefinesByProperties")
            for ps in [rel.RelatingPropertyDefinition]
            if ps.is_a("IfcPropertySet") and ps.Name == "Pset_Custom"]
# guard rails: resetting a prop with no type backing / no occurrence value is refused loudly
for bad in (("Pset_Custom", "OnlyOnInstance"), ("Pset_Nope", "Finish")):
    try:
        instance_props.reset_property_to_type(m, guid1, *bad)
        raise AssertionError(f"expected ValueError for {bad}")
    except ValueError:
        pass

# --- the recipe + route ----------------------------------------------------------------------------
ips2 = ifcopenshell.api.run("pset.add_pset", m, product=el2, name="Pset_Custom")
ifcopenshell.api.run("pset.edit_pset", m, pset=ips2, properties={"Grade": "B"})
edit.RECIPES["reset_prop_to_type"](m, {"guid": guid2, "pset": "Pset_Custom", "prop": "Grade"})
assert instance_props.effective_properties(m, guid2)["psets"]["Pset_Custom"]["Grade"]["value"] == "A"
m.write(str(_ifc))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Inst"}).json()["id"]
    with SessionLocal() as db:
        db.get(Project, pid).source_ifc = str(_ifc)
        db.commit()
    r = c.get(f"/projects/{pid}/model/element/{guid1}/effective-props")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["psets"]["Pset_Custom"]["Finish"]["source"] == "type"
    assert c.get(f"/projects/{pid}/model/element/NOPE/effective-props").status_code == 404

if _ifc.exists():
    _ifc.unlink()

print("INSTANCE-PROPS OK - the effective view layers occurrence psets over the type's (desk 1's "
      "Walnut shadows the type's Oak with overridden=true while its sibling stays pure type, "
      "override_count tracks); reset-to-type removes the occurrence property so Oak shows through "
      "again and drops the now-empty pset shell; resetting without type backing or without an "
      "occurrence value is refused by name; the reset_prop_to_type recipe and the "
      "/model/element/{guid}/effective-props route (404 unknown) serve it end to end.")
