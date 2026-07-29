"""R23-RECIPE-ARTIFACT over HTTP — the capture actually fires, and the replay actually reproduces.

The engine is tested in `test_recipe_log.py`. What only a live app can show is whether the four
capture hooks in `authoring.py` are on the paths edits really take, and — the assertion the whole
item is for — whether replaying the logged steps against a *fresh* model produces the same building.

That last one is the difference between a log and a provenance artifact. A log that records
plausible-looking steps nobody has ever re-run is indistinguishable from one that works.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_recipe_route.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_recipe_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_recipe_route"
os.environ["IFC_DIR"] = "./test_ifc_recipe_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_recipe_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_data import massing  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


blank = Path(tempfile.gettempdir()) / "recipe_route.ifc"
massing.generate_blank_ifc(str(blank), name="Recipe Tower", storeys=2, storey_height=3.5)


def new_project(c, name):
    pid = c.post("/projects", json={"name": name}).json()["id"]
    r = c.post(f"/projects/{pid}/source-ifc?publish=false",
               files={"file": ("model.ifc", blank.read_bytes(), "application/octet-stream")})
    assert r.status_code == 200, r.text[:160]
    return pid


def wall_count(c, pid):
    r = c.post(f"/projects/{pid}/model/query", json={"query": "IfcWall"})
    if r.status_code != 200:
        r = c.get(f"/projects/{pid}/model/query?query=IfcWall")
    return r


with TestClient(app) as c:
    c.headers.update({"X-User": "ana@test"})
    pid = new_project(c, "Recipe Tower")

    empty = c.get(f"/projects/{pid}/recipes/log")
    check("GET /recipes/log answers 200 on a project with no edits", empty.status_code == 200,
          empty.text[:200])
    check("  and is empty", empty.json()["total"] == 0)

    # --- a single edit through /edit ---------------------------------------------------------------
    e1 = c.post(f"/projects/{pid}/edit",
                json={"recipe": "add_wall",
                      "params": {"start": [0, 0], "end": [6, 0], "height": 3.0, "storey": "Level 1"},
                      "publish": False})
    check("POST /edit succeeds", e1.status_code == 200, e1.text[:250])

    L = c.get(f"/projects/{pid}/recipes/log").json()
    check("the edit was captured", L["total"] == 1, L)
    row = L["entries"][0]
    check("  with its recipe", row["recipe"] == "add_wall")
    check("  with its PARAMETERS — the half that did not exist before",
          row["params"]["end"] == [6, 0] and row["params"]["height"] == 3.0, row["params"])
    check("  with the actor", row["actor"] == "ana@test", row["actor"])
    check("  and the source it ran between",
          row["source_in"] and row["source_out"] and row["source_in"] != row["source_out"],
          (row["source_in"], row["source_out"]))
    check("  paths are basenames, not server paths", "/" not in (row["source_out"] or ""))

    # --- a batch: one version, N log entries -------------------------------------------------------
    e2 = c.post(f"/projects/{pid}/edit/batch", json={
        "steps": [
            {"recipe": "add_wall", "params": {"start": [0, 0], "end": [0, 4], "height": 3.0,
                                              "storey": "Level 1"}},
            {"recipe": "add_column", "params": {"point": [2, 2], "height": 3.0, "storey": "Level 2"}},
        ], "publish": False})
    check("POST /edit/batch succeeds", e2.status_code == 200, e2.text[:250])

    L2 = c.get(f"/projects/{pid}/recipes/log").json()
    check("a 2-step batch logs 2 entries — one version, two operations", L2["total"] == 3, L2["total"])
    batch = [r for r in L2["entries"] if r.get("batch")]
    check("  both carry the same batch id", len({r["batch"] for r in batch}) == 1, batch)
    check("  and their parameters are kept per step",
          sorted(r["recipe"] for r in batch) == ["add_column", "add_wall"])
    check("the log is newest-first", L2["entries"][0]["recipe"] in ("add_wall", "add_column")
          and L2["entries"][-1]["recipe"] == "add_wall")
    check("the recipes actually used are listed", set(L2["recipes"]) == {"add_wall", "add_column"})

    filt = c.get(f"/projects/{pid}/recipes/log?recipe=add_column").json()
    check("filtering by recipe works",
          filt["total"] == 1 and filt["entries"][0]["recipe"] == "add_column", filt["total"])

    # --- export is oldest-first, and says so --------------------------------------------------------
    ex = c.get(f"/projects/{pid}/recipes/export").json()
    check("GET /recipes/export returns the whole log", ex["count"] == 3)
    check("  oldest first, stated in the payload", ex["order"] == "oldest_first")
    check("  the first entry is the first edit", ex["entries"][0]["params"]["end"] == [6, 0],
          ex["entries"][0]["params"])
    check("  and it reports whether the log is replayable", ex["replayable"] is True)

    # --- diff ----------------------------------------------------------------------------------------
    d = c.get(f"/projects/{pid}/recipes/diff?a=0&b=1").json()
    check("two add_wall runs are comparable", d["comparable"] is True, d.get("reason"))
    check("  and only the changed parameter is named",
          [x["param"] for x in d["changed"]] == ["end"], d["changed"])
    cross = c.get(f"/projects/{pid}/recipes/diff?a=0&b=2").json()
    check("add_wall vs add_column is refused as incomparable", cross["comparable"] is False)
    check("an out-of-range index is a 404",
          c.get(f"/projects/{pid}/recipes/diff?a=0&b=99").status_code == 404)

    # --- THE assertion: replay onto a fresh model reproduces the building --------------------------
    plan = c.post(f"/projects/{pid}/recipes/replay-plan", json={})
    check("POST /recipes/replay-plan answers 200", plan.status_code == 200, plan.text[:250])
    steps = plan.json()["steps"]
    check("  the plan has every logged step, in order", len(steps) == 3
          and [s["recipe"] for s in steps] == ["add_wall", "add_wall", "add_column"],
          [s["recipe"] for s in steps])

    fresh = new_project(c, "Replayed Tower")
    applied = c.post(f"/projects/{fresh}/edit/batch", json={"steps": steps, "publish": False})
    check("the plan applies to a DIFFERENT project's fresh model", applied.status_code == 200,
          applied.text[:250])

    # What this asserts, stated plainly: the replay ran the SAME recipes with the SAME parameters, in
    # the same order, against the same starting model, and every step was accepted. That is the
    # property the log is responsible for.
    #
    # It does NOT compare the two models geometrically. There is no endpoint on this build that
    # returns a comparable whole-model summary, and an assertion written as `if the endpoint exists`
    # is worse than none: it passes silently when the endpoint 500s, so a green run stops meaning
    # anything. Element-level equivalence between an original and its replay is exactly what
    # R23-DIGEST's `diff()` answers, and wiring the two together is the follow-up.
    rl2 = c.get(f"/projects/{fresh}/recipes/log").json()
    check("  and the replay is itself captured on the new project, step for step",
          [r["recipe"] for r in reversed(rl2["entries"])] == [s["recipe"] for s in steps],
          [r["recipe"] for r in rl2["entries"]])
    check("  with the same parameters that were logged on the original",
          [r["params"] for r in reversed(rl2["entries"])] == [s["params"] for s in steps])

    sub = c.post(f"/projects/{pid}/recipes/replay-plan", json={"indices": [2]}).json()
    check("a subset can be replayed", sub["count"] == 1 and sub["steps"][0]["recipe"] == "add_column")
    bad = c.post(f"/projects/{pid}/recipes/replay-plan", json={"indices": [99]})
    check("an out-of-range index is a 422, not a 500", bad.status_code == 422, bad.status_code)

    # --- the log must never be able to break an edit -------------------------------------------------
    # append_safe swallows storage faults because the edit has already been committed by then; a
    # logging fault must not turn a successful edit into a reported failure.
    from aec_api import recipe_log as rl

    orig = rl.record
    try:
        rl.record = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("storage down"))
        still = c.post(f"/projects/{pid}/edit",
                       json={"recipe": "add_column",
                             "params": {"point": [4, 4], "height": 3.0, "storey": "Level 2"},
                             "publish": False})
        check("an edit still succeeds when the log cannot be written", still.status_code == 200,
              still.text[:200])
    finally:
        rl.record = orig
    check("  and the failure left a gap rather than a corrupt entry",
          c.get(f"/projects/{pid}/recipes/log").json()["total"] == 3)

print()
if FAILED:
    print(f"recipe_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("recipe_route: all checks passed")
