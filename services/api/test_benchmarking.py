"""Cross-project benchmarking — cost distribution per cost code (percentiles) + RFI/submittal
response-rate KPIs, aggregated across multiple projects.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_benchmarking.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_benchmarking.db"
os.environ["STORAGE_DIR"] = "./test_storage_benchmarking"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_benchmarking.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient           # noqa: E402
from aec_api.main import app                          # noqa: E402

with TestClient(app) as c:
    # two projects, direct costs under the same cost code -> cross-project distribution
    p1 = c.post("/projects", json={"name": "A"}).json()["id"]
    p2 = c.post("/projects", json={"name": "B"}).json()["id"]
    amounts = {p1: [1000, 2000, 3000], p2: [4000, 5000]}      # 5 samples for code 03-3000
    for pid, amts in amounts.items():
        for a in amts:
            r = c.post(f"/projects/{pid}/modules/direct_cost",
                       json={"data": {"description": "concrete", "cost_code": "03-3000", "amount": a}})
            assert r.status_code == 201, r.text[:160]
        # a second code with too few samples (should be dropped at min_samples=3)
        c.post(f"/projects/{pid}/modules/direct_cost",
               json={"data": {"description": "misc", "cost_code": "01-0000", "amount": 500}})

    cb = c.get("/benchmarks/costs").json()
    code = next((x for x in cb["cost_codes"] if x["cost_code"] == "03-3000"), None)
    assert code and code["samples"] == 5, cb
    assert code["low"] == 1000 and code["high"] == 5000 and code["median"] == 3000, code
    assert code["p25"] == 2000 and code["p75"] == 4000, code           # interpolated percentiles
    assert all(x["cost_code"] != "01-0000" for x in cb["cost_codes"]), "under-threshold code must drop"

    # response rates: an overdue open RFI + an answered RFI; a returned submittal (turnaround)
    c.post(f"/projects/{p1}/modules/rfi",
           json={"data": {"subject": "overdue", "question": "?", "due_date": "2000-01-01"}})   # open+overdue
    rfi2 = c.post(f"/projects/{p1}/modules/rfi",
                  json={"data": {"subject": "done", "question": "?", "answer": "yes"}}).json()
    # drive it to answered so it counts as turnaround
    c.post(f"/projects/{p1}/modules/rfi/{rfi2['id']}/transition", json={"action": "submit"})
    c.post(f"/projects/{p1}/modules/rfi/{rfi2['id']}/transition", json={"action": "respond"})
    sr = c.post(f"/projects/{p1}/modules/submittal",
                json={"data": {"title": "s1", "spec_section": "03 30 00", "type": "Product Data",
                               "date_received": "2024-01-01", "date_returned": "2024-01-15"}})
    assert sr.status_code == 201, sr.text[:160]

    rr = c.get("/benchmarks/response-rates").json()
    assert rr["rfi"]["total"] == 2 and rr["rfi"]["overdue"] == 1, rr["rfi"]
    assert rr["rfi"]["answered_or_closed"] == 1, rr["rfi"]
    assert rr["submittal"]["avg_turnaround_days"] == 14.0, rr["submittal"]

print("BENCHMARKING OK - cross-project cost distribution per code (p25/median/p75 interpolated, "
      "under-threshold codes dropped); RFI overdue count + submittal 14-day turnaround across projects")
