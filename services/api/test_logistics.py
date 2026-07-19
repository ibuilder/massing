"""Site logistics on the 4D timeline (Wave 9 W9-5): schedule-windowed resources, time-phased state_at,
summary roll-up, and the resource round-trip endpoints.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_logistics.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_logistics.db"
os.environ["STORAGE_DIR"] = "./test_storage_logistics"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_logistics.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import logistics  # noqa: E402
from aec_api.main import app  # noqa: E402

RES = [
    {"id": "tc1", "kind": "crane", "label": "Tower crane", "position": [10, 20, 0], "radius": 30,
     "start": "2026-03-01", "end": "2026-09-30"},
    {"id": "ld1", "kind": "laydown", "label": "Steel laydown", "polygon": [[0, 0], [10, 0], [10, 8], [0, 8]],
     "start": "2026-04-01", "end": "2026-06-30"},
    {"id": "g1", "kind": "gate", "label": "Main gate", "position": [0, 40, 0]},   # no window = always
]

# state_at: mid-May -> crane + laydown + gate; October -> only the gate (open-ended)
may = logistics.state_at(RES, "2026-05-15")
assert may["active_count"] == 3, may
oct_ = logistics.state_at(RES, "2026-10-15")
assert {r["id"] for r in oct_["active"]} == {"g1"}, oct_        # laydown+crane ended, gate open-ended
assert oct_["active_count"] == 1 and oct_["total"] == 3
# before anything but the always-on gate
feb = logistics.state_at(RES, "2026-02-01")
assert {r["id"] for r in feb["active"]} == {"g1"}, feb
# no date -> the whole plan
assert logistics.state_at(RES, None)["active_count"] == 3

s = logistics.summary(RES)
assert s["total"] == 3 and s["by_kind"] == {"crane": 1, "laydown": 1, "gate": 1}, s
assert s["start"] == "2026-03-01" and s["end"] == "2026-09-30", s   # overall scheduled window

# --- W9-5b: motion along a path ---------------------------------------------------------------------
walker = {"id": "c2", "kind": "crane", "radius": 20,
          "path": [[0, 0], [100, 0]], "start": "2026-03-01", "end": "2026-04-30"}
# schedule midpoint → halfway along the 100 m runway; start/end → the path ends
mid = logistics.position_at(walker, "2026-03-31")
assert mid is not None and abs(mid[0] - 50.0) < 2.0 and abs(mid[1]) < 1e-6, mid
assert logistics.position_at(walker, "2026-03-01") == [0.0, 0.0]
assert logistics.position_at(walker, "2026-04-30") == [100.0, 0.0]
assert logistics.position_at(walker, "2026-01-01") == [0.0, 0.0], "before the window → path start"
# a static resource just reports its position
assert logistics.position_at(RES[0], "2026-05-01") == [float(RES[0]["position"][0]),
                                                       float(RES[0]["position"][1]),
                                                       float(RES[0]["position"][2])][:len(RES[0]["position"])]
# state_at carries the interpolated position for pathed resources
stm = logistics.state_at([walker], "2026-03-31")
assert abs(stm["active"][0]["position"][0] - 50.0) < 2.0, stm["active"][0]

# --- W9-5b: swept crane-reach clash -----------------------------------------------------------------
# two fixed cranes 30 m apart with 20 m jibs, overlapping windows → discs intersect (10 m overlap)
c_a = {"id": "TC1", "kind": "crane", "radius": 20, "position": [0, 0],
       "start": "2026-03-01", "end": "2026-06-30"}
c_b = {"id": "TC2", "kind": "crane", "radius": 20, "position": [30, 0],
       "start": "2026-05-01", "end": "2026-08-31"}
sc = logistics.swept_clash([c_a, c_b])
assert sc["clash_count"] == 1, sc
hit = sc["clashes"][0]
assert {hit["a"], hit["b"]} == {"TC1", "TC2"} and hit["closest_m"] == 30.0, hit
assert hit["overlap_m"] == 10.0 and "stagger" in hit["note"], hit
# disjoint windows → no clash even though the discs overlap in space
c_b2 = dict(c_b, start="2026-07-01", end="2026-08-31")
assert logistics.swept_clash([c_a, c_b2])["clash_count"] == 0, "time separation clears it"
# far apart → no clash
assert logistics.swept_clash([c_a, dict(c_b, position=[100, 0])])["clash_count"] == 0
# a WALKING crane that ends its runway near TC1 clashes — motion is what creates the conflict
c_walk = {"id": "TC3", "kind": "crane", "radius": 20,
          "path": [[200, 0], [35, 0]], "start": "2026-03-01", "end": "2026-06-30"}
scw = logistics.swept_clash([c_a, c_walk], samples=32)
assert scw["clash_count"] == 1 and scw["clashes"][0]["worst_date"] >= "2026-06", scw
# a trailer under TC1's hook → an under-hook safety flag (not a clash)
trailer = {"id": "t1", "kind": "trailer", "position": [10, 0],
           "start": "2026-03-01", "end": "2026-06-30"}
su = logistics.swept_clash([c_a, trailer])
assert su["clash_count"] == 0 and len(su["under_hook"]) == 1, su
assert su["under_hook"][0]["resource"] == "t1" and "hook" in su["under_hook"][0]["note"], su
assert "not a jib" in sc["disclaimer"]

# --- endpoint round-trip ----------------------------------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Logistics Test"}).json()["id"]
    assert c.get(f"/projects/{pid}/logistics").json()["resources"] == []
    put = c.put(f"/projects/{pid}/logistics", json={"resources": RES})
    assert put.status_code == 200 and len(put.json()["resources"]) == 3, put.text[:200]
    got = c.get(f"/projects/{pid}/logistics").json()
    assert got["summary"]["by_kind"]["crane"] == 1, got
    st = c.get(f"/projects/{pid}/logistics/state", params={"date": "2026-10-15"}).json()
    assert st["active_count"] == 1 and st["active"][0]["id"] == "g1", st
    # the swept-clash route serves the plan-level screen
    c.put(f"/projects/{pid}/logistics", json={"resources": [c_a, c_b, trailer]})
    rc = c.get(f"/projects/{pid}/logistics/clash").json()
    assert rc["clash_count"] == 1 and len(rc["under_hook"]) == 1 and rc["cranes"] == 2, rc

print("LOGISTICS OK - schedule-windowed resources; state_at gives 3 active in May, only the open-ended "
      "gate in Oct/Feb, all 3 with no date; summary rolls kinds + the overall window; PUT/GET/state "
      "endpoints round-trip. W9-5b: position_at walks a crane along its runway by schedule progress "
      "(midpoint -> 50 m, clamped at the ends) and state_at carries it; swept_clash flags the 30 m "
      "crane pair with 20 m jibs (10 m overlap, worst date), clears time-separated and far pairs, "
      "catches a WALKING crane ending near a fixed one, flags a trailer under the hook, and serves "
      "via GET /logistics/clash.")
