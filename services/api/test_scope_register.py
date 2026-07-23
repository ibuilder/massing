"""SCOPE-REG — the scope register + gap analysis: each item resolves quantity/value (QTO by cost code),
owner, and schedule window; surfaces unquantified / unallocated / unscheduled scope.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_scope_register.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scope_register.db"
os.environ["STORAGE_DIR"] = "./test_storage_scope"
os.environ.pop("AEC_RBAC", None)

from aec_api import scope_register as sr  # noqa: E402

scope = [
    {"id": "s1", "name": "Concrete", "cost_code": "03-30", "responsible": "ABC Concrete", "activity_id": "a1"},
    {"id": "s2", "name": "Steel", "cost_code": "05-12"},                       # quantified, but unallocated + unscheduled
    {"id": "s3", "name": "Landscaping", "package": "Sitework buyout"},          # allocated, but unquantified + unscheduled
]
qto = [{"cost_code": "03-30", "qty": 100, "cost": 50000}, {"cost_code": "05-12", "qty": 20, "cost": 30000}]
acts = [{"id": "a1", "cost_code": "03-30", "start": "2026-09-01", "finish": "2026-09-15"}]

r = sr.register(scope, qto, acts)
assert r["item_count"] == 3 and r["complete"] == 1 and r["with_gaps"] == 2, r
assert r["pct_quantified"] == 0.667 and r["pct_allocated"] == 0.667 and r["pct_scheduled"] == 0.333, r
assert r["total_value"] == 80000, r["total_value"]

by = {x["id"]: x for x in r["items"]}
assert by["s1"]["status"] == "complete" and by["s1"]["value"] == 50000 and by["s1"]["start"] == "2026-09-01", by["s1"]
assert set(by["s2"]["gaps"]) == {"unallocated", "unscheduled"} and by["s2"]["quantified"] is True, by["s2"]
assert "unquantified" in by["s3"]["gaps"] and by["s3"]["allocated"] is True, by["s3"]
assert len(r["gap_items"]) == 2, r["gap_items"]
assert r["items"][0]["id"] == "s2", r["items"]                # highest-value gap first
assert r["by_owner"][0]["owner"] == "ABC Concrete" and r["by_owner"][0]["value"] == 50000, r["by_owner"]

# empty input is well-formed
e = sr.register([])
assert e["item_count"] == 0 and e["pct_quantified"] == 0.0 and e["total_value"] == 0.0, e

# --- route: 404 missing project; 200 otherwise -----------------------------------------------------
if os.path.exists("./test_scope_register.db"):
    os.remove("./test_scope_register.db")
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as c:
    assert c.post("/projects/nope/scope/register", json={"scope_items": scope}).status_code == 404
    pid = c.post("/projects", json={"name": "Scope"}).json()["id"]
    rr = c.post(f"/projects/{pid}/scope/register", json={"scope_items": scope, "qto_lines": qto, "activities": acts})
    assert rr.status_code == 200, rr.text
    j = rr.json()
    assert j["with_gaps"] == 2 and j["items"][0]["id"] == "s2", j

print("SCOPE-REG OK - the scope register ties each item to its QTO quantity/value (by cost code), owner "
      "(responsible/package), and schedule window (activity by id/cost code): a concrete item with all three "
      "is complete ($50k, starts 2026-09-01), a steel item is quantified but unallocated + unscheduled, and a "
      "landscaping item is allocated but unquantified — 67% quantified/allocated, 33% scheduled, gaps first "
      "highest-value first ($30k steel gap leads); the /scope/register route 404s on a missing project.")
