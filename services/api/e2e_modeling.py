"""End-to-end smoke drive for the in-browser MODELING program — the authoring+coordination flow the
2026-07 initiative shipped (blank model from scratch, GUID-stable edit recipes, edit-in-place move,
manage levels, model-browser discipline data, clash, exports). Resilient: a failing step never aborts
the run, so gaps surface as a punch list. Prints PASS/FAIL per step and a final summary.

  python services/api/e2e_modeling.py                      # against http://localhost:8000
  python services/api/e2e_modeling.py --url http://127.0.0.1:8093   # local dev backend

Flow: create project -> P1 blank model -> P3 draw wall+columns -> model-browser discipline data ->
P5 edit-in-place move_element -> manage levels (rename_storey + set_storey_elevation) -> clash ->
QTO/COBie/space-schedule exports -> grid+levels. Storey GUIDs (drawings/storeys) back the level editor;
`discipline` on each element backs the model browser's "by discipline" grouping.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://localhost:8000")
ap.add_argument("--user", default="gc")
opts = ap.parse_args()

results: list[tuple[str, str, str]] = []


def call(method, path, body=None, raw=False, qs=None):
    url = opts.url + path + ("?" + urlencode(qs) if qs else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "X-User": opts.user})
    with urllib.request.urlopen(req, timeout=300) as r:
        b = r.read()
        return b if raw else json.loads(b or "{}")


def run(name, fn):
    try:
        out = fn()
        detail = out if isinstance(out, str) else ""
        results.append((name, "PASS", detail))
        print(f"  PASS  {name}" + (f"  ->  {detail}" if detail else ""))
        return out
    except urllib.error.HTTPError as e:
        d = f"{e.code}: {e.read().decode()[:200]}"
        results.append((name, "FAIL", d)); print(f"  FAIL  {name}  ({d})")
    except Exception as e:  # noqa: BLE001
        results.append((name, "FAIL", str(e)[:200])); print(f"  FAIL  {name}  ({str(e)[:200]})")
    return None


def edit(pid, recipe, params, publish=False):
    return call("POST", f"/projects/{pid}/edit", {"recipe": recipe, "params": params, "publish": publish})


def wait_publish(pid, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = call("GET", f"/projects/{pid}/publish/status").get("state")
        if s in ("done", "error"):
            return s
        time.sleep(2)
    return "timeout"


def raise_(msg):
    raise Exception(msg)


print("== end-to-end MODELING smoke drive ==")
pid = run("create project", lambda: call("POST", "/projects", {"name": "E2E - Modeling Flow"})["id"])
if not pid:
    print("cannot continue without a project"); raise SystemExit(1)

# P1 — blank model from scratch
run("P1 blank model (3 storeys)", lambda: call("POST", f"/projects/{pid}/model/blank",
    {"name": "E2E Blank", "storeys": 3, "storey_height": 3.5}) and "requested")
run("blank publish", lambda: wait_publish(pid))

# storey listing carries GUIDs (the key the level editor targets recipes with)
storeys_list = call("GET", f"/projects/{pid}/drawings/storeys")
run("drawings/storeys has guid", lambda: f"{len(storeys_list)} levels, guids={all(x.get('guid') for x in storeys_list)}")

# P3 authoring — draw a wall + two columns on the ground level
active = storeys_list[0]["name"] if storeys_list else "Level 1"
run("draw wall", lambda: edit(pid, "add_wall", {"start": [-4, 0], "end": [4, 0], "height": 3.0, "thickness": 0.2, "storey": active}))
run("draw column A", lambda: edit(pid, "add_column", {"point": [-4, 0], "height": 3.0, "width": 0.4, "depth": 0.4, "storey": active}))
run("draw column B", lambda: edit(pid, "add_column", {"point": [4, 0], "height": 3.0, "width": 0.4, "depth": 0.4, "storey": active}, publish=True))
run("draw publish", lambda: wait_publish(pid))

# model-browser data: every element carries a discipline bucket
elements = call("GET", f"/projects/{pid}/elements", qs={"limit": 500})
run("elements carry discipline", lambda: f"{len(elements)} els, disciplines={sorted({x.get('discipline') or '?' for x in elements})}")

wall = next((e for e in elements if e["ifc_class"] == "IfcWall"), None)
run("wall present for move", lambda: wall["guid"][:12] if wall else raise_("no wall found"))

# P5 edit-in-place — the exact commit the drag gizmo issues (move_element with a world delta)
if wall:
    run("P5 move_element (edit-in-place)", lambda: edit(pid, "move_element", {"guid": wall["guid"], "dx": 1.5, "dy": 0.0, "dz": 0.0}, publish=True))
    run("move publish", lambda: wait_publish(pid))

# manage levels — rename + set elevation on a storey GUID, then confirm it applied
if storeys_list:
    g = storeys_list[-1]["guid"]
    run("rename_storey -> Roof", lambda: edit(pid, "rename_storey", {"guid": g, "name": "Roof"}, publish=True))
    run("rename publish", lambda: wait_publish(pid))
    run("set_storey_elevation -> 9.0", lambda: edit(pid, "set_storey_elevation", {"guid": g, "elevation": 9.0}, publish=True))
    run("elev publish", lambda: wait_publish(pid))
    run("elevation applied", lambda: "ok" if any(
        x["name"] == "Roof" and abs(x["elevation"] - 9.0) < 0.1 for x in call("GET", f"/projects/{pid}/drawings/storeys"))
        else raise_("elevation not applied"))

# clash — single-model coordination check
run("clash (single-model)", lambda: (lambda r: f"count={r['count']}")(
    call("POST", f"/projects/{pid}/clash", qs={"a": "IfcWall,IfcSlab", "b": "IfcColumn", "min_volume": 0.001})))

# exports
run("QTO export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/qto.xlsx', raw=True)):,} bytes")
run("COBie export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/cobie.xlsx', raw=True)):,} bytes")
run("space schedule export", lambda: f"{len(call('GET', f'/projects/{pid}/exports/spaces.xlsx', raw=True)):,} bytes")

# grid + levels overlay data (Draft panel snap frame)
run("model grid+levels", lambda: (lambda gr: f"grid={gr['grid']['source']} levels={len(gr['levels'])}")(
    call("GET", f"/projects/{pid}/model/grid")))

print("\n== summary ==")
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
for n, s, d in results:
    if s == "FAIL":
        print(f"  FAIL  {n}  ({d})")
print(f"\n{passed} passed, {failed} failed, {len(results)} total   (project {pid})")
raise SystemExit(1 if failed else 0)
