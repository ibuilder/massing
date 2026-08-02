"""R28-UNIFY — opening a project guarantees there is something to draw on.

Creating a blank model already existed (`POST /model/blank`), but only as an explicit user action, so
a project with no model still opened into an empty viewer. `POST /model/ensure` is the same capability
made **idempotent**, so an open path can call it every time.

The assertions are about the two ways an "ensure" endpoint destroys data:

1. **it must never overwrite a model that is already there.** Idempotence is the whole safety
   property — an ensure that can overwrite is a data-loss endpoint wearing a helpful name;
2. **a BROKEN reference is not "no model".** If `source_ifc` is set but the file is missing, quietly
   creating a blank one destroys the only pointer to something that may be recoverable, and reports
   success while doing it. Refused, and the missing path is named so somebody can look for it.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_model_ensure.py
"""
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./test_model_ensure.db"
os.environ["STORAGE_DIR"] = "./test_storage_model_ensure"
# IFC_DIR must be set BEFORE the app imports: _IFC_DIR defaults to /app/ifc, which is writable on a
# Windows dev box (C:\app) and PermissionError on a CI runner — the test passed everywhere except
# where it mattered. Same reason DATABASE_URL/STORAGE_DIR are pinned above.
os.environ["IFC_DIR"] = "./test_ifc_model_ensure"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_ensure.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


with TestClient(app) as c:
    c.headers.update({"X-User": "ensure@test"})

    # --- 1. a project with no model gets one -------------------------------------------------------
    pid = c.post("/projects", json={"name": "Fresh"}).json()["id"]
    r = c.post(f"/projects/{pid}/model/ensure")
    check("ensure answers 200 on a project with no model", r.status_code == 200, r.text[:200])
    j = r.json()
    check("  it reports CREATED, not a bare success", j["status"] == "created" and j["created"] is True, j)
    check("  and the project now points at a real file", os.path.exists(j["source_ifc"]), j["source_ifc"])
    check("  with a note saying why, so an open path can show it",
          "start immediately" in j["note"], j["note"])

    first_path = j["source_ifc"]
    first_bytes = os.path.getsize(first_path)

    # --- 2. IDEMPOTENCE — the whole safety property ------------------------------------------------
    r2 = c.post(f"/projects/{pid}/model/ensure").json()
    check("a second ensure reports FOUND, not created again", r2["status"] == "found", r2)
    check("  created is False — the distinction a caller acts on", r2["created"] is False, r2)
    check("  it points at the SAME file", r2["source_ifc"] == first_path, r2)
    check("  and NOTHING was written — the file is byte-identical",
          os.path.getsize(first_path) == first_bytes,
          f"{first_bytes} -> {os.path.getsize(first_path)}")
    check("  the note says nothing was written", "nothing was written" in r2["note"], r2["note"])

    # An authored model must survive. This is the data-loss case in its most ordinary form: a user has
    # drawn something, the open path calls ensure, and the drawing had better still be there.
    with open(first_path, "ab") as fh:
        fh.write(b"\n/* authored content marker */\n")
    marked = os.path.getsize(first_path)
    c.post(f"/projects/{pid}/model/ensure")
    check("A MODEL WITH CONTENT IS NEVER REPLACED — the user's drawing survives ensure",
          os.path.getsize(first_path) == marked,
          f"expected {marked}, got {os.path.getsize(first_path)}")

    # --- 3. A BROKEN REFERENCE IS REFUSED, not silently healed --------------------------------------
    pid2 = c.post("/projects", json={"name": "Broken"}).json()["id"]
    missing = os.path.abspath("./definitely_not_here_" + pid2 + ".ifc")
    with SessionLocal() as db:
        p = db.get(Project, pid2)
        p.source_ifc = missing
        db.commit()

    r3 = c.post(f"/projects/{pid2}/model/ensure").json()
    check("a project pointing at a MISSING model is not treated as having no model",
          r3["status"] == "broken_reference", r3)
    check("  nothing is created", r3["created"] is False, r3)
    check("  the missing path is NAMED so somebody can go and look for it",
          r3["source_ifc"] == missing, r3)
    check("  and the refusal explains the loss it is preventing",
          "may still be recoverable" in r3["note"], r3["note"])
    check("  no file was conjured at the missing path", not os.path.exists(missing), missing)

    with SessionLocal() as db:
        check("  and source_ifc is left untouched, not cleared",
              db.get(Project, pid2).source_ifc == missing)

    # --- 4. ordinary failures -----------------------------------------------------------------------
    check("an unknown project is 404, not a new model somewhere",
          c.post("/projects/nope-not-a-project/model/ensure").status_code == 404)

    # --- 5. the storeys parameter is honoured on creation -------------------------------------------
    pid3 = c.post("/projects", json={"name": "Tall"}).json()["id"]
    j3 = c.post(f"/projects/{pid3}/model/ensure?storeys=7&storey_height=4.0").json()
    check("ensure honours the requested storey count when it creates",
          j3["storeys"] == 7 and j3["storey_height"] == 4.0, j3)
    import ifcopenshell  # noqa: E402
    check("  and the model really has them",
          len(ifcopenshell.open(j3["source_ifc"]).by_type("IfcBuildingStorey")) == 7,
          len(ifcopenshell.open(j3["source_ifc"]).by_type("IfcBuildingStorey")))

print()
if FAILED:
    print(f"model_ensure: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("model_ensure: all checks passed")
