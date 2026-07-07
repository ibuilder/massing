"""Resource-loaded scheduling (C2): crew histogram + S-curve + peak + over-allocation.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_resource_loading.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_resource_loading.db"
os.environ["STORAGE_DIR"] = "./test_storage_resource_loading"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_resource_loading.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import reports  # noqa: E402
from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "P"}).json()["id"]

    def act(data):
        r = c.post(f"/projects/{pid}/modules/schedule_activity", json={"data": data})
        assert r.status_code == 201, r.text[:160]

    # Concrete spans two weeks; Steel overlaps the 2nd; the third carries no crew (excluded).
    act({"name": "Foundations", "trade": "Concrete", "crew_size": 6,
         "start": "2026-03-02", "finish": "2026-03-13"})
    act({"name": "Steel erection", "trade": "Steel", "crew_size": 4,
         "start": "2026-03-09", "finish": "2026-03-13"})
    act({"name": "Submittals", "trade": "PM", "start": "2026-03-02", "finish": "2026-03-06"})  # no crew

    rl = c.get(f"/projects/{pid}/schedule/resource-loading").json()
    assert rl["activities_loaded"] == 2, rl                       # the no-crew activity is excluded
    assert set(rl["trades"]) == {"Concrete", "Steel"}, rl["trades"]
    assert rl["peak"]["crew"] == 10.0, rl["peak"]                 # overlap week: 6 concrete + 4 steel
    # S-curve is monotonic non-decreasing and ends at the sum of weekly totals
    cums = [p["cumulative"] for p in rl["scurve"]]
    assert cums == sorted(cums) and cums[-1] == sum(w["total"] for w in rl["histogram"]), rl["scurve"]

    # over-allocation against an 8-worker cap flags the peak week
    over = c.get(f"/projects/{pid}/schedule/resource-loading", params={"cap": 8}).json()
    assert len(over["over_allocation"]) >= 1 and over["over_allocation"][0]["crew"] == 10.0, over["over_allocation"]

    # report + PDF
    assert "resource_loading" in {x["id"] for x in reports.catalog()}, "resource_loading missing"
    rep = c.get(f"/projects/{pid}/reports/resource_loading.pdf")
    assert rep.status_code == 200 and rep.content[:4] == b"%PDF", rep.status_code

print("RESOURCE LOADING OK - 2 crew-loaded activities (no-crew excluded); weekly histogram sums "
      "concurrent crew (peak 10 = 6 concrete + 4 steel in the overlap week); monotonic S-curve; "
      "over-allocation flags the peak week vs an 8-worker cap; report PDF served")
