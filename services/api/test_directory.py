"""Company / contact directory + first-class lookups: directory records exist, and reference fields
(contact.company, subcontract.vendor_company) resolve to the company + show as incoming links.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_directory.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_directory.db"
os.environ["STORAGE_DIR"] = "./test_storage_directory"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_directory.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Dir"}).json()["id"]

    # directory: a company + a contact that belongs to it (first-class lookup via a reference field)
    org = c.post(f"/projects/{pid}/modules/company",
                 json={"data": {"name": "Ace Mechanical", "type": "Subcontractor", "trade": "HVAC",
                                "email": "ops@ace.com", "phone": "512-555-0100"}}).json()
    assert org["ref"].startswith("ORG-"), org
    per = c.post(f"/projects/{pid}/modules/contact",
                 json={"data": {"name": "Dana Lee", "company": org["id"], "title": "PM"}}).json()
    # the contact's company reference resolves to a brief
    perr = c.get(f"/projects/{pid}/modules/contact/{per['id']}").json()
    assert perr["data_refs"]["company"]["ref"] == org["ref"], perr["data_refs"]

    # first-class vendor lookup on a subcontract (alongside the free-text vendor)
    sub = c.post(f"/projects/{pid}/modules/subcontract",
                 json={"data": {"vendor": "Ace Mechanical", "vendor_company": org["id"],
                                "trade": "HVAC", "value": 850000}}).json()
    subr = c.get(f"/projects/{pid}/modules/subcontract/{sub['id']}").json()
    assert subr["data_refs"]["vendor_company"]["ref"] == org["ref"], subr["data_refs"]

    # reverse: the company's related records show the contact + subcontract pointing at it
    rel = c.get(f"/projects/{pid}/modules/company/{org['id']}/related").json()
    incoming = {(x["module"], x["ref"]) for x in rel["incoming"]}
    assert ("contact", per["ref"]) in incoming and ("subcontract", sub["ref"]) in incoming, rel["incoming"]

    # directory lists
    assert len(c.get(f"/projects/{pid}/modules/company").json()) == 1
    assert len(c.get(f"/projects/{pid}/modules/contact").json()) == 1

print("DIRECTORY OK - company + contact directory; contact.company + subcontract.vendor_company "
      "resolve to the company; reverse links list the contact + subcontract; lists work")
