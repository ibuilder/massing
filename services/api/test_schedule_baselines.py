"""RESOURCE-LEVEL — multiple NAMED schedule baselines + variance against any chosen one.
Two baselines captured before/after a 10-day slip; variance vs each; added/removed; latest alias; delete.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_schedule_baselines.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_schedule_baselines.db"
os.environ["STORAGE_DIR"] = "./test_storage_schedule_baselines"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_schedule_baselines.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402


def mk(c, pid, name, start, finish):
    return c.post(f"/projects/{pid}/modules/schedule_activity",
                  json={"data": {"name": name, "start": start, "finish": finish}}).json()["id"]


with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "RL"}).json()["id"]
    a1 = mk(c, pid, "Foundations", "2026-03-01", "2026-03-20")
    mk(c, pid, "Superstructure", "2026-03-21", "2026-07-15")

    # capture the "GMP" baseline (2 activities)
    b1 = c.post(f"/projects/{pid}/schedule/baselines", json={"name": "GMP"}).json()
    assert b1["name"] == "GMP" and b1["count"] == 2, b1
    lst = c.get(f"/projects/{pid}/schedule/baselines").json()["baselines"]
    assert len(lst) == 1 and lst[0]["id"] == b1["id"], lst

    # slip Foundations' finish by 10 days, then capture a SECOND named baseline after the slip
    c.patch(f"/projects/{pid}/modules/schedule_activity/{a1}", json={"finish": "2026-03-30"})
    b2 = c.post(f"/projects/{pid}/schedule/baselines", json={"name": "Recovery"}).json()
    lst2 = c.get(f"/projects/{pid}/schedule/baselines").json()["baselines"]
    assert len(lst2) == 2 and lst2[0]["id"] == b2["id"], lst2          # newest first

    # variance vs GMP (pre-slip) → Foundations slipped +10
    v1 = c.get(f"/projects/{pid}/schedule/baselines/{b1['id']}/variance").json()
    assert v1["baseline"]["name"] == "GMP", v1["baseline"]
    fnd = next(x for x in v1["activities"] if x["name"] == "Foundations")
    assert fnd["finish_var"] == 10 and fnd["status"] == "slipped", fnd
    assert v1["summary"]["slipped"] == 1 and v1["summary"]["max_slip_days"] == 10, v1["summary"]

    # variance vs Recovery (post-slip) → on_baseline (no drift yet)
    v2 = c.get(f"/projects/{pid}/schedule/baselines/{b2['id']}/variance").json()
    fnd2 = next(x for x in v2["activities"] if x["name"] == "Foundations")
    assert fnd2["finish_var"] == 0 and fnd2["status"] == "on_baseline", fnd2

    # the "latest" alias resolves to the most recent baseline
    vlatest = c.get(f"/projects/{pid}/schedule/baselines/latest/variance").json()
    assert vlatest["baseline"]["id"] == b2["id"], vlatest["baseline"]

    # a new activity shows as "added" vs the older baseline
    mk(c, pid, "Punchlist", "2026-07-16", "2026-07-30")
    v3 = c.get(f"/projects/{pid}/schedule/baselines/{b1['id']}/variance").json()
    assert v3["summary"]["added"] == 1, v3["summary"]

    # delete GMP; library shrinks; missing-baseline variance + delete both 404
    assert c.delete(f"/projects/{pid}/schedule/baselines/{b1['id']}").json()["deleted"] is True
    assert len(c.get(f"/projects/{pid}/schedule/baselines").json()["baselines"]) == 1
    assert c.get(f"/projects/{pid}/schedule/baselines/nope/variance").status_code == 404
    assert c.delete(f"/projects/{pid}/schedule/baselines/nope").status_code == 404

print("SCHED-BASELINES OK - named baseline library (GMP + Recovery); variance vs each (GMP shows +10d "
      "slip, Recovery on-baseline); latest alias; added activity tracked; delete + 404s")
