"""E6 — recipe-log design-option branches: snapshot the model as a named option, keep editing,
switch back (undoably), diff branches. Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_model_options.py"""
import os
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_model_options.db"
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="opt_store_")
os.environ["IFC_DIR"] = tempfile.mkdtemp(prefix="opt_ifc_")   # /app is read-only on CI
os.environ["AEC_TRUST_XUSER"] = "1"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_model_options.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "editor"}
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Branches"}, headers=H).json()["id"]
    g = c.post(f"/projects/{pid}/generate/massing",
               json={"lot_width": 20, "lot_depth": 15, "far": 1.0, "use_type": "commercial"},
               headers=H)
    assert g.status_code == 200 and g.json()["source_ifc"], g.text[:200]

    # snapshot the base scheme; a nameless snapshot is a clean 400
    a = c.post(f"/projects/{pid}/model/options", json={"name": "Scheme A — base"}, headers=H)
    assert a.status_code == 200 and a.json()["slug"] == "scheme-a-base", a.text[:200]
    assert a.json()["elements"] and a.json()["size_bytes"] > 0, a.json()
    assert c.post(f"/projects/{pid}/model/options", json={"name": "  "}, headers=H).status_code == 400

    # edit the model (add a wall, no publish) → the working model diverges from Scheme A
    e = c.post(f"/projects/{pid}/edit",
               json={"recipe": "add_wall",
                     "params": {"start": [0, 0], "end": [5, 0], "height": 3, "thickness": 0.2},
                     "publish": False}, headers=H)
    assert e.status_code == 200, e.text[:300]

    # snapshot the edited scheme → 2 options; B is byte-identical to the current source
    b = c.post(f"/projects/{pid}/model/options", json={"name": "Scheme B — extra wall"}, headers=H)
    assert b.status_code == 200, b.text[:200]
    ls = c.get(f"/projects/{pid}/model/options", headers=H).json()
    assert ls["count"] == 2, ls
    by = {o["slug"]: o for o in ls["options"]}
    assert by["scheme-b-extra-wall"]["current"] is True and by["scheme-a-base"]["current"] is False, by

    # diff current vs Scheme A: exactly the added wall separates them
    d = c.get(f"/projects/{pid}/model/options/scheme-a-base/diff", headers=H).json()
    assert d["added_count"] == 1 and d["removed_count"] == 0 and not d["identical"], d
    assert d["class_deltas"].get("IfcWall", {}).get("delta") == 1, d["class_deltas"]
    # vs Scheme B it's identical
    assert c.get(f"/projects/{pid}/model/options/scheme-b-extra-wall/diff", headers=H).json()["identical"]

    # activate Scheme A → the working model flips back (wall gone), and the switch is ONE undo step
    act = c.post(f"/projects/{pid}/model/options/scheme-a-base/activate",
                 json={"publish": False}, headers=H)
    assert act.status_code == 200 and act.json()["activated"] == "scheme-a-base", act.text[:200]
    ls2 = c.get(f"/projects/{pid}/model/options", headers=H).json()
    assert {o["slug"]: o["current"] for o in ls2["options"]}["scheme-a-base"] is True, ls2
    u = c.post(f"/projects/{pid}/edit/undo", json={"publish": False}, headers=H)
    assert u.status_code == 200, u.text[:200]
    ls3 = c.get(f"/projects/{pid}/model/options", headers=H).json()
    assert {o["slug"]: o["current"] for o in ls3["options"]}["scheme-b-extra-wall"] is True, \
        "undoing the activate returns to Scheme B"

    # unknown option → 404; delete removes the branch (history untouched)
    assert c.get(f"/projects/{pid}/model/options/nope/diff", headers=H).status_code == 404
    assert c.post(f"/projects/{pid}/model/options/nope/activate", json={},
                  headers=H).status_code == 404
    assert c.delete(f"/projects/{pid}/model/options/scheme-a-base", headers=H).json()["deleted"] is True
    assert c.get(f"/projects/{pid}/model/options", headers=H).json()["count"] == 1

print("MODEL-OPTIONS OK - E6 branches: snapshot names a whole-model branch (slug/size/element count; "
      "blank name 400s); editing diverges the working model; list flags the byte-identical branch as "
      "current; diff reports the added wall (class delta +1 IfcWall) and identical-vs-B; activate "
      "switches schemes and is ONE undo step (undo returns to Scheme B); unknown slugs 404; delete "
      "drops the branch only.")
