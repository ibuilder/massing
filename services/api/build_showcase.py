"""
Author the showcase project — a real two-storey house, end to end, through the live API.

This exists because the sample library needs *content*, and the machinery around it is now proven:
containers carry the element index (v0.3.746), `build_samples.py` fails on an unusable one
(v0.3.757), and the library is finally served from the right directory (v0.3.757 again).

**Everything here goes through HTTP, deliberately.** A script that reached into the database would
build a project the product cannot build, and the whole point of a showcase is that it demonstrates
the product rather than a private path into it. If a step here is awkward, that awkwardness is real
and worth seeing.

    python build_showcase.py --url http://127.0.0.1:8093

Then package it with the SAME environment the server runs under — that mismatch was the entire cause
of two "0 elements" containers:

    DATABASE_URL=... STORAGE_DIR=... python build_samples.py --project <pid> --out ../../samples
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--url", default="http://127.0.0.1:8093")
ap.add_argument("--user", default="gc")
ap.add_argument("--name", default="Maple Grove House")
args = ap.parse_args()

BASE = args.url.rstrip("/")
steps: list[tuple[str, bool, str]] = []


def call(method: str, path: str, body=None, quiet=False):
    req = urllib.request.Request(f"{BASE}{path}", method=method,
                                 headers={"Content-Type": "application/json", "X-User": args.user})
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=180) as r:      # noqa: S310 — fixed local URL
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:200]
        if not quiet:
            print(f"    HTTP {e.code} {method} {path} :: {detail}")
        return None
    except Exception as e:                                   # noqa: BLE001 — a step failing is data
        if not quiet:
            print(f"    ERR {method} {path} :: {e}")
        return None


def step(label: str, ok: bool, detail: str = ""):
    steps.append((label, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"  ->  {detail}" if detail else ""))


def wait_publish(pid: str, timeout: int = 180) -> bool:
    """Block until the in-flight publish finishes.

    **Publishing is asynchronous**, and this is the barrier the whole script turns on. Without it the
    first draft fired ten edits with `publish=False` and a single bare `POST /publish`, and ended up
    with **one** element out of ten: each edit raced the in-flight publish and overwrote the last.
    Every `/edit` returned 200 the entire time, so the script reported ten passes for a model that
    had one slab in it.

    `e2e_modeling.py` had this right already — publish per edit, then poll `/publish/status`. Reading
    the existing script before writing a new one would have saved the whole detour.
    """
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = (call("GET", f"/projects/{pid}/publish/status", quiet=True) or {}).get("state")
        if st in ("done", "ready", "ok", "idle", None):
            return True
        if st == "error":
            return False
        time.sleep(1.0)
    return False


def edit(pid: str, recipe: str, params: dict, publish: bool = True):
    """One GUID-stable edit recipe, published and awaited.

    `publish=True` by default and a barrier after it: batching without waiting is what produced a
    one-element house. Slower, and correct."""
    r = call("POST", f"/projects/{pid}/edit", {"recipe": recipe, "params": params, "publish": publish})
    if r is not None and publish:
        wait_publish(pid)
    return r


def wait_for_index(pid: str, tries: int = 20, delay: float = 1.0) -> bool:
    """Block until the property index exists, or give up.

    Publishing does **not** synchronously produce the element index — it is written a moment later,
    and `/elements` answers `404 no properties index for project` in the gap. The first version of
    this script queried immediately, got the 404, and reported "0 walls", which reads exactly like a
    model that failed to author. It had authored fine; the index simply was not there yet.

    So this waits on the actual condition rather than sleeping a guessed amount. Worth noting as a
    product observation too: a 404 saying *no index* is indistinguishable, to a client, from *no
    such project* — "not ready yet" and "not there" deserve different answers.
    """
    import time
    for _ in range(tries):
        if call("GET", f"/projects/{pid}/elements?limit=1", quiet=True) is not None:
            return True
        time.sleep(delay)
    return False


print(f"== authoring '{args.name}' via {BASE} ==")

# --- the project + a blank model ------------------------------------------------------------------
proj = call("POST", "/projects", {"name": args.name})
if not proj:
    print("cannot create project — is the API up? `curl /health` (status=000 means dead)")
    sys.exit(1)
PID = proj["id"]
step("create project", True, PID)

blank = call("POST", f"/projects/{PID}/model/blank",
             {"name": args.name, "storeys": 2, "storey_height": 3.0})
step("blank model (2 storeys @ 3.0m)", blank is not None)
call("POST", f"/projects/{PID}/publish"); step("publish blank", wait_publish(PID))

# --- the shell -------------------------------------------------------------------------------------
# A 12 x 8 m footprint: big enough that room subdivision is meaningful, small enough that the sample
# stays a few hundred KB. Coordinates are metres in the model's own frame.
W, D, H = 12.0, 8.0, 3.0
FOOTPRINT = [[0, 0], [W, 0], [W, D], [0, D]]

step("ground slab", edit(PID, "add_slab", {"points": FOOTPRINT, "thickness": 0.25}) is not None)

exterior = [([0, 0], [W, 0]), ([W, 0], [W, D]), ([W, D], [0, D]), ([0, D], [0, 0])]
walls_ok = 0
for a, b in exterior:
    if edit(PID, "add_wall", {"start": a, "end": b, "height": H, "thickness": 0.3}) is not None:
        walls_ok += 1
step("exterior walls", walls_ok == 4, f"{walls_ok}/4")

# Interior partitions — a spine wall and two cross walls, which is what makes the plan read as a
# house rather than a shed when the plan sheet is generated.
interior = [([0, 4.0], [W, 4.0]), ([5.0, 0], [5.0, 4.0]), ([8.0, 4.0], [8.0, D])]
part_ok = sum(1 for a, b in interior
              if edit(PID, "add_wall", {"start": a, "end": b, "height": H, "thickness": 0.15}) is not None)
step("interior partitions", part_ok == 3, f"{part_ok}/3")

step("upper floor slab", edit(PID, "add_slab",
                             {"points": FOOTPRINT, "thickness": 0.22, "storey": "Level 2"}) is not None)
step("roof", edit(PID, "add_roof", {"points": FOOTPRINT, "thickness": 0.3}) is not None)

call("POST", f"/projects/{PID}/publish")
step("publish shell", wait_publish(PID))

# --- openings, hosted on real walls ----------------------------------------------------------------
# Doors and windows need a host GUID, so they come after the shell exists and is indexed. This is the
# ordering the product itself imposes; a script that skipped it would be demonstrating nothing.
step("index built after publish", wait_for_index(PID), "waited for props.json")
els = call("GET", f"/projects/{PID}/elements?ifc_class=IfcWall&limit=50") or []
wall_guids = [e["guid"] for e in els if isinstance(e, dict) and e.get("guid")]
step("walls are indexed and addressable", len(wall_guids) >= 4, f"{len(wall_guids)} walls")

if wall_guids:
    d_ok = sum(1 for g in wall_guids[:2]
               if edit(PID, "add_door", {"host_guid": g, "width": 0.9, "height": 2.1}) is not None)
    step("doors", d_ok > 0, f"{d_ok} placed")
    w_ok = sum(1 for g in wall_guids[:4]
               if edit(PID, "add_window", {"host_guid": g, "width": 1.4, "height": 1.2, "sill": 0.9})
               is not None)
    step("windows", w_ok > 0, f"{w_ok} placed")

step("rooms", edit(PID, "add_spaces", {"rooms_per_storey": 4, "ceiling_height": 2.7}) is not None)
call("POST", f"/projects/{PID}/publish")
step("publish openings + rooms", wait_publish(PID))

# --- what the model now measures -------------------------------------------------------------------
wait_for_index(PID)
final = call("GET", f"/projects/{PID}/elements?limit=500") or []
step("element index is populated", len(final) > 8, f"{len(final)} elements")
by_class: dict[str, int] = {}
for e in final:
    if isinstance(e, dict):
        by_class[e.get("ifc_class", "?")] = by_class.get(e.get("ifc_class", "?"), 0) + 1
if by_class:
    print(f"    classes: {dict(sorted(by_class.items()))}")

print("\n== summary ==")
passed = sum(1 for _, ok, _ in steps if ok)
print(f"{passed} passed, {len(steps) - passed} failed, {len(steps)} total")
print(f"\nproject: {PID}")
print("package it with the SERVER'S env (a mismatch is what produced two empty containers):")
print(f"  DATABASE_URL=... STORAGE_DIR=... python build_samples.py --project {PID} \\")
print("      --out ../../samples --name maple_grove_house")
sys.exit(0 if passed == len(steps) else 1)
