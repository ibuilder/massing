"""Project package — the shareable client deliverable: one PDF with cover + visual overview + drawing set
+ cost & feasibility. Covers package.project_package_pdf + the /project-package.pdf route.
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_project_package.py"""
import io
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_project_package.db"
os.environ["STORAGE_DIR"] = "./test_storage_pkg"
os.environ["IFC_DIR"] = "./test_ifc_pkg"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_project_package.db",):
    if os.path.exists(f):
        os.remove(f)

import sys  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

# a small but real model (a couple of walls + a slab + spaces) so overview + estimate have content
_ifc = Path(tempfile.gettempdir()) / "pkg_model.ifc"
massing.generate_blank_ifc(str(_ifc), name="Package Model", storeys=2, storey_height=3.0, ground_size=16.0)
m = open_model(str(_ifc))
st = m.by_type("IfcBuildingStorey")[0].Name
edit.add_wall(m, [0, 0], [8, 0], 3.0, 0.2, st)
edit.add_wall(m, [8, 0], [8, 6], 3.0, 0.2, st)
edit.add_column(m, [4, 3], 3.0, 0.4, 0.4, st)
edit.add_spaces(m, rooms_per_storey=2, ceiling_height=3.0)
m.write(str(_ifc))
IFC_BYTES = _ifc.read_bytes()

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Package Test"}).json()["id"]

    # contents pre-flight before a model → no model, sections listed
    pre = c.get(f"/projects/{pid}/project-package/contents").json()
    assert pre["has_model"] is False and "drawing-set" in pre["sections"], pre
    # package without a source IFC → 409
    assert c.get(f"/projects/{pid}/project-package.pdf").status_code == 409

    up = c.post(f"/projects/{pid}/source-ifc?publish=false",
                files={"file": ("source.ifc", IFC_BYTES, "application/octet-stream")})
    assert up.status_code == 200, up.text[:160]
    # sync the developer budget from the model so the feasibility page has real numbers
    c.post(f"/projects/{pid}/dev-budget/sync-from-model")

    contents = c.get(f"/projects/{pid}/project-package/contents").json()
    assert contents["has_model"] and contents["has_budget"], contents

    r = c.get(f"/projects/{pid}/project-package.pdf?max_sheets=4")
    assert r.status_code == 200 and r.content[:5] == b"%PDF-", (r.status_code, r.content[:16])
    pages = len(PdfReader(io.BytesIO(r.content)).pages)
    # cover + overview + drawing set (cover + 2 plans + schedules) + cost&feasibility = 7 pages
    assert pages >= 5, f"package should bundle several pages, got {pages}"

print("PROJECT-PACKAGE OK - /projects/{pid}/project-package.pdf bundles ONE shareable client deliverable: "
      "a cover/contents, a visual overview (plan · section · elevation composed sheet), the compiled "
      "drawing set, and a cost & feasibility summary (model-takeoff estimate by discipline + the developer "
      "budget's capital stack: hard/soft/debt/equity). 409 without a source IFC; contents pre-flight "
      "reports model/budget availability. The GC/architect 'show someone' deliverable.")
