"""Element → linked-records reverse deep-link (all pinnable modules) + FF&E classification.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_element_records.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_element_records.db"
os.environ["STORAGE_DIR"] = "./test_storage_er"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_element_records.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

GUID = "3xY7zAbCdEf0GhIjKlMnOp"

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "Links Tower"}).json()["id"]

    # (1) a field_verification record whose data.guid is the element
    fv = tc.post(f"/projects/{pid}/modules/field_verification",
                 json={"data": {"guid": GUID, "element": "C-12", "ifc_class": "IfcColumn"}})
    assert fv.status_code in (200, 201), fv.text[:200]

    # (2) an RFI tagged to the same element via element_guids (the top-level tag list)
    rfi = tc.post(f"/projects/{pid}/modules/rfi",
                  json={"data": {"subject": "Column clash at C-12", "question": "Confirm the column offset."}}).json()
    tag = tc.post(f"/projects/{pid}/modules/rfi/{rfi['id']}/elements", json={"guids": [GUID], "mode": "add"})
    assert tag.status_code in (200, 201), tag.text[:200]

    # reverse lookup: the element is referenced by 2 records across 2 modules
    r = tc.get(f"/projects/{pid}/elements/{GUID}/records")
    assert r.status_code == 200, r.text[:200]
    b = r.json()
    assert b["total"] == 2, b
    mods = {g["module"]: g for g in b["modules"]}
    assert set(mods) == {"field_verification", "rfi"}, list(mods)
    assert mods["field_verification"]["records"][0]["ref"] and mods["rfi"]["count"] == 1, b

    # an unreferenced GUID returns an empty (but well-formed) result
    empty = tc.get(f"/projects/{pid}/elements/does-not-exist/records").json()
    assert empty["total"] == 0 and empty["modules"] == [], empty

# FF&E / Furnishings classification (from the pics8 research) — furnishing classes map to Div 12
from aec_api import classification  # noqa: E402

for cls in ("IfcFurniture", "IfcFurnishingElement", "IfcSystemFurnitureElement"):
    code, title = classification.classify(cls, "masterformat")
    assert code.startswith("12") and "FF&E" in title, (cls, code, title)

print("ELEMENT-RECORDS OK - reverse deep-link: an element referenced by a field_verification (data.guid) "
      "and an RFI (element_guids tag) is found across both pinnable modules (total 2); unreferenced GUID "
      "returns empty; FF&E furnishing classes (IfcFurniture/IfcFurnishingElement/IfcSystemFurnitureElement) "
      "classify to MasterFormat Division 12. Completes the record<->element round-trip.")
