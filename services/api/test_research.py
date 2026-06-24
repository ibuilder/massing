"""Built-world techniques (R2 takt/LOB · R4 lean PPC · R5 benchmarks + comps).
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_research.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_research.db"
os.environ["STORAGE_DIR"] = "./test_storage_research"
os.environ.pop("AEC_RBAC", None)
for f in ("./test_research.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402
from aec_api import lean, takt  # noqa: E402
from aec_api.main import app  # noqa: E402

# --- R2: takt / line-of-balance ----------------------------------------------
p = takt.plan(10)                                  # 10 floors, default 5-trade train
assert len(p["trades"]) == 5 and p["floors"] == 10
# each trade ascends floor by floor; finish is monotonic and after start
struct = p["trades"][0]
assert struct["floor_starts"] == sorted(struct["floor_starts"]), "trade ascends in order"
# later trades finish after earlier ones (the train chases up the building)
assert p["trades"][-1]["finish_day"] > p["trades"][0]["finish_day"], "finishes chase upward"
assert p["duration_days"] > 0 and p["crew_peak"] == 5 and p["floors_per_week"] > 0, p
# JIT: every floor×trade has a delivery, ordered by need date
assert len(p["delivery_plan"]) == 10 * 5 and p["delivery_plan"] == sorted(p["delivery_plan"], key=lambda d: d["deliver_by_day"])
# more floors -> longer duration
assert takt.plan(20)["duration_days"] > p["duration_days"]
# faster takt -> faster ascent
fast = takt.plan(10, [{"name": "Structure", "takt_days": 2}])
assert fast["floors_per_week"] > p["floors_per_week"]

# --- C3: 4D sequencing — elements appear when their trade reaches their floor -
from aec_api import fourd  # noqa: E402
els = [{"guid": "c1", "ifc_class": "IfcColumn", "storey": "Level 1"},
       {"guid": "c2", "ifc_class": "IfcColumn", "storey": "Level 3"},
       {"guid": "w1", "ifc_class": "IfcWall", "storey": "Level 1"},
       {"guid": "s1", "ifc_class": "IfcSpace", "storey": "Level 1"}]
tl = fourd.timeline(takt.plan(3), els)
assert tl["element_count"] == 4 and tl["frames"], tl
# cumulative is monotonic and ends at 100%
assert tl["frames"][-1]["completed_cumulative"] == 4 and tl["frames"][-1]["pct"] == 100.0, tl["frames"][-1]
# structure (column L1) completes before interiors (space L1) — trades chase in order
col_day = min(f["day"] for f in tl["frames"] if "c1" in f["new_guids"])
space_day = min(f["day"] for f in tl["frames"] if "s1" in f["new_guids"])
assert col_day < space_day, (col_day, space_day)
# a higher floor's column finishes after the ground floor's
c2_day = min(f["day"] for f in tl["frames"] if "c2" in f["new_guids"])
assert c2_day > col_day, (c2_day, col_day)

# --- R4: lean PPC ------------------------------------------------------------
recs = [{"data": {"status": "Complete"}}, {"data": {"status": "Complete"}},
        {"data": {"status": "Complete"}}, {"data": {"status": "Complete"}},
        {"data": {"status": "Missed", "variance_reason": "Materials"}}]
m = lean.ppc(recs)
assert m["commitments"] == 5 and m["completed"] == 4 and m["ppc"] == 0.8, m
assert m["rating"] == "good" and m["top_variance_reasons"][0]["reason"] == "Materials", m
assert lean.ppc([])["ppc"] == 0.0

# --- endpoints + R5 ----------------------------------------------------------
with TestClient(app) as c:
    t = c.post("/schedule/takt", json={"floors": 8})
    assert t.status_code == 200 and t.json()["crew_peak"] == 5, t.text
    svg = c.get("/schedule/takt.svg", params={"floors": 8})
    assert svg.status_code == 200 and svg.content[:4] == b"<svg" and b"floors/wk" in svg.content, svg.status_code
    b = c.get("/benchmarks")
    assert b.status_code == 200 and "cap_rate" in b.json()["benchmarks"], b.text
    pid = c.post("/projects", json={"name": "Lean Job"}).json()["id"]
    # seed weekly-plan commitments via the auto-created module, then read PPC
    for st in ("Complete", "Complete", "Missed"):
        body = {"data": {"task": "Pour deck", "status": st, "variance_reason": "Labor"}}
        c.post(f"/projects/{pid}/modules/weekly_plan", json=body)
    r = c.get(f"/projects/{pid}/lean/ppc")
    assert r.status_code == 200 and r.json()["commitments"] == 3 and abs(r.json()["ppc"] - 0.667) < 0.01, r.text
    # comparables module auto-created
    cmp = c.post(f"/projects/{pid}/modules/comparable", json={"data": {"address": "123 Main", "cap_rate": 5.5}})
    assert cmp.status_code in (200, 201), cmp.text
    # 4D endpoint responds even with no published model (empty timeline)
    fd = c.get(f"/projects/{pid}/schedule/4d")
    assert fd.status_code == 200 and "frames" in fd.json() and "duration_days" in fd.json(), fd.text
    assert fd.json()["source"] == "takt", fd.json().get("source")
    # Primavera P6 .xer import → 4D reports real calendar dates (source=p6); bad file → 422; clear → takt
    _xer = "\n".join(["\t".join(["%T", "TASK"]),
        "\t".join(["%F", "task_code", "task_name", "target_start_date", "target_end_date"]),
        "\t".join(["%R", "A1010", "Foundations", "2026-03-01 08:00", "2026-03-20 17:00"]),
        "\t".join(["%R", "A1020", "Superstructure", "2026-03-21 08:00", "2026-07-15 17:00"])])
    imp = c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("p.xer", _xer, "application/octet-stream")})
    assert imp.status_code == 201 and imp.json()["count"] == 2 and imp.json()["start"] == "2026-03-01", imp.text
    fd2 = c.get(f"/projects/{pid}/schedule/4d").json()
    assert fd2["source"] == "p6" and fd2["start_date"] == "2026-03-01" and fd2["finish_date"] == "2026-07-15", fd2
    assert c.post(f"/projects/{pid}/schedule/import-xer", files={"file": ("x.xer", "junk", "text/plain")}).status_code == 422
    c.delete(f"/projects/{pid}/schedule/import-xer")
    assert c.get(f"/projects/{pid}/schedule/4d").json()["source"] == "takt"

print(f"RESEARCH OK - takt {p['duration_days']}d / {p['floors_per_week']} fl-wk / {len(p['delivery_plan'])} JIT deliveries; "
      f"lean PPC {m['ppc']} ({m['rating']}); benchmarks + weekly_plan + comparable modules + endpoints verified")
