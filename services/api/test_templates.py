"""Reusable templates: save a module's records as a template, list, apply to a project, delete.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_templates.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./templates_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_tpl"
os.environ.pop("AEC_RBAC", None)
for f in ("./templates_test.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    src = c.post("/projects", json={"name": "Source"}).json()["id"]
    dst = c.post("/projects", json={"name": "Target"}).json()["id"]

    # build a checklist in the source project, then save it as a template
    for item in ["Rebar placement", "Formwork", "Embeds"]:
        r = c.post(f"/projects/{src}/modules/checklist", json={"data": {"name": item, "category": "Pre-pour"}})
        assert r.status_code == 201, r.text
    saved = c.post(f"/projects/{src}/modules/checklist/save-template", json={"name": "Concrete pre-pour"})
    assert saved.status_code == 201 and saved.json()["item_count"] == 3, saved.text
    tid = saved.json()["id"]

    # it shows up in the template list for the module
    lst = c.get("/templates?module=checklist").json()
    assert any(t["id"] == tid and t["name"] == "Concrete pre-pour" for t in lst), lst

    # apply it to a different project -> 3 new records
    ap = c.post(f"/projects/{dst}/modules/checklist/apply-template/{tid}")
    assert ap.status_code == 201 and ap.json()["created"] == 3, ap.text
    recs = c.get(f"/projects/{dst}/modules/checklist").json()
    assert len(recs) == 3 and {r["data"]["name"] for r in recs} == {"Rebar placement", "Formwork", "Embeds"}, recs

    # wrong-module apply is rejected; delete works
    assert c.post(f"/projects/{dst}/modules/rfi/apply-template/{tid}").status_code == 404
    assert c.delete(f"/templates/{tid}").json()["ok"] is True
    assert not c.get("/templates?module=checklist").json()

    print("TEMPLATES OK - save module records as template, list, apply to another project (3 records), wrong-module 404, delete")
