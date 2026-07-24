"""VIEW-TEMPLATES — reusable layered view presets: class visibility + isolate scope + stacked color
rules, resolved deterministically (same template + same index = same answer). Engine + routes.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_view_templates.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_view_templates.db"
os.environ["STORAGE_DIR"] = "./test_storage_viewtpl"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_view_templates.db"):
    os.remove("./test_view_templates.db")

from aec_api import view_templates as vt  # noqa: E402

IDX = {
    "w1": {"ifc_class": "IfcWall", "storey": "L1", "psets": {"Pset_WallCommon": {"IsExternal": "true"}}},
    "w2": {"ifc_class": "IfcWall", "storey": "L2", "psets": {"Pset_WallCommon": {"IsExternal": "false"}}},
    "d1": {"ifc_class": "IfcDoor", "storey": "L1", "psets": {}},
    "p1": {"ifc_class": "IfcPump", "storey": "L1", "psets": {}},
}

# --- validation: selectors must parse, colors must be hex, empty templates rejected ----------------
tpl = vt._norm({"name": "Fire plan", "hide_classes": ["IfcPump"],
                "isolate": "storey=L1",
                "rules": [{"selector": "IfcWall", "color": "#FF0000"},
                          {"selector": "Pset_WallCommon.IsExternal=true", "color": "#00ff00"}]})
assert tpl["rules"][0]["color"] == "#ff0000", tpl                      # normalized lowercase
for bad in ({"name": "x"},                                             # nothing to do
            {"name": "x", "rules": [{"selector": "IfcWall", "color": "red"}]},   # bad color
            {"name": "x", "rules": [{"selector": "&", "color": "#ff0000"}]},     # bad selector
            {"name": "x", "isolate": "a" * 501}):                      # oversized selector
    try:
        vt._norm(bad)
        raise AssertionError(f"expected QueryError for {bad!r}")
    except vt.QueryError:
        pass

# --- resolve: isolate scope + class hiding + later-rule-wins colors, all deterministic -------------
r = vt.resolve(IDX, tpl)
assert r["visible"] == ["d1", "w1"], r["visible"]         # L1 only, pump hidden by class, w2 off-scope
assert r["hidden_count"] == 2 and r["visible_count"] == 2, r
# w1 matched BOTH rules — the later (external, green) wins; d1 matched neither
assert r["colors"] == {"w1": "#00ff00"}, r["colors"]
assert vt.resolve(IDX, tpl) == r, "same template + same index must resolve identically"

# no isolate → whole model in scope; only the hide matrix applies
r2 = vt.resolve(IDX, vt._norm({"name": "No pumps", "hide_classes": ["IfcPump"]}))
assert r2["visible"] == ["d1", "w1", "w2"] and r2["hidden_count"] == 1, r2

# --- routes: save (atomic validation) + resolve against the loaded model ---------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Templates"}).json()["id"]
    assert c.get(f"/projects/{pid}/view-templates").json()["templates"] == []
    ok = c.put(f"/projects/{pid}/view-templates", json={"templates": [
        {"name": "Fire plan", "hide_classes": ["IfcPump"], "isolate": "storey=L1",
         "rules": [{"selector": "IfcWall", "color": "#ff0000"}]}]})
    assert ok.status_code == 200 and ok.json()["saved"] == 1, ok.text
    tid = ok.json()["templates"][0]["id"]
    # a bad save is rejected atomically — the stored set is unchanged
    bad = c.put(f"/projects/{pid}/view-templates",
                json={"templates": [{"name": "x", "rules": [{"selector": "IfcWall", "color": "red"}]}]})
    assert bad.status_code == 422, bad.text
    assert len(c.get(f"/projects/{pid}/view-templates").json()["templates"]) == 1
    # resolve: no model loaded → empty-but-well-formed; unknown id 404
    rr = c.get(f"/projects/{pid}/view-templates/{tid}/resolve")
    assert rr.status_code == 200 and rr.json()["visible_count"] == 0, rr.text
    assert c.get(f"/projects/{pid}/view-templates/nope/resolve").status_code == 404

print("VIEW-TEMPLATES OK - layered presets validate atomically (selectors parse, colors are #rrggbb, "
      "empty templates rejected) and resolve deterministically: an L1 isolate + IfcPump hide leaves "
      "d1+w1 visible, stacked color rules apply later-wins (the external wall takes the second rule's "
      "green), an identical re-resolve is byte-identical, and a hide-only template scopes the whole "
      "model; the routes round-trip templates (bad saves rejected atomically), resolve against the "
      "loaded model, and 404 unknown ids.")
