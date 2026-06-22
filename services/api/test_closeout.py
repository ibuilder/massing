"""Turnover/closeout deliverables: the closeout package ZIP + module-log PDF.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_closeout.py"""
import io
import os
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./test_closeout.db"
os.environ["STORAGE_DIR"] = "./test_storage_closeout"
os.environ["IFC_DIR"] = "./test_ifc_closeout"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_closeout.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Turnover Tower"}, headers=H).json()["id"]
    # a generated model so the package has an as-built IFC + COBie/QTO/spaces
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 30, "lot_depth": 20, "far": 2.0, "units": True}, headers=H)
    assert g.status_code == 200, g.text

    # closeout records (subject alias fills each module's title field)
    for mod, subj in [("commissioning", "HVAC Cx"), ("om_manual", "O&M"), ("warranty", "Roof 10yr"),
                      ("as_built", "Structural"), ("asset_register", "AHU-1"),
                      ("completion_certificate", "Substantial completion")]:
        r = c.post(f"/projects/{pid}/modules/{mod}", json={"data": {"subject": subj}}, headers=H)
        assert r.status_code == 201, (mod, r.text)
    # a couple RFIs for the log
    for s in ("Beam clash", "Door mismatch"):
        c.post(f"/projects/{pid}/modules/rfi", json={"data": {"subject": s, "question": "?"}}, headers=H)

    # --- closeout package ZIP -------------------------------------------------
    z = c.get(f"/projects/{pid}/closeout/package.zip", headers=H)
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip", z.status_code
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    names = zf.namelist()
    assert "as-built/model.ifc" in names, names
    assert "data/cobie.xlsx" in names and "data/qto.xlsx" in names and "data/spaces.xlsx" in names, names
    assert "report/status.pdf" in names, names
    assert "closeout/manifest.json" in names, names
    import json
    manifest = json.loads(zf.read("closeout/manifest.json"))
    assert manifest["closeout"]["warranty"][0]["title"] == "Roof 10yr", manifest["closeout"]["warranty"]
    assert len(manifest["closeout"]["completion_certificate"]) == 1

    # --- module log PDF -------------------------------------------------------
    log = c.get(f"/projects/{pid}/modules/rfi/log.pdf", headers=H)
    assert log.status_code == 200 and log.content[:4] == b"%PDF", log.status_code
    assert len(log.content) > 800, len(log.content)

print("CLOSEOUT OK - package.zip bundles as-built IFC + COBie/QTO/spaces + status PDF + closeout "
      "manifest; module log.pdf renders the RFI register")
