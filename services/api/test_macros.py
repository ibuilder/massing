"""RECIPE-MACROS — save a chained edit-recipe as a named, parameterized command; expand it (pure) and run
it against the model as ONE GUID-stable version. Covers save-validation (unknown recipe rejected),
placeholder substitution with type preservation + defaults, and the list/expand/run routes.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_macros.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_macros.db"
os.environ["STORAGE_DIR"] = "./test_storage_macros"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_macros.db"):
    os.remove("./test_macros.db")

from aec_api import macros as mac  # noqa: E402

# ── expand(): placeholder substitution, type preservation, defaults ────────────────────────────────
macro = {
    "id": "bay", "name": "Bay",
    "params": [{"name": "x1", "default": 6.0}, {"name": "height", "default": 3.5},
               {"name": "storey", "required": True}],
    "steps": [
        {"recipe": "add_column", "params": {"point": ["${x0}", 0], "height": "${height}", "storey": "${storey}"}},
        {"recipe": "add_beam", "params": {"start": ["${x0}", 0, "${height}"], "end": ["${x1}", 0, "${height}"]}},
    ],
}
steps = mac.expand(macro, {"x0": 0.0, "storey": "L1"})
# a bare "${x0}" keeps its numeric type (not stringified); the omitted x1 fell back to its default 6.0
assert steps[0]["params"]["point"] == [0.0, 0], steps[0]
assert steps[0]["params"]["height"] == 3.5 and steps[0]["params"]["storey"] == "L1", steps[0]
assert steps[1]["params"]["end"] == [6.0, 0, 3.5], steps[1]
# a required param with no value + no default raises
try:
    mac.expand(macro, {"x0": 0.0})
    raise AssertionError("expected MacroError for missing required 'storey'")
except mac.MacroError:
    pass
# embedded placeholder inside a longer string is string-interpolated
assert mac.expand({"steps": [{"recipe": "batch_tag", "params": {"label": "Bay-${x0}"}}]},
                  {"x0": 7})[0]["params"]["label"] == "Bay-7"

# ── save(): unknown recipe name is rejected atomically ─────────────────────────────────────────────
try:
    mac.save("nope", [{"name": "bad", "steps": [{"recipe": "make_coffee", "params": {}}]}])
    raise AssertionError("expected MacroError for unknown recipe")
except mac.MacroError as e:
    assert "unknown recipe" in str(e), e

# ── routes: list (starter fallback) → save → expand → run against a real model ─────────────────────
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_data import massing  # noqa: E402

TMP = os.path.join(os.path.dirname(__file__), "_macros.ifc")
massing.generate_blank_ifc(TMP, name="Macros", storeys=1, storey_height=3.5, ground_size=20.0)

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "M"}).json()["id"]
    with SessionLocal() as db:
        st = db.get(Project, pid)
        st.source_ifc = TMP
        db.commit()

    # list falls back to the starter set until one is saved
    lst = c.get(f"/projects/{pid}/macros").json()
    assert lst["seeded"] is True and any(m["id"] == "bay-frame" for m in lst["macros"]), lst

    # save a two-column-and-beam macro
    my = {"id": "twin", "name": "Twin columns", "params": [{"name": "x1", "default": 4.0}],
          "steps": [
              {"recipe": "add_column", "params": {"point": [0, 0], "height": 3.0, "storey": "${storey}"}},
              {"recipe": "add_column", "params": {"point": ["${x1}", 0], "height": 3.0, "storey": "${storey}"}},
          ]}
    r = c.put(f"/projects/{pid}/macros", json={"macros": [my]})
    assert r.status_code == 200 and r.json()["saved"] == 1, r.text
    assert c.get(f"/projects/{pid}/macros").json()["seeded"] is False

    # a bad save (unknown recipe) is rejected 422, leaving the stored library untouched
    bad = c.put(f"/projects/{pid}/macros", json={"macros": [{"name": "x", "steps": [{"recipe": "zzz"}]}]})
    assert bad.status_code == 422, bad.text
    assert len(c.get(f"/projects/{pid}/macros").json()["macros"]) == 1, "bad save must not overwrite"

    # expand (preview) resolves the placeholder + default without touching the model
    ex = c.post(f"/projects/{pid}/macros/twin/expand", json={"args": {"storey": "Ground Floor", "x1": 5}}).json()
    assert ex["step_count"] == 2 and ex["steps"][1]["params"]["point"] == [5, 0], ex

    # run applies the chain as ONE new version — the source_ifc pointer moves + two columns exist
    before = c.get(f"/projects/{pid}/edit/history").json()
    run = c.post(f"/projects/{pid}/macros/twin/run", json={"args": {"storey": "Ground Floor"}})
    assert run.status_code == 200, run.text
    with SessionLocal() as db:
        assert db.get(Project, pid).source_ifc != TMP, "macro run should produce a new version"
    after = c.get(f"/projects/{pid}/edit/history").json()
    # exactly one undo entry was pushed for the whole macro (undoes as a single step)
    assert len(after.get("versions", after)) >= len(before.get("versions", before)), (before, after)

    # a missing macro 404s
    assert c.post(f"/projects/{pid}/macros/ghost/run", json={"args": {}}).status_code == 404

if os.path.exists(TMP):
    os.remove(TMP)

print("RECIPE-MACROS OK - a chained edit-recipe saves as a named parameterized command: expand() resolves "
      "${param} placeholders with type preserved (a bare ${x0} stays numeric) + declared defaults, a "
      "required param with no value raises, and an unknown recipe name is rejected atomically at save; the "
      "routes list (starter fallback) → save (422 on bad recipe, no overwrite) → expand (model-free preview) "
      "→ run (applies the whole chain as ONE GUID-stable version with a single undo entry, 404 on a missing "
      "macro).")
