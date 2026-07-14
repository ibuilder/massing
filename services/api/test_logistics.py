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

print("LOGISTICS OK - schedule-windowed resources; state_at gives 3 active in May, only the open-ended "
      "gate in Oct/Feb, all 3 with no date; summary rolls kinds + the overall window; PUT/GET/state "
      "endpoints round-trip.")
