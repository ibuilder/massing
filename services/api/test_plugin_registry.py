"""PLUGIN-REGISTRY: manifest-gated recipe plugins — opt-in discovery, api-version gate, namespacing +
collision refusal, idempotent reload, end-to-end recipe application, endpoints.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_plugin_registry.py"""
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./_plugreg_test.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_plugreg")
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./_plugreg_test.db"):
    os.remove("./_plugreg_test.db")

import sys  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

PDIR = Path(tempfile.mkdtemp(prefix="aec_plugins_"))
os.environ["AEC_PLUGINS_DIR"] = str(PDIR)


def _mk(name: str, manifest: dict | None, entry_src: str | None = None, entry_name: str = "plugin.py"):
    d = PDIR / name
    d.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    if entry_src is not None:
        (d / entry_name).write_text(entry_src, encoding="utf-8")


GOOD = """
def bump(model, params):
    # count storeys — every generated model has them (massing IFCs carry slabs/storeys/spaces, no walls)
    return {"changed": len(model.by_type("IfcBuildingStorey")), "note": params.get("note")}

def register(api):
    api.register_recipe("bump", bump, category="properties", produces="IfcPropertySet")
"""

_mk("goodplug", {"name": "goodplug", "version": "1.0.0", "api_version": "1.0"}, GOOD)
_mk("oldapi", {"name": "oldapi", "version": "0.9", "api_version": "2.0"}, GOOD)     # major mismatch
_mk("nomanifest", None, GOOD)                                                        # no plugin.json
_mk("broken", {"name": "broken", "version": "1.0", "api_version": "1.0"}, "def register(api):\n    raise RuntimeError('boom')\n")
_mk("collide", {"name": "goodplug", "version": "9.9", "api_version": "1.0"}, GOOD)  # same ns + recipe → collision

from aec_api import plugin_registry as pr  # noqa: E402
from aec_data import edit  # noqa: E402

# --- gate 1: OFF by default — plugins execute code at load, so nothing loads without the env opt-in --
os.environ.pop("AEC_PLUGINS_ENABLED", None)
r0 = pr.load_all()
assert r0["enabled"] is False and r0["loaded"] == [] and "goodplug.bump" not in edit.RECIPES

# --- enabled: good loads; bad api / missing manifest / broken register / collision are refused -------
os.environ["AEC_PLUGINS_ENABLED"] = "1"
r = pr.load_all()
assert r["enabled"] is True
loaded_names = [p["name"] for p in r["loaded"]]
assert loaded_names.count("goodplug") == 1, loaded_names           # collide/ refused, not double-loaded
good = next(p for p in r["loaded"] if p["name"] == "goodplug")
assert good["recipes"] == ["goodplug.bump"]
refused = {p["name"]: p["reason"] for p in r["refused"]}
assert "oldapi" in refused and "incompatible" in refused["oldapi"], refused
assert "nomanifest" in refused and "manifest" in refused["nomanifest"], refused
assert "broken" in refused and "boom" in refused["broken"], refused
assert any("already registered" in v for v in refused.values()), refused   # the colliding dir
assert "goodplug.bump" in edit.RECIPES

# --- idempotent reload: same state, no duplicate keys ------------------------------------------------
r2 = pr.load_all()
assert [p["name"] for p in r2["loaded"]] == loaded_names
assert list(edit.RECIPES).count("goodplug.bump") == 1

# --- end-to-end: the namespaced recipe runs through apply_recipe on a real model --------------------
from aec_data import massing  # noqa: E402

metrics = massing.compute_massing({"lot_width": 12, "lot_depth": 10, "far": 1.0, "floor_to_floor": 3.5})
src = str(PDIR / "m.ifc")
massing.generate_ifc(metrics, src, name="PlugTest")
out = str(PDIR / "m_out.ifc")
res = edit.apply_recipe(src, "goodplug.bump", {"note": "hi"}, out)
assert res["recipe"] == "goodplug.bump" and res["changed"]["note"] == "hi"
assert res["changed"]["changed"] > 0, "the model has storeys for the recipe to count"

# --- the authoring matrix picks the plugin recipe up, categorized (not uncategorized) ---------------
from aec_api import authoring_matrix  # noqa: E402

mx = authoring_matrix.matrix()
assert "goodplug.bump" not in mx["uncategorized"], mx["uncategorized"]
all_recipes = {row["recipe"] for rows in mx["by_category"].values() for row in rows["recipes"]}
assert "goodplug.bump" in all_recipes

# --- endpoints ---------------------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    st = c.get("/plugins").json()
    assert st["api_version"] == pr.PLUGIN_API_VERSION and st["enabled"] is True
    assert any(p["name"] == "goodplug" for p in st["loaded"]), st
    rl = c.post("/plugins/reload")
    assert rl.status_code == 200 and any(p["name"] == "goodplug" for p in rl.json()["loaded"])
    # SEC: with RBAC on, reload is a platform-admin operation (plugins execute code)
    from aec_api import rbac as _rbac
    _saved = _rbac.RBAC_ON
    _rbac.RBAC_ON = True
    try:
        assert c.post("/plugins/reload").status_code == 403
        assert c.get("/plugins").status_code in (200, 401, 403)   # status stays readable for authed users
    finally:
        _rbac.RBAC_ON = _saved

# cleanup: unload so no plugin recipe leaks into other suites' RECIPES view
os.environ.pop("AEC_PLUGINS_ENABLED", None)
pr.load_all()
assert "goodplug.bump" not in edit.RECIPES

print("PLUGIN-REGISTRY OK - off by default (code execution is opt-in); manifest + api-version MAJOR "
      "gate; broken plugins refused with reasons (bad api / no manifest / register() raised / recipe "
      "collision) and never block the rest; reload idempotent; the namespaced recipe applies through "
      "apply_recipe on a real IFC and shows in the authoring matrix categorized; GET /plugins + "
      "admin-gated POST /plugins/reload work.")
