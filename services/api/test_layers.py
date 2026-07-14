"""IFC5-style property-override layers (Wave 9 W9-3): composition/resolution (strongest enabled layer
wins), cross-layer conflict detection, provenance, bake list, and the stack round-trip endpoints.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_layers.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_layers.db"
os.environ["STORAGE_DIR"] = "./test_storage_layers"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_layers.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import layers  # noqa: E402
from aec_api.main import app  # noqa: E402

# base (weakest) -> discipline -> coordination (strongest). Coordination overrides the discipline
# layer's FireRating (a conflict); a disabled layer contributes nothing.
STACK = [
    {"name": "Architectural", "enabled": True, "overrides": [
        {"guid": "wall1", "pset": "Pset_WallCommon", "prop": "FireRating", "value": "1HR"},
        {"guid": "wall1", "pset": "Pset_WallCommon", "prop": "IsExternal", "value": True}]},
    {"name": "Fire coordination", "enabled": True, "overrides": [
        {"guid": "wall1", "pset": "Pset_WallCommon", "prop": "FireRating", "value": "2HR"}]},
    {"name": "Draft (off)", "enabled": False, "overrides": [
        {"guid": "wall1", "pset": "Pset_WallCommon", "prop": "FireRating", "value": "3HR"}]},
]
base = {("wall1", "Pset_WallCommon", "FireRating"): "0HR"}
r = layers.resolve(STACK, lambda g, p, pr: base.get((g, p, pr)))

fr = next(o for o in r["overrides"] if o["prop"] == "FireRating")
assert fr["effective"] == "2HR", fr                       # strongest ENABLED layer wins
assert fr["winning_layer"] == "Fire coordination", fr
assert fr["base"] == "0HR", fr                            # annotated with what it overrides
assert fr["setters"] == ["Architectural", "Fire coordination"], fr   # disabled layer excluded
assert r["conflict_count"] == 1 and r["conflicts"][0]["prop"] == "FireRating", r
assert {v["value"] for v in r["conflicts"][0]["values"]} == {"1HR", "2HR"}, r["conflicts"]
# IsExternal set by only one layer -> effective, no conflict
ext = next(o for o in r["overrides"] if o["prop"] == "IsExternal")
assert ext["effective"] is True and ext["winning_layer"] == "Architectural"
assert r["effective_count"] == 2, r                       # FireRating + IsExternal

# bake list = resolved effective overrides (top wins, deduped)
baked = layers.bake_overrides(STACK)
assert {(b["prop"], b["value"]) for b in baked} == {("FireRating", "2HR"), ("IsExternal", True)}, baked

# a fully-disabled stack composes to nothing
assert layers.resolve([{"name": "X", "enabled": False, "overrides": [
    {"guid": "w", "pset": "P", "prop": "A", "value": 1}]}])["effective_count"] == 0

# --- endpoint round-trip: store + read the stack (pure data, no IFC needed) --------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Layers Test"}).json()["id"]
    assert c.get(f"/projects/{pid}/layers").json() == {"layers": []}      # empty default
    put = c.put(f"/projects/{pid}/layers", json={"layers": STACK})
    assert put.status_code == 200 and len(put.json()["layers"]) == 3, put.text[:200]
    got = c.get(f"/projects/{pid}/layers").json()
    assert got["layers"][1]["name"] == "Fire coordination", got
    # resolve with no source IFC still composes (base annotations just come back null)
    res = c.get(f"/projects/{pid}/layers/resolve").json()
    assert res["conflict_count"] == 1 and res["effective_count"] == 2, res

print("LAYERS OK - 3-layer stack composes (strongest enabled wins: FireRating 1HR<-2HR, disabled 3HR "
      "excluded); conflict flagged with both values + provenance; base value annotated; bake list = "
      "resolved effective overrides; stack PUT/GET/resolve endpoints round-trip.")
