"""R23-PREFAB-KIT over HTTP — the register is reachable and the freeze actually writes.

The engine is tested in `test_prefab_kit.py`. This asserts the live path: that the module is
installed, the endpoints answer, the register joins records created through the ordinary module API
to a real uploaded model index, and — the one that matters — that `POST .../freeze` persists the
GlobalId list, so that a later model change is reported as drift instead of quietly redefining what
the shop is building.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_prefab_route.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_prefab_route.db"
os.environ["STORAGE_DIR"] = "./test_storage_prefab_route"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_prefab_route.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import model_index  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def el(guid, cls, type_name, storey, qtos=None):
    return {"guid": guid, "ifc_class": cls, "name": guid, "type_name": type_name,
            "storey": storey, "psets": {}, "qtos": qtos or {}}


ELEMENTS = [
    el("g1", "IfcDuctSegment", "600x300", "L3",
       {"Qto_DuctSegmentBaseQuantities": {"Length": 4.0}}),
    el("g2", "IfcDuctSegment", "600x300", "L3",
       {"Qto_DuctSegmentBaseQuantities": {"Length": 6.0}}),
    el("g3", "IfcDuctSegment", "400x200", "L2",
       {"Qto_DuctSegmentBaseQuantities": {"Length": 3.0}}),
]

TODAY = "2026-04-01"

with TestClient(app) as c:
    c.headers.update({"X-User": "prefab@test"})
    pid = c.post("/projects", json={"name": "Kit Tower"}).json()["id"]

    def create(key, data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:200])
        return r.json()

    # The prefab_kit module has to be a real registered module, not just a folder on disk.
    mods = c.get("/modules").json()
    keys = {m["key"] for m in (mods["modules"] if isinstance(mods, dict) else mods)}
    check("the prefab_kit module is registered", "prefab_kit" in keys)

    empty = c.get(f"/projects/{pid}/prefab/kits?as_of={TODAY}")
    check("GET /prefab/kits answers 200 on an empty project", empty.status_code == 200,
          empty.text[:200])
    E = empty.json()
    check("  with no kits and no model", E["total"] == 0 and E["model_loaded"] is False)

    # --- a kit with no model loaded still appears, blocked ---------------------------------------
    task = create("pull_plan_task", {"task": "Hang L3 duct", "planned_week": "2026-W18",
                                     "trade": "MEP", "constraints": ["Materials"]})
    delivery = create("delivery", {"description": "L3 duct kit", "date": "2026-04-20",
                                   "supplier": "Acme Sheet Metal"})
    kit = create("prefab_kit", {"name": "L3 duct kit", "trade": "MEP",
                                "selector": "IfcDuctSegment & storey=L3",
                                "fabricator": "Acme Sheet Metal",
                                "needed_on_site": "2026-04-10",
                                "pull_task": task["id"], "delivery": delivery["id"]})
    rid = kit["id"]

    nomodel = c.get(f"/projects/{pid}/prefab/kits?as_of={TODAY}").json()
    check("a kit with no model loaded still appears in the register", nomodel["total"] == 1)
    check("  blocked, because its scope cannot be resolved",
          "no_model" in nomodel["blocker_counts"], nomodel["blocker_counts"])

    # --- load a model index ------------------------------------------------------------------------
    model_index.load(pid, {"schema": "IFC4", "elements": ELEMENTS,
                           "counts": {"elements": len(ELEMENTS)}})
    reg = c.get(f"/projects/{pid}/prefab/kits?as_of={TODAY}")
    check("with a model the register resolves the scope", reg.status_code == 200, reg.text[:200])
    R = reg.json()["kits"][0]
    check("  the selector matched the two L3 segments", R["elements"] == 2, R["elements"])
    check("  the BOM sums their declared length", R["bom"]["totals"].get("length") == 10.0,
          R["bom"]["totals"])
    check("  the scope comes from the selector while the kit is a draft",
          R["scope_source"] == "selector")
    codes = {b["code"] for b in R["blockers"]}
    check("  the constrained install task blocks it", "task_constrained" in codes, sorted(codes))
    check("  and the late delivery blocks it", "delivery_late" in codes, sorted(codes))

    detail = c.get(f"/projects/{pid}/prefab/kits/{rid}?as_of={TODAY}")
    check("GET one kit answers 200", detail.status_code == 200, detail.text[:200])
    check("  and agrees with the register", detail.json()["elements"] == R["elements"])

    # --- freeze --------------------------------------------------------------------------------------
    fr = c.post(f"/projects/{pid}/prefab/kits/{rid}/freeze")
    check("POST /freeze answers 200", fr.status_code == 200, fr.text[:200])
    check("  it froze the two matching elements", fr.json()["frozen"] == 2, fr.json())
    rec = c.get(f"/projects/{pid}/modules/prefab_kit/{rid}").json()
    check("  and PERSISTED the list onto the record — not just returned it",
          sorted((rec["data"].get("frozen_guids") or "").split()) == ["g1", "g2"],
          rec["data"].get("frozen_guids"))

    # Release it, then change the model underneath. This is the whole feature.
    # The `release` transition declares requires: [frozen_guids, released_on] — a kit cannot reach
    # the state the shop works from without a written scope AND a release date. Asserted, not
    # assumed: that requirement is what stops a kit being released empty.
    early = c.post(f"/projects/{pid}/modules/prefab_kit/{rid}/transition", json={"action": "scope"})
    check("the kit can be scoped", early.status_code == 200, early.text[:200])
    blocked = c.post(f"/projects/{pid}/modules/prefab_kit/{rid}/transition",
                     json={"action": "release"})
    check("release is refused before a release date is recorded",
          blocked.status_code >= 400, blocked.status_code)
    c.patch(f"/projects/{pid}/modules/prefab_kit/{rid}", json={"released_on": "2026-04-01"})
    done = c.post(f"/projects/{pid}/modules/prefab_kit/{rid}/transition", json={"action": "release"})
    check("and allowed once it is", done.status_code == 200, done.text[:200])
    state = c.get(f"/projects/{pid}/modules/prefab_kit/{rid}").json().get("workflow_state")
    check("the kit reached the released state", state == "released", state)

    after = c.get(f"/projects/{pid}/prefab/kits/{rid}?as_of={TODAY}").json()
    check("once released the FROZEN list defines the kit", after["scope_source"] == "frozen")
    check("  and it has not drifted yet", after["drift"]["drifted"] is False, after["drift"])

    # A design change: one duct moves off L3, and a new one appears on it.
    changed = [e for e in ELEMENTS if e["guid"] != "g2"]
    changed.append({**ELEMENTS[1], "storey": "L4"})
    changed.append(el("g9", "IfcDuctSegment", "600x300", "L3",
                      {"Qto_DuctSegmentBaseQuantities": {"Length": 5.0}}))
    model_index.load(pid, {"schema": "IFC4", "elements": changed,
                           "counts": {"elements": len(changed)}})

    drifted = c.get(f"/projects/{pid}/prefab/kits/{rid}?as_of={TODAY}").json()
    check("a model change is reported as DRIFT, not absorbed into the kit",
          drifted["drift"]["drifted"] is True, drifted["drift"])
    check("  the kit still contains what the shop was given", drifted["elements"] == 2)
    check("  the element that left the scope is named",
          drifted["drift"]["removed"] == ["g2"], drifted["drift"])
    check("  and the one that joined it is named separately",
          drifted["drift"]["added"] == ["g9"], drifted["drift"])
    check("  drift is a blocker", "scope_drift" in {b["code"] for b in drifted["blockers"]})

    # --- freeze refuses what it should ----------------------------------------------------------
    bad = create("prefab_kit", {"name": "nothing matches", "selector": "IfcWall & storey=L9"})
    r422 = c.post(f"/projects/{pid}/prefab/kits/{bad['id']}/freeze")
    check("freezing a selector that matches nothing is a 422, not an empty release",
          r422.status_code == 422, r422.status_code)
    broken = create("prefab_kit", {"name": "broken selector", "selector": "&&&"})
    r422b = c.post(f"/projects/{pid}/prefab/kits/{broken['id']}/freeze")
    check("freezing a broken selector is a 422", r422b.status_code == 422, r422b.status_code)
    check("  and the register still lists all three kits rather than failing wholesale",
          c.get(f"/projects/{pid}/prefab/kits?as_of={TODAY}").json()["total"] == 3)
    check("freezing an unknown kit is a 404",
          c.post(f"/projects/{pid}/prefab/kits/nope/freeze").status_code == 404)

print()
if FAILED:
    print(f"prefab_route: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("prefab_route: all checks passed")
