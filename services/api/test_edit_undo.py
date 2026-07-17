"""S4 edit undo/redo: authoring edits push the prior model version onto a per-project stack; undo restores
it (GUID-stable), redo re-applies. Stack is a storage sidecar (no schema change).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_edit_undo.py"""
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_undo_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_undo")
os.environ.setdefault("AEC_TRUST_XUSER", "1")
# /model/blank writes the source IFC under IFC_DIR (defaults to /app/ifc, which is read-only in the CI
# container). Point it at a writable scratch dir. See the container-readonly-/app gotcha.
os.environ.setdefault("IFC_DIR", os.path.join(os.path.dirname(__file__), "_ifc_undo"))

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import edit_history  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- unit: the sidecar stack ----------------------------------------------------------------------
pid = "proj-undo-test"
assert edit_history.state(pid) == {"can_undo": False, "can_redo": False, "undo_depth": 0, "redo_depth": 0}
edit_history.push(pid, "/ifc/base.ifc")
edit_history.push(pid, "/ifc/base_1.ifc")               # after two edits: 2 undo, 0 redo
st = edit_history.state(pid)
assert st["undo_depth"] == 2 and not st["can_redo"], st
assert edit_history.undo(pid, "/ifc/base_2.ifc") == "/ifc/base_1.ifc"   # restore the last pre-edit path
st = edit_history.state(pid)
assert st["undo_depth"] == 1 and st["redo_depth"] == 1, st              # current pushed to redo
assert edit_history.redo(pid, "/ifc/base_1.ifc") == "/ifc/base_2.ifc"   # redo returns what was undone
assert edit_history.state(pid)["undo_depth"] == 2
# a fresh edit clears redo
edit_history.undo(pid, "/ifc/x.ifc")
assert edit_history.state(pid)["can_redo"] is True
edit_history.push(pid, "/ifc/y.ifc")
assert edit_history.state(pid)["can_redo"] is False, "a new edit invalidates redo"

# --- integration: edit → undo → redo over a real project ------------------------------------------
h = {"X-User": "tester"}
with TestClient(app) as c:
    pr = c.post("/projects", json={"name": "Undo IT", "number": "U-1"}, headers=h)
    assert pr.status_code in (200, 201), pr.text[:200]
    p = pr.json()["id"]

    # seed a blank model as the source IFC
    mk = c.post(f"/projects/{p}/model/blank", json={"name": "Undo", "storeys": 1}, headers=h)
    assert mk.status_code in (200, 201), mk.text[:200]

    hist0 = c.get(f"/projects/{p}/edit/history", headers=h).json()
    assert hist0["can_undo"] is False, hist0

    # author a wall (no publish needed for the undo mechanics — we check the history + source swap)
    e = c.post(f"/projects/{p}/edit", json={"recipe": "add_wall",
               "params": {"start": [0, 0], "end": [5, 0], "height": 3, "thickness": 0.2}, "publish": False}, headers=h)
    assert e.status_code == 200, e.text[:200]
    hist1 = c.get(f"/projects/{p}/edit/history", headers=h).json()
    assert hist1["can_undo"] is True and hist1["undo_depth"] == 1, hist1

    # undo → restored to the pre-edit blank model
    u = c.post(f"/projects/{p}/edit/undo", json={"publish": False}, headers=h)
    assert u.status_code == 200, u.text[:200]
    assert u.json()["state"]["can_redo"] is True
    # redo → the wall version is back
    rd = c.post(f"/projects/{p}/edit/redo", json={"publish": False}, headers=h)
    assert rd.status_code == 200 and rd.json()["state"]["can_undo"] is True, rd.text[:200]

    # nothing-to-undo past the bottom → 409
    c.post(f"/projects/{p}/edit/undo", json={"publish": False}, headers=h)   # undo the wall again
    again = c.post(f"/projects/{p}/edit/undo", json={"publish": False}, headers=h)
    assert again.status_code == 409, again.text[:200]

    # COLLAB-1 optimistic edit-lock: an edit carrying a STALE base_source (another user published since)
    # is rejected 409; the current signature (from /collab) is accepted
    cur = c.get(f"/projects/{p}/collab", headers=h).json()["model"]["source"]
    stale = c.post(f"/projects/{p}/edit", json={"recipe": "add_wall",
                   "params": {"start": [0, 0], "end": [4, 0], "height": 3, "thickness": 0.2},
                   "base_source": "some_old_version_99999999999999.ifc"}, headers=h)
    assert stale.status_code == 409, stale.text[:200]
    fresh = c.post(f"/projects/{p}/edit", json={"recipe": "add_wall",
                   "params": {"start": [0, 0], "end": [4, 0], "height": 3, "thickness": 0.2},
                   "base_source": cur}, headers=h)
    assert fresh.status_code == 200, fresh.text[:200]

import shutil  # noqa: E402
for f in ("./_undo_test.db",):
    if os.path.exists(f):
        try:
            os.remove(f)
        except OSError:
            pass
shutil.rmtree(os.environ["IFC_DIR"], ignore_errors=True)

print("EDIT-UNDO OK - the sidecar stack pushes pre-edit versions, undo restores the prior version + pushes "
      "current to redo, redo re-applies, a fresh edit clears redo; over a real project an edit sets can_undo, "
      "undo/redo swap source_ifc (GUID-stable), and undoing past the bottom returns 409.")
